import uuid
import contextvars
import logging

from typing import Optional

# Context variable for the per-request correlation ID.  Accessed by the
# logging filter and by django-auditlog (via AUDITLOG_CID_HEADER) so that
# log entries and audit records share the same trace identifier without
# passing the request object through every call site.
correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('correlation_id', default=None)

def get_correlation_id():
    """Retrieve the correlation ID for the current request context."""
    return correlation_id_var.get()

class CorrelationIdMiddleware:
    """
    Middleware that generates or extracts a Correlation ID for every incoming request.
    This ID is stored in a context variable, making it accessible anywhere in the application
    (e.g., in logging filters or signals) without passing the request object around.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        req_id = request.META.get('HTTP_X_CORRELATION_ID') or str(uuid.uuid4())

        # We intentionally do NOT reset the context var in a finally block:
        # the WSGI request handler emits its summary log line *after* the
        # middleware stack returns, so resetting here would cause that line
        # (and any post-response logging) to see ``no-id``.  Each request
        # overwrites the previous value, so there is no cross-request leak
        # in the thread-per-request model.
        correlation_id_var.set(req_id)
        request.correlation_id = req_id

        response = self.get_response(request)
        response['X-Correlation-ID'] = req_id
        return response

class CorrelationIdFilter(logging.Filter):
    """
    A custom logging filter that injects the correlation ID into every log record.
    """
    def filter(self, record):
        record.correlation_id = get_correlation_id() or 'no-id'
        return True


class ScreenLockMiddleware:
    """Enforces the server-side screen-lock session flag.

    When ``request.session['screen_locked']`` is ``True`` (set either by
    the manual lock page ``screen_lock_view`` or by the idle overlay's
    ``screen_lock_arm_view``), every request is redirected to the
    full-page lock screen — *except* for the lock/verify/logout
    endpoints themselves and static/media assets.

    This closes the "refresh to bypass" hole: the idle overlay is
    client-side Alpine state that vanishes on refresh, but the session
    flag survives and the middleware forces the user back to the lock
    page on the very next request (including a refresh).

    Must run AFTER ``AuthenticationMiddleware`` so ``request.user`` is
    available.  Anonymous users are never locked.
    """

    # URL names that remain reachable while the screen is locked.
    _ALLOWED_NAMES = frozenset({
        'users:screen_lock',
        'users:screen_lock_submit',
        'users:screen_lock_verify',
        'users:screen_lock_arm',
        'users:logout',
    })

    # Path prefixes that bypass the lock (static/media served by
    # WhiteNoise / Django, plus the Django admin login fallback and health checks).
    _ALLOWED_PREFIXES = ('/static/', '/media/', '/health/', '/healthz/', '/up/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and request.session.get('screen_locked'):
            if not self._is_allowed(request):
                return self._lock_redirect(request)
        return self.get_response(request)

    def _is_allowed(self, request) -> bool:
        """True if the request path is reachable while locked."""
        path = request.path
        for prefix in self._ALLOWED_PREFIXES:
            if path.startswith(prefix):
                return True
        # URL resolution hasn't happened yet at middleware stage
        # (resolver_match is populated inside get_response), so resolve
        # the path ourselves to discover the matched URL name.
        from django.urls import resolve, Resolver404
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return False
        name = match.url_name or ''
        namespace = ':'.join(match.namespaces) if match.namespaces else ''
        full_name = f"{namespace}:{name}" if namespace else name
        if full_name in self._ALLOWED_NAMES:
            return True
        # Also allow bare names (e.g. 'logout' without namespace).
        if name and name in {n.split(':')[-1] for n in self._ALLOWED_NAMES}:
            return True
        return False

    def _lock_redirect(self, request):
        """Redirect to the full-page lock screen.

        For HTMX requests, emit an ``HX-Redirect`` response header so
        HTMX performs a full-page navigation rather than swapping the
        lock page into a fragment target.
        """
        from django.http import HttpResponse
        from django.urls import reverse

        lock_url = reverse('users:screen_lock')
        is_htmx = request.headers.get('HX-Request') == 'true'
        if is_htmx:
            resp = HttpResponse()
            resp['HX-Redirect'] = lock_url
            return resp
        from django.shortcuts import redirect
        return redirect(lock_url)

