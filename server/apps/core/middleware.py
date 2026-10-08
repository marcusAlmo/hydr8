import contextvars
import logging
import time
import uuid

from django.conf import settings
from django.db import connection

perf_logger = logging.getLogger('apps.performance')

# Create a context variable to hold the correlation ID for the current thread/async task
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar('correlation_id', default=None)

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
        # 1. Extract from headers (if called by an upstream microservice) or generate a new one
        req_id = request.META.get('HTTP_X_CORRELATION_ID') or str(uuid.uuid4())

        # 2. Set the ID in the context variable. We intentionally do NOT reset
        #    it in a finally block: the WSGI request handler (django.server)
        #    emits its request/response summary log line *after* the middleware
        #    stack returns, so resetting here would cause that line — and any
        #    other post-response logging — to see ``no-id`` instead of the real
        #    correlation id. Each request overwrites the previous value, so
        #    there is no cross-request leak in the thread-per-request model.
        correlation_id_var.set(req_id)
        # Also stash it on the request so downstream code can read it directly.
        request.correlation_id = req_id

        # 3. Process the request (this calls views, other middlewares, etc.)
        response = self.get_response(request)

        # 4. Inject the Correlation ID into the response headers for the client/frontend
        response['X-Correlation-ID'] = req_id
        return response

class CorrelationIdFilter(logging.Filter):
    """
    A custom logging filter that injects the correlation ID into every log record.
    """
    def filter(self, record):
        record.correlation_id = get_correlation_id() or 'no-id'
        return True


class ProcessPerformanceMiddleware:
    """Measures and logs server request duration, view processing time,
    and PostgreSQL query metrics per request.

    Adheres to RA 10173 & ISO 27001 logging rules:
    - Never logs query strings, request bodies, or user PII.
    - Logs actor ID, HTTP method, sanitized path, status code, and latencies.
    - Emits W3C Server-Timing headers for client visibility.
    - Automatically flags slow requests exceeding PERFORMANCE_SLOW_THRESHOLD_MS.
    """

    _BYPASS_PREFIXES = ('/static/', '/media/', '/health/', '/healthz/', '/up/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, 'path', '')
        for prefix in self._BYPASS_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        db_queries = 0
        db_time_ms = 0.0

        def db_timing_wrapper(execute, sql, params, many, context):
            nonlocal db_queries, db_time_ms
            t_start = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                db_queries += 1
                db_time_ms += (time.perf_counter() - t_start) * 1000.0

        start_time = time.perf_counter()

        with connection.execute_wrapper(db_timing_wrapper):
            response = self.get_response(request)

        total_duration_ms = (time.perf_counter() - start_time) * 1000.0
        view_duration_ms = max(0.0, total_duration_ms - db_time_ms)

        user = getattr(request, 'user', None)
        actor_id = getattr(user, 'id', 'anon') if (user and user.is_authenticated) else 'anon'

        slow_threshold_ms = getattr(settings, 'PERFORMANCE_SLOW_THRESHOLD_MS', 500.0)

        log_payload = (
            "[%s] HTTP %s %s -> %s | total=%.2fms | view=%.2fms | db=%.2fms (queries=%d)"
        )
        log_args = (
            actor_id,
            getattr(request, 'method', 'UNKNOWN'),
            path,
            getattr(response, 'status_code', 200),
            total_duration_ms,
            view_duration_ms,
            db_time_ms,
            db_queries,
        )

        if total_duration_ms >= slow_threshold_ms:
            perf_logger.warning(log_payload, *log_args)
        else:
            perf_logger.info(log_payload, *log_args)

        if hasattr(response, '__setitem__'):
            response['Server-Timing'] = (
                f"total;dur={total_duration_ms:.2f}, "
                f"db;dur={db_time_ms:.2f}, "
                f"view;dur={view_duration_ms:.2f}"
            )

        return response


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
        if (
            user
            and user.is_authenticated
            and request.session.get('screen_locked')
            and not self._is_allowed(request)
        ):
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
        from django.urls import Resolver404, resolve
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
        return bool(name and name in {n.split(':')[-1] for n in self._ALLOWED_NAMES})

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


class TenantMiddleware:
    """Sets the Postgres session variable ``app.current_tenant`` so that RLS
    policies can enforce row-level isolation.

    For regular users: sets it to the user's ``company_id`` (as text).
    For platform superusers (``company_id`` is None): sets it to an empty
    string, which RLS policies interpret as "see all tenants".

    Must run AFTER ``AuthenticationMiddleware`` so ``request.user`` is
    available.
    """

    _BYPASS_PREFIXES = ('/static/', '/media/', '/health/', '/healthz/', '/up/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = getattr(request, 'path', '')
        for prefix in self._BYPASS_PREFIXES:
            if path.startswith(prefix):
                return self.get_response(request)

        from django.db import connection

        user = getattr(request, 'user', None)
        company_id = None
        if user and user.is_authenticated:
            company_id = getattr(user, 'company_id', None)

        with connection.cursor() as cursor:
            if company_id is not None:
                cursor.execute("SET app.current_tenant = %s", [str(company_id)])
            else:
                cursor.execute("SET app.current_tenant = ''")

        try:
            response = self.get_response(request)
        finally:
            # Reset after the request so a pooled connection can't leak the
            # tenant context to the next request.
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")

        return response
