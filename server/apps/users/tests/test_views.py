from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.users.models import Role, User
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
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.user = User.objects.create_user(
            username="hydr8user",
            password="securepassword123",
            is_staff=True,
        )
        self.user.role = admin_role
        self.user.save()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_landing_page_renders_abyss_brand(self):
        """Test that the landing page renders Abyss brand, links to legacy login, and has no embedded form."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hydr8')
        self.assertContains(response, 'Water. Delivered. Managed.')
        self.assertContains(response, 'Sign In to Station')
        self.assertContains(response, reverse('users:login'))
        # Embedded authentication form has been removed from landing page
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="password"')
        self.assertNotContains(response, 'id="signin"')

    def test_landing_page_features_pricing_and_contact(self):
        """Test landing page renders Command Queue, Gallery, ₱499 pricing, and subscription contact email."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # Features and Command Queue
        self.assertContains(response, 'Command Queue')
        self.assertContains(response, 'Offline-First')
        # Feature Gallery
        self.assertContains(response, 'Feature Gallery')
        self.assertContains(response, 'Daily Remittance Ledger')
        # Pricing at 499
        self.assertContains(response, '₱499')
        # Action Buttons
        self.assertContains(response, 'Get Started')
        self.assertContains(response, 'Log In')
        # Contact Email for Subscription
        self.assertContains(response, 'rushdashvx@gmail.com')

    def test_landing_page_theme_toggle_and_default_light_mode(self):
        """Test landing page renders theme toggle and pre-hydrates light mode by default."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # Pre-hydration script & helper contract
        self.assertContains(response, 'window.toggleHydr8Theme')
        self.assertContains(response, 'window.getHydr8Theme')
        self.assertContains(response, 'window.setHydr8Theme')
        self.assertContains(response, "document.documentElement.setAttribute('data-theme', 'light')")
        # Toggle button in navigation
        self.assertContains(response, 'toggleTheme()')
        self.assertContains(response, 'Switch to Light Mode')

    def test_landing_page_technical_jargon_removed(self):
        """Test landing page has all developer-centric technical jargon removed."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # Jargon explicitly banned
        self.assertNotContains(response, 'PostgreSQL ACID • Redis Caching • Atomic F() Updates')
        self.assertNotContains(response, 'Atomic F() Balance Updates')
        self.assertNotContains(response, 'PostgreSQL')
        self.assertNotContains(response, 'Redis')
        self.assertNotContains(response, 'Latency: 1.2ms')
        # Value-focused customer guarantees present
        self.assertContains(response, '99.9% Station Uptime • 100% Audit Accurate')
        self.assertContains(response, 'Automatic Balance Protection')
        self.assertContains(response, 'Speed: Instant')

    def test_login_view_get(self):
        """Test direct GET request to login view renders dedicated login page."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sign In')
        self.assertContains(response, 'Hydr8')

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
        response = self.client.get('/login/')
        self.assertContains(response, 'x-data="{ show: false }"')
        self.assertContains(response, '@click="show = !show"')
        self.assertContains(response, 'visibility')
        self.assertContains(response, 'visibility_off')
        self.assertContains(response, ":type=\"show ? 'text' : 'password'\"")

    def test_login_lockout_after_five_failures(self):
        """Test that 5 failed attempts locks the (ip, username) bucket for 1 minute."""
        for _ in range(LOGIN_MAX_ATTEMPTS):
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
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        other = User.objects.create_user(
            username="otheruser",
            password="otherpass123",
            is_staff=True,
        )
        other.role = admin_role
        other.save()
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

    def test_login_allows_staff_role_without_is_staff_flag(self):
        """A user with Role='Staff' but is_staff=False may log in.

        Regression: the login gate used to check only the `is_staff` boolean,
        so accounts created outside the user-creation service (admin, shell,
        fixtures) were rejected even though their Role granted back-office
        access. The gate now honors the Role model as the source of truth.
        """
        staff_role, _ = Role.objects.get_or_create(name="Staff")
        user = User.objects.create_user(
            username="rolestaff",
            password="securepassword123",
            is_staff=False,
        )
        user.role = staff_role
        user.save()

        response = self.client.post('/login/', {
            'username': 'rolestaff',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertIn('HX-Redirect', response.headers)

    def test_login_allows_admin_role_without_is_staff_flag(self):
        """A user with Role='Admin' but is_staff=False may log in."""
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        user = User.objects.create_user(
            username="roleadmin",
            password="securepassword123",
            is_staff=False,
        )
        user.role = admin_role
        user.save()

        response = self.client.post('/login/', {
            'username': 'roleadmin',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertIn('HX-Redirect', response.headers)

    def test_login_rejects_driver_role_without_flag(self):
        """A user with Role='Driver' and no is_staff/superuser is still rejected."""
        driver_role, _ = Role.objects.get_or_create(name="Driver")
        user = User.objects.create_user(
            username="roledriver",
            password="securepassword123",
            is_staff=False,
        )
        user.role = driver_role
        user.save()

        response = self.client.post('/login/', {
            'username': 'roledriver',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response.headers)
        self.assertContains(response, "Only staff and administrators are allowed to log in.")

    def test_login_rejects_user_with_no_role_and_no_flag(self):
        """A user with neither a back-office role nor the is_staff flag is rejected."""
        User.objects.create_user(
            username="norole",
            password="securepassword123",
            is_staff=False,
        )

        response = self.client.post('/login/', {
            'username': 'norole',
            'password': 'securepassword123'
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('HX-Redirect', response.headers)
        self.assertContains(response, "Only staff and administrators are allowed to log in.")


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

