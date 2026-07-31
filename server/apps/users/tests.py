from django.test import TestCase
from .models import User, Role, Permission


class UserModelTests(TestCase):
    def setUp(self):
        self.role = Role.objects.create(name="Admin")
        self.permission = Permission.objects.create(
            role=self.role, 
            action="dashboard", 
            can_read=True, 
            can_write=False
        )
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="password123"
        )

    def test_user_initial_state(self):
        """Test that a user starts with default active status."""
        self.assertEqual(self.user.status, User.StatusChoices.ACTIVE)
        self.assertIsNone(self.user.deleted_at)

    def test_assign_role(self):
        """Test assigning a role to a user."""
        self.user.role = self.role
        self.user.save()
        self.assertEqual(self.user.role, self.role)

    def test_role_permissions(self):
        """Test accessing permissions associated with a user's role."""
        self.user.role = self.role
        self.user.save()
        permission = self.user.role.permissions.get(action="dashboard")
        self.assertTrue(permission.can_read)
        self.assertFalse(permission.can_write)


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


