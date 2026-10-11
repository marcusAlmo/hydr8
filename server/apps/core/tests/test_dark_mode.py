"""Tests for Hydr8 Dark Mode support, pre-hydration script, sidebar toggle, and settings."""
from django.test import TestCase
from django.urls import reverse

from apps.settings.models import Company
from apps.users.models import Role, User


class DarkModeTests(TestCase):
    """Verifies dark mode infrastructure across base template, sidebar, and settings."""

    def setUp(self):
        self.company = Company.objects.create(name="Hydr8 Station Dark Mode Test")
        self.admin_role, _ = Role.objects.get_or_create(name="Admin", company=None)

        self.user = User.objects.create_user(
            username="dark_mode_tester",
            password="testpassword123",
            role=self.admin_role,
            company=self.company,
        )

    def test_base_template_pre_hydration_script_and_api(self):
        """The base template must include pre-hydration script and window helpers."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        # Verify pre-hydration script runs in <head> to prevent FOUC
        self.assertIn("localStorage.getItem('hydr8_theme')", html)
        self.assertIn("window.getHydr8Theme", html)
        self.assertIn("window.setHydr8Theme", html)
        self.assertIn("window.toggleHydr8Theme", html)
        self.assertIn('darkMode: "class"', html)
        self.assertIn("hydr8:theme-change", html)

    def test_sidebar_theme_toggle_button(self):
        """The sidebar must render the theme toggle button with light/dark icons."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("analytics:dashboard"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        # Verify toggle button and its icons
        self.assertIn("window.toggleHydr8Theme()", html)
        self.assertIn("dark_mode", html)
        self.assertIn("light_mode", html)
        self.assertIn("Switch to Light Mode", html)
        self.assertIn("Switch to Dark Mode", html)

    def test_settings_appearance_theme_selector(self):
        """Settings profile tab must render the Appearance & Theme selector card."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("settings:list") + "?tab=profile")
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        # Verify Appearance & Theme card
        self.assertIn("Appearance &amp; Theme", html)
        self.assertIn("setTheme('light')", html)
        self.assertIn("setTheme('dark')", html)
        self.assertIn("setTheme('system')", html)
        self.assertIn("Sync with device settings", html)

    def test_employees_directory_theme_aware_charts(self):
        """Employees directory template must include theme change listener and dynamic colors."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("employees:list"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn("hydr8:theme-change", html)
        self.assertIn("mode: isDark ? 'dark' : 'light'", html)
        self.assertIn("background: 'transparent'", html)
        self.assertIn("colors: [isDark ? '#38BDF8' : '#006591']", html)
        self.assertIn("colors: [isDark ? '#34D399' : '#006C4A']", html)

    def test_remittance_history_theme_aware_charts(self):
        """Remittance history template must include theme change listener, dynamic colors, and rider palettes."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("remittance:history"))
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn("hydr8:theme-change", html)
        self.assertIn("mode: isDark ? 'dark' : 'light'", html)
        self.assertIn("background: 'transparent'", html)
        self.assertIn("salesColor = isDark ? '#38BDF8' : '#006591'", html)
        self.assertIn("debtColor  = isDark ? '#FBBF24' : '#D97706'", html)
        self.assertIn("commColor  = isDark ? '#34D399' : '#006C4A'", html)
        self.assertIn("darkRiderPalette", html)
        self.assertIn("riderColor(rider, index)", html)
        self.assertIn("html.dark .chart-skeleton", html)

    def test_base_template_with_alpha_and_tailwind_tokens(self):
        """Base template must use withAlpha color-mix helper for opacity and dark mode support."""
        self.client.force_login(self.user)
        response = self.client.get(reverse("analytics:dashboard"))
        html = response.content.decode()
        self.assertIn("function withAlpha(varName, fallback)", html)
        self.assertIn("color-mix(in srgb, var(", html)
        self.assertIn('withAlpha("--color-surface-container-lowest"', html)
        self.assertIn('withAlpha("--color-outline-variant"', html)

    def test_login_page_theme_pre_hydration(self):
        """Login page must pre-hydrate theme from localStorage before render."""
        response = self.client.get(reverse("users:login"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("localStorage.getItem('hydr8_theme')", html)
        self.assertIn("document.documentElement.classList.add('dark')", html)

