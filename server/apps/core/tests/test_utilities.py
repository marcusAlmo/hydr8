"""Tests for core utilities: error_message, toast helpers, and middleware.

Covers the shared utility functions used across all HTMX views and the
correlation ID / tenant middleware.
"""
import logging

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.core.middleware import (
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    correlation_id_var,
    get_correlation_id,
)
from apps.core.views import (
    error_message,
    toast_error,
    toast_for_exception,
    toast_response,
    toast_success,
)

# ---------------------------------------------------------------------------
# error_message
# ---------------------------------------------------------------------------


class ErrorMessageTests(SimpleTestCase):
    """Tests for the error_message utility."""

    def test_generic_exception_returns_str(self):
        """Generic exception returns str(exc)."""
        self.assertEqual(error_message(Exception("Something went wrong")), "Something went wrong")

    def test_validation_error_with_message(self):
        """ValidationError with a message attribute uses it."""
        self.assertEqual(error_message(ValidationError("Invalid input")), "Invalid input")

    def test_validation_error_with_messages_list(self):
        """ValidationError with a messages list joins them with spaces."""
        exc = ValidationError(["Error 1", "Error 2"])
        self.assertEqual(error_message(exc), "Error 1 Error 2")


# ---------------------------------------------------------------------------
# toast helpers
# ---------------------------------------------------------------------------


class ToastResponseTests(TestCase):
    """Tests for toast_response, toast_success, toast_error, toast_for_exception."""

    def setUp(self):
        from apps.users.models import User
        self.user = User.objects.create_user(username="toast_user", password="pass123")
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _request(self):
        request = self.factory.get("/")
        request.user = self.user
        return request

    def test_toast_response_success(self):
        """toast_response renders with the given message and success type."""
        response = toast_response(self._request(), "Success message", type="success")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Success message", response.content.decode())

    def test_toast_response_error_with_status(self):
        """toast_response renders with custom status code."""
        response = toast_response(self._request(), "Error msg", type="error", status=400)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Error msg", response.content.decode())

    def test_toast_success_defaults(self):
        """toast_success defaults to status=200."""
        response = toast_success(self._request(), "Done")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Done", response.content.decode())

    def test_toast_error_defaults(self):
        """toast_error defaults to status=400."""
        response = toast_error(self._request(), "Failed")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Failed", response.content.decode())

    def test_toast_for_exception_generic(self):
        """toast_for_exception converts a generic exception to an error toast."""
        response = toast_for_exception(self._request(), Exception("Boom"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Boom", response.content.decode())

    def test_toast_for_exception_validation_error(self):
        """toast_for_exception extracts the message from a ValidationError."""
        response = toast_for_exception(self._request(), ValidationError("Bad input"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Bad input", response.content.decode())


# ---------------------------------------------------------------------------
# CorrelationIdMiddleware
# ---------------------------------------------------------------------------


class CorrelationIdMiddlewareTests(SimpleTestCase):
    """Tests for CorrelationIdMiddleware."""

    def setUp(self):
        self.middleware = CorrelationIdMiddleware(lambda r: HttpResponse("ok"))

    def test_generates_uuid_when_header_missing(self):
        """Generates a UUID when X-Correlation-ID header is missing."""
        request = type("Req", (), {"META": {}})()
        response = self.middleware(request)
        self.assertIn("X-Correlation-ID", response)
        self.assertTrue(response["X-Correlation-ID"])

    def test_uses_header_when_present(self):
        """Uses the X-Correlation-ID from the header when present."""
        test_id = "test-cid-123"
        request = type("Req", (), {"META": {"HTTP_X_CORRELATION_ID": test_id}})()
        response = self.middleware(request)
        self.assertEqual(response["X-Correlation-ID"], test_id)

    def test_sets_correlation_id_on_request(self):
        """Sets the correlation_id attribute on the request object."""
        request = type("Req", (), {"META": {}})()
        self.middleware(request)
        self.assertTrue(hasattr(request, "correlation_id"))
        self.assertIsNotNone(request.correlation_id)

    def test_sets_context_variable(self):
        """Sets the correlation ID in the context variable."""
        test_id = "ctx-id-456"
        request = type("Req", (), {"META": {"HTTP_X_CORRELATION_ID": test_id}})()
        self.middleware(request)
        self.assertEqual(get_correlation_id(), test_id)


class CorrelationIdFilterTests(SimpleTestCase):
    """Tests for CorrelationIdFilter logging filter."""

    def test_filter_adds_correlation_id(self):
        """The filter adds the correlation_id to the log record."""
        correlation_id_var.set("filter-test-id")
        filt = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        self.assertTrue(filt.filter(record))
        self.assertEqual(record.correlation_id, "filter-test-id")

    def test_filter_defaults_to_no_id(self):
        """The filter uses 'no-id' when correlation ID is not set."""
        correlation_id_var.set(None)
        filt = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="test", args=(), exc_info=None,
        )
        filt.filter(record)
        self.assertEqual(record.correlation_id, "no-id")


# ---------------------------------------------------------------------------
# health check endpoints
# ---------------------------------------------------------------------------


class HealthCheckTests(SimpleTestCase):
    """Tests for health check endpoints used by Docker/Coolify probes."""

    def test_health_check_view_direct(self):
        from apps.core.views import health_check_view
        rf = RequestFactory()
        request = rf.get('/health/')
        response = health_check_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"OK")
        self.assertEqual(response['Content-Type'], "text/plain")

    def test_health_check_urls_return_ok(self):
        for path in ['/health/', '/healthz/', '/up/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"OK")

    def test_production_allowed_hosts_includes_loopback(self):
        """Production settings always include localhost and loopback interfaces."""
        from config.settings import production
        self.assertIn("localhost", production.ALLOWED_HOSTS)
        self.assertIn("127.0.0.1", production.ALLOWED_HOSTS)
        self.assertIn("[::1]", production.ALLOWED_HOSTS)


