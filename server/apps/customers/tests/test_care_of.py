"""Self-contained tests for the ``care_of`` responsibility link on
borrowed containers and credit lines.

These tests create their own customer / product / user fixtures so they
do not depend on the seed data referenced by ``test_views.py``.
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product
from apps.customers.models import BorrowedContainer, CreditLine, Customer
from apps.customers.services import record_customer_borrowed, record_customer_debt
from apps.customers.selectors import (
    get_customer_collect_context,
    get_record_borrowed_context,
    get_record_debt_context,
)
from apps.users.models import Role, User


def _make_staff_user(**kwargs) -> User:
    """Creates a test user with the canonical Staff back-office role."""
    staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)
    return User.objects.create_user(role=staff_role, **kwargs)


class CareOfServicesTests(TestCase):
    """Service-layer behaviour for the ``care_of`` responsibility link."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="staff_recorder",
            password="securepassword123",
            first_name="Staff",
            last_name="Recorder",
        )
        self.admin = _make_staff_user(
            username="admin_lender",
            password="securepassword123",
            first_name="Admin",
            last_name="Lender",
        )
        self.customer = Customer.objects.create(name="Care Of Test Store")
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    # --- Borrowed containers -------------------------------------------------

    def test_record_borrowed_creates_instance_linked_to_care_of(self):
        """Recording borrowed containers creates a BorrowedContainer row
        whose ``care_of`` points at the supplied user."""
        borrowed = record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=3,
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        self.assertEqual(borrowed.qty_borrowed, 3)
        self.assertEqual(borrowed.qty_returned, 0)
        self.assertEqual(borrowed.qty_remaining, 3)
        self.assertEqual(borrowed.care_of_id, self.admin.pk)
        self.assertEqual(borrowed.recorded_by_id, self.staff.pk)
        self.assertEqual(borrowed.container_key, "round_8gal")
        self.assertEqual(borrowed.container_label, "Round 8gal")

    def test_record_borrowed_without_care_of_leaves_it_null(self):
        """The ``care_of`` field is optional — omitting it leaves it NULL."""
        borrowed = record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="slim_8gal",
            qty_borrowed=2,
            performed_by=self.staff,
        )
        self.assertIsNone(borrowed.care_of)

    def test_record_borrowed_still_updates_aggregate_counters(self):
        """The aggregate counters on Customer are kept in sync for the
        existing table/detail views."""
        record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=3,
            performed_by=self.staff,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.borrowed_round_8gal, 3)

    def test_record_borrowed_rejects_invalid_care_of(self):
        """A non-empty ``care_of_id`` that does not match a user raises."""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            record_customer_borrowed(
                customer_id=f"HY-{self.customer.pk:04d}",
                container_key="round_8gal",
                qty_borrowed=1,
                care_of_id="00000000-0000-0000-0000-000000000000",
                performed_by=self.staff,
            )

    # --- Credit lines --------------------------------------------------------

    def test_record_debt_sets_care_of_on_credit_line(self):
        """Recording debt links the credit line to the supplied ``care_of``."""
        credit_line = record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        self.assertEqual(credit_line.care_of_id, self.admin.pk)
        self.assertEqual(credit_line.qty_remaining, 5)

    def test_record_debt_without_care_of_leaves_it_null(self):
        """The ``care_of`` field is optional on credit lines too."""
        credit_line = record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=2,
            unit_price="40.00",
            performed_by=self.staff,
        )
        self.assertIsNone(credit_line.care_of)


class CareOfSelectorTests(TestCase):
    """Selector-layer behaviour for the ``care_of`` dropdowns and the
    collect-modal list of borrowed/credited items."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="staff_recorder",
            password="securepassword123",
            first_name="Staff",
            last_name="Recorder",
        )
        self.admin = _make_staff_user(
            username="admin_lender",
            password="securepassword123",
            first_name="Admin",
            last_name="Lender",
        )
        self.customer = Customer.objects.create(name="Selector Test Store")
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_record_borrowed_context_includes_care_of_users(self):
        """The record-borrowed modal context lists active users."""
        ctx = get_record_borrowed_context(self.staff)
        self.assertIn("care_of_users", ctx)
        ids = {u["id"] for u in ctx["care_of_users"]}
        self.assertIn(str(self.staff.pk), ids)
        self.assertIn(str(self.admin.pk), ids)

    def test_record_debt_context_includes_care_of_users(self):
        """The record-debt modal context lists active users."""
        ctx = get_record_debt_context(self.staff)
        self.assertIn("care_of_users", ctx)
        ids = {u["id"] for u in ctx["care_of_users"]}
        self.assertIn(str(self.admin.pk), ids)

    def test_collect_context_lists_borrowed_entries_with_care_of(self):
        """The collect modal lists borrowed entries (not just credit lines)
        and surfaces the ``care_of`` user for each."""
        record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=3,
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        ctx = get_customer_collect_context(self.customer)
        borrowed_entries = ctx["borrowed_entries"]
        self.assertEqual(len(borrowed_entries), 1)
        entry = borrowed_entries[0]
        self.assertEqual(entry["container_key"], "round_8gal")
        self.assertEqual(entry["outstanding"], 3)
        self.assertEqual(entry["care_of"]["name"], self.admin.full_name)

    def test_collect_context_lists_credit_lines_with_care_of(self):
        """The collect modal surfaces the ``care_of`` user on credit lines."""
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        ctx = get_customer_collect_context(self.customer)
        credit_items = [i for i in ctx["credit_lines"] if i.get("product")]
        self.assertEqual(len(credit_items), 1)
        self.assertEqual(credit_items[0]["care_of"]["name"], self.admin.full_name)

    def test_collect_context_groups_manual_debt_under_care_of_user(self):
        """A manually-recorded debt (no remittance rider product) is grouped
        under its ``care_of`` user in the collect modal, not "Unassigned".

        Regression: previously the rider group header fell back to
        "Unassigned" whenever ``remittance_rider_product`` was null, even
        though ``care_of`` had been assigned during debt creation.
        """
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        ctx = get_customer_collect_context(self.customer)
        rider_groups = ctx["rider_groups"]
        self.assertEqual(len(rider_groups), 1)
        group = rider_groups[0]
        self.assertEqual(group["rider"]["name"], self.admin.full_name)
        self.assertNotEqual(group["rider"]["name"], "Unassigned")

    def test_collect_context_groups_unassigned_debt_separately(self):
        """A debt recorded without a ``care_of`` user is still grouped under
        "Unassigned" so it is not silently hidden."""
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=2,
            unit_price="40.00",
            performed_by=self.staff,
        )
        ctx = get_customer_collect_context(self.customer)
        rider_groups = ctx["rider_groups"]
        self.assertEqual(len(rider_groups), 1)
        self.assertEqual(rider_groups[0]["rider"]["name"], "Unassigned")


class CareOfViewTests(TestCase):
    """HTMX view-layer behaviour for the ``care_of`` field."""

    def setUp(self):
        self.staff = _make_staff_user(
            username="staff_recorder",
            password="securepassword123",
            first_name="Staff",
            last_name="Recorder",
        )
        self.admin = _make_staff_user(
            username="admin_lender",
            password="securepassword123",
            first_name="Admin",
            last_name="Lender",
        )
        self.customer = Customer.objects.create(name="View Test Store")
        self.product = Product.objects.create(
            name="Alkaline",
            variation="Round",
            price=Decimal("40.00"),
        )
        cache.clear()
        self.client.force_login(self.staff)

    def tearDown(self):
        cache.clear()

    def test_record_borrowed_modal_renders_care_of_field(self):
        """GET /customers/record-borrowed/ renders the care of dropdown."""
        response = self.client.get("/customers/record-borrowed/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="care_of_id"')
        self.assertContains(response, "Admin Lender")

    def test_record_debt_modal_renders_care_of_field(self):
        """GET /customers/record-debt/ renders the care of dropdown."""
        response = self.client.get("/customers/record-debt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="care_of_id"')
        self.assertContains(response, "Admin Lender")

    def test_record_borrowed_submit_persists_care_of(self):
        """POST /customers/record-borrowed/submit/ links the borrowing to
        the supplied ``care_of`` user."""
        response = self.client.post(
            "/customers/record-borrowed/submit/",
            {
                "customer_id": f"HY-{self.customer.pk:04d}",
                "container_key": "round_8gal",
                "qty_borrowed": "3",
                "care_of_id": str(self.admin.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        borrowed = BorrowedContainer.objects.get(customer=self.customer)
        self.assertEqual(borrowed.qty_borrowed, 3)
        self.assertEqual(borrowed.care_of_id, self.admin.pk)

    def test_record_debt_submit_persists_care_of(self):
        """POST /customers/record-debt/submit/ links the credit line to the
        supplied ``care_of`` user."""
        response = self.client.post(
            "/customers/record-debt/submit/",
            {
                "customer_id": f"HY-{self.customer.pk:04d}",
                "product_key": str(self.product.pk),
                "qty_credited": "5",
                "unit_price": "40.00",
                "care_of_id": str(self.admin.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        line = CreditLine.objects.get(customer=self.customer)
        self.assertEqual(line.qty_credited, 5)
        self.assertEqual(line.care_of_id, self.admin.pk)

    def test_collect_modal_shows_care_of_for_borrowed_and_credited(self):
        """The collect modal renders the ``care of`` line for both borrowed
        containers and accredited items."""
        record_customer_borrowed(
            customer_id=f"HY-{self.customer.pk:04d}",
            container_key="round_8gal",
            qty_borrowed=3,
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        record_customer_debt(
            customer_id=f"HY-{self.customer.pk:04d}",
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            care_of_id=str(self.admin.pk),
            performed_by=self.staff,
        )
        response = self.client.get(
            f"/customers/HY-{self.customer.pk:04d}/collect/"
        )
        self.assertEqual(response.status_code, 200)
        # "Care of:" appears once per borrowed entry and once per credit line.
        self.assertContains(response, "Care of:")
        self.assertContains(response, "Admin Lender")
