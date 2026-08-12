import logging
from urllib.parse import quote

from django import forms
from django.forms.forms import NON_FIELD_ERRORS
from django.forms.utils import ErrorList
from django.shortcuts import redirect, render
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.users.models import User
from apps.users.signals import login_failed
from .selectors import get_roles_for_user, get_user_by_id
from .services import (
    change_user_password,
    check_login_lockout,
    get_client_ip,
    record_failed_login,
    reset_failed_login,
    set_temporary_password,
)

logger = logging.getLogger(__name__)

# Rate limit: 10 login POSTs per minute per IP. This is the outer abuse shield;
# the inner 5-failure lockout (per ip+username) protects against credential
# guessing. Both use the 'default' cache (Redis in prod, locmem in dev/test).
LOGIN_RATELIMIT = ratelimit(key='ip', rate='10/m', method='POST', block=True)


def _can_change_user(user) -> bool:
    """Django built-in RBAC check for user-management mutations."""
    return user.is_authenticated and (
        user.is_staff or user.is_superuser or user.has_perm("users.change_user")
    )


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


def index(request):
    """
    Renders the full login landing page (users/index.html).
    Reads the optional `next` query param (set by @login_required redirects)
    and passes it to the template so the embedded login form can carry it
    through the HTMX POST and redirect to the originally requested page.
    """
    form = AuthenticationForm()
    next_url = request.GET.get('next', '')
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
        ip = get_client_ip(request)
        next_url = request.POST.get('next', '')

        # Short-circuit if this (ip, username) bucket is locked out.
        try:
            check_login_lockout(ip=ip, username=username)
        except ValidationError as exc:
            form = _form_with_non_field_error(form, str(exc))
            return render(request, 'users/partials/login_form.html', {'form': form, 'next': next_url})

        # TEMP DEBUG: log submitted field shapes (never the raw password value).
        submitted_pw = request.POST.get('password', '')
        logger.warning(
            "DEBUG login submit. username=%r pw_len=%r pw_first_char=%r",
            username, len(submitted_pw), submitted_pw[:1],
        )

        if form.is_valid():
            user = form.get_user()
            if not (user.is_staff or user.is_superuser):
                form = _form_with_non_field_error(
                    form,
                    "Only staff and administrators are allowed to log in.",
                )
                logger.warning("[%s] Login denied for non-staff user. ip=%s", user.id, ip)
                return render(request, 'users/partials/login_form.html', {'form': form, 'next': next_url})
            auth_login(request, user)
            reset_failed_login(ip=ip, username=username)
            logger.info("[%s] Login success. ip=%s", user.id, ip)

            # If the user was issued a temporary password, force a password
            # change before they can access the app.
            if user.force_password_change:
                response = HttpResponse()
                response['HX-Redirect'] = reverse('users:password_change')
                return response

            safe_next = _safe_next_url(next_url, request)
            redirect_url = safe_next or reverse('analytics:dashboard')
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
    Custom handler for Ratelimited (HTTP 403) — renders a friendly message
    inside the HTMX login form so the user sees feedback instead of a blank 403.
    Preserves the `next` parameter so it survives the retry.
    """
    form = AuthenticationForm()
    form = _form_with_non_field_error(form, "Too many requests. Please try again in 1 minute.")
    next_url = (
        request.POST.get('next', '')
        if request.method == 'POST'
        else request.GET.get('next', '')
    )
    return TemplateResponse(
        request,
        'users/partials/login_form.html',
        {'form': form, 'next': next_url},
        status=429,
    )


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
        change_user_password(request.user, form.cleaned_data['new_password'])
        response = HttpResponse()
        response['HX-Redirect'] = reverse('analytics:dashboard')
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

    Protected by Django's built-in users.change_user permission (or
    is_staff / is_superuser).
    """
    if not _can_change_user(request.user):
        return HttpResponse("Forbidden", status=403)

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    raw_password = set_temporary_password(target_user)

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
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'is_active']
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
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 rounded border-outline-variant text-primary focus:ring-primary',
            }),
        }


@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def edit_user_view(request, user_id):
    """
    HTMX endpoint — returns the edit user form partial for the drawer.
    Protected by Django's built-in users.change_user permission.
    """
    if not _can_change_user(request.user):
        return HttpResponse("Forbidden", status=403)

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    form = EditUserForm(instance=target_user)
    form.fields['role'].queryset = get_roles_for_user(request.user)
    roles = get_roles_for_user(request.user)

    return render(request, 'users/partials/edit_user_form.html', {
        'form': form,
        'target_user': target_user,
        'roles': roles,
    })


@login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def edit_user_submit_view(request, user_id):
    """
    HTMX endpoint — processes the edit user form submission.
    On success, returns a success toast partial. On failure, re-renders
    the form with errors.
    """
    if not _can_change_user(request.user):
        return HttpResponse("Forbidden", status=403)

    target_user = get_user_by_id(request.user, user_id)
    if target_user is None:
        return HttpResponse("User not found.", status=404)

    form = EditUserForm(request.POST, instance=target_user)
    form.fields['role'].queryset = get_roles_for_user(request.user)

    if form.is_valid():
        form.save()
        logger.info("[%s] Updated User id=%s", request.user.id, target_user.id)
        return render(request, 'users/partials/edit_user_success.html', {
            'target_user': target_user,
        })
    return render(request, 'users/partials/edit_user_form.html', {
        'form': form,
        'target_user': target_user,
        'roles': get_roles_for_user(request.user),
    })