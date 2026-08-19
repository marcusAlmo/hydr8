"""Tests for the check-date endpoint's date-dependent credit data.

Verifies that when the remittance date is changed on the Add Remittance
form, the ``check-date`` endpoint returns credit payments, total credits,
and per-rider credited/repaid counts filtered for the selected date — not
just today's date.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import Customer
from apps.customers.services import record_customer_collection, record_customer_debt
from apps.remittance.selectors import (
    get_remittance_date_data,
    get_remittance_summary_for_date,
)
from apps.users.models import DriverCommission, Role, User


class CheckDateCreditDataTests(TestCase):
    """Tests that the check-date endpoint returns date-filtered credit data."""

    def setUp(self):
        cache.clear()
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            first_name="Ad",
            last_name="Min",
            role=self.admin_role,
        )
        self.rider = User.objects.create_user(
            username="rider1",
            password="securepassword123",
            first_name="Ri",
            last_name="Der",
            role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        DriverCommission.objects.create(
            driver=self.rider,
            product=self.product,
            rate_per_unit=Decimal("5.00"),
        )
        self.customer = Customer.objects.create(name="Test Store")
        self.today = timezone.localdate()
        self.yesterday = self.today - timedelta(days=1)

    def tearDown(self):
        cache.clear()

    # --- helpers ------------------------------------------------------------

    def _extend_credit(self, qty=5, care_of=None):
        return record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price="40.00",
            care_of_id=str(care_of.pk) if care_of else "",
            performed_by=self.admin,
        )

    def _collect_payment(self, credit_line, qty_paid=3, amount="120.00"):
        return record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.admin,
            returns=[],
            payments=[{
                "credit_line_id": str(credit_line.pk),
                "qty_paid": qty_paid,
                "amount": amount,
            }],
        )

    # --- selector tests -----------------------------------------------------

    def test_selector_returns_repayments_for_selected_date(self):
        """get_remittance_date_data returns repayments for the given date."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=3, amount="120.00")

        data = get_remittance_date_data(self.admin, self.today)
        self.assertEqual(len(data["repayments"]), 1)
        self.assertEqual(data["repayments"][0]["qty"], 3)

    def test_selector_returns_zero_repayments_for_date_with_none(self):
        """get_remittance_date_data returns empty list for a date with no payments."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=3, amount="120.00")

        data = get_remittance_date_data(self.admin, self.yesterday)
        self.assertEqual(data["repayments"], [])

    def test_selector_returns_total_credits_for_selected_date(self):
        """get_remittance_date_data returns total credits for the given date."""
        self._extend_credit(qty=5, care_of=self.rider)
        # total_credit_amount = 5 * 40 = 200
        data = get_remittance_date_data(self.admin, self.today)
        self.assertEqual(data["total_credits"], 200.0)

    def test_selector_returns_zero_credits_for_date_with_none(self):
        """get_remittance_date_data returns 0 credits for a date with no credit sales."""
        self._extend_credit(qty=5, care_of=self.rider)

        data = get_remittance_date_data(self.admin, self.yesterday)
        self.assertEqual(data["total_credits"], 0.0)

    def test_selector_returns_credit_repaid_counts_for_selected_date(self):
        """get_remittance_date_data returns credited/repaid counts per rider/product."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=2, amount="80.00")

        data = get_remittance_date_data(self.admin, self.today)
        counts = data["credit_repaid_counts"]
        rider_key = str(self.rider.pk)
        product_key = str(self.product.pk)
        self.assertIn(rider_key, counts)
        self.assertIn(product_key, counts[rider_key])
        self.assertEqual(counts[rider_key][product_key]["credited"], 5)
        self.assertEqual(counts[rider_key][product_key]["repaid"], 2)

    def test_selector_returns_empty_counts_for_date_with_none(self):
        """get_remittance_date_data returns empty counts dict for a date with no data."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=2, amount="80.00")

        data = get_remittance_date_data(self.admin, self.yesterday)
        self.assertEqual(data["credit_repaid_counts"], {})

    # --- view tests ---------------------------------------------------------

    def test_check_date_endpoint_returns_repayments(self):
        """The check-date JSON response includes repayments for the date."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=3, amount="120.00")

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["repayments"]), 1)
        self.assertEqual(data["repayments"][0]["qty"], 3)

    def test_check_date_endpoint_returns_empty_repayments_for_other_date(self):
        """The check-date endpoint returns no repayments for a date with none."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=3, amount="120.00")

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.yesterday.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["repayments"], [])

    def test_check_date_endpoint_returns_total_credits(self):
        """The check-date JSON response includes total_credits for the date."""
        self._extend_credit(qty=5, care_of=self.rider)

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_credits"], 200.0)

    def test_check_date_endpoint_returns_credit_repaid_counts(self):
        """The check-date JSON response includes credit_repaid_counts."""
        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=2, amount="80.00")

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        counts = data["credit_repaid_counts"]
        rider_key = str(self.rider.pk)
        product_key = str(self.product.pk)
        self.assertIn(rider_key, counts)
        self.assertEqual(counts[rider_key][product_key]["credited"], 5)
        self.assertEqual(counts[rider_key][product_key]["repaid"], 2)

    def test_check_date_endpoint_no_credit_data_for_finalized_date(self):
        """When a date has a FINALIZED remittance, credit data is empty
        (the date is locked and the form can't use it)."""
        from apps.remittance.services import create_remittance

        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=3, amount="120.00")

        # Finalize a remittance for today — this locks the date and links
        # the payment.
        create_remittance(
            performed_by=self.admin,
            riders_data=[{
                "id": str(self.rider.pk),
                "commission_override": "",
                "product_lines": [
                    {"product_key": str(self.product.pk), "sold": 2,
                     "credited": 0, "borrowed": 0},
                ],
            }],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
            finalize=True,
        )

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["status"], "FINALIZED")
        self.assertEqual(data["repayments"], [])
        self.assertEqual(data["total_credits"], 0)
        self.assertEqual(data["credit_repaid_counts"], {})

    def test_check_date_endpoint_returns_credit_data_for_draft_date(self):
        """When a date has a DRAFT remittance, credit data is still returned
        (the user can continue editing)."""
        from apps.remittance.services import save_remittance_draft

        cl = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(cl, qty_paid=2, amount="80.00")

        save_remittance_draft(
            performed_by=self.admin,
            riders_data=[{
                "id": str(self.rider.pk),
                "commission_override": "",
                "product_lines": [
                    {"product_key": str(self.product.pk), "sold": 1,
                     "credited": 0, "borrowed": 0},
                ],
            }],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
        )

        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["status"], "DRAFT")
        # Repayments should still be returned for a draft date.
        self.assertEqual(len(data["repayments"]), 1)
        self.assertEqual(data["total_credits"], 200.0)


class CheckDateSummaryTests(TestCase):
    """Tests for the read-only ``summary`` payload returned by the
    check-date endpoint when a draft or finalized remittance exists for
    the selected date."""

    def setUp(self):
        cache.clear()
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")

        self.admin = User.objects.create_user(
            username="admin_sum",
            password="securepassword123",
            first_name="Ad",
            last_name="Min",
            role=self.admin_role,
        )
        self.rider = User.objects.create_user(
            username="rider_sum",
            password="securepassword123",
            first_name="Ri",
            last_name="Der",
            role=self.driver_role,
        )
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        DriverCommission.objects.create(
            driver=self.rider,
            product=self.product,
            rate_per_unit=Decimal("5.00"),
        )
        self.today = timezone.localdate()

    def tearDown(self):
        cache.clear()

    def _rider_payload(self, sold=2):
        return [{
            "id": str(self.rider.pk),
            "commission_override": "",
            "product_lines": [
                {"product_key": str(self.product.pk), "sold": sold,
                 "credited": 0, "borrowed": 0},
            ],
        }]

    # --- selector -----------------------------------------------------------

    def test_selector_returns_none_when_no_remittance(self):
        self.assertIsNone(
            get_remittance_summary_for_date(self.admin, self.today)
        )

    def test_selector_returns_summary_for_draft(self):
        from apps.remittance.services import save_remittance_draft
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=self._rider_payload(sold=3),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
        )
        summary = get_remittance_summary_for_date(self.admin, self.today)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["status"], "DRAFT")
        self.assertEqual(summary["date"], self.today.isoformat())
        self.assertEqual(summary["created_by"], self.admin.full_name)
        self.assertEqual(len(summary["riders"]), 1)
        self.assertEqual(summary["riders"][0]["name"], self.rider.full_name)
        self.assertEqual(len(summary["riders"][0]["product_lines"]), 1)
        self.assertEqual(summary["riders"][0]["product_lines"][0]["qty_sold"], 3)
        # Drafts carry a form-facing draft_state for the "Load draft" button.
        self.assertIsNotNone(summary["draft_state"])
        self.assertIn("rider_sold", summary["draft_state"])

    def test_selector_returns_summary_for_finalized_without_draft_state(self):
        from apps.remittance.services import create_remittance
        create_remittance(
            performed_by=self.admin,
            riders_data=self._rider_payload(sold=2),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
            finalize=True,
        )
        summary = get_remittance_summary_for_date(self.admin, self.today)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["status"], "FINALIZED")
        self.assertEqual(summary["finalized_by"], self.admin.full_name)
        self.assertIsNotNone(summary["finalized_at"])
        # Finalized records are locked — no draft_state (that key is for
        # the editable "Load draft" flow which only applies to drafts).
        self.assertIsNone(summary["draft_state"])
        # Finalized records carry a form_state so the Add Remittance page
        # can populate the read-only finalized view in the form fields.
        self.assertIsNotNone(summary["form_state"])
        self.assertIn("rider_sold", summary["form_state"])
        rider_key = str(self.rider.pk)
        product_key = str(self.product.pk)
        self.assertEqual(summary["form_state"]["rider_sold"][rider_key][product_key], 2)
        # Totals are populated from the finalized record.
        self.assertGreater(summary["totals"]["total_sales"], 0)

    # --- endpoint -----------------------------------------------------------

    def test_check_date_endpoint_includes_summary_for_draft(self):
        from apps.remittance.services import save_remittance_draft
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=self._rider_payload(sold=1),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["status"], "DRAFT")
        self.assertIsNotNone(data["summary"])
        self.assertEqual(data["summary"]["status"], "DRAFT")
        self.assertIsNotNone(data["summary"]["draft_state"])

    def test_check_date_endpoint_includes_summary_for_finalized(self):
        from apps.remittance.services import create_remittance
        create_remittance(
            performed_by=self.admin,
            riders_data=self._rider_payload(sold=2),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=self.today,
            finalize=True,
        )
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["status"], "FINALIZED")
        self.assertIsNotNone(data["summary"])
        self.assertEqual(data["summary"]["status"], "FINALIZED")
        self.assertIsNone(data["summary"]["draft_state"])
        # Finalized records expose a form_state for the read-only view.
        self.assertIsNotNone(data["summary"]["form_state"])
        self.assertIn("rider_sold", data["summary"]["form_state"])

    def test_check_date_endpoint_summary_none_when_no_remittance(self):
        self.client.force_login(self.admin)
        resp = self.client.get(
            reverse("remittance:check_date"),
            {"date": self.today.isoformat()},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["exists"])
        self.assertIsNone(data["summary"])

