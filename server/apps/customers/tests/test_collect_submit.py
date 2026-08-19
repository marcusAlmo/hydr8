"""Self-contained tests for the collect-submit flow.

These tests create their own customer / product / user fixtures (following
the ``test_care_of.py`` pattern) so they do not depend on seed data.

Covers:
  - Service layer: ``record_customer_collection``
  - View layer: ``POST /customers/<id>/collect/submit/``
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product
from apps.customers.models import (
    BorrowedContainer,
    CreditLine,
    CreditPayment,
    Customer,
)
from apps.customers.services import (
    record_customer_borrowed,
    record_customer_collection,
    record_customer_debt,
)
from apps.users.models import Role, User


def _make_staff_user(**kwargs) -> User:
    """Creates a test user with the canonical Staff back-office role."""
    staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)
    return User.objects.create_user(role=staff_role, **kwargs)


class RecordCollectionServiceTests(TestCase):
    """Service-layer behaviour for ``record_customer_collection``."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="collect_staff",
            password="securepassword123",
            first_name="Collect",
            last_name="Staff",
        )
        self.customer = Customer.objects.create(name="Collection Test Store")
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    # --- helpers ------------------------------------------------------------

    def _borrow(self, qty=3, key="round_8gal"):
        return record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key=key,
            qty_borrowed=qty,
            performed_by=self.staff,
        )

    def _credit(self, qty=5, price="40.00"):
        return record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price=price,
            performed_by=self.staff,
        )

    # --- container returns --------------------------------------------------

    def test_return_containers_increments_qty_returned(self):
        """Returning containers increments ``qty_returned`` on the borrowed row."""
        borrowed = self._borrow(qty=5)
        result = record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[{"borrowed_id": str(borrowed.pk), "qty": 3}],
            payments=[],
        )
        self.assertEqual(result["returns_recorded"], 3)
        borrowed.refresh_from_db()
        self.assertEqual(borrowed.qty_returned, 3)
        self.assertEqual(borrowed.qty_remaining, 2)

    def test_return_containers_decrements_customer_aggregate(self):
        """Returning containers decrements the aggregate counter on Customer."""
        borrowed = self._borrow(qty=5, key="round_8gal")
        record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[{"borrowed_id": str(borrowed.pk), "qty": 2}],
            payments=[],
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 3)

    def test_return_exceeding_outstanding_raises(self):
        """Returning more than outstanding raises ValidationError."""
        from django.core.exceptions import ValidationError

        borrowed = self._borrow(qty=3)
        with self.assertRaises(ValidationError):
            record_customer_collection(
                customer_id=f"HY-{self.customer.pk:04d}",
                performed_by=self.staff,
                returns=[{"borrowed_id": str(borrowed.pk), "qty": 4}],
                payments=[],
            )

    # --- credit payments ----------------------------------------------------

    def test_payment_creates_credit_payment_row(self):
        """A credit payment creates a CreditPayment with the correct fields."""
        line = self._credit(qty=5, price="40.00")
        result = record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 2,
                "amount": "80.00",
            }],
        )
        self.assertEqual(result["payments_recorded"], 2)
        self.assertEqual(result["total_collected"], Decimal("80.00"))
        payment = CreditPayment.objects.get(credit_line=line)
        self.assertEqual(payment.containers_paid, 2)
        self.assertEqual(payment.amount, Decimal("80.00"))
        self.assertIsNone(payment.remittance)
        self.assertEqual(payment.recorded_by_id, self.staff.pk)

    def test_payment_decrements_qty_remaining(self):
        """A payment decrements ``CreditLine.qty_remaining``."""
        line = self._credit(qty=5)
        record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 3,
                "amount": "120.00",
            }],
        )
        line.refresh_from_db()
        self.assertEqual(line.qty_remaining, 2)

    def test_payment_reduces_debt_balance(self):
        """A payment reduces ``Customer.debt_balance`` by the amount paid."""
        self._credit(qty=5, price="40.00")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("200.00"))
        line = CreditLine.objects.get(customer=self.customer)
        record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 2,
                "amount": "80.00",
            }],
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("120.00"))

    def test_payment_exceeding_qty_remaining_raises(self):
        """Paying more units than remaining raises ValidationError."""
        from django.core.exceptions import ValidationError

        line = self._credit(qty=3)
        with self.assertRaises(ValidationError):
            record_customer_collection(
                customer_id=f"HY-{self.customer.pk:04d}",
                performed_by=self.staff,
                returns=[],
                payments=[{
                    "credit_line_id": str(line.pk),
                    "qty_paid": 4,
                    "amount": "160.00",
                }],
            )

    def test_payment_with_zero_amount_auto_computes_from_unit_price(self):
        """When qty_paid > 0 but amount = 0, the amount is auto-computed
        from qty_paid x credit_line.unit_price_snapshot.

        This guards against the client-side auto-fill (Alpine @input)
        failing to populate the amount field, which would otherwise
        create a CreditPayment with containers_paid > 0 and amount = 0
        — decoupling "Total Repayments" from repaid unit counts on the
        remittance form.
        """
        line = self._credit(qty=5, price="40.00")
        result = record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 3,
                "amount": "0",
            }],
        )
        self.assertEqual(result["payments_recorded"], 3)
        self.assertEqual(result["total_collected"], Decimal("120.00"))
        payment = CreditPayment.objects.get(credit_line=line)
        self.assertEqual(payment.containers_paid, 3)
        self.assertEqual(payment.amount, Decimal("120.00"))

    def test_payment_with_zero_amount_and_zero_qty_is_skipped(self):
        """An all-zero payment entry is still skipped (no auto-compute)."""
        borrowed = self._borrow(qty=5)
        line = self._credit(qty=5, price="40.00")
        record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[{"borrowed_id": str(borrowed.pk), "qty": 1}],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 0,
                "amount": "0",
            }],
        )
        self.assertFalse(CreditPayment.objects.filter(credit_line=line).exists())

    # --- combined / edge cases ----------------------------------------------

    def test_combined_returns_and_payments(self):
        """Returns and payments can be recorded in a single call."""
        borrowed = self._borrow(qty=5)
        line = self._credit(qty=4, price="40.00")
        result = record_customer_collection(
            customer_id=f"HY-{self.customer.pk:04d}",
            performed_by=self.staff,
            returns=[{"borrowed_id": str(borrowed.pk), "qty": 2}],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 1,
                "amount": "40.00",
            }],
        )
        self.assertEqual(result["returns_recorded"], 2)
        self.assertEqual(result["payments_recorded"], 1)
        self.assertEqual(result["total_collected"], Decimal("40.00"))
        borrowed.refresh_from_db()
        self.assertEqual(borrowed.qty_returned, 2)
        line.refresh_from_db()
        self.assertEqual(line.qty_remaining, 3)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("120.00"))

    def test_empty_submission_raises(self):
        """Submitting all-zero values raises ValidationError."""
        from django.core.exceptions import ValidationError

        self._borrow(qty=3)
        self._credit(qty=3)
        with self.assertRaises(ValidationError):
            record_customer_collection(
                customer_id=f"HY-{self.customer.pk:04d}",
                performed_by=self.staff,
                returns=[{"borrowed_id": "1", "qty": 0}],
                payments=[{"credit_line_id": "1", "qty_paid": 0, "amount": "0"}],
            )

    def test_borrowed_container_belonging_to_other_customer_raises(self):
        """A borrowed container from a different customer is rejected."""
        from django.core.exceptions import ValidationError

        other = Customer.objects.create(name="Other Store")
        other_borrowed = BorrowedContainer.objects.create(
            customer=other,
            container_key="round_8gal",
            qty_borrowed=5,
            qty_returned=0,
        )
        with self.assertRaises(ValidationError):
            record_customer_collection(
                customer_id=f"HY-{self.customer.pk:04d}",
                performed_by=self.staff,
                returns=[{"borrowed_id": str(other_borrowed.pk), "qty": 1}],
                payments=[],
            )

    def test_unknown_customer_raises(self):
        """A non-existent customer ID raises ValidationError."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            record_customer_collection(
                customer_id="HY-9999",
                performed_by=self.staff,
                returns=[{"borrowed_id": "1", "qty": 1}],
                payments=[],
            )


class CollectSubmitViewTests(TestCase):
    """View-layer behaviour for POST /customers/<id>/collect/submit/."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="collect_view_staff",
            password="securepassword123",
            first_name="View",
            last_name="Staff",
        )
        self.customer = Customer.objects.create(name="View Collection Store")
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        # Set up borrowed containers and a credit line
        self.borrowed = record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=5,
            performed_by=self.staff,
        )
        self.credit_line = record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=4,
            unit_price="40.00",
            performed_by=self.staff,
        )
        cache.clear()
        self.client.force_login(self.staff)

    def tearDown(self):
        cache.clear()

    @property
    def _url(self):
        return f"/customers/HY-{self.customer.pk:04d}/collect/submit/"

    def test_submit_returns_success_for_valid_returns(self):
        """POST with a valid return quantity returns 200 and persists."""
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "3",
        })
        self.assertEqual(response.status_code, 200)
        trigger = response.headers.get("HX-Trigger", "")
        self.assertIn("showToast", trigger)
        self.assertIn("container(s) returned", trigger)
        self.borrowed.refresh_from_db()
        self.assertEqual(self.borrowed.qty_returned, 3)

    def test_submit_returns_success_for_valid_payment(self):
        """POST with a valid payment returns 200 and persists."""
        response = self.client.post(self._url, {
            f"qty_paid_CL-{self.credit_line.pk}": "2",
            f"amount_paid_CL-{self.credit_line.pk}": "80.00",
        })
        self.assertEqual(response.status_code, 200)
        trigger = response.headers.get("HX-Trigger", "")
        self.assertIn("showToast", trigger)
        self.assertIn("collected", trigger)
        self.credit_line.refresh_from_db()
        self.assertEqual(self.credit_line.qty_remaining, 2)
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.amount, Decimal("80.00"))

    def test_submit_sets_hx_trigger_refresh(self):
        """The response includes HX-Trigger to refresh the customer table.

        Replaced HX-Redirect with HX-Trigger for optimistic UI — the modal
        closes via the form_success script and the table re-fetches via
        the refreshCustomerTable event.
        """
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "1",
        })
        self.assertIn("refreshCustomerTable", response["HX-Trigger"])
        self.assertNotIn("HX-Redirect", response)

    def test_submit_returns_400_for_empty_submission(self):
        """POST with all-zero values returns 400."""
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "0",
            f"qty_paid_CL-{self.credit_line.pk}": "0",
            f"amount_paid_CL-{self.credit_line.pk}": "0.00",
        })
        self.assertEqual(response.status_code, 400)

    def test_submit_returns_400_for_excess_return(self):
        """POST returning more than outstanding returns 400."""
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "10",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "outstanding", status_code=400)

    def test_submit_returns_404_for_unknown_customer(self):
        """POST for a non-existent customer returns 404."""
        response = self.client.post("/customers/HY-NOPE/collect/submit/", {
            "returned_BC-1": "1",
        })
        self.assertEqual(response.status_code, 404)

    def test_submit_requires_login(self):
        """An anonymous request is redirected to login."""
        self.client.logout()
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response["Location"])

    def test_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get(self._url)
        self.assertEqual(response.status_code, 405)

    def test_submit_combined_returns_and_payments(self):
        """POST with both returns and payments persists both atomically."""
        response = self.client.post(self._url, {
            f"returned_BC-{self.borrowed.pk}": "2",
            f"qty_paid_CL-{self.credit_line.pk}": "1",
            f"amount_paid_CL-{self.credit_line.pk}": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        self.borrowed.refresh_from_db()
        self.assertEqual(self.borrowed.qty_returned, 2)
        self.credit_line.refresh_from_db()
        self.assertEqual(self.credit_line.qty_remaining, 3)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("120.00"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 3)

    def test_submit_auto_computes_amount_when_zero(self):
        """POST with qty_paid > 0 and amount = 0 auto-computes the amount
        server-side from qty_paid x unit_price_snapshot.

        Regression guard for the bug where a CreditPayment was persisted
        with containers_paid > 0 and amount = 0, decoupling "Total
        Repayments" (sum of amount) from the repaid unit counts (sum of
        containers_paid) on the remittance form.
        """
        response = self.client.post(self._url, {
            f"qty_paid_CL-{self.credit_line.pk}": "2",
            f"amount_paid_CL-{self.credit_line.pk}": "0.00",
        })
        self.assertEqual(response.status_code, 200)
        self.credit_line.refresh_from_db()
        self.assertEqual(self.credit_line.qty_remaining, 2)
        payment = CreditPayment.objects.get(credit_line=self.credit_line)
        self.assertEqual(payment.containers_paid, 2)
        self.assertEqual(payment.amount, Decimal("80.00"))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("80.00"))
