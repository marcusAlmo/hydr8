import uuid
import contextvars
import logging

from typing import Optional

# Create a context variable to hold the correlation ID for the current thread/async task
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


class TenantMiddleware:
    """Sets the Postgres session variable ``app.current_tenant`` so that RLS
    policies can enforce row-level isolation.

    For regular users: sets it to the user's ``company_id`` (as text).
    For platform superusers (``company_id`` is None): sets it to an empty
    string, which RLS policies interpret as "see all tenants".

    Must run AFTER ``AuthenticationMiddleware`` so ``request.user`` is
    available.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
