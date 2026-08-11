import logging

from django.forms.forms import NON_FIELD_ERRORS
from django.forms.utils import ErrorList
from django.shortcuts import render
from django.contrib.auth import login as auth_login
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .services import (
    check_login_lockout,
    get_client_ip,
    record_failed_login,
    reset_failed_login,
)

logger = logging.getLogger(__name__)

# Rate limit: 10 login POSTs per minute per IP. This is the outer abuse shield;
# the inner 5-failure lockout (per ip+username) protects against credential
# guessing. Both use the 'default' cache (Redis in prod, locmem in dev/test).
LOGIN_RATELIMIT = ratelimit(key='ip', rate='10/m', method='POST', block=True)


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


def index(request):
    """
    Renders the initial landing page for the application.
    Passes an empty AuthenticationForm so the initial form can render without errors.
    """
    form = AuthenticationForm()
    return render(request, 'users/index.html', {'form': form})


@require_http_methods(["GET", "POST"])
@LOGIN_RATELIMIT
def login_view(request):
    """
    Handles the HTMX login flow using industry standard Django Forms.
    - POST: Validates via AuthenticationForm. Returns failure state (form) or redirects.
    - Rate limited: 10 POSTs/min per IP (django-ratelimit).
    - Lockout: 5 failed attempts for a (ip, username) bucket locks for 1 minute.
    """
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        username = request.POST.get('username', '')
        ip = get_client_ip(request)

        # Short-circuit if this (ip, username) bucket is locked out.
        try:
            check_login_lockout(ip=ip, username=username)
        except ValidationError as exc:
            form = _form_with_non_field_error(form, str(exc))
            return render(request, 'users/partials/login_form.html', {'form': form})

        # TEMP DEBUG: log submitted field shapes (never the raw password value).
        submitted_pw = request.POST.get('password', '')
        logger.warning(
            "DEBUG login submit. username=%r pw_len=%r pw_first_char=%r",
            username, len(submitted_pw), submitted_pw[:1],
        )

        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            reset_failed_login(ip=ip, username=username)
            logger.info("[%s] Login success. ip=%s", user.id, ip)

            response = HttpResponse()
            response['HX-Redirect'] = reverse('analytics:dashboard')
            return response
        else:
            # Login failed — record the attempt and re-render with errors.
            record_failed_login(ip=ip, username=username)
            logger.warning(
                "DEBUG login FAILED. form_errors=%r",
                {k: [str(e) for e in v] for k, v in form.errors.items()},
            )
            return render(request, 'users/partials/login_form.html', {'form': form})

    # GET: return a fresh form partial.
    form = AuthenticationForm()
    return render(request, 'users/partials/login_form.html', {'form': form})


def ratelimited_view(request, exception=None):
    """
    Custom handler for Ratelimited (HTTP 403) — renders a friendly message
    inside the HTMX login form so the user sees feedback instead of a blank 403.
    """
    form = AuthenticationForm()
    form = _form_with_non_field_error(form, "Too many requests. Please try again in 1 minute.")
    return TemplateResponse(
        request,
        'users/partials/login_form.html',
        {'form': form},
        status=429,
    )