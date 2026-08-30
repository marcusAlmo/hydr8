import json
import logging
from urllib.parse import quote

from django import forms
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms.forms import NON_FIELD_ERRORS
from django.forms.utils import ErrorList
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django_ratelimit.exceptions import Ratelimited

from apps.core.views import (
    error_message,
    toast_for_exception,
)
from apps.employees.selectors import get_user_detail_context
from apps.users.models import Role, User
from apps.users.permissions import is_admin as user_is_admin
from apps.users.permissions import is_back_office as user_is_back_office
from apps.users.permissions import is_staff_role as user_is_staff_role
from apps.users.signals import login_failed

from .selectors import get_roles_for_user, get_user_by_id, username_exists
from .services import (
    activate_user,
    change_user_password,
    check_login_lockout,
    create_user_account,
    deactivate_user,
    generate_deactivate_challenge,
    get_client_ip,
    onboard_user,
    record_failed_login,
    reset_failed_login,
    set_temporary_password,
    validate_user_pin,
)

logger = logging.getLogger(__name__)

# Rate limit: 10 login POSTs per minute per IP. This is the outer abuse shield;
# the inner 5-failure lockout (per ip+username) protects against credential
# guessing. Both use the 'default' cache (Redis in prod, locmem in dev/test).
LOGIN_RATELIMIT = ratelimit(key='ip', rate='10/m', method='POST', block=True)


def _is_back_office_user(user) -> bool:
    """Login gate: Admin/Staff role (or platform superuser) may sign in."""
    return user_is_back_office(user)


def _can_change_user(user) -> bool:
    """Admin role (or platform superuser) may mutate other users."""
    return user_is_admin(user)


def _can_add_user(user) -> bool:
    """Admin role (or platform superuser) may create new users."""
    return user_is_admin(user)


def _form_with_non_field_error(form: AuthenticationForm, message: str) -> AuthenticationForm:
    """
    Attaches a non-field error to the form WITHOUT triggering full_clean().

    Django's Form.errors property calls full_clean() on first access (when
    _errors is None), which resets _errors and runs AuthenticationForm.clean()
    — wiping any error we added via form.add_error() and replacing it with the
    auth error. By pre-setting _errors we prevent full_clean() from running,
    so the template can safely read form.non_field_errors and see our message.
    """
    form._errors = {NON_FIELD_ERRORS: ErrorList([message])}
    return form


def _safe_next_url(next_url: str, request) -> str:
    """
    Validates a `next` redirect URL to prevent open-redirect attacks.
    Returns the URL if it is a safe relative path on this host, else ''.
    """
    if not next_url:
        return ''
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return ''


def _post_auth_redirect_url(user) -> str:
    """Returns the default landing page URL after successful auth/onboarding.

    Staff users land on the Add Remittance page (their primary workflow —
    recording sales and creating drafts). Admin and platform superusers
    land on the Dashboard.
    """
    if user_is_staff_role(user):
        return reverse('remittance:add')
    return reverse('analytics:dashboard')


def index(request):
    """
    Renders the full login landing page (users/index.html).
    Reads the optional `next` query param (set by @login_required redirects)
    and the optional `error` query param (set by the rate-limited handler)
    and passes them to the template so the embedded login form can carry
    them through the HTMX POST and redirect to the originally requested page.
    """
    form = AuthenticationForm()
    next_url = request.GET.get('next', '')
    if request.GET.get('error') == 'rate_limited':
        form = _form_with_non_field_error(form, "Too many requests. Please try again later.")
    return render(request, 'users/index.html', {'form': form, 'next': next_url})


@require_http_methods(["GET", "POST"])
@LOGIN_RATELIMIT
def login_view(request):
    """
    Handles the HTMX login flow using industry standard Django Forms.
    - POST: Validates via AuthenticationForm. Returns failure state (form) or redirects.
    - GET:  Redirects to the full landing page (users:index) so a direct visit
            to /login/ shows the branded login UI, not the bare form partial.
    - Rate limited: 10 POSTs/min per IP (django-ratelimit).
    - Lockout: 5 failed attempts for a (ip, username) bucket locks for 1 minute.
    - The `next` parameter is threaded through failed attempts so it survives
      retries and is honored on successful login (with open-redirect protection).
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        username = request.POST.get('username', '')
        ip = get_client_ip(request=request)
        next_url = request.POST.get('next', '')

        # Short-circuit if this (ip, username) bucket is locked out.
        try:
            check_login_lockout(ip=ip, username=username)
        except ValidationError as exc:
            form = _form_with_non_field_error(form, str(exc))
            return render(request, 'users/partials/login_form.html', {'form': form, 'next': next_url})

        if form.is_valid():
            user = form.get_user()
            if not _is_back_office_user(user):
                form = _form_with_non_field_error(
                    form,
                    "Only staff and administrators are allowed to log in.",
                )
                logger.warning("[%s] Login denied for non-staff user. ip=%s", user.id, ip)
                return render(request, 'users/partials/login_form.html', {'form': form, 'next': next_url})
            auth_login(request, user)
            reset_failed_login(ip=ip, username=username)
            logger.info("[%s] Login success. ip=%s", user.id, ip)

            # If the user has no PIN or was issued a temporary password, force
            # onboarding (password + PIN setup) before they can access the app.
            if not user.pin or user.force_password_change:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('users:onboarding')
                return response

            safe_next = _safe_next_url(next_url, request)
            redirect_url = safe_next or _post_auth_redirect_url(user)
            response = HttpResponse()
            response['HX-Redirect'] = redirect_url
            return response
        else:
            # Login failed — record the attempt and re-render with errors.
            # Preserve `next` so the hidden input survives the HTMX swap.
            record_failed_login(ip=ip, username=username)
            login_failed.send(sender=None, request=request, username=username, ip=ip)
            logger.warning(
                "DEBUG login FAILED. form_errors=%r",
                {k: [str(e) for e in v] for k, v in form.errors.items()},
            )
            return render(request, 'users/partials/login_form.html', {'form': form, 'next': next_url})

    # GET: redirect to the full landing page, preserving ?next= if present.
    next_url = request.GET.get('next', '')
    target = reverse('users:index')
    if next_url:
        target = f"{target}?next={quote(next_url)}"
    return redirect(target)


def ratelimited_view(request, exception=None):
    """
    Custom handler for 403 responses.

    * Ratelimited: logs the user out and redirects them to the login page with
      a rate-limit error, which is the expected flow for rate-limited requests.
    * Plain PermissionDenied: returns a real 403 so role-gated endpoints keep
      their HTTP semantics; it does not log the user out.
    """
    if not isinstance(exception, Ratelimited):
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse("Forbidden", status=403)
        return HttpResponse("Forbidden", status=403)

    auth_logout(request)
    next_url = (
        request.POST.get('next', '')
        if request.method == 'POST'
        else request.GET.get('next', '')
    )
    safe_next = _safe_next_url(next_url, request)
    if safe_next:
        target = f"{reverse('users:index')}?error=rate_limited&next={quote(safe_next)}"
    else:
        target = f"{reverse('users:index')}?error=rate_limited"
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse()
        response['HX-Redirect'] = target
        return response
    return redirect(target)


# ---------------------------------------------------------------------------
# Forced password change — shown after a temporary-password login.
# ---------------------------------------------------------------------------

class PasswordChangeForm(forms.Form):
    """Simple password change form for the forced post-temp-login flow."""
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
        min_length=8,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
        min_length=8,
    )

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get('new_password', '')
        pw2 = cleaned.get('confirm_password', '')
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError("Passwords do not match.")
        return cleaned


@login_required
@require_http_methods(["GET"])
def password_change_view(request):
    """
    Renders the forced password change page.
    The user is sent here after logging in with a temporary password
    (when ``force_password_change`` is True on the User model).
    """
    form = PasswordChangeForm()
    return render(request, 'users/password_change.html', {'form': form})


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def password_change_submit_view(request):
    """
    HTMX endpoint — processes the forced password change form.
    On success, clears the ``force_password_change`` flag and redirects
    to the dashboard. On failure, re-renders the form with errors.
    """
    form = PasswordChangeForm(request.POST)
    if form.is_valid():
        change_user_password(user=request.user, new_password=form.cleaned_data['new_password'])
        response = HttpResponse()
        response['HX-Redirect'] = _post_auth_redirect_url(request.user)
        return response
    return render(request, 'users/partials/password_change_form.html', {'form': form})


# ---------------------------------------------------------------------------
# Generate temporary password — admin action on a user detail drawer.
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def generate_temp_password_view(request, user_id):
    """
    HTMX endpoint — generates a temporary password for the specified user,
    sets it as their password, and flags them for a forced password change
    on next login.

    Returns a partial with the plaintext password displayed once for copy.
    The plaintext is never logged (RA 10173).

    Requires the admin's PIN for verification before generating the password.

    Protected by the Admin role (or platform superuser) via
    ``_can_change_user`` → ``apps.users.permissions.is_admin``.
    """
    if not _can_change_user(request.user):
        raise PermissionDenied("Forbidden")

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    # --- PIN verification (server-side, defence in depth) ---
    pin = (request.POST.get('pin', '') or '').strip()
    try:
        validate_user_pin(user=request.user, pin=pin)
    except ValidationError as exc:
        logger.info("[%s] generate_temp_password PIN verification failed: %s", request.user.id, exc)
        context = get_user_detail_context(request.user, target_user.id)
        if context is None:
            return HttpResponse("User not found.", status=404)
        context['pin_error'] = error_message(exc)
        return render(request, 'employees/partials/user_detail.html', context, status=403)

    raw_password = set_temporary_password(user=target_user)

    return render(request, 'users/partials/temp_password_result.html', {
        'target_user': target_user,
        'temp_password': raw_password,
    })


# ---------------------------------------------------------------------------
# Edit user — admin action on a user detail drawer.
# ---------------------------------------------------------------------------

class EditUserForm(forms.ModelForm):
    """Form for editing a user's profile details (admin action)."""

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'daily_rate']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent',
            }),
            'daily_rate': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
                'placeholder': 'e.g. 500.00',
                'step': '0.01',
                'min': '0',
            }),
        }

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        daily_rate = cleaned.get('daily_rate')
        if role and role.name == 'Staff':
            if daily_rate is None:
                self.add_error('daily_rate', "Daily rate is required for Staff role.")
            elif daily_rate < 0:
                self.add_error('daily_rate', "Daily rate cannot be negative.")
        return cleaned


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def edit_user_view(request, user_id):
    """
    HTMX endpoint — returns the edit user form partial for the drawer.
    Protected by Django's built-in users.change_user permission.
    """
    if not _can_change_user(request.user):
        raise PermissionDenied("Forbidden")

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    roles = get_roles_for_user(request.user)
    form = EditUserForm(instance=target_user)
    form.fields['role'].queryset = roles

    # Generate a one-time deactivation-confirmation challenge and stash it in
    # the session so the deactivate endpoint can verify it on POST. Regenerated
    # on every edit-form load so it cannot be replayed across sessions.
    deactivate_challenge = generate_deactivate_challenge()
    request.session[f'deactivate_challenge:{target_user.pk}'] = deactivate_challenge

    # Prevent self-deactivation in the UI — hide the status buttons for the
    # current user on their own edit form.
    can_change_status = _can_change_user(request.user) and request.user.pk != target_user.pk

    return render(request, 'users/partials/edit_user_form.html', {
        'form': form,
        'target_user': target_user,
        'roles': roles,
        'deactivate_challenge': deactivate_challenge,
        'can_change_status': can_change_status,
    })


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def edit_user_submit_view(request, user_id):
    """
    HTMX endpoint — processes the edit user form submission.
    On success, returns a success toast partial. On failure, re-renders
    the form with errors.

    Requires the admin's PIN for verification before saving changes.
    """
    if not _can_change_user(request.user):
        raise PermissionDenied("Forbidden")

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    roles = get_roles_for_user(request.user)
    form = EditUserForm(request.POST, instance=target_user)
    form.fields['role'].queryset = roles

    # --- PIN verification (server-side, defence in depth) ---
    pin = (request.POST.get('pin', '') or '').strip()
    pin_error = ''
    try:
        validate_user_pin(user=request.user, pin=pin, required_message="PIN is required to save changes.")
    except ValidationError as exc:
        logger.info("[%s] edit_user PIN verification failed: %s", request.user.id, exc)
        pin_error = error_message(exc)

    if form.is_valid() and not pin_error:
        try:
            form.save()
        except ValidationError as exc:
            logger.warning("[%s] Failed to update User id=%s: %s",
                           request.user.id, target_user.id, error_message(exc))
            return toast_for_exception(request, exc)

        logger.info("[%s] Updated User id=%s", request.user.id, target_user.id)
        # Re-render the user detail partial with the updated values so the
        # drawer reflects the saved state. No toast — the updated values in
        # the drawer are the feedback. The drawer's built-in close button
        # handles dismissal.
        context = get_user_detail_context(request.user, target_user.id)
        if context is None:
            return HttpResponse("User not found.", status=404)
        return render(request, 'employees/partials/user_detail.html', context)
    # Re-render the form with errors — preserve the deactivation challenge so
    # the status panel stays functional after a failed save.
    deactivate_challenge = request.session.get(f'deactivate_challenge:{target_user.pk}', generate_deactivate_challenge())
    return render(request, 'users/partials/edit_user_form.html', {
        'form': form,
        'target_user': target_user,
        'roles': roles,
        'deactivate_challenge': deactivate_challenge,
        'can_change_status': _can_change_user(request.user) and request.user.pk != target_user.pk,
        'pin_error': pin_error,
    })


# ---------------------------------------------------------------------------
# Deactivate / activate user — admin action on the edit user form.
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def deactivate_user_view(request, user_id):
    """
    HTMX endpoint — deactivates a user after verifying the typed
    deactivation-confirmation challenge matches the one issued when the
    edit form was rendered.

    On success, returns a confirmation partial and triggers a refresh of the
    employees directory table so the deactivated user is immediately marked
    as inactive. On failure (wrong challenge, self-deactivation, already
    deactivated), re-renders the edit form with an error message.
    """
    if not _can_change_user(request.user):
        raise PermissionDenied("Forbidden")

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    roles = get_roles_for_user(request.user)
    session_key = f'deactivate_challenge:{target_user.pk}'
    expected_challenge = request.session.get(session_key, '')
    typed_challenge = (request.POST.get('deactivate_challenge', '') or '').strip()

    if not expected_challenge:
        # No challenge was issued (stale form / session expired). Regenerate
        # one and re-render the edit form with a fresh challenge + error.
        deactivate_challenge = generate_deactivate_challenge()
        request.session[session_key] = deactivate_challenge
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': deactivate_challenge,
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': "The deactivation session expired. Please retry the confirmation.",
        })

    if typed_challenge != expected_challenge:
        # Wrong code — re-render the edit form with the same challenge and
        # an error so the user can retry without reloading the whole form.
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': expected_challenge,
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': "The code you entered does not match. Please type it exactly as shown.",
        })

    # --- PIN verification (server-side, defence in depth) ---
    pin = (request.POST.get('pin', '') or '').strip()
    try:
        validate_user_pin(user=request.user, pin=pin, required_message="PIN is required to deactivate a user.")
    except ValidationError as exc:
        logger.info("[%s] deactivate_user PIN verification failed: %s", request.user.id, exc)
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': expected_challenge,
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': error_message(exc),
        })

    try:
        deactivate_user(user=target_user, performed_by=request.user)
    except ValidationError as exc:
        logger.warning("[%s] Failed to deactivate User id=%s: %s",
                       request.user.id, target_user.id, error_message(exc))
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': expected_challenge,
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': str(exc),
        })

    # Clear the spent challenge so it cannot be replayed.
    request.session.pop(session_key, None)

    # Confirmation partial — swaps into the drawer content area. Trigger a
    # refresh of the directory table so the deactivated user is immediately
    # marked inactive.
    response = render(request, 'users/partials/user_deleted_confirm.html', {
        'target_user': target_user,
        'deactivated': True,
    })
    response['HX-Trigger'] = '{"refreshUsersTable": ""}'
    return response


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def activate_user_view(request, user_id):
    """
    HTMX endpoint — reactivates a previously deactivated user after PIN
    verification.

    On success, returns a confirmation partial and triggers a refresh of the
    employees directory table. On failure (wrong PIN, already active),
    re-renders the edit form with an error message.
    """
    if not _can_change_user(request.user):
        raise PermissionDenied("Forbidden")

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    roles = get_roles_for_user(request.user)

    # --- PIN verification (server-side, defence in depth) ---
    pin = (request.POST.get('pin', '') or '').strip()
    try:
        validate_user_pin(user=request.user, pin=pin, required_message="PIN is required to activate a user.")
    except ValidationError as exc:
        logger.info("[%s] activate_user PIN verification failed: %s", request.user.id, exc)
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': generate_deactivate_challenge(),
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': error_message(exc),
        })

    try:
        activate_user(user=target_user, performed_by=request.user)
    except ValidationError as exc:
        logger.warning("[%s] Failed to activate User id=%s: %s",
                       request.user.id, target_user.id, error_message(exc))
        form = EditUserForm(instance=target_user)
        form.fields['role'].queryset = roles
        return render(request, 'users/partials/edit_user_form.html', {
            'form': form,
            'target_user': target_user,
            'roles': roles,
            'deactivate_challenge': generate_deactivate_challenge(),
            'can_change_status': request.user.pk != target_user.pk,
            'status_error': str(exc),
        })

    # Confirmation partial — swaps into the drawer content area. Trigger a
    # refresh of the directory table so the reactivated user reappears.
    response = render(request, 'users/partials/user_deleted_confirm.html', {
        'target_user': target_user,
        'deactivated': False,
    })
    response['HX-Trigger'] = '{"refreshUsersTable": ""}'
    return response


# ---------------------------------------------------------------------------
# Add user — admin action on the employee directory.
# ---------------------------------------------------------------------------

class AddUserForm(forms.Form):
    """Form for adding a new user and sending them to onboarding."""

    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
        }),
        max_length=150,
    )
    first_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent',
        }),
        required=False,
    )
    last_name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent',
        }),
        required=False,
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
        }),
        required=False,
    )
    role = forms.ModelChoiceField(
        queryset=Role.objects.none(),
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md focus:ring-2 focus:ring-primary focus:border-transparent appearance-none',
        }),
        required=True,
    )
    daily_rate = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-3 py-2 bg-surface-container-low border border-outline-variant/30 rounded-lg text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'e.g. 500.00',
            'step': '0.01',
            'min': '0',
        }),
    )
    pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full h-12 text-center text-2xl font-data-mono tracking-[0.5em] rounded-lg border border-outline-variant bg-surface-container-lowest text-on-surface focus:ring-2 focus:ring-primary focus:border-transparent outline-none',
            'placeholder': '••••',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'maxlength': '6',
            'autocomplete': 'off',
        }),
        required=False,
    )

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if username_exists(username):
            raise ValidationError("A user with that username already exists.")
        return username

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        daily_rate = cleaned.get('daily_rate')
        if role and role.name == 'Staff':
            if daily_rate is None:
                self.add_error('daily_rate', "Daily rate is required for Staff role.")
            elif daily_rate < 0:
                self.add_error('daily_rate', "Daily rate cannot be negative.")
        return cleaned


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def add_user_view(request):
    """HTMX endpoint — returns the add user form partial for the drawer."""
    if not _can_add_user(request.user):
        raise PermissionDenied("Forbidden")

    roles = get_roles_for_user(request.user)
    form = AddUserForm()
    form.fields['role'].queryset = roles
    return render(request, 'users/partials/add_user_form.html', {
        'form': form,
        'roles': roles,
    })


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def add_user_submit_view(request):
    """HTMX endpoint — creates the user, sets a temporary password, and
    returns a partial displaying the one-time temporary password.

    Requires the admin's PIN for verification before creating the account.
    """
    if not _can_add_user(request.user):
        raise PermissionDenied("Forbidden")

    roles = get_roles_for_user(request.user)
    form = AddUserForm(request.POST)
    form.fields['role'].queryset = roles

    # --- PIN verification (server-side, defence in depth) ---
    pin = (request.POST.get('pin', '') or '').strip()
    try:
        validate_user_pin(user=request.user, pin=pin, required_message="PIN is required to create a new user.")
    except ValidationError as exc:
        logger.info("[%s] add_user PIN verification failed: %s", request.user.id, exc)
        form.add_error(None, error_message(exc))

    if form.is_valid() and not form.non_field_errors():
        try:
            with transaction.atomic():
                new_user = create_user_account(
                    username=form.cleaned_data['username'].strip(),
                    first_name=form.cleaned_data.get('first_name', ''),
                    last_name=form.cleaned_data.get('last_name', ''),
                    email=form.cleaned_data.get('email', ''),
                    role=form.cleaned_data['role'],
                    company_id=None if request.user.is_superuser else request.user.company_id,
                    performed_by=request.user,
                    daily_rate=form.cleaned_data.get('daily_rate'),
                )
                raw_password = set_temporary_password(user=new_user)
        except ValidationError as exc:
            return toast_for_exception(request, exc)

        logger.info("[%s] Created and issued temporary password for User id=%s", request.user.id, new_user.id)
        return render(request, 'users/partials/temp_password_result.html', {
            'target_user': new_user,
            'temp_password': raw_password,
        })

    return render(request, 'users/partials/add_user_form.html', {
        'form': form,
        'roles': roles,
    })


# ---------------------------------------------------------------------------
# Onboarding — first-time setup of password and PIN.
# ---------------------------------------------------------------------------

class OnboardingForm(forms.Form):
    """Form for setting a new password and PIN during onboarding."""

    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
        min_length=8,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
        min_length=8,
    )
    pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Enter 4-6 digit PIN',
            'autocomplete': 'new-password',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
        }),
        min_length=4,
        max_length=6,
    )
    confirm_pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Confirm PIN',
            'autocomplete': 'new-password',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
        }),
        min_length=4,
        max_length=6,
    )

    def clean_pin(self):
        pin = self.cleaned_data.get('pin', '')
        if not pin.isdigit():
            raise ValidationError("PIN must contain only digits.")
        return pin

    def clean(self):
        cleaned = super().clean()
        pw1 = cleaned.get('new_password', '')
        pw2 = cleaned.get('confirm_password', '')
        if pw1 and pw2 and pw1 != pw2:
            self.add_error('confirm_password', "Passwords do not match.")
        p1 = cleaned.get('pin', '')
        p2 = cleaned.get('confirm_pin', '')
        if p1 and p2 and p1 != p2:
            self.add_error('confirm_pin', "PINs do not match.")
        return cleaned


def _needs_onboarding(user) -> bool:
    """Returns True if the user still needs to set a password or PIN."""
    if not user.pin or user.force_password_change:
        return True
    now = timezone.now()
    return (
        (user.password_expires_at is not None and user.password_expires_at < now)
        or (user.pin_expires_at is not None and user.pin_expires_at < now)
    )


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def onboarding_view(request):
    """Renders the first-time onboarding page (password + PIN)."""
    if not _needs_onboarding(request.user):
        return redirect(_post_auth_redirect_url(request.user))
    form = OnboardingForm()
    return render(request, 'users/onboarding.html', {'form': form})


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def onboarding_submit_view(request):
    """HTMX endpoint — completes onboarding by setting password and PIN."""
    if not _needs_onboarding(request.user):
        return redirect(_post_auth_redirect_url(request.user))

    form = OnboardingForm(request.POST)
    if form.is_valid():
        onboard_user(
            user=request.user,
            new_password=form.cleaned_data['new_password'],
            new_pin=form.cleaned_data['pin'],
        )
        response = HttpResponse()
        response['HX-Redirect'] = _post_auth_redirect_url(request.user)
        return response

    return render(request, 'users/partials/onboarding_form.html', {'form': form})


# ---------------------------------------------------------------------------
# Screen lock — require PIN to re-enter, 3 attempts then logout.
# ---------------------------------------------------------------------------

class ScreenLockForm(forms.Form):
    """Form for unlocking the screen with the user's PIN."""

    pin = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-surface-container-low border border-outline-variant/30 rounded-xl text-body-md font-data-mono focus:ring-2 focus:ring-primary focus:border-transparent',
            'placeholder': 'Enter PIN',
            'autocomplete': 'off',
            'inputmode': 'numeric',
            'pattern': '[0-9]*',
            'maxlength': '6',
        }),
        min_length=4,
        max_length=6,
    )


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def screen_lock_view(request):
    """Renders the screen lock overlay and marks the session as locked."""
    request.session['screen_locked'] = True
    return render(request, 'users/screen_lock.html', {'form': ScreenLockForm()})


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def screen_lock_arm_view(request):
    """JSON endpoint — arms the server-side screen-lock flag.

    Called by the Alpine.js idle lock-screen overlay (in ``base.html``)
    the moment the client-side idle timer fires.  Setting
    ``request.session['screen_locked'] = True`` ensures that
    ``ScreenLockMiddleware`` will redirect *any* subsequent request —
    including a page refresh — to the full-page lock screen, closing
    the "refresh to bypass the PIN modal" hole.

    Returns JSON ``{"armed": true}``.
    """
    request.session['screen_locked'] = True
    logger.info("[%s] Idle lock-screen armed via overlay.", request.user.id)
    return JsonResponse({"armed": True})


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def screen_lock_submit_view(request):
    """
    HTMX endpoint — verifies the PIN to unlock the screen.
    Allows up to 3 attempts; after that the user is logged out and
    redirected to the login page, which deletes the session.
    """
    form = ScreenLockForm(request.POST)
    if not form.is_valid():
        return render(request, 'users/partials/screen_lock_form.html', {'form': form})

    raw_pin = form.cleaned_data['pin']
    user = request.user

    attempts = request.session.get('pin_attempts', 0)
    if user.check_pin(raw_pin):
        request.session.pop('pin_attempts', None)
        request.session.pop('screen_locked', None)
        logger.info("[%s] Screen unlocked via PIN.", user.id)
        response = HttpResponse()
        response['HX-Redirect'] = _post_auth_redirect_url(user)
        return response

    attempts += 1
    request.session['pin_attempts'] = attempts

    if attempts >= 3:
        logger.warning("[%s] Screen lock PIN exceeded 3 attempts; logging out.", user.id)
        auth_logout(request)
        response = HttpResponse()
        response['HX-Redirect'] = reverse('users:index')
        return response

    return render(
        request,
        'users/partials/screen_lock_form.html',
        {
            'form': form,
            'pin_error': "Incorrect PIN.",
            'attempts_left': 3 - attempts,
        },
    )


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='5/15m', method='POST', block=True)
def screen_lock_verify_view(request):
    """JSON endpoint — verifies the PIN to dismiss the idle lock-screen overlay.

    Used by the Alpine.js lock-screen overlay in ``base.html``.  The
    overlay arms itself client-side after the configured idle timeout
    (``lockscreen_timeout_minutes`` SystemConfig) and posts the user's
    PIN here.

    Returns JSON::

        {"verified": true}                          # on success
        {"verified": false, "attempts_left": 2}     # on wrong PIN
        {"verified": false, "logged_out": true,
         "redirect": "/users/"}                     # after 3 failures

    After 3 failed attempts the user is logged out (session destroyed)
    and the client redirects to the login page — matching the rule on
    the standalone screen-lock page.

    Shares the ``pin_attempts`` session counter with
    ``screen_lock_submit_view`` so the two flows cannot be used to
    bypass the 3-attempt ceiling.
    """
    try:
        body = json.loads(request.body or b'{}')
    except (ValueError, TypeError):
        return JsonResponse(
            {"verified": False, "error": "Invalid request."}, status=400,
        )

    pin = str(body.get("pin", "")).strip()
    if not pin:
        return JsonResponse(
            {"verified": False, "error": "PIN is required."}, status=400,
        )

    user = request.user
    attempts = request.session.get('pin_attempts', 0)

    if user.check_pin(pin):
        request.session.pop('pin_attempts', None)
        request.session.pop('screen_locked', None)
        logger.info("[%s] Lock-screen overlay unlocked via PIN.", user.id)
        return JsonResponse({"verified": True})

    attempts += 1
    request.session['pin_attempts'] = attempts

    if attempts >= 3:
        logger.warning(
            "[%s] Lock-screen overlay PIN exceeded 3 attempts; logging out.",
            user.id,
        )
        auth_logout(request)
        return JsonResponse(
            {
                "verified": False,
                "logged_out": True,
                "redirect": reverse('users:index'),
            },
        )

    logger.info("[%s] Lock-screen overlay PIN failed (attempt %s).", user.id, attempts)
    return JsonResponse(
        {"verified": False, "attempts_left": 3 - attempts},
    )


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def logout_view(request):
    """Logs out the current user and redirects to the login landing page.

    POST-only to prevent CSRF-via-GET logout attacks. ``auth_logout`` fires
    the ``user_logged_out`` signal, which ``apps.audit.signals`` turns into
    an ACCESS log entry automatically.
    """
    user_id = request.user.id
    auth_logout(request)
    logger.info("[%s] Logged out via sidebar action.", user_id)
    target = reverse('users:index')
    if request.headers.get('HX-Request') == 'true':
        response = HttpResponse()
        response['HX-Redirect'] = target
        return response
    return redirect(target)
