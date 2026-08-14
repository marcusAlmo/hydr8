"""Self-contained HTMX view tests for the Customers app.

Each test class creates its own customer / product / user fixtures (following
the ``test_collect_submit.py`` pattern) so they do not depend on seed data.

Covers:
  - Customer detail modal (GET /customers/<id>/)
  - Customer collect modal (GET /customers/<id>/collect/)
  - Customer table partial (GET /customers/table/)
  - Add customer modal + submit (GET/POST /customers/add/, /customers/add/submit/)
  - Record debt modal + submit (GET/POST /customers/record-debt/, /customers/record-debt/submit/)
  - Record borrowed modal + submit (GET/POST /customers/record-borrowed/, /customers/record-borrowed/submit/)
  - Customer delete (POST /customers/<id>/delete/)
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from apps.core.models import Product, SystemConfig
from apps.customers.models import (
    BorrowedContainer,
    CreditLine,
    Customer,
)
from apps.customers.services import (
    record_customer_borrowed,
    record_customer_debt,
)
from apps.settings.models import Company
from apps.users.models import User
from apps.users.presentation import driver_code as user_driver_code


def _display_id(customer: Customer) -> str:
    """Returns the HY-XXXX display id for a customer."""
    return f"HY-{customer.pk:04d}"


class CustomerDetailViewTests(TestCase):
    """Tests for the HTMX customer detail modal endpoint.

    A row click issues an HTMX GET to ``/customers/<id>/`` and the view
    returns a modal partial swapped into ``#modal-root``.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        # Customer with debt + borrowed + FLAGGED status
        self.flagged = Customer.objects.create(
            name="Sari-Sari Store",
            contact_number="0917-555-1234",
            address="Brgy. 14, Mabini St.",
            credit_limit=Decimal("5000.00"),
            status=Customer.Status.FLAGGED,
            flagged_reason="3 overdue cycles in 60 days",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        record_customer_debt(
            customer_id=_display_id(self.flagged),
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        record_customer_borrowed(
            customer_id=_display_id(self.flagged),
            container_key="round_8gal",
            qty_borrowed=3,
            performed_by=self.user,
        )
        # Debt-free, borrow-free customer (deletable)
        self.clean = Customer.objects.create(
            name="Aqua Services Inc.",
            contact_number="0918-555-5678",
            address="123 Aguinaldo Hwy",
        )
        # Customer with empty contact/address
        self.sparse = Customer.objects.create(name="No Contact Store")
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_detail_returns_modal_partial_for_known_customer(self):
        """GET /customers/<id>/ returns 200 and the modal markup."""
        response = self.client.get(f"/customers/{_display_id(self.flagged)}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sari-Sari Store")
        self.assertContains(response, _display_id(self.flagged))
        # Enrichment fields rendered
        self.assertContains(response, "Outstanding Debt")
        self.assertContains(response, "Credit Limit")
        self.assertContains(response, "Borrowed Containers")

    def test_detail_includes_status_badge_for_flagged_customer(self):
        """A flagged customer renders the FLAGGED anomaly banner."""
        response = self.client.get(f"/customers/{_display_id(self.flagged)}/")
        self.assertContains(response, "FLAGGED")
        self.assertContains(response, "3 overdue cycles in 60 days")

    def test_detail_includes_collect_button_when_has_debt(self):
        """A customer with debt shows the Collect action in the footer."""
        response = self.client.get(f"/customers/{_display_id(self.flagged)}/")
        self.assertContains(response, "Collect")

    def test_detail_omits_collect_button_when_no_debt(self):
        """A debt-free customer does not show the Collect action."""
        response = self.client.get(f"/customers/{_display_id(self.clean)}/")
        self.assertContains(response, "Aqua Services Inc.")
        self.assertNotContains(response, ">Collect<")

    def test_detail_returns_404_for_unknown_customer(self):
        """An unknown customer ID returns 404, not the full page."""
        response = self.client.get("/customers/HY-DOES-NOT-EXIST/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Customer not found.", status_code=404)

    def test_detail_requires_login(self):
        """An anonymous request is redirected to the login flow (login_required)."""
        self.client.logout()
        url = f"/customers/{_display_id(self.flagged)}/"
        response = self.client.get(url)
        # login_required redirects (302) to the landing page with a next param.
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"next={url}", response["Location"])

    def test_detail_rejects_non_get_methods(self):
        """POST is not allowed on the detail endpoint (require_http_methods)."""
        response = self.client.post(f"/customers/{_display_id(self.flagged)}/")
        self.assertEqual(response.status_code, 405)

    def test_detail_omits_account_notes_section(self):
        """The detail modal no longer renders an Account Notes section."""
        response = self.client.get(f"/customers/{_display_id(self.flagged)}/")
        self.assertNotContains(response, "Account Notes")

    def test_detail_handles_missing_contact_and_address(self):
        """A customer with empty contact/address renders 'Not provided'."""
        response = self.client.get(f"/customers/{_display_id(self.sparse)}/")
        self.assertContains(response, "Not provided")


class CustomerCollectViewTests(TestCase):
    """Tests for the HTMX collect modal endpoint.

    The COLLECT buttons in the customer table, debt management table, and
    detail modal footer issue an HTMX GET to ``/customers/<id>/collect/``
    and the view returns a collect modal partial swapped into
    ``#modal-root``.
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        # Two riders for the multi-rider customer
        self.rider1 = User.objects.create_user(
            username="juan_delacruz",
            password="securepassword123",
            first_name="Juan",
            last_name="Dela Cruz",
        )
        self.rider2 = User.objects.create_user(
            username="roberto_santos",
            password="securepassword123",
            first_name="Roberto",
            last_name="Santos",
        )
        self.rider3 = User.objects.create_user(
            username="maria_garcia",
            password="securepassword123",
            first_name="Maria",
            last_name="Garcia",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )

        # Multi-rider customer: debt + borrowed via two riders
        self.multi = Customer.objects.create(name="Multi Rider Store")
        # Credit line via rider1 (care_of)
        CreditLine.objects.create(
            customer=self.multi,
            product=self.product,
            qty_credited=5,
            qty_remaining=5,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
            care_of=self.rider1,
        )
        # Credit line via rider2 (care_of)
        CreditLine.objects.create(
            customer=self.multi,
            product=self.product,
            qty_credited=4,
            qty_remaining=4,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("160.00"),
            care_of=self.rider2,
        )
        # Borrowed container via rider1
        BorrowedContainer.objects.create(
            customer=self.multi,
            container_key="round_8gal",
            qty_borrowed=3,
            qty_returned=0,
            care_of=self.rider1,
        )

        # Single-rider customer
        self.single = Customer.objects.create(name="Single Rider Store")
        CreditLine.objects.create(
            customer=self.single,
            product=self.product,
            qty_credited=3,
            qty_remaining=3,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("120.00"),
            care_of=self.rider3,
        )

        cache.clear()
        self.client.force_login(self.staff)

    def tearDown(self):
        cache.clear()

    def test_collect_returns_modal_for_customer_with_debt(self):
        """GET /customers/<id>/collect/ returns the collect modal."""
        response = self.client.get(f"/customers/{_display_id(self.multi)}/collect/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Collect Payment")
        # Per-item labels (singular — one per row inside rider sections)
        self.assertContains(response, "Borrowed Container")
        self.assertContains(response, "Accredited Item")
        # Borrowed container return input (keyed by borrowed entry ID)
        borrowed = BorrowedContainer.objects.get(customer=self.multi)
        self.assertContains(response, f'name="returned_BC-{borrowed.pk}"')
        # Credit line amount input
        line = CreditLine.objects.filter(customer=self.multi).first()
        self.assertContains(response, f'name="amount_paid_CL-{line.pk}"')

    def test_collect_returns_404_for_unknown_customer(self):
        """An unknown customer ID returns 404."""
        response = self.client.get("/customers/HY-NOPE/collect/")
        self.assertEqual(response.status_code, 404)

    def test_collect_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        url = f"/customers/{_display_id(self.multi)}/collect/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"next={url}", response["Location"])

    def test_collect_rejects_non_get_methods(self):
        """POST is not allowed on the collect endpoint."""
        response = self.client.post(f"/customers/{_display_id(self.multi)}/collect/")
        self.assertEqual(response.status_code, 405)

    def test_collect_segments_items_by_rider(self):
        """The collect modal groups credit lines and borrowed entries by rider."""
        response = self.client.get(f"/customers/{_display_id(self.multi)}/collect/")
        self.assertEqual(response.status_code, 200)
        # Multi-rider customer has Juan Dela Cruz and Roberto Santos
        self.assertContains(response, "Juan Dela Cruz")
        self.assertContains(response, "Roberto Santos")
        # Driver codes appear as badges
        self.assertContains(response, user_driver_code(self.rider1))
        self.assertContains(response, user_driver_code(self.rider2))

    def test_collect_shows_rider_transaction_count(self):
        """Each rider section shows how many transactions they handled."""
        response = self.client.get(f"/customers/{_display_id(self.multi)}/collect/")
        self.assertContains(response, "transaction")

    def test_collect_single_rider_shows_one_section(self):
        """A customer served by one rider has a single rider section."""
        response = self.client.get(f"/customers/{_display_id(self.single)}/collect/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Maria Garcia")
        self.assertContains(response, user_driver_code(self.rider3))
        # Other riders should not appear
        self.assertNotContains(response, "Juan Dela Cruz")
        self.assertNotContains(response, "Roberto Santos")

    def test_collect_credit_line_tagged_to_correct_rider(self):
        """Each credit line row appears within its rider's section."""
        response = self.client.get(f"/customers/{_display_id(self.multi)}/collect/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Sections are sorted by rider name, so Juan comes before Roberto.
        juan_pos = content.find("Juan Dela Cruz")
        roberto_pos = content.find("Roberto Santos")
        self.assertLess(juan_pos, roberto_pos)


class CustomerTableViewTests(TestCase):
    """Tests for the HTMX sortable customer table partial endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        # Create customers with different names and debt for sorting tests.
        # "Aling Nena" — alphabetically first, low debt
        self.aling = Customer.objects.create(name="Aling Nena Store")
        # "Aqua Services" — alphabetically second, no debt
        self.aqua = Customer.objects.create(name="Aqua Services Inc.")
        # "Zari-Sari" — highest debt, alphabetically last
        self.zari = Customer.objects.create(name="Zari-Sari Store")
        record_customer_debt(
            customer_id=_display_id(self.zari),
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        record_customer_debt(
            customer_id=_display_id(self.aling),
            product_key=str(self.product.pk),
            qty_credited=1,
            unit_price="40.00",
            performed_by=self.user,
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_table_returns_partial(self):
        """GET /customers/table/ returns the customer table partial."""
        response = self.client.get("/customers/table/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "customer-table")
        self.assertContains(response, "Aling Nena Store")

    def test_table_sort_by_debt_balance_desc(self):
        """?sort=debt_balance&dir=desc orders rows by debt descending."""
        response = self.client.get("/customers/table/?sort=debt_balance&dir=desc")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Zari-Sari has the highest debt (₱200) so it should appear before
        # Aqua Services (which has no debt).
        first_pos = content.find(_display_id(self.zari))
        other_pos = content.find(_display_id(self.aqua))
        self.assertLess(first_pos, other_pos)

    def test_table_sort_by_name_asc(self):
        """?sort=name&dir=asc orders rows alphabetically."""
        response = self.client.get("/customers/table/?sort=name&dir=asc")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # 'Aling Nena' should come before 'Aqua Services'.
        aling_pos = content.find("Aling Nena Store")
        aqua_pos = content.find("Aqua Services Inc.")
        self.assertLess(aling_pos, aqua_pos)

    def test_table_invalid_sort_falls_back_to_default(self):
        """An unknown sort field falls back to the default (name) without error."""
        response = self.client.get("/customers/table/?sort=bogus&dir=asc")
        self.assertEqual(response.status_code, 200)

    def test_table_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/customers/table/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/table/", response["Location"])

    def test_table_rejects_non_get_methods(self):
        """POST is not allowed on the table endpoint."""
        response = self.client.post("/customers/table/")
        self.assertEqual(response.status_code, 405)


class CustomerAddViewTests(TestCase):
    """Tests for the HTMX add-customer modal + submission endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_add_get_returns_modal_partial(self):
        """GET /customers/add/ returns the add-customer modal."""
        response = self.client.get("/customers/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add Customer")
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="contact_number"')
        self.assertContains(response, 'name="address"')
        self.assertContains(response, 'name="credit_limit"')

    def test_add_get_pre_populates_default_credit_limit(self):
        """The credit limit field is pre-filled with the configured default.

        With no SystemConfig row present, the hardcoded default (3000.00)
        is used so the operator doesn't have to re-enter the ceiling for
        every new customer.
        """
        response = self.client.get("/customers/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="3000.00"')
        self.assertContains(response, "Pre-filled from System Config")

    def test_add_get_uses_tenant_scoped_credit_limit(self):
        """A tenant-scoped SystemConfig row overrides the global default."""
        company = Company.objects.create(name="Tenant Co")
        self.user.company = company
        self.user.save()
        SystemConfig.objects.update_or_create(
            company=company,
            key="approved_credit_limit",
            defaults={"value": "5000.00"},
        )
        try:
            response = self.client.get("/customers/add/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'value="5000.00"')
            self.assertNotContains(response, 'value="3000.00"')
        finally:
            self.user.company = None
            self.user.save()

    def test_add_get_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/customers/add/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/add/", response["Location"])

    def test_add_get_rejects_non_get_methods(self):
        """POST is not allowed on the add GET endpoint."""
        response = self.client.post("/customers/add/")
        self.assertEqual(response.status_code, 405)

    def test_add_submit_returns_success_for_valid_name(self):
        """POST /customers/add/submit/ with a name returns a success toast."""
        response = self.client.post("/customers/add/submit/", {"name": "Test Customer"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, "Test Customer")

    def test_add_submit_returns_400_for_missing_name(self):
        """POST without a name returns 400 with an error fragment."""
        response = self.client.post("/customers/add/submit/", {"name": ""})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Customer name is required.", status_code=400)

    def test_add_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get("/customers/add/submit/")
        self.assertEqual(response.status_code, 405)

    def test_add_submit_requires_login(self):
        """An anonymous POST is redirected to the login flow."""
        self.client.logout()
        response = self.client.post("/customers/add/submit/", {"name": "Test"})
        self.assertEqual(response.status_code, 302)


class RecordDebtViewTests(TestCase):
    """Tests for the HTMX record-debt modal + submission endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        self.customer = Customer.objects.create(name="Debt Test Store")
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_record_debt_get_returns_modal_partial(self):
        """GET /customers/record-debt/ returns the record-debt modal."""
        response = self.client.get("/customers/record-debt/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record Debt")
        self.assertContains(response, 'name="customer_id"')
        self.assertContains(response, 'name="customer_name"')
        self.assertContains(response, 'name="product_key"')
        self.assertContains(response, 'name="qty_credited"')
        # Customer data embedded for Alpine combobox
        self.assertContains(response, "debt-customers-data")
        self.assertContains(response, _display_id(self.customer))
        # Product dropdown populated
        self.assertContains(response, "Alkaline Water")

    def test_record_debt_get_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/customers/record-debt/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/record-debt/", response["Location"])

    def test_record_debt_get_rejects_non_get_methods(self):
        """POST is not allowed on the record-debt GET endpoint."""
        response = self.client.post("/customers/record-debt/")
        self.assertEqual(response.status_code, 405)

    def test_record_debt_submit_returns_success_for_valid_input(self):
        """POST with valid fields returns a success toast."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": _display_id(self.customer),
            "product_key": str(self.product.pk),
            "qty_credited": "5",
            "unit_price": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, _display_id(self.customer))

    def test_record_debt_submit_returns_400_for_missing_customer(self):
        """POST without a customer returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "product_key": str(self.product.pk),
            "qty_credited": "5",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a customer", status_code=400)

    def test_record_debt_submit_returns_400_for_missing_product(self):
        """POST without a product returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": _display_id(self.customer),
            "qty_credited": "5",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a product", status_code=400)

    def test_record_debt_submit_returns_400_for_non_numeric_qty(self):
        """POST with a non-numeric quantity returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": _display_id(self.customer),
            "product_key": str(self.product.pk),
            "qty_credited": "abc",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "whole number", status_code=400)

    def test_record_debt_submit_returns_400_for_zero_qty(self):
        """POST with a zero quantity returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": _display_id(self.customer),
            "product_key": str(self.product.pk),
            "qty_credited": "0",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "greater than zero", status_code=400)

    def test_record_debt_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get("/customers/record-debt/submit/")
        self.assertEqual(response.status_code, 405)

    def test_record_debt_submit_creates_customer_if_not_found(self):
        """POST with customer_name (no customer_id) creates a customer on the fly."""
        existing_count = Customer.objects.count()
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "",
            "customer_name": "Brand New Debt Store",
            "product_key": str(self.product.pk),
            "qty_credited": "3",
            "unit_price": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        # A new customer was created
        self.assertEqual(Customer.objects.count(), existing_count + 1)
        new_customer = Customer.objects.filter(name="Brand New Debt Store").first()
        self.assertIsNotNone(new_customer)
        # The new customer has the debt recorded
        self.assertEqual(new_customer.credit_lines.count(), 1)
        self.assertTrue(new_customer.debt_balance > 0)

    def test_record_debt_submit_new_customer_gets_default_credit_limit(self):
        """A customer created on the fly gets the default credit limit from settings."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "",
            "customer_name": "Default Limit Store",
            "product_key": str(self.product.pk),
            "qty_credited": "1",
            "unit_price": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        new_customer = Customer.objects.filter(name="Default Limit Store").first()
        self.assertIsNotNone(new_customer)
        # Default credit limit is 3000.00 (from SYSTEM_CONFIG_DEFAULTS)
        self.assertEqual(new_customer.credit_limit, Decimal("3000.00"))

    def test_record_debt_submit_returns_400_for_no_customer(self):
        """POST with neither customer_id nor customer_name returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "",
            "customer_name": "",
            "product_key": str(self.product.pk),
            "qty_credited": "5",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a customer", status_code=400)

    def test_record_debt_submit_prefers_existing_customer_over_name(self):
        """When both customer_id and customer_name are sent, customer_id wins."""
        existing_count = Customer.objects.count()
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": _display_id(self.customer),
            "customer_name": "Should Not Be Created",
            "product_key": str(self.product.pk),
            "qty_credited": "2",
            "unit_price": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        # No new customer was created — the existing one was used
        self.assertEqual(Customer.objects.count(), existing_count)
        self.assertFalse(Customer.objects.filter(name="Should Not Be Created").exists())


class RecordBorrowedViewTests(TestCase):
    """Tests for the HTMX record-borrowed modal + submission endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        self.customer = Customer.objects.create(name="Borrow Test Store")
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_record_borrowed_get_returns_modal_partial(self):
        """GET /customers/record-borrowed/ returns the record-borrowed modal."""
        response = self.client.get("/customers/record-borrowed/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record Borrowed")
        self.assertContains(response, 'name="customer_id"')
        self.assertContains(response, 'name="customer_name"')
        self.assertContains(response, 'name="container_key"')
        self.assertContains(response, 'name="qty_borrowed"')
        # Customer data embedded for Alpine combobox
        self.assertContains(response, "borrow-customers-data")
        # Container type dropdown populated
        self.assertContains(response, "Round 8gal")

    def test_record_borrowed_get_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/customers/record-borrowed/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/record-borrowed/", response["Location"])

    def test_record_borrowed_get_rejects_non_get_methods(self):
        """POST is not allowed on the record-borrowed GET endpoint."""
        response = self.client.post("/customers/record-borrowed/")
        self.assertEqual(response.status_code, 405)

    def test_record_borrowed_submit_returns_success_for_valid_input(self):
        """POST with valid fields returns a success toast."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": _display_id(self.customer),
            "container_key": "round_8gal",
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, _display_id(self.customer))

    def test_record_borrowed_submit_returns_400_for_missing_customer(self):
        """POST without a customer returns 400."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "container_key": "round_8gal",
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a customer", status_code=400)

    def test_record_borrowed_submit_returns_400_for_missing_container(self):
        """POST without a container type returns 400."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": _display_id(self.customer),
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a container", status_code=400)

    def test_record_borrowed_submit_returns_400_for_zero_qty(self):
        """POST with a zero quantity returns 400."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": _display_id(self.customer),
            "container_key": "round_8gal",
            "qty_borrowed": "0",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "greater than zero", status_code=400)

    def test_record_borrowed_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get("/customers/record-borrowed/submit/")
        self.assertEqual(response.status_code, 405)

    def test_record_borrowed_submit_creates_customer_if_not_found(self):
        """POST with customer_name (no customer_id) creates a customer on the fly."""
        existing_count = Customer.objects.count()
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": "",
            "customer_name": "Brand New Borrow Store",
            "container_key": "round_8gal",
            "qty_borrowed": "4",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        # A new customer was created
        self.assertEqual(Customer.objects.count(), existing_count + 1)
        new_customer = Customer.objects.filter(name="Brand New Borrow Store").first()
        self.assertIsNotNone(new_customer)
        # The new customer has the borrowed container recorded
        self.assertTrue(new_customer.borrowed_round_8gal > 0)

    def test_record_borrowed_submit_new_customer_gets_default_credit_limit(self):
        """A customer created on the fly gets the default credit limit."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": "",
            "customer_name": "Borrow Default Limit Store",
            "container_key": "slim_8gal",
            "qty_borrowed": "2",
        })
        self.assertEqual(response.status_code, 200)
        new_customer = Customer.objects.filter(name="Borrow Default Limit Store").first()
        self.assertIsNotNone(new_customer)
        self.assertEqual(new_customer.credit_limit, Decimal("3000.00"))

    def test_record_borrowed_submit_returns_400_for_no_customer(self):
        """POST with neither customer_id nor customer_name returns 400."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": "",
            "customer_name": "",
            "container_key": "round_8gal",
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a customer", status_code=400)


class CustomerDeleteViewTests(TestCase):
    """Tests for the HTMX customer delete endpoint.

    A customer can only be deleted when there are no pending borrowed
    containers and no outstanding debt. The detail modal only renders the
    Delete button when ``can_delete`` is True, but the view re-checks
    server-side.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )
        # Deletable customer — no debt, no borrowed
        self.clean = Customer.objects.create(name="Clean Store")
        # Customer with debt (and borrowed)
        self.with_debt = Customer.objects.create(name="Indebted Store")
        record_customer_debt(
            customer_id=_display_id(self.with_debt),
            product_key=str(self.product.pk),
            qty_credited=5,
            unit_price="40.00",
            performed_by=self.user,
        )
        record_customer_borrowed(
            customer_id=_display_id(self.with_debt),
            container_key="round_8gal",
            qty_borrowed=3,
            performed_by=self.user,
        )
        # Customer with borrowed only (no debt)
        self.with_borrowed = Customer.objects.create(name="Borrowed Only Store")
        record_customer_borrowed(
            customer_id=_display_id(self.with_borrowed),
            container_key="round_8gal",
            qty_borrowed=2,
            performed_by=self.user,
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_delete_succeeds_for_customer_with_no_pending_items(self):
        """POST /customers/<id>/delete/ succeeds (no debt, no borrowed)."""
        response = self.client.post(f"/customers/{_display_id(self.clean)}/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, _display_id(self.clean))
        # HX-Redirect header set so the list refreshes
        self.assertEqual(response["HX-Redirect"], "/customers/")

    def test_delete_returns_400_for_customer_with_debt(self):
        """POST for a customer with debt + borrowed returns 400."""
        response = self.client.post(f"/customers/{_display_id(self.with_debt)}/delete/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Cannot delete", status_code=400)

    def test_delete_returns_400_for_customer_with_borrowed_only(self):
        """POST for a customer with borrowed (no debt) returns 400."""
        response = self.client.post(f"/customers/{_display_id(self.with_borrowed)}/delete/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Cannot delete", status_code=400)

    def test_delete_returns_404_for_unknown_customer(self):
        """POST for an unknown customer ID returns 404."""
        response = self.client.post("/customers/HY-NOPE/delete/")
        self.assertEqual(response.status_code, 404)

    def test_delete_rejects_non_post_methods(self):
        """GET is not allowed on the delete endpoint."""
        response = self.client.get(f"/customers/{_display_id(self.clean)}/delete/")
        self.assertEqual(response.status_code, 405)

    def test_delete_requires_login(self):
        """An anonymous POST is redirected to the login flow."""
        self.client.logout()
        response = self.client.post(f"/customers/{_display_id(self.clean)}/delete/")
        self.assertEqual(response.status_code, 302)

    def test_detail_modal_shows_delete_button_for_deletable_customer(self):
        """The detail modal for a clean customer renders a Delete button."""
        response = self.client.get(f"/customers/{_display_id(self.clean)}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete")
        # The hx-post to the delete endpoint is present
        self.assertContains(response, f"/customers/{_display_id(self.clean)}/delete/")

    def test_detail_modal_shows_disabled_delete_for_customer_with_debt(self):
        """The detail modal for a customer with debt renders a disabled Delete."""
        response = self.client.get(f"/customers/{_display_id(self.with_debt)}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete")
        self.assertContains(response, "disabled")
        self.assertContains(response, "Cannot delete")
