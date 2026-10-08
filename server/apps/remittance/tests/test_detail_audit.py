"""Tests for the remittance detail audit view and HTMX tab endpoints."""
import html
import json
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Product
from apps.customers.models import CreditLine, CreditPayment, Customer
from apps.remittance.models import (
    Expense,
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

    def test_total_credits_shows_date_credits_even_if_already_repaid_and_unlinked(self):
        """Total credits in remittance detail reflects credit loans based on credit date,
        even if the remittance DB row had 0.00, credit_line.remittance is None, and
        loans are already fully repaid."""
        from apps.remittance.selectors import get_credits_recorded_for_remittance

        target_date = date(2026, 8, 30)
        # Remittance with 0 total_credit_sales in the DB
        rem = Remittance.objects.create(
            date=target_date,
            created_by=self.admin,
            company=self.company,
            status=Remittance.StatusChoices.FINALIZED,
            total_sales=Decimal("500.00"),
            total_credit_sales=Decimal("0.00"),
            total_repayments_received=Decimal("0.00"),
            net_remittance=Decimal("500.00"),
        )

        # Credit line on that date, unlinked (remittance=None), but already fully repaid
        cl = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            remittance=None,
            care_of=self.driver,
            company=self.company,
            qty_credited=4,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("140.00"),
            qty_remaining=0,  # fully repaid!
            transaction_date=target_date,
        )

        # Payment that fully paid the credit line
        CreditPayment.objects.create(
            credit_line=cl,
            remittance=None,
            containers_paid=4,
            amount=Decimal("140.00"),
            paid_at=target_date,
            recorded_by=self.admin,
            company=self.company,
        )

        # 1. Detail selector must dynamically resolve total credits from the credit date
        detail = get_remittance_detail(self.admin, rem.id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["total_credit_sales"], "₱140.00")
        self.assertEqual(detail["total_repayments_received"], "₱140.00")

        # 2. Credits recorded selector must return the credit line with Repaid status
        credits_data = get_credits_recorded_for_remittance(self.admin, rem.id)
        self.assertEqual(credits_data["total"], 1)
        self.assertEqual(credits_data["credits"][0]["customer_name"], "Audit Customer")
        self.assertEqual(credits_data["credits"][0]["amount"], "₱140.00")
        self.assertEqual(credits_data["credits"][0]["status"], "Repaid")
        self.assertTrue(credits_data["credits"][0]["is_repaid"])

        # 3. View render must display ₱140.00 in the Deductions KPI card
        self.client.force_login(self.admin)
        response = self.client.get(reverse("remittance:detail", args=[rem.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "₱140.00")
        self.assertEqual(response.context["credits_count"], 1)

    def test_create_remittance_incorporates_unlinked_date_credits_into_total_credit_sales(self):
        """create_remittance calculates total_credit_sales including existing credit lines
        on that transaction date, even when rider product lines have 0 credited."""
        from apps.remittance.services import create_remittance

        tx_date = date(2026, 9, 1)
        unlinked_credit = CreditLine.objects.create(
            customer=self.customer,
            product=self.product,
            care_of=self.driver,
            company=self.company,
            qty_credited=2,
            unit_price_snapshot=Decimal("35.00"),
            total_credit_amount=Decimal("70.00"),
            qty_remaining=0,  # already paid
            transaction_date=tx_date,
        )
        self.assertIsNone(unlinked_credit.remittance)

        rem = create_remittance(
            performed_by=self.admin,
            remittance_date=tx_date,
            riders_data=[],  # no credited lines entered manually
            expenses_data=[],
            staff_data=[],
            manual_offering=Decimal("0.00"),
            tithe_rate=Decimal("0.10"),
            finalize=False,
        )

        self.assertEqual(rem.total_credit_sales, Decimal("70.00"))
        unlinked_credit.refresh_from_db()
        self.assertEqual(unlinked_credit.remittance, rem)

    def test_expenses_audit_breakdown_per_rider_staff_and_station(self):
        """get_remittance_detail breaks down expenses across riders, staff, and general station operations."""
        audit_date = date(2026, 9, 15)
        rem = Remittance.objects.create(
            date=audit_date,
            created_by=self.admin,
            company=self.company,
            status=Remittance.StatusChoices.DRAFT,
            total_sales=Decimal("500.00"),
            total_expenses=Decimal("870.00"),
            net_remittance=Decimal("500.00"),
        )
        rem_rider = RemittanceRider.objects.create(
            remittance=rem,
            rider=self.driver,
            company=self.company,
            subtotal_payable=Decimal("500.00"),
            subtotal_commission=Decimal("50.00"),
            remitted=Decimal("500.00"),
        )
        rem_staff = RemittanceStaff.objects.create(
            remittance=rem,
            staff=self.staff,
            company=self.company,
            daily_rate_snapshot=Decimal("350.00"),
            total_deductions=Decimal("0.00"),
            net_pay=Decimal("350.00"),
        )

        # 1. Add rider expense
        Expense.objects.create(
            remittance=rem,
            remittance_rider=rem_rider,
            description="Tire Patch",
            amount=Decimal("120.00"),
            company=self.company,
            recorded_by=self.admin,
        )

        # 2. Add staff operational expense
        Expense.objects.create(
            remittance=rem,
            remittance_staff=rem_staff,
            description="Cleaning Supplies",
            amount=Decimal("250.00"),
            company=self.company,
            recorded_by=self.admin,
        )

        # 3. Add general station expense (no rider, no staff)
        Expense.objects.create(
            remittance=rem,
            remittance_rider=None,
            remittance_staff=None,
            description="Electricity Bill",
            amount=Decimal("500.00"),
            company=self.company,
            recorded_by=self.admin,
        )

        # Finalize remittance after child records exist
        rem.status = Remittance.StatusChoices.FINALIZED
        rem.finalized_by = self.admin
        rem.save(update_fields=["status", "finalized_by", "updated_at"])

        detail = get_remittance_detail(self.admin, rem.id)
        self.assertIsNotNone(detail)

        # Check expenses_breakdown rollup
        breakdown = detail.get("expenses_breakdown")
        self.assertIsNotNone(breakdown)
        self.assertEqual(breakdown["rider_total"], "₱120.00")
        self.assertEqual(breakdown["rider_total_raw"], 120.0)
        self.assertEqual(breakdown["staff_total"], "₱250.00")
        self.assertEqual(breakdown["staff_total_raw"], 250.0)
        self.assertEqual(breakdown["general_total"], "₱500.00")
        self.assertEqual(breakdown["general_total_raw"], 500.0)
        self.assertEqual(breakdown["grand_total"], "₱870.00")
        self.assertEqual(breakdown["grand_total_raw"], 870.0)
        self.assertEqual(len(breakdown["general_items"]), 1)
        self.assertEqual(breakdown["general_items"][0]["description"], "Electricity Bill")
        self.assertEqual(breakdown["general_items"][0]["amount"], "₱500.00")

        # Check riders_detail
        rider_entry = detail["riders"][0]
        self.assertEqual(rider_entry["total_expenses"], "₱120.00")
        self.assertEqual(rider_entry["total_expenses_raw"], 120.0)
        self.assertEqual(len(rider_entry["expenses"]), 1)
        self.assertEqual(rider_entry["expenses"][0]["description"], "Tire Patch")
        self.assertEqual(rider_entry["expenses"][0]["amount"], "₱120.00")

        # Check staff_detail
        staff_entry = next(s for s in detail["staff"] if s["id"] == str(self.staff.id))
        self.assertEqual(staff_entry["total_expenses"], "₱250.00")
        self.assertEqual(staff_entry["total_expenses_raw"], 250.0)
        self.assertEqual(len(staff_entry["expenses"]), 1)
        self.assertEqual(staff_entry["expenses"][0]["description"], "Cleaning Supplies")
        self.assertEqual(staff_entry["expenses"][0]["amount"], "₱250.00")

        # View render check
        self.client.force_login(self.admin)
        url = reverse("remittance:detail", args=[rem.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expenses Audit Breakdown:")
        self.assertContains(response, "Cleaning Supplies")
        self.assertContains(response, "Electricity Bill")
        self.assertContains(response, "Tire Patch")

    def test_create_and_draft_remittance_persists_staff_expenses_and_round_trips(self):
        """create_remittance and save_remittance_draft correctly persist staff expenses and hydrate draft state."""
        from apps.remittance.selectors import _load_draft_state
        from apps.remittance.services import create_remittance, save_remittance_draft

        test_date = date(2026, 9, 10)
        staff_payload = [{
            "id": self.staff.id,
            "salary_override": "400.00",
            "deductions": [{"description": "Uniform", "amount": "50.00"}],
            "expenses": [
                {"description": "Soap & Bleach", "amount": "85.00"},
                {"description": "Receipt Paper", "amount": "45.00"},
            ],
        }]

        # 1. Test create_remittance
        rem = create_remittance(
            performed_by=self.admin,
            remittance_date=test_date,
            riders_data=[],
            expenses_data=[{"description": "Mineral Salt", "amount": "300.00"}],
            staff_data=staff_payload,
            manual_offering=Decimal("0.00"),
            tithe_rate=Decimal("0.10"),
            finalize=False,
        )

        # Total expenses should include general (300) + staff (85 + 45 = 130) = 430.00
        self.assertEqual(rem.total_expenses, Decimal("430.00"))

        staff_expenses = Expense.objects.filter(remittance_staff__staff=self.staff)
        self.assertEqual(staff_expenses.count(), 2)
        descriptions = set(staff_expenses.values_list("description", flat=True))
        self.assertEqual(descriptions, {"Soap & Bleach", "Receipt Paper"})

        # 2. Test round trip through _load_draft_state
        state = _load_draft_state(self.admin, test_date)
        self.assertIsNotNone(state)
        staff_draft = state["staff_data"].get(str(self.staff.id))
        self.assertIsNotNone(staff_draft)
        self.assertEqual(len(staff_draft["expenses"]), 2)
        self.assertEqual(staff_draft["expenses"][0]["description"], "Soap & Bleach")
        self.assertEqual(staff_draft["expenses"][0]["amount"], "85.00")

        # 3. Test save_remittance_draft updating the draft
        updated_staff_payload = [{
            "id": self.staff.id,
            "salary_override": "400.00",
            "deductions": [],
            "expenses": [
                {"description": "Soap & Bleach", "amount": "100.00"},
            ],
        }]
        updated_rem = save_remittance_draft(
            performed_by=self.admin,
            remittance_date=test_date,
            riders_data=[],
            expenses_data=[{"description": "Mineral Salt", "amount": "300.00"}],
            staff_data=updated_staff_payload,
            manual_offering=Decimal("0.00"),
            tithe_rate=Decimal("0.10"),
        )
        self.assertEqual(updated_rem.total_expenses, Decimal("400.00"))
        updated_state = _load_draft_state(self.admin, test_date)
        self.assertEqual(len(updated_state["staff_data"][str(self.staff.id)]["expenses"]), 1)
        self.assertEqual(updated_state["staff_data"][str(self.staff.id)]["expenses"][0]["amount"], "100.00")



