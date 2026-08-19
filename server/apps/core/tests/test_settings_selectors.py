"""Tests for apps.core.selectors_settings.

Verifies the read-side enrichment and formatting that the templates
consume — especially the tithe_rate display conversion (the inverse of
the service's raw→display conversion).
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import SystemConfig
from apps.core.models import Company
from apps.core.selectors_settings import get_default_credit_limit, get_settings_context
from apps.users.models import User


class GetSettingsContextTests(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
            first_name="Adrian", last_name="Thorne",
        )

    def tearDown(self):
        cache.clear()

    def test_context_has_all_tabs(self):
        ctx = get_settings_context(self.user)
        tab_ids = {t['id'] for t in ctx['tabs']}
        self.assertEqual(tab_ids, {'system-config', 'company', 'profile'})

    def test_system_config_has_five_rows(self):
        ctx = get_settings_context(self.user)
        keys = [row['key'] for row in ctx['system_config']]
        self.assertEqual(keys, [
            'lockscreen_timeout_minutes', 'tithe_rate',
            'approved_credit_limit', 'approved_container_limit',
            'overdue_threshold_days',
        ])

    def test_tithe_rate_displayed_as_percentage(self):
        """Stored 0.10 → displayed 10.00 (inverse of the service conversion)."""
        SystemConfig.objects.update_or_create(
            company=self.company, key='tithe_rate',
            defaults={'value': '0.10'},
        )
        ctx = get_settings_context(self.user)
        tithe = next(r for r in ctx['system_config'] if r['key'] == 'tithe_rate')
        self.assertEqual(tithe['value'], '10.00')

    def test_credit_limit_displayed_with_commas(self):
        SystemConfig.objects.update_or_create(
            company=self.company, key='approved_credit_limit',
            defaults={'value': '3000.00'},
        )
        ctx = get_settings_context(self.user)
        limit = next(r for r in ctx['system_config']
                     if r['key'] == 'approved_credit_limit')
        self.assertEqual(limit['value'], '3,000.00')

    def test_lockscreen_displayed_as_label(self):
        SystemConfig.objects.update_or_create(
            company=self.company, key='lockscreen_timeout_minutes',
            defaults={'value': '15'},
        )
        ctx = get_settings_context(self.user)
        timeout = next(r for r in ctx['system_config']
                       if r['key'] == 'lockscreen_timeout_minutes')
        self.assertEqual(timeout['value'], '15 min')

    def test_company_context_from_user_tenant(self):
        ctx = get_settings_context(self.user)
        self.assertEqual(ctx['company']['name'], 'Test Co')
        self.assertTrue(ctx['company']['has_company'])

    def test_company_context_for_superuser_without_tenant(self):
        superuser = User.objects.create_user(
            username="root", password="securepassword123",
            is_superuser=True, company=None,
        )
        ctx = get_settings_context(superuser)
        self.assertFalse(ctx['company']['has_company'])
        self.assertEqual(ctx['company']['name'], '')

    def test_profile_context_from_user(self):
        ctx = get_settings_context(self.user)
        self.assertEqual(ctx['profile']['first_name'], 'Adrian')
        self.assertEqual(ctx['profile']['last_name'], 'Thorne')
        self.assertEqual(ctx['profile']['username'], 'admin')
        self.assertEqual(ctx['profile']['avatar_initials'], 'AT')
        self.assertEqual(ctx['profile']['full_name'], 'Adrian Thorne')

    def test_falls_back_to_defaults_when_rows_missing(self):
        """If SystemConfig rows are missing, defaults are used (no crash)."""
        SystemConfig.objects.filter(company=self.company).delete()
        ctx = get_settings_context(self.user)
        # Should still render all 5 rows with default values.
        self.assertEqual(len(ctx['system_config']), 5)


class GetDefaultCreditLimitTests(TestCase):
    """Tests for the get_default_credit_limit domain helper.

    This selector feeds the Add Customer modal so the credit limit field
    is pre-populated with the tenant's configured ceiling.
    """

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Test Co")
        self.user = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
        )

    def tearDown(self):
        cache.clear()

    def test_returns_hardcoded_default_when_no_rows(self):
        """With no SystemConfig rows, the 3000.00 default is returned."""
        SystemConfig.objects.all().delete()
        self.assertEqual(get_default_credit_limit(self.user), Decimal("3000.00"))

    def test_returns_tenant_scoped_value_when_present(self):
        """A tenant-scoped row takes precedence over the global row."""
        SystemConfig.objects.update_or_create(
            company=self.company, key="approved_credit_limit",
            defaults={"value": "5000.00"},
        )
        self.assertEqual(get_default_credit_limit(self.user), Decimal("5000.00"))

    def test_falls_back_to_global_when_no_tenant_row(self):
        """A global (company=NULL) row is used when no tenant row exists."""
        SystemConfig.objects.update_or_create(
            company=None, key="approved_credit_limit",
            defaults={"value": "1500.00"},
        )
        self.assertEqual(get_default_credit_limit(self.user), Decimal("1500.00"))

    def test_tenant_row_overrides_global_row(self):
        """Tenant-scoped value wins over a present global row."""
        SystemConfig.objects.update_or_create(
            company=None, key="approved_credit_limit",
            defaults={"value": "1500.00"},
        )
        SystemConfig.objects.update_or_create(
            company=self.company, key="approved_credit_limit",
            defaults={"value": "7500.00"},
        )
        self.assertEqual(get_default_credit_limit(self.user), Decimal("7500.00"))

    def test_returns_decimal_quantized_to_two_places(self):
        """The returned value is always quantized to two decimal places."""
        SystemConfig.objects.update_or_create(
            company=self.company, key="approved_credit_limit",
            defaults={"value": "1234.5"},
        )
        self.assertEqual(
            get_default_credit_limit(self.user), Decimal("1234.50"),
        )

    def test_user_without_company_uses_global_row(self):
        """A user with no tenant falls back to the global row, then default."""
        SystemConfig.objects.all().delete()
        root = User.objects.create_user(
            username="root", password="securepassword123",
            is_superuser=True, company=None,
        )
        self.assertEqual(get_default_credit_limit(root), Decimal("3000.00"))
