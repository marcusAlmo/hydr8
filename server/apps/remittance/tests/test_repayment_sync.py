"""Self-contained tests for the credit repayment → remittance sync.

Verifies that CreditPayments collected on the remittance date (attributed
to an active rider via ``CreditLine.care_of``) are:
  1. Populated in the selector seed for the Add Remittance form.
  2. Linked to the new Remittance on create / draft save.
  3. Counted in ``total_repayments_received`` and ``total_commission``.
  4. Unlinked when a draft is deleted or replaced.
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.customers.models import CreditLine, CreditPayment, Customer
from apps.customers.services import record_customer_collection, record_customer_debt
from apps.remittance.models import Remittance, RemittanceRider
from apps.remittance.selectors import _repayments_for_date, list_riders_for_remittance
from apps.remittance.services import (
    create_remittance,
    delete_draft_remittance,
    save_remittance_draft,
)
from apps.users.models import DriverCommission, Role, User


class RepaymentSyncTests(TestCase):
    """End-to-end repayment sync: collect → remittance create → verify."""

    def setUp(self):
        cache.clear()
        self.driver_role, _ = Role.objects.get_or_create(name="Driver")
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")

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

    def tearDown(self):
        cache.clear()

    # --- helpers ------------------------------------------------------------

    def _extend_credit(self, qty=5, care_of=None):
        """Extends credit to the customer, attributed to ``care_of``."""
        return record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price="40.00",
            care_of_id=str(care_of.pk) if care_of else "",
            performed_by=self.admin,
        )

    def _collect_payment(self, qty_paid=3, amount="120.00"):
        """Records a credit payment for the customer."""
        return record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.admin,
            returns=[],
            payments=[{
                "credit_line_id": str(self.credit_line.pk),
                "qty_paid": qty_paid,
                "amount": amount,
            }],
        )

    def _collect_payment2(self, qty_paid=3, amount="120.00"):
        """Records a credit payment for the second credit line."""
        return record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.admin,
            returns=[],
            payments=[{
                "credit_line_id": str(self.credit_line2.pk),
                "qty_paid": qty_paid,
                "amount": amount,
            }],
        )

    def _riders_data(self, remitted="80"):
        return [{
            "id": str(self.rider.pk),
            "commission_override": "",
            "remitted": remitted,
            "product_lines": [
                {"product_key": str(self.product.pk), "sold": 2, "credited": 0, "borrowed": 0},
            ],
        }]

    # --- selector tests -----------------------------------------------------

    def test_selector_populates_repayments_for_rider(self):
        """CreditPayments collected today appear in the flat repayments list."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=3, amount="120.00")

        from apps.remittance.selectors import _active_riders_qs
        riders_qs = _active_riders_qs(self.admin)
        repayments = _repayments_for_date(self.admin, riders_qs, timezone.localdate())
        self.assertEqual(len(repayments), 1)
        rp = repayments[0]
        self.assertEqual(rp["payer"], "Test Store")
        self.assertEqual(rp["product_key"], str(self.product.pk))
        self.assertEqual(rp["qty"], 3)
        self.assertEqual(rp["amount"], 120.0)
        self.assertEqual(rp["care_of_id"], str(self.rider.pk))
        self.assertEqual(rp["care_of_name"], self.rider.full_name)
        self.assertTrue(rp["care_of_is_driver"])

    def test_selector_includes_staff_attributed_repayments(self):
        """Payments where care_of is staff (not a driver) are still included."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.admin)
        self._collect_payment(qty_paid=3, amount="120.00")

        from apps.remittance.selectors import _active_riders_qs
        riders_qs = _active_riders_qs(self.admin)
        repayments = _repayments_for_date(self.admin, riders_qs, timezone.localdate())
        self.assertEqual(len(repayments), 1)
        rp = repayments[0]
        self.assertEqual(rp["care_of_id"], str(self.admin.pk))
        self.assertFalse(rp["care_of_is_driver"])

    def test_selector_excludes_payments_already_linked_to_remittance(self):
        """Payments already linked to a remittance are not re-listed."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=3, amount="120.00")

        # Create a remittance — this links the payment.
        create_remittance(
            performed_by=self.admin,
            riders_data=self._riders_data(),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )

        # The payment is now linked; selector should show no repayments.
        from apps.remittance.selectors import _active_riders_qs
        riders_qs = _active_riders_qs(self.admin)
        repayments = _repayments_for_date(self.admin, riders_qs, timezone.localdate())
        self.assertEqual(repayments, [])

    # --- service tests ------------------------------------------------------

    def test_create_remittance_links_payments_and_sets_totals(self):
        """Creating a remittance links CreditPayments and sets totals."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=3, amount="120.00")

        rem = create_remittance(
            performed_by=self.admin,
            riders_data=self._riders_data(remitted="200"),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()

        # total_sales = 2 sold * 40 = 80
        self.assertEqual(rem.total_sales, Decimal("80.00"))
        # total_repayments_received = 120
        self.assertEqual(rem.total_repayments_received, Decimal("120.00"))
        # commission = 2 sold * 5 (line) + 3 repaid * 5 (repayment) = 10 + 15 = 25
        self.assertEqual(rem.total_commission, Decimal("25.00"))
        # net = total_remitted + other_sales - total_commission - total_salary
        #     = 200 + 0 - 25 - 0 = 175
        self.assertEqual(rem.net_profit, Decimal("175.00"))
        # tithes = 175 * 0.10 = 17.50
        self.assertEqual(rem.tithe_amount, Decimal("17.50"))

        # The CreditPayment is now linked.
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.remittance_id, rem.id)

    def test_create_remittance_with_rider_not_in_payload(self):
        """A rider with repayments but no sales in the payload still gets
        a RemittanceRider row and their repayment commission is counted."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=2, amount="80.00")

        # Payload with empty product lines for the rider.
        riders_data = [{
            "id": str(self.rider.pk),
            "commission_override": "",
            "remitted": "80",
            "product_lines": [],
        }]
        rem = create_remittance(
            performed_by=self.admin,
            riders_data=riders_data,
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()

        self.assertEqual(rem.total_sales, Decimal("0.00"))
        self.assertEqual(rem.total_repayments_received, Decimal("80.00"))
        # commission = 2 repaid * 5 = 10
        self.assertEqual(rem.total_commission, Decimal("10.00"))
        # net = total_remitted + other_sales - total_commission - total_salary
        #     = 80 + 0 - 10 - 0 = 70
        self.assertEqual(rem.net_profit, Decimal("70.00"))

        # A RemittanceRider row exists for the rider.
        self.assertTrue(
            RemittanceRider.objects.filter(remittance=rem, rider=self.rider).exists()
        )

    def test_draft_save_then_delete_unlinks_payments(self):
        """Saving a draft links payments; deleting the draft unlinks them."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=3, amount="120.00")

        rem = save_remittance_draft(
            performed_by=self.admin,
            riders_data=self._riders_data(),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
        )
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.remittance_id, rem.id)

        # Delete the draft — payment should be unlinked.
        delete_draft_remittance(
            performed_by=self.admin,
            remittance_date=timezone.localdate(),
        )
        payment.refresh_from_db()
        self.assertIsNone(payment.remittance)

    def test_draft_replace_unlinks_old_payments(self):
        """Replacing a draft (upsert) unlinks payments from the old draft."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=3, amount="120.00")

        rem1 = save_remittance_draft(
            performed_by=self.admin,
            riders_data=self._riders_data(),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
        )
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.remittance_id, rem1.id)

        # Save again — old draft is deleted, new one created.
        rem2 = save_remittance_draft(
            performed_by=self.admin,
            riders_data=self._riders_data(),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
        )
        self.assertNotEqual(rem1.id, rem2.id)
        payment.refresh_from_db()
        # Payment should now be linked to the new draft.
        self.assertEqual(payment.remittance_id, rem2.id)

    def test_repayment_commission_uses_driver_commission_rate(self):
        """Repayment commission = qty_paid * DriverCommission.rate_per_unit."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=4, amount="160.00")

        riders_data = [{
            "id": str(self.rider.pk),
            "commission_override": "",
            "product_lines": [],
        }]
        rem = create_remittance(
            performed_by=self.admin,
            riders_data=riders_data,
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()
        # 4 repaid * 5.00 rate = 20.00
        self.assertEqual(rem.total_commission, Decimal("20.00"))

    def test_no_repayments_yields_zero_total(self):
        """With no CreditPayments, total_repayments_received is 0."""
        rem = create_remittance(
            performed_by=self.admin,
            riders_data=self._riders_data(),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()
        self.assertEqual(rem.total_repayments_received, Decimal("0.00"))
        # net = 80 + 0 - 0 - 10 = 70
        self.assertEqual(rem.net_profit, Decimal("70.00"))

    def test_staff_attributed_repayment_links_but_no_commission(self):
        """A repayment attributed to staff is linked and counted in
        total_repayments, but earns 0 commission (no RemittanceRider row
        for the staff member)."""
        self.credit_line = self._extend_credit(qty=5, care_of=self.admin)
        self._collect_payment(qty_paid=3, amount="120.00")

        rem = create_remittance(
            performed_by=self.admin,
            riders_data=self._riders_data(remitted="80"),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()

        # total_repayments includes the staff-attributed payment.
        self.assertEqual(rem.total_repayments_received, Decimal("120.00"))
        # Commission is only from the rider's sales line (2 sold * 5 = 10).
        # No repayment commission because care_of is staff.
        self.assertEqual(rem.total_commission, Decimal("10.00"))
        # net = total_remitted + other_sales - total_commission - total_salary
        #     = 80 + 0 - 10 - 0 = 70
        self.assertEqual(rem.net_profit, Decimal("70.00"))

        # The CreditPayment is linked to the remittance.
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.remittance_id, rem.id)

        # No RemittanceRider row was created for the staff member.
        self.assertFalse(
            RemittanceRider.objects.filter(remittance=rem, rider=self.admin).exists()
        )

    def test_mixed_rider_and_staff_repayments(self):
        """Both rider- and staff-attributed repayments are linked and
        counted; only the rider earns commission."""
        # Rider-attributed credit
        self.credit_line = self._extend_credit(qty=5, care_of=self.rider)
        self._collect_payment(qty_paid=2, amount="80.00")

        # Staff-attributed credit
        self.credit_line2 = self._extend_credit(qty=3, care_of=self.admin)
        self._collect_payment2(qty_paid=2, amount="80.00")

        rem = create_remittance(
            performed_by=self.admin,
            riders_data=self._riders_data(remitted="160"),
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=timezone.localdate(),
            finalize=True,
        )
        rem.refresh_from_db()

        # total_repayments = 80 + 80 = 160
        self.assertEqual(rem.total_repayments_received, Decimal("160.00"))
        # Commission = 2 sold * 5 (line) + 2 repaid * 5 (rider repayment) = 10 + 10 = 20
        # Staff repayment earns 0 commission.
        self.assertEqual(rem.total_commission, Decimal("20.00"))
        # net = total_remitted + other_sales - total_commission - total_salary
        #     = 160 + 0 - 20 - 0 = 140
        self.assertEqual(rem.net_profit, Decimal("140.00"))

        # Both payments are linked.
        self.assertEqual(
            CreditPayment.objects.filter(remittance=rem).count(), 2
        )
