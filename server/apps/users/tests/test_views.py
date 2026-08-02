from django.test import TestCase
from apps.users.models import User


class UserLandingAndLoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8user",
            password="securepassword123"
        )

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
