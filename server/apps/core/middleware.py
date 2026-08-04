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
        
        # 2. Set the ID in the context variable for the duration of this request
        token = correlation_id_var.set(req_id)

        try:
            # 3. Process the request (this calls views, other middlewares, etc.)
            response = self.get_response(request)
            
            # 4. Inject the Correlation ID into the response headers for the client/frontend
            response['X-Correlation-ID'] = req_id
            return response
        finally:
            # 5. Reset the context variable to avoid leaking state between requests
            correlation_id_var.reset(token)

class CorrelationIdFilter(logging.Filter):
    """
    A custom logging filter that injects the correlation ID into every log record.
    """
    def filter(self, record):
        record.correlation_id = get_correlation_id() or 'no-id'
        return True
