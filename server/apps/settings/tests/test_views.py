"""Tests for apps.settings.views.

Covers the GET page render and all 5 POST endpoints — including the
admin-only restriction on system config / company writes, and the
current-password verification on credential changes.
"""
from django.core.cache import cache
from django.test import TestCase

from apps.core.models import SystemConfig
from apps.settings.models import Company
from apps.users.models import Role, User


class SettingsViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Test Co")
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
            first_name="Adrian", last_name="Thorne",
        )
        self.admin.role = admin_role
        self.admin.save()
        self.staff = User.objects.create_user(
            username="staff", password="securepassword123",
            company=self.company,
        )
        self.staff.role = staff_role
        self.staff.save()
        self.client.force_login(self.admin)

    def tearDown(self):
        cache.clear()

    def test_settings_page_renders(self):
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'System Config')
        self.assertContains(response, 'Company')
        self.assertContains(response, 'My Profile')
        self.assertContains(response, 'AI Model')

    def test_settings_page_deep_links_to_profile_tab(self):
        response = self.client.get('/settings/?tab=profile')
        self.assertContains(response, "activeTab: 'profile'")

    def test_settings_page_invalid_tab_falls_back(self):
        response = self.client.get('/settings/?tab=<script>')
        self.assertContains(response, "activeTab: 'system-config'")


class SaveSystemConfigViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Test Co")
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
        )
        self.admin.role = admin_role
        self.admin.save()
        self.staff = User.objects.create_user(
            username="staff", password="securepassword123",
            company=self.company,
        )
        self.staff.role = staff_role
        self.staff.save()

    def tearDown(self):
        cache.clear()

    def test_admin_can_save_tithe_rate(self):
        self.client.force_login(self.admin)
        response = self.client.post('/settings/system-config/save/', {
            'tithe_rate': '12.50',
        })
        self.assertEqual(response.status_code, 200)
        row = SystemConfig.objects.get(
            company=self.company, key='tithe_rate')
        self.assertEqual(row.value, '0.1250')

    def test_non_admin_blocked(self):
        """A non-staff user cannot save system config."""
        self.client.force_login(self.staff)
        response = self.client.post('/settings/system-config/save/', {
            'tithe_rate': '12.50',
        })
        self.assertEqual(response.status_code, 403)

    def test_invalid_value_returns_error(self):
        self.client.force_login(self.admin)
        response = self.client.post('/settings/system-config/save/', {
            'tithe_rate': 'not-a-number',
        })
        self.assertEqual(response.status_code, 400)

    def test_multiple_keys_saved_at_once(self):
        self.client.force_login(self.admin)
        response = self.client.post('/settings/system-config/save/', {
            'tithe_rate': '15.00',
            'approved_container_limit': '25',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            SystemConfig.objects.get(
                company=self.company, key='tithe_rate').value, '0.1500')
        self.assertEqual(
            SystemConfig.objects.get(
                company=self.company, key='approved_container_limit').value, '25')


class SaveCompanyViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Original Co")
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        staff_role, _ = Role.objects.get_or_create(name="Staff")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
        )
        self.admin.role = admin_role
        self.admin.save()
        self.staff = User.objects.create_user(
            username="staff", password="securepassword123",
            company=self.company,
        )
        self.staff.role = staff_role
        self.staff.save()

    def tearDown(self):
        cache.clear()

    def test_admin_can_save_company(self):
        self.client.force_login(self.admin)
        response = self.client.post('/settings/company/save/', {
            'name': 'New Co',
            'contact_number': '+63 917 555 1212',
            'email': 'new@test.io',
            'address': '456 Ave',
        })
        self.assertEqual(response.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, 'New Co')

    def test_non_admin_blocked(self):
        self.client.force_login(self.staff)
        response = self.client.post('/settings/company/save/', {
            'name': 'New Co', 'contact_number': '', 'email': '', 'address': '',
        })
        self.assertEqual(response.status_code, 403)

    def test_empty_name_returns_error(self):
        self.client.force_login(self.admin)
        response = self.client.post('/settings/company/save/', {
            'name': '', 'contact_number': '', 'email': '', 'address': '',
        })
        self.assertEqual(response.status_code, 400)


class SaveProfileViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
            first_name="Jane", last_name="Doe",
        )
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_save_profile_updates_name(self):
        response = self.client.post('/settings/profile/save/', {
            'first_name': 'Janet', 'last_name': 'Smith',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Janet')
        self.assertEqual(self.user.last_name, 'Smith')


class ChangeUsernameViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
        )
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_change_with_correct_password(self):
        response = self.client.post('/settings/username/change/', {
            'current_password': 'securepassword123',
            'new_username': 'jane.new',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'jane.new')

    def test_change_with_wrong_password_returns_error(self):
        response = self.client.post('/settings/username/change/', {
            'current_password': 'wrong',
            'new_username': 'jane.new',
        })
        self.assertEqual(response.status_code, 400)


class ChangePasswordViewTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
        )
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_change_with_correct_password(self):
        response = self.client.post('/settings/password/change/', {
            'current_password': 'securepassword123',
            'new_password': 'newsecurepass456',
            'confirm_password': 'newsecurepass456',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newsecurepass456'))

    def test_change_with_wrong_password_returns_error(self):
        response = self.client.post('/settings/password/change/', {
            'current_password': 'wrong',
            'new_password': 'newsecurepass456',
            'confirm_password': 'newsecurepass456',
        })
        self.assertEqual(response.status_code, 400)

    def test_mismatched_new_passwords_return_error(self):
        response = self.client.post('/settings/password/change/', {
            'current_password': 'securepassword123',
            'new_password': 'newsecurepass456',
            'confirm_password': 'differentpass789',
        })
        self.assertEqual(response.status_code, 400)

    def test_session_stays_alive_after_password_change(self):
        """update_session_auth_hash should prevent logout."""
        self.client.post('/settings/password/change/', {
            'current_password': 'securepassword123',
            'new_password': 'newsecurepass456',
            'confirm_password': 'newsecurepass456',
        })
        # The next request should still be authenticated.
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 200)
