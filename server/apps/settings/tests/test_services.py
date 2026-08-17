"""Tests for apps.settings.services.

Covers the critical paths:
  - tithe_rate display→raw conversion (financial integrity)
  - system config save with audit trail (updated_by)
  - company save (tenant-scoped)
  - profile name update
  - username change (current-password verified)
  - password change (current-password verified)
"""
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import SystemConfig
from apps.customers.models import Customer
from apps.settings.models import Company
from apps.settings.services import (
    apply_credit_limit_to_all_customers,
    change_password,
    change_username,
    save_company,
    save_system_config,
    update_profile,
)
from apps.users.models import User


class SaveSystemConfigTests(TestCase):
    """System Config save service — the critical financial-integrity path."""

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Test Co")
        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            is_staff=True,
            company=self.company,
        )

    def tearDown(self):
        cache.clear()

    def test_tithe_rate_stores_decimal_fraction_not_percentage(self):
        """CRITICAL: '10.00' (display %) must be stored as '0.10' (fraction).

        The remittance finalize service reads this as
        Decimal(SystemConfig.objects.get_value('tithe_rate', '0.10'))
        and multiplies by net_profit. Storing 10.00 would make tithes
        100x too large.
        """
        save_system_config(
            key='tithe_rate',
            display_value='10.00',
            performed_by=self.admin,
        )
        row = SystemConfig.objects.get(company=self.company, key='tithe_rate')
        self.assertEqual(row.value, '0.1000')

    def test_tithe_rate_zero(self):
        save_system_config(key='tithe_rate', display_value='0',
                           performed_by=self.admin)
        row = SystemConfig.objects.get(company=self.company, key='tithe_rate')
        self.assertEqual(row.value, '0.0000')

    def test_tithe_rate_over_100_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(key='tithe_rate', display_value='150',
                               performed_by=self.admin)

    def test_tithe_rate_negative_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(key='tithe_rate', display_value='-5',
                               performed_by=self.admin)

    def test_tithe_rate_non_numeric_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(key='tithe_rate', display_value='abc',
                               performed_by=self.admin)

    def test_credit_limit_strips_currency_and_commas(self):
        save_system_config(
            key='approved_credit_limit',
            display_value='₱3,000.00',
            performed_by=self.admin,
        )
        row = SystemConfig.objects.get(
            company=self.company, key='approved_credit_limit')
        self.assertEqual(row.value, '3000.00')

    def test_credit_limit_negative_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(
                key='approved_credit_limit', display_value='-100',
                performed_by=self.admin)

    def test_container_limit_must_be_whole_number(self):
        save_system_config(
            key='approved_container_limit', display_value='25',
            performed_by=self.admin)
        row = SystemConfig.objects.get(
            company=self.company, key='approved_container_limit')
        self.assertEqual(row.value, '25')

    def test_container_limit_non_integer_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(
                key='approved_container_limit', display_value='20.5',
                performed_by=self.admin)

    def test_lockscreen_timeout_display_label_converted(self):
        save_system_config(
            key='lockscreen_timeout_minutes', display_value='15 min',
            performed_by=self.admin)
        row = SystemConfig.objects.get(
            company=self.company, key='lockscreen_timeout_minutes')
        self.assertEqual(row.value, '15')

    def test_lockscreen_timeout_never_converts_to_zero(self):
        save_system_config(
            key='lockscreen_timeout_minutes', display_value='Never',
            performed_by=self.admin)
        row = SystemConfig.objects.get(
            company=self.company, key='lockscreen_timeout_minutes')
        self.assertEqual(row.value, '0')

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValidationError):
            save_system_config(key='bogus_key', display_value='x',
                               performed_by=self.admin)

    def test_updated_by_set_on_save(self):
        """The audit trail field updated_by must be set."""
        save_system_config(key='tithe_rate', display_value='10.00',
                           performed_by=self.admin)
        row = SystemConfig.objects.get(
            company=self.company, key='tithe_rate')
        self.assertEqual(row.updated_by, self.admin)

    def test_save_creates_row_if_missing(self):
        """If a key doesn't exist for the tenant, it is created."""
        # Delete the seeded row (if any) for this tenant.
        SystemConfig.objects.filter(
            company=self.company, key='approved_container_limit').delete()
        save_system_config(
            key='approved_container_limit', display_value='30',
            performed_by=self.admin)
        row = SystemConfig.objects.get(
            company=self.company, key='approved_container_limit')
        self.assertEqual(row.value, '30')


class SaveCompanyTests(TestCase):

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Original Co")
        self.admin = User.objects.create_user(
            username="admin", password="securepassword123",
            is_staff=True, company=self.company,
        )

    def tearDown(self):
        cache.clear()

    def test_save_updates_company_fields(self):
        save_company(
            user=self.admin, name="New Co Name",
            contact_number="+63 917 123 4567",
            email="new@test.io", address="123 New St",
        )
        self.company.refresh_from_db()
        self.assertEqual(self.company.name, "New Co Name")
        self.assertEqual(self.company.contact_number, "+63 917 123 4567")
        self.assertEqual(self.company.email, "new@test.io")
        self.assertEqual(self.company.address, "123 New St")

    def test_save_rejects_empty_name(self):
        with self.assertRaises(ValidationError):
            save_company(user=self.admin, name="",
                         contact_number="", email="", address="")

    def test_save_rejects_user_without_company(self):
        """Platform superuser (company=NULL) cannot save company."""
        superuser = User.objects.create_user(
            username="root", password="securepassword123",
            is_superuser=True, company=None,
        )
        with self.assertRaises(ValidationError):
            save_company(user=superuser, name="X",
                         contact_number="", email="", address="")


class UpdateProfileTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
            first_name="Jane", last_name="Doe",
        )

    def tearDown(self):
        cache.clear()

    def test_update_changes_name_fields(self):
        update_profile(user=self.user, first_name="Janet", last_name="Smith")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Janet")
        self.assertEqual(self.user.last_name, "Smith")


class ChangeUsernameTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
        )
        self.other = User.objects.create_user(
            username="taken", password="securepassword123",
        )

    def tearDown(self):
        cache.clear()

    def test_change_with_correct_password(self):
        change_username(user=self.user, current_password="securepassword123",
                        new_username="jane.new")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "jane.new")

    def test_change_with_wrong_password_rejected(self):
        with self.assertRaises(ValidationError):
            change_username(user=self.user, current_password="wrong",
                            new_username="jane.new")

    def test_change_to_existing_username_rejected(self):
        with self.assertRaises(ValidationError):
            change_username(user=self.user, current_password="securepassword123",
                            new_username="taken")

    def test_change_to_blank_username_rejected(self):
        with self.assertRaises(ValidationError):
            change_username(user=self.user, current_password="securepassword123",
                            new_username="   ")


class ChangePasswordTests(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="jane", password="securepassword123",
        )

    def tearDown(self):
        cache.clear()

    def test_change_with_correct_password(self):
        change_password(user=self.user, current_password="securepassword123",
                        new_password="newsecurepass456")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newsecurepass456"))

    def test_change_with_wrong_password_rejected(self):
        with self.assertRaises(ValidationError):
            change_password(user=self.user, current_password="wrong",
                            new_password="newsecurepass456")

    def test_change_to_short_password_rejected(self):
        with self.assertRaises(ValidationError):
            change_password(user=self.user, current_password="securepassword123",
                            new_password="short")

    def test_change_clears_force_password_change_flag(self):
        self.user.force_password_change = True
        self.user.save(update_fields=['force_password_change'])
        change_password(user=self.user, current_password="securepassword123",
                        new_password="newsecurepass456")
        self.user.refresh_from_db()
        self.assertFalse(self.user.force_password_change)


class ApplyCreditLimitToAllCustomersTests(TestCase):
    """Tests for apply_credit_limit_to_all_customers service."""

    def setUp(self):
        cache.clear()
        self.company = Company.objects.create(name="Water Co")
        self.other_company = Company.objects.create(name="Other Co")
        self.admin = User.objects.create_user(
            username="admin_user",
            password="securepassword123",
            is_staff=True,
            company=self.company,
        )
        self.admin.set_pin("1234")
        self.admin.save()

        self.c1 = Customer.objects.create(
            name="Customer 1",
            company=self.company,
            credit_limit=Decimal("1000.00"),
        )
        self.c2 = Customer.objects.create(
            name="Customer 2",
            company=self.company,
            credit_limit=Decimal("2000.00"),
        )
        self.c_deleted = Customer.objects.create(
            name="Deleted Customer",
            company=self.company,
            credit_limit=Decimal("500.00"),
            deleted_at=timezone.now(),
        )
        self.c_other = Customer.objects.create(
            name="Other Customer",
            company=self.other_company,
            credit_limit=Decimal("1500.00"),
        )

    def tearDown(self):
        cache.clear()

    def test_valid_pin_updates_config_and_all_tenant_customers(self):
        config_obj, count = apply_credit_limit_to_all_customers(
            display_value="₱5,000.00",
            pin="1234",
            performed_by=self.admin,
        )
        self.assertEqual(count, 2)
        self.assertEqual(config_obj.value, "5000.00")

        self.c1.refresh_from_db()
        self.c2.refresh_from_db()
        self.c_deleted.refresh_from_db()
        self.c_other.refresh_from_db()

        self.assertEqual(self.c1.credit_limit, Decimal("5000.00"))
        self.assertEqual(self.c2.credit_limit, Decimal("5000.00"))
        self.assertEqual(self.c_deleted.credit_limit, Decimal("500.00"))
        self.assertEqual(self.c_other.credit_limit, Decimal("1500.00"))

    def test_wrong_pin_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            apply_credit_limit_to_all_customers(
                display_value="5000.00",
                pin="9999",
                performed_by=self.admin,
            )
        self.assertIn("Incorrect PIN", str(ctx.exception))
        self.c1.refresh_from_db()
        self.assertEqual(self.c1.credit_limit, Decimal("1000.00"))

    def test_user_without_pin_rejected(self):
        self.admin.pin = None
        self.admin.save()
        with self.assertRaises(ValidationError) as ctx:
            apply_credit_limit_to_all_customers(
                display_value="5000.00",
                pin="1234",
                performed_by=self.admin,
            )
        self.assertIn("No PIN is configured", str(ctx.exception))

    def test_negative_credit_limit_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            apply_credit_limit_to_all_customers(
                display_value="-500.00",
                pin="1234",
                performed_by=self.admin,
            )
        self.assertIn("Credit limit cannot be negative", str(ctx.exception))
