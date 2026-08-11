from django.test import TestCase
from django.core.cache import cache

from apps.users.models import User
from apps.users.services import (
    LOGIN_LOCKOUT_SECONDS,
    LOGIN_MAX_ATTEMPTS,
    get_failed_attempt_count,
    is_login_locked,
    record_failed_login,
    reset_failed_login,
)


class UserLandingAndLoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8user",
            password="securepassword123"
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_landing_page_renders_abyss_brand(self):
        """Test that the landing page renders split-screen Abyss brand and Sign In card."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hydr8')
        self.assertContains(response, 'Water. Delivered. Managed.')
        self.assertContains(response, 'Sign In')

    def test_login_view_get(self):
        """Test direct GET request to login view returns partial form."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'username')

    def test_login_htmx_failure_returns_partial(self):
        """Test HTMX login failure returns inline form errors."""
        response = self.client.post('/login/', {
            'username': 'hydr8user',
            'password': 'wrongpassword'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct username and password')

    def test_login_htmx_success_sets_redirect(self):
        """Test successful HTMX login sets HX-Redirect header."""
        response = self.client.post('/login/', {
            'username': 'hydr8user',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertIn('HX-Redirect', response.headers)

    def test_login_form_has_password_eye_toggle(self):
        """Test the password field includes the Alpine.js eye toggle button."""
        response = self.client.get('/')
        self.assertContains(response, 'x-data="{ show: false }"')
        self.assertContains(response, '@click="show = !show"')
        self.assertContains(response, 'visibility')
        self.assertContains(response, 'visibility_off')
        self.assertContains(response, ":type=\"show ? 'text' : 'password'\"")

    def test_login_lockout_after_five_failures(self):
        """Test that 5 failed attempts locks the (ip, username) bucket for 1 minute."""
        for i in range(LOGIN_MAX_ATTEMPTS):
            response = self.client.post('/login/', {
                'username': 'hydr8user',
                'password': 'wrongpassword'
            }, HTTP_HX_REQUEST='true')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Please enter a correct username and password')

        # 6th attempt should be locked out with the lockout message
        response = self.client.post('/login/', {
            'username': 'hydr8user',
            'password': 'wrongpassword'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many failed attempts. Please try again in 1 minute.')

        # Even the correct password should be rejected while locked out
        response = self.client.post('/login/', {
            'username': 'hydr8user',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many failed attempts. Please try again in 1 minute.')
        self.assertNotIn('HX-Redirect', response.headers)

    def test_login_success_resets_failure_counter(self):
        """Test that a successful login clears the failed-attempt counter."""
        # Accumulate 3 failures
        for _ in range(3):
            self.client.post('/login/', {
                'username': 'hydr8user',
                'password': 'wrongpassword'
            }, HTTP_HX_REQUEST='true')
        self.assertEqual(get_failed_attempt_count(ip='127.0.0.1', username='hydr8user'), 3)

        # Successful login resets the counter
        response = self.client.post('/login/', {
            'username': 'hydr8user',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertIn('HX-Redirect', response.headers)
        self.assertEqual(get_failed_attempt_count(ip='127.0.0.1', username='hydr8user'), 0)

    def test_login_lockout_is_per_username(self):
        """Test that lockout on one username does not block a different username from the same IP."""
        User.objects.create_user(username="otheruser", password="otherpass123")
        for _ in range(LOGIN_MAX_ATTEMPTS):
            self.client.post('/login/', {
                'username': 'hydr8user',
                'password': 'wrongpassword'
            }, HTTP_HX_REQUEST='true')

        # hydr8user is locked, but otheruser can still log in
        response = self.client.post('/login/', {
            'username': 'otheruser',
            'password': 'otherpass123'
        }, HTTP_HX_REQUEST='true')
        self.assertIn('HX-Redirect', response.headers)


class LoginLockoutServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_record_and_reset_failed_login(self):
        record_failed_login(ip='1.2.3.4', username='alice')
        record_failed_login(ip='1.2.3.4', username='alice')
        self.assertEqual(get_failed_attempt_count(ip='1.2.3.4', username='alice'), 2)

        reset_failed_login(ip='1.2.3.4', username='alice')
        self.assertEqual(get_failed_attempt_count(ip='1.2.3.4', username='alice'), 0)

    def test_is_login_locked_after_max_attempts(self):
        for _ in range(LOGIN_MAX_ATTEMPTS):
            record_failed_login(ip='1.2.3.4', username='bob')
        self.assertTrue(is_login_locked(ip='1.2.3.4', username='bob'))

    def test_is_login_locked_below_max_attempts(self):
        for _ in range(LOGIN_MAX_ATTEMPTS - 1):
            record_failed_login(ip='1.2.3.4', username='carol')
        self.assertFalse(is_login_locked(ip='1.2.3.4', username='carol'))

    def test_lockout_constants(self):
        """Lockout policy: 5 attempts, 60 seconds."""
        self.assertEqual(LOGIN_MAX_ATTEMPTS, 5)
        self.assertEqual(LOGIN_LOCKOUT_SECONDS, 60)

