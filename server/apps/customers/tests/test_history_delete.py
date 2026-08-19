"""Tests for the admin-only ledger history delete services and views.

Covers:
  - ``delete_credit_line`` — cascades payments, recomputes debt balance
  - ``delete_credit_payment`` — restores qty_remaining + debt balance
  - ``delete_borrowed_container`` — recomputes aggregate borrowed counter
  - Admin-only enforcement (non-admin gets ValidationError / 403)
  - PIN verification (missing/incorrect PIN rejected)
  - Remittance PROTECT — payments linked to a remittance cannot be deleted
  - View layer: GET confirm form, POST submit, 403 for non-admins
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Product
from apps.customers.models import (
    BorrowedContainer,
    CreditLine,
    CreditPayment,
    Customer,
)
from apps.customers.services import (
    delete_borrowed_container,
    delete_credit_line,
    delete_credit_payment,
    record_customer_borrowed,
    record_customer_collection,
    record_customer_debt,
)
from apps.users.models import Role, User


def _display_id(customer: Customer) -> str:
    return f"HY-{customer.pk:04d}"


def _make_admin_user(username: str, password: str = "securepassword123") -> User:
    """Creates a user with the Admin role and a known PIN."""
    admin_role, _ = Role.objects.get_or_create(name="Admin", company=None)
    user = User.objects.create_user(username=username, password=password)
    user.role = admin_role
    user.set_pin("1234")
    user.save()
    return user


def _make_staff_user(username: str, password: str = "securepassword123") -> User:
    """Creates a user with the Staff role and a known PIN."""
    staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)
    user = User.objects.create_user(username=username, password=password)
    user.role = staff_role
    user.set_pin("1234")
    user.save()
    return user


class DeleteCreditLineServiceTests(TestCase):
    """``delete_credit_line`` — cascade payments + recompute debt balance."""

    def setUp(self):
        self.admin = _make_admin_user("del_admin")
        self.customer = Customer.objects.create(name="Delete CL Store")
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _credit(self, qty=5, price="40.00"):
        return record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price=price,
            performed_by=self.admin,
        )

    def test_delete_credit_line_restores_debt_balance(self):
        """Deleting a credit line with no payments restores the full amount."""
        line = self._credit(qty=5, price="40.00")
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("200.00"))

        delete_credit_line(
            credit_line_id=str(line.pk),
            customer=self.customer,
            pin="1234",
            performed_by=self.admin,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("0.00"))
        self.assertFalse(CreditLine.objects.filter(pk=line.pk).exists())

    def test_delete_credit_line_cascades_payments(self):
        """Deleting a credit line also deletes its non-remittance payments."""
        line = self._credit(qty=5, price="40.00")
        # Record a partial payment of 2 units = 80.00
        record_customer_collection(
            customer_id=_display_id(self.customer),
            performed_by=self.admin,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": 2,
                "amount": "80.00",
                "paid_at": "",
            }],
        )
        self.customer.refresh_from_db()
        # 200 credited - 80 paid = 120 outstanding
        self.assertEqual(self.customer.debt_balance, Decimal("120.00"))
        self.assertEqual(CreditPayment.objects.filter(credit_line=line).count(), 1)

        delete_credit_line(
            credit_line_id=str(line.pk),
            customer=self.customer,
            pin="1234",
            performed_by=self.admin,
        )
        self.customer.refresh_from_db()
        # Only the outstanding (120) is subtracted; the 80 was already paid.
        self.assertEqual(self.customer.debt_balance, Decimal("0.00"))
        self.assertFalse(CreditLine.objects.filter(pk=line.pk).exists())
        self.assertEqual(CreditPayment.objects.filter(credit_line=line).count(), 0)

    def test_delete_credit_line_non_admin_raises(self):
        """Staff users cannot delete credit lines."""
        staff = _make_staff_user("del_staff")
        line = self._credit(qty=2)
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError) as ctx:
            delete_credit_line(
                credit_line_id=str(line.pk),
                customer=self.customer,
                pin="1234",
                performed_by=staff,
            )
        self.assertIn("administrators", str(ctx.exception))
        # Record untouched
        self.assertTrue(CreditLine.objects.filter(pk=line.pk).exists())

    def test_delete_credit_line_wrong_pin_raises(self):
        """An incorrect PIN is rejected."""
        from django.core.exceptions import ValidationError

        line = self._credit(qty=2)
        with self.assertRaises(ValidationError):
            delete_credit_line(
                credit_line_id=str(line.pk),
                customer=self.customer,
                pin="9999",
                performed_by=self.admin,
            )
        self.assertTrue(CreditLine.objects.filter(pk=line.pk).exists())

    def test_delete_credit_line_missing_pin_raises(self):
        """A missing PIN is rejected."""
        from django.core.exceptions import ValidationError

        line = self._credit(qty=2)
        with self.assertRaises(ValidationError):
            delete_credit_line(
                credit_line_id=str(line.pk),
                customer=self.customer,
                pin="",
                performed_by=self.admin,
            )

    def test_delete_credit_line_with_remittance_payment_raises(self):
        """A credit line with a remittance-linked payment cannot be deleted."""
        from django.core.exceptions import ValidationError

        from apps.remittance.models import Remittance

        line = self._credit(qty=5, price="40.00")
        remittance = Remittance.objects.create(
            date=line.transaction_date,
            created_by=self.admin,
        )
        CreditPayment.objects.create(
            credit_line=line,
            remittance=remittance,
            containers_paid=1,
            amount=Decimal("40.00"),
            recorded_by=self.admin,
        )
        # Manually adjust debt balance to simulate the payment effect
        Customer.objects.filter(pk=self.customer.pk).update(
            debt_balance=Decimal("160.00")
        )

        with self.assertRaises(ValidationError) as ctx:
            delete_credit_line(
                credit_line_id=str(line.pk),
                customer=self.customer,
                pin="1234",
                performed_by=self.admin,
            )
        self.assertIn("remittance", str(ctx.exception).lower())
        self.assertTrue(CreditLine.objects.filter(pk=line.pk).exists())


class DeleteCreditPaymentServiceTests(TestCase):
    """``delete_credit_payment`` — restore qty_remaining + debt balance."""

    def setUp(self):
        self.admin = _make_admin_user("pay_del_admin")
        self.customer = Customer.objects.create(name="Delete CP Store")
        self.product = Product.objects.create(
            name="Alkaline", variation="Slim", price=Decimal("25.00")
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _credit_and_pay(self, qty=4, pay_qty=2, pay_amount="50.00"):
        line = record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price="25.00",
            performed_by=self.admin,
        )
        record_customer_collection(
            customer_id=_display_id(self.customer),
            performed_by=self.admin,
            returns=[],
            payments=[{
                "credit_line_id": str(line.pk),
                "qty_paid": pay_qty,
                "amount": pay_amount,
                "paid_at": "",
            }],
        )
        self.customer.refresh_from_db()
        return line

    def test_delete_credit_payment_restores_balance_and_qty(self):
        """Deleting a payment restores debt balance and qty_remaining."""
        line = self._credit_and_pay(qty=4, pay_qty=2, pay_amount="50.00")
        payment = CreditPayment.objects.get(credit_line=line)
        # 100 credited - 50 paid = 50 outstanding
        self.assertEqual(self.customer.debt_balance, Decimal("50.00"))
        line.refresh_from_db()
        self.assertEqual(line.qty_remaining, 2)

        delete_credit_payment(
            payment_id=str(payment.pk),
            customer=self.customer,
            pin="1234",
            performed_by=self.admin,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal("100.00"))
        line.refresh_from_db()
        self.assertEqual(line.qty_remaining, 4)
        self.assertFalse(CreditPayment.objects.filter(pk=payment.pk).exists())

    def test_delete_credit_payment_non_admin_raises(self):
        """Staff users cannot delete payments."""
        from django.core.exceptions import ValidationError

        staff = _make_staff_user("pay_del_staff")
        line = self._credit_and_pay(qty=4, pay_qty=2, pay_amount="50.00")
        payment = CreditPayment.objects.get(credit_line=line)

        with self.assertRaises(ValidationError):
            delete_credit_payment(
                payment_id=str(payment.pk),
                customer=self.customer,
                pin="1234",
                performed_by=staff,
            )

    def test_delete_credit_payment_remittance_linked_raises(self):
        """A payment linked to a remittance cannot be deleted (PROTECT)."""
        from django.core.exceptions import ValidationError

        from apps.remittance.models import Remittance

        line = record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=4,
            unit_price="25.00",
            performed_by=self.admin,
        )
        remittance = Remittance.objects.create(
            date=line.transaction_date,
            created_by=self.admin,
        )
        payment = CreditPayment.objects.create(
            credit_line=line,
            remittance=remittance,
            containers_paid=1,
            amount=Decimal("25.00"),
            recorded_by=self.admin,
        )

        with self.assertRaises(ValidationError) as ctx:
            delete_credit_payment(
                payment_id=str(payment.pk),
                customer=self.customer,
                pin="1234",
                performed_by=self.admin,
            )
        self.assertIn("remittance", str(ctx.exception).lower())
        self.assertTrue(CreditPayment.objects.filter(pk=payment.pk).exists())


class DeleteBorrowedContainerServiceTests(TestCase):
    """``delete_borrowed_container`` — recompute aggregate counter."""

    def setUp(self):
        self.admin = _make_admin_user("bc_del_admin")
        self.customer = Customer.objects.create(name="Delete BC Store")
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _borrow(self, qty=5, key="round_8gal"):
        return record_customer_borrowed(
            customer_id=_display_id(self.customer),
            container_key=key,
            qty_borrowed=qty,
            performed_by=self.admin,
        )

    def test_delete_borrowed_restores_counter(self):
        """Deleting a borrowed entry with no returns restores the full qty."""
        borrowed = self._borrow(qty=5)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 5)

        delete_borrowed_container(
            borrowed_id=str(borrowed.pk),
            customer=self.customer,
            pin="1234",
            performed_by=self.admin,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 0)
        self.assertFalse(BorrowedContainer.objects.filter(pk=borrowed.pk).exists())

    def test_delete_borrowed_with_partial_returns_restores_outstanding(self):
        """Deleting after partial returns only restores the outstanding qty."""
        borrowed = self._borrow(qty=5)
        record_customer_collection(
            customer_id=_display_id(self.customer),
            performed_by=self.admin,
            returns=[{
                "borrowed_id": str(borrowed.pk),
                "qty": 2,
                "returned_at": "",
            }],
            payments=[],
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 3)

        delete_borrowed_container(
            borrowed_id=str(borrowed.pk),
            customer=self.customer,
            pin="1234",
            performed_by=self.admin,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 0)

    def test_delete_borrowed_non_admin_raises(self):
        """Staff users cannot delete borrowed containers."""
        from django.core.exceptions import ValidationError

        staff = _make_staff_user("bc_del_staff")
        borrowed = self._borrow(qty=3)

        with self.assertRaises(ValidationError):
            delete_borrowed_container(
                borrowed_id=str(borrowed.pk),
                customer=self.customer,
                pin="1234",
                performed_by=staff,
            )


class HistoryDeleteViewTests(TestCase):
    """View-layer tests for the delete confirm + submit endpoints."""

    def setUp(self):
        self.admin = _make_admin_user("view_del_admin")
        self.staff = _make_staff_user("view_del_staff")
        self.customer = Customer.objects.create(name="View Delete Store")
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _credit(self, qty=3):
        return record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price="40.00",
            performed_by=self.admin,
        )

    def _borrow(self, qty=3):
        return record_customer_borrowed(
            customer_id=_display_id(self.customer),
            container_key="round_8gal",
            qty_borrowed=qty,
            performed_by=self.admin,
        )

    def test_delete_confirm_get_admin_returns_form(self):
        """Admin GET returns the inline delete-confirm form."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Delete this record?")

    def test_delete_confirm_get_non_admin_returns_403(self):
        """Staff GET on the delete-confirm endpoint returns 403."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.staff)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_delete_submit_admin_deletes_record(self):
        """Admin POST with correct PIN deletes the record and refreshes."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.admin)
        resp = self.client.post(url, {"pin": "1234"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CreditLine.objects.filter(pk=line.pk).exists())
        # The success toast is fired via HX-Trigger, not in the body.
        self.assertIn("Record deleted.", resp.headers.get("HX-Trigger", ""))

    def test_delete_submit_non_admin_returns_403(self):
        """Staff POST on the delete-submit endpoint returns 403."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.staff)
        resp = self.client.post(url, {"pin": "1234"})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(CreditLine.objects.filter(pk=line.pk).exists())

    def test_delete_submit_wrong_pin_returns_400(self):
        """An incorrect PIN returns 400 and keeps the record."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.admin)
        resp = self.client.post(url, {"pin": "9999"})
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(CreditLine.objects.filter(pk=line.pk).exists())

    def test_delete_submit_borrowed_container(self):
        """Admin POST deletes a borrowed container and recomputes counter."""
        borrowed = self._borrow(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"BC-{borrowed.pk}"],
        )
        self.client.force_login(self.admin)
        resp = self.client.post(url, {"pin": "1234"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(BorrowedContainer.objects.filter(pk=borrowed.pk).exists())
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 0)

    def test_delete_submit_requires_login(self):
        """Unauthenticated requests are redirected to login."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        resp = self.client.post(url, {"pin": "1234"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn("next=", resp.url)

    def test_delete_submit_rejects_non_post_methods(self):
        """GET on the submit endpoint returns 405."""
        line = self._credit(qty=3)
        url = reverse(
            "customers:history_delete_submit",
            args=[_display_id(self.customer), f"CL-{line.pk}"],
        )
        self.client.force_login(self.admin)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 405)


class HistoryDeleteFlagTests(TestCase):
    """The ``is_deletable`` flag in the history context respects admin role."""

    def setUp(self):
        self.admin = _make_admin_user("flag_admin")
        self.staff = _make_staff_user("flag_staff")
        self.customer = Customer.objects.create(name="Flag Delete Store")
        self.product = Product.objects.create(
            name="Alkaline", variation="Round", price=Decimal("40.00")
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _credit(self, qty=2):
        return record_customer_debt(
            customer_id=_display_id(self.customer),
            product_key=str(self.product.pk),
            qty_credited=qty,
            unit_price="40.00",
            performed_by=self.admin,
        )

    def test_admin_sees_deletable_flag_true(self):
        """Admin history context marks credit lines as deletable."""
        from apps.customers.presentation import get_customer_history_context

        self._credit(qty=2)
        ctx = get_customer_history_context(self.customer, self.admin)
        cl_entries = [e for e in ctx["history"] if e["kind"] == "credit_line"]
        self.assertTrue(len(cl_entries) >= 1)
        self.assertTrue(cl_entries[0]["is_deletable"])

    def test_staff_sees_deletable_flag_false(self):
        """Staff history context marks credit lines as non-deletable."""
        from apps.customers.presentation import get_customer_history_context

        self._credit(qty=2)
        ctx = get_customer_history_context(self.customer, self.staff)
        cl_entries = [e for e in ctx["history"] if e["kind"] == "credit_line"]
        self.assertTrue(len(cl_entries) >= 1)
        self.assertFalse(cl_entries[0]["is_deletable"])
        self.assertEqual(cl_entries[0]["delete_disabled_reason"], "Admin only")
