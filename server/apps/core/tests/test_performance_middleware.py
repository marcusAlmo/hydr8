"""Tests for ``ProcessPerformanceMiddleware`` — server process speed,
database query execution metrics, and latency logging.
"""
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.middleware import ProcessPerformanceMiddleware
from apps.users.models import Role, User


class ProcessPerformanceMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.user = User.objects.create_user(
            username="perf_tester",
            password="testpassword123",
            is_staff=True,
        )
        self.user.role = admin_role
        self.user.save()

    def test_server_timing_header_present_in_client_response(self):
        """Verifies that normal requests receive the W3C Server-Timing header."""
        resp = self.client.get("/")
        self.assertIn("Server-Timing", resp.headers)
        header_val = resp.headers["Server-Timing"]
        self.assertIn("total;dur=", header_val)
        self.assertIn("db;dur=", header_val)
        self.assertIn("view;dur=", header_val)

    def test_performance_log_emitted_for_anonymous_request(self):
        """Verifies structured INFO logging with actor_id='anon' for unauthenticated requests."""
        with self.assertLogs("apps.performance", level="INFO") as cm:
            resp = self.client.get("/")
            self.assertEqual(resp.status_code, 200)

        log_output = cm.output[0]
        self.assertIn("[anon] HTTP GET / -> 200", log_output)
        self.assertIn("total=", log_output)
        self.assertIn("view=", log_output)
        self.assertIn("db=", log_output)
        self.assertIn("queries=", log_output)

    def test_performance_log_emitted_with_authenticated_actor_id(self):
        """Verifies that authenticated requests log the user's ID without PII."""
        self.client.force_login(self.user)
        with self.assertLogs("apps.performance", level="INFO") as cm:
            resp = self.client.get(reverse("analytics:dashboard"))
            self.assertEqual(resp.status_code, 200)

        log_output = "\n".join(cm.output)
        expected_actor = f"[{self.user.id}]"
        self.assertIn(expected_actor, log_output)
        # Verify no usernames or sensitive strings leaked
        self.assertNotIn("perf_tester", log_output)

    def test_database_queries_tracked_by_wrapper(self):
        """Verifies that SQL queries inside views are counted and timed."""
        def view_with_db_query(request):
            # Execute an actual ORM query against the database
            _ = list(User.objects.filter(id=self.user.id))
            return HttpResponse("OK")

        middleware = ProcessPerformanceMiddleware(view_with_db_query)
        request = self.factory.get("/test-db/")
        request.user = self.user

        with self.assertLogs("apps.performance", level="INFO") as cm:
            response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Server-Timing", response.headers)
        # Verify that queries were recorded
        log_line = cm.output[0]
        self.assertIn("queries=1", log_line)

    @override_settings(PERFORMANCE_SLOW_THRESHOLD_MS=10.0)
    def test_slow_request_threshold_escalates_to_warning(self):
        """Verifies that requests exceeding PERFORMANCE_SLOW_THRESHOLD_MS trigger a WARNING."""
        def simulated_slow_view(request):
            return HttpResponse("SLOW")

        middleware = ProcessPerformanceMiddleware(simulated_slow_view)
        request = self.factory.get("/slow-view/")

        # Patch time.perf_counter to simulate a duration > 10ms
        with (
            patch("apps.core.middleware.time.perf_counter", side_effect=[0.0, 0.05]),
            self.assertLogs("apps.performance", level="WARNING") as cm,
        ):
            response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("WARNING" in record for record in cm.output))
        self.assertIn("/slow-view/", cm.output[0])

    def test_bypass_static_and_health_endpoints(self):
        """Verifies that /static/, /media/, and health checks bypass performance logging."""
        def dummy_view(request):
            return HttpResponse("BYPASS")

        middleware = ProcessPerformanceMiddleware(dummy_view)

        for bypass_path in ("/static/app.css", "/media/photo.jpg", "/health/", "/up/"):
            request = self.factory.get(bypass_path)
            response = middleware(request)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("Server-Timing", response.headers)

    def test_privacy_no_query_parameters_in_logs(self):
        """Verifies compliance with RA 10173: query string params are not logged."""
        with self.assertLogs("apps.performance", level="INFO") as cm:
            resp = self.client.get("/?token=secret123&phone=09171234567")
            self.assertEqual(resp.status_code, 200)

        log_output = cm.output[0]
        self.assertNotIn("secret123", log_output)
        self.assertNotIn("09171234567", log_output)
        self.assertNotIn("token=", log_output)
