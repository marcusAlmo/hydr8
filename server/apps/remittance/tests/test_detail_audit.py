"""Tests for the remittance detail audit view and HTMX tab endpoints."""
from datetime import date
from decimal import Decimal
import html
import json

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Product
from apps.customers.models import Customer, CreditLine, CreditPayment
from apps.remittance.models import (
    Remittance,
    RemittanceRider,
    RemittanceRiderProductLine,
    RemittanceStaff,
)
from apps.remittance.selectors import get_remittance_detail
from apps.users.models import Role, User


def _make_user(username: str, role_name: str, password: str = "securepassword123") -> User:
    role, _ = Role.objects.get_or_create(name=role_name, company=None)
    user = User.objects.create_user(
        username=username,
        password=password,
        first_name="Test",
        last_name=username.capitalize(),
    )
    user.role = role
    user.save()
    return user


class RemittanceDetailAuditViewTests(TestCase):
    """Tests for remittance_detail_view, detail_repayments, and detail_credits."""

    def setUp(self):
        cache.clear()
        from apps.settings.models import Company
        company = Company.objects.filter(deleted_at__isnull=True).first()
        if not company:
            company = Company.objects.create(name="Test Refill Station")

        self.company = company
        self.admin = _make_user("admin_audit", "Admin")
        self.admin.company = company
        self.admin.save(update_fields=["company"])

        self.staff = _make_user("staff_audit", "Staff")
        self.staff.company = company
        self.staff.save(update_fields=["company"])

        self.driver = _make_user("driver_audit", "Driver")
        self.driver.company = company
        self.driver.save(update_fields=["company"])

        self.customer = Customer.objects.create(
            name="Audit Customer",
            contact_number="09123456789",
            company=self.company,
        )

        self.product = Product.objects.create(
            name="Purified Water",
            price=Decimal("35.00"),
            company=self.company,
        )

        self.remittance = Remittance.objects.create(
            date=date(2026, 8, 15),
            created_by=self.admin,
            company=self.company,
            status=Remittance.StatusChoices.DRAFT,
            total_sales=Decimal("350.00"),
            total_credit_sales=Decimal("70.00"),
            total_repayments_received=Decimal("105.00"),
            net_remittance=Decimal("350.00"),
        )

        self.rem_rider = RemittanceRider.objects.create(
            remittance=self.remittance,
            rider=self.driver,
            company=self.company,
            subtotal_payable=Decimal("350.00"),
            subtotal_commission=Decimal("50.00"),
            remitted=Decimal("350.00"),
        )

        self.product_line = RemittanceRiderProductLine.objects.create(
            remittance_rider=self.rem_rider,
            product=self.product,
            qty_sold=10,
            qty_credited=2,
            unit_price_snapshot=Decimal("35.00"),
            commission_rate_snapshot=Decimal("5.00"),
            subtotal_payable=Decimal("350.00"),
            subtotal_credit=Decimal("70.00"),
            subtotal_commission=Decimal("50.00"),
        )

        self.rem_staff = RemittanceStaff.objects.create(
            remittance=self.remittance,
            staff=self.staff,
            company=self.company,
            daily_rate_snapshot=Decimal("350.00"),
            total_deductions=Decimal("0.00"),
            net_pay=Decimal("350.00"),
        )

        # Credit line issued by driver
        self.credit_line = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            remittance=self.remittance,
            care_of=self.driver,
            company=self.company,
            qty_credited=2,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("70.00"),
            qty_remaining=0,
            transaction_date=date(2026, 8, 15),
        )

        # Repayment collected by driver
        self.credit_payment = CreditPayment.objects.create(
            credit_line=self.credit_line,
            remittance=self.remittance,
            containers_paid=3,
            amount=Decimal("105.00"),
            paid_at=date(2026, 8, 15),
            recorded_by=self.admin,
        )

        # Now finalize the remittance after child records exist
        self.remittance.status = Remittance.StatusChoices.FINALIZED
        self.remittance.finalized_by = self.admin
        self.remittance.save(update_fields=["status", "finalized_by", "updated_at"])

    def tearDown(self):
        cache.clear()

    def test_detail_view_renders_for_admin(self):
        """Admin can access the remittance detail page."""
        self.client.force_login(self.admin)
        url = reverse("remittance:detail", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "remittance/remittance_detail.html")
        self.assertTemplateUsed(response, "remittance/partials/detail_riders_tab.html")
        self.assertTemplateUsed(response, "remittance/partials/detail_staff_tab.html")

    def test_detail_view_contains_per_rider_audit_breakdown(self):
        """Remittance detail context and alpine_seed contain per-rider audit data."""
        self.client.force_login(self.admin)
        url = reverse("remittance:detail", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        seed = json.loads(html.unescape(response.context["alpine_seed"]))
        self.assertEqual(len(seed["riders"]), 1)
        rider = seed["riders"][0]

        # Verify sold, credited, and repaid counts
        self.assertEqual(rider["total_sold"], 10)
        self.assertEqual(rider["total_credited"], 2)
        self.assertEqual(rider["total_repaid"], 3)

        # Verify product line counts
        line = rider["product_lines"][0]
        self.assertEqual(line["qty_sold"], 10)
        self.assertEqual(line["qty_credited"], 2)
        self.assertEqual(line["qty_repaid"], 3)

        # Verify per-rider repayments and credits tables
        self.assertEqual(len(rider["repayments"]), 1)
        self.assertEqual(rider["repayments"][0]["payer"], "Audit Customer")
        self.assertEqual(rider["repayments"][0]["qty"], 3)

        self.assertEqual(len(rider["credits"]), 1)
        self.assertEqual(rider["credits"][0]["customer_name"], "Audit Customer")
        self.assertEqual(rider["credits"][0]["qty"], 2)

    def test_detail_view_forbidden_for_staff(self):
        """Staff users receive HTTP 403 when accessing remittance detail."""
        self.client.force_login(self.staff)
        url = reverse("remittance:detail", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_detail_view_redirects_unauthenticated(self):
        """Unauthenticated requests redirect to login."""
        url = reverse("remittance:detail", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_repayments_htmx_endpoint(self):
        """Admin can fetch paginated repayments partial."""
        self.client.force_login(self.admin)
        url = reverse("remittance:detail_repayments", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "remittance/partials/credit_repayments_table.html")
        self.assertContains(response, "Audit Customer")

    def test_credits_htmx_endpoint(self):
        """Admin can fetch paginated credits partial."""
        self.client.force_login(self.admin)
        url = reverse("remittance:detail_credits", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "remittance/partials/credits_recorded_table.html")
        self.assertContains(response, "Audit Customer")

    def test_repayments_htmx_forbidden_for_staff(self):
        """Staff users receive HTTP 403 on repayments endpoint."""
        self.client.force_login(self.staff)
        url = reverse("remittance:detail_repayments", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_credits_htmx_forbidden_for_staff(self):
        """Staff users receive HTTP 403 on credits endpoint."""
        self.client.force_login(self.staff)
        url = reverse("remittance:detail_credits", args=[self.remittance.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_credit_line_linked_on_create_remittance(self):
        """CreditLine created on remittance date gets linked to remittance on creation."""
        from apps.remittance.services import create_remittance
        unlinked_credit = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            care_of=self.driver,
            company=self.admin.company,
            qty_credited=1,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("35.00"),
            qty_remaining=1,
            transaction_date=date(2026, 8, 20),
        )
        self.assertIsNone(unlinked_credit.remittance)

        rem = create_remittance(
            performed_by=self.admin,
            remittance_date=date(2026, 8, 20),
            riders_data=[],
            expenses_data=[],
            staff_data=[],
            manual_offering=Decimal("0.00"),
            tithe_rate=Decimal("0.10"),
            finalize=False,
        )

        unlinked_credit.refresh_from_db()
        self.assertEqual(unlinked_credit.remittance, rem)

    def test_unattributed_and_offduty_activity_included_in_staff_detail(self):
        """Unattributed (care_of=None) and off-duty staff activity appear in staff audit detail."""
        # Create an off-duty user who is not in RemittanceStaff
        off_duty_user = _make_user("offduty_manager", "Staff")
        off_duty_user.company = self.company
        off_duty_user.save(update_fields=["company"])

        # Create a new draft remittance for testing
        rem = Remittance.objects.create(
            date=date(2026, 8, 25),
            created_by=self.admin,
            company=self.company,
            status=Remittance.StatusChoices.DRAFT,
            total_sales=Decimal("0.00"),
            total_credit_sales=Decimal("100.00"),
            total_repayments_received=Decimal("50.00"),
            net_remittance=Decimal("50.00"),
        )

        # 1. Storefront unattributed credit (care_of=None)
        cl_storefront = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            remittance=rem,
            care_of=None,
            company=self.company,
            qty_credited=2,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("70.00"),
            qty_remaining=2,
            transaction_date=date(2026, 8, 25),
        )
        # Storefront repayment (care_of=None)
        CreditPayment.objects.create(
            credit_line=cl_storefront,
            remittance=rem,
            containers_paid=1,
            amount=Decimal("35.00"),
            paid_at=date(2026, 8, 25),
            recorded_by=self.admin,
        )

        # 2. Off-duty staff credit
        CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            remittance=rem,
            care_of=off_duty_user,
            company=self.company,
            qty_credited=1,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("35.00"),
            qty_remaining=1,
            transaction_date=date(2026, 8, 25),
        )

        detail = get_remittance_detail(self.admin, rem.id)
        self.assertIsNotNone(detail)

        staff_ids = [s["id"] for s in detail["staff"]]
        self.assertIn("station", staff_ids)
        self.assertIn(str(off_duty_user.id), staff_ids)

        station_entry = next(s for s in detail["staff"] if s["id"] == "station")
        self.assertEqual(station_entry["name"], "Station (Storefront / Walk-in)")
        self.assertEqual(len(station_entry["credits"]), 1)
        self.assertEqual(len(station_entry["repayments"]), 1)

        off_duty_entry = next(s for s in detail["staff"] if s["id"] == str(off_duty_user.id))
        self.assertEqual(len(off_duty_entry["credits"]), 1)

