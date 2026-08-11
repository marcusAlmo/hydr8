from django.test import TestCase
from django.core.cache import cache

from apps.users.models import User


class CustomerDetailViewTests(TestCase):
    """Tests for the HTMX customer detail modal endpoint.

    Mirrors the audit log detail pattern: a row click issues an HTMX GET
    to ``/customers/<id>/`` and the view returns a modal partial swapped
    into ``#modal-root``.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_detail_returns_modal_partial_for_known_customer(self):
        """GET /customers/HY-8021/ returns 200 and the modal markup."""
        response = self.client.get("/customers/HY-8021/")
        self.assertEqual(response.status_code, 200)
        # Modal backdrop + panel anchors (apostrophe is HTML-escaped by
        # Django autoescape, so assert on a non-escaped substring).
        self.assertContains(response, "Sari-Sari")
        self.assertContains(response, "HY-8021")
        # Enrichment fields rendered
        self.assertContains(response, "Outstanding Debt")
        self.assertContains(response, "Credit Limit")
        self.assertContains(response, "Borrowed Containers")

    def test_detail_includes_status_badge_for_flagged_customer(self):
        """A flagged customer renders the FLAGGED anomaly banner."""
        response = self.client.get("/customers/HY-8021/")
        self.assertContains(response, "FLAGGED")
        self.assertContains(response, "3 overdue cycles in 60 days")

    def test_detail_includes_collect_button_when_has_debt(self):
        """A customer with debt shows the Collect action in the footer."""
        response = self.client.get("/customers/HY-8021/")
        self.assertContains(response, "Collect")

    def test_detail_omits_collect_button_when_no_debt(self):
        """A debt-free customer does not show the Collect action."""
        response = self.client.get("/customers/HY-7712/")
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
        response = self.client.get("/customers/HY-8021/")
        # login_required redirects (302) to the landing page with a next param.
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/HY-8021/", response["Location"])

    def test_detail_rejects_non_get_methods(self):
        """POST is not allowed on the detail endpoint (require_http_methods)."""
        response = self.client.post("/customers/HY-8021/")
        self.assertEqual(response.status_code, 405)

    def test_detail_omits_account_notes_section(self):
        """The detail modal no longer renders an Account Notes section."""
        response = self.client.get("/customers/HY-8021/")
        self.assertNotContains(response, "Account Notes")

    def test_detail_handles_missing_contact_and_address(self):
        """A customer with empty contact/address renders 'Not provided'."""
        response = self.client.get("/customers/HY-6644/")
        self.assertContains(response, "Not provided")


class CustomerCollectViewTests(TestCase):
    """Tests for the HTMX collect modal endpoint.

    The COLLECT buttons in the customer table, debt management table, and
    detail modal footer issue an HTMX GET to ``/customers/<id>/collect/``
    and the view returns a collect modal partial swapped into
    ``#modal-root``.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_collect_returns_modal_for_customer_with_debt(self):
        """GET /customers/HY-8021/collect/ returns the collect modal."""
        response = self.client.get("/customers/HY-8021/collect/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Collect Payment")
        # Per-item labels (singular — one per row inside rider sections)
        self.assertContains(response, "Borrowed Container")
        self.assertContains(response, "Accredited Item")
        # Borrowed container return input (keyed by borrowed entry ID)
        self.assertContains(response, "name=\"returned_B-8021-")
        # Credit line amount input
        self.assertContains(response, "name=\"amount_paid_CL-8021-")

    def test_collect_returns_404_for_unknown_customer(self):
        """An unknown customer ID returns 404."""
        response = self.client.get("/customers/HY-NOPE/collect/")
        self.assertEqual(response.status_code, 404)

    def test_collect_requires_login(self):
        """An anonymous request is redirected to the login flow."""
        self.client.logout()
        response = self.client.get("/customers/HY-8021/collect/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=/customers/HY-8021/collect/", response["Location"])

    def test_collect_rejects_non_get_methods(self):
        """POST is not allowed on the collect endpoint."""
        response = self.client.post("/customers/HY-8021/collect/")
        self.assertEqual(response.status_code, 405)

    def test_collect_segments_items_by_rider(self):
        """The collect modal groups credit lines and borrowed entries by rider."""
        response = self.client.get("/customers/HY-8021/collect/")
        self.assertEqual(response.status_code, 200)
        # HY-8021 has two riders: Juan Dela Cruz (R-001) and Roberto Santos (R-004)
        self.assertContains(response, "Juan Dela Cruz")
        self.assertContains(response, "Roberto Santos")
        # Driver codes appear as badges
        self.assertContains(response, "DRV-001")
        self.assertContains(response, "DRV-004")

    def test_collect_shows_rider_transaction_count(self):
        """Each rider section shows how many transactions they handled."""
        response = self.client.get("/customers/HY-8021/collect/")
        self.assertContains(response, "transaction")

    def test_collect_single_rider_shows_one_section(self):
        """A customer served by one rider has a single rider section."""
        response = self.client.get("/customers/HY-4421/collect/")
        self.assertEqual(response.status_code, 200)
        # HY-4421 is served only by Maria Garcia (R-012)
        self.assertContains(response, "Maria Garcia")
        self.assertContains(response, "DRV-012")
        # Other riders should not appear
        self.assertNotContains(response, "Juan Dela Cruz")
        self.assertNotContains(response, "Roberto Santos")

    def test_collect_credit_line_tagged_to_correct_rider(self):
        """Each credit line row appears within its rider's section."""
        response = self.client.get("/customers/HY-5530/collect/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # HY-5530 has two riders: Juan (R-001, 2 units) and Roberto (R-004, 4 units)
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
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_table_returns_partial(self):
        """GET /customers/table/ returns the customer table partial."""
        response = self.client.get("/customers/table/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "customer-table")
        self.assertContains(response, "Aling Nena")

    def test_table_sort_by_debt_balance_desc(self):
        """?sort=debt_balance&dir=desc orders rows by debt descending."""
        response = self.client.get("/customers/table/?sort=debt_balance&dir=desc")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # HY-8021 has the highest debt (₱1,850) so it should appear first.
        first_pos = content.find("HY-8021")
        other_pos = content.find("HY-4421")
        self.assertLess(first_pos, other_pos)

    def test_table_sort_by_name_asc(self):
        """?sort=name&dir=asc orders rows alphabetically."""
        response = self.client.get("/customers/table/?sort=name&dir=asc")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # 'Aling Nena' should come before 'Aqua Services'.
        aling_pos = content.find("Aling Nena")
        aqua_pos = content.find("Aqua Services")
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
        self.assertContains(response, 'name="product_key"')
        self.assertContains(response, 'name="qty_credited"')
        # Customer dropdown populated from mock data
        self.assertContains(response, "HY-8021")
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
            "customer_id": "HY-8021",
            "product_key": "5gal_alk_round",
            "qty_credited": "5",
            "unit_price": "40.00",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, "HY-8021")

    def test_record_debt_submit_returns_400_for_missing_customer(self):
        """POST without a customer returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "product_key": "5gal_alk_round",
            "qty_credited": "5",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a customer", status_code=400)

    def test_record_debt_submit_returns_400_for_missing_product(self):
        """POST without a product returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "HY-8021",
            "qty_credited": "5",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a product", status_code=400)

    def test_record_debt_submit_returns_400_for_non_numeric_qty(self):
        """POST with a non-numeric quantity returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "HY-8021",
            "product_key": "5gal_alk_round",
            "qty_credited": "abc",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "whole number", status_code=400)

    def test_record_debt_submit_returns_400_for_zero_qty(self):
        """POST with a zero quantity returns 400."""
        response = self.client.post("/customers/record-debt/submit/", {
            "customer_id": "HY-8021",
            "product_key": "5gal_alk_round",
            "qty_credited": "0",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "greater than zero", status_code=400)

    def test_record_debt_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get("/customers/record-debt/submit/")
        self.assertEqual(response.status_code, 405)


class RecordBorrowedViewTests(TestCase):
    """Tests for the HTMX record-borrowed modal + submission endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="hydr8staff",
            password="securepassword123",
        )
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
        self.assertContains(response, 'name="container_key"')
        self.assertContains(response, 'name="qty_borrowed"')
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
            "customer_id": "HY-8021",
            "container_key": "round_8gal",
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, "HY-8021")

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
            "customer_id": "HY-8021",
            "qty_borrowed": "3",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "select a container", status_code=400)

    def test_record_borrowed_submit_returns_400_for_zero_qty(self):
        """POST with a zero quantity returns 400."""
        response = self.client.post("/customers/record-borrowed/submit/", {
            "customer_id": "HY-8021",
            "container_key": "round_8gal",
            "qty_borrowed": "0",
        })
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "greater than zero", status_code=400)

    def test_record_borrowed_submit_rejects_non_post_methods(self):
        """GET is not allowed on the submit endpoint."""
        response = self.client.get("/customers/record-borrowed/submit/")
        self.assertEqual(response.status_code, 405)


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
        cache.clear()
        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_delete_succeeds_for_customer_with_no_pending_items(self):
        """POST /customers/HY-7712/delete/ succeeds (no debt, no borrowed)."""
        response = self.client.post("/customers/HY-7712/delete/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "toast")
        self.assertContains(response, "HY-7712")
        # HX-Redirect header set so the list refreshes
        self.assertEqual(response["HX-Redirect"], "/customers/")

    def test_delete_returns_400_for_customer_with_debt(self):
        """POST /customers/HY-8021/delete/ returns 400 (has debt + borrowed)."""
        response = self.client.post("/customers/HY-8021/delete/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Cannot delete", status_code=400)

    def test_delete_returns_400_for_customer_with_borrowed_only(self):
        """POST /customers/HY-9011/delete/ returns 400 (has borrowed, no debt)."""
        response = self.client.post("/customers/HY-9011/delete/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Cannot delete", status_code=400)

    def test_delete_returns_404_for_unknown_customer(self):
        """POST for an unknown customer ID returns 404."""
        response = self.client.post("/customers/HY-NOPE/delete/")
        self.assertEqual(response.status_code, 404)

    def test_delete_rejects_non_post_methods(self):
        """GET is not allowed on the delete endpoint."""
        response = self.client.get("/customers/HY-7712/delete/")
        self.assertEqual(response.status_code, 405)

    def test_delete_requires_login(self):
        """An anonymous POST is redirected to the login flow."""
        self.client.logout()
        response = self.client.post("/customers/HY-7712/delete/")
        self.assertEqual(response.status_code, 302)

    def test_detail_modal_shows_delete_button_for_deletable_customer(self):
        """The detail modal for HY-7712 (no debt/borrowed) renders a Delete button."""
        response = self.client.get("/customers/HY-7712/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete")
        # The hx-post to the delete endpoint is present
        self.assertContains(response, "/customers/HY-7712/delete/")

    def test_detail_modal_shows_disabled_delete_for_customer_with_debt(self):
        """The detail modal for HY-8021 (has debt) renders a disabled Delete."""
        response = self.client.get("/customers/HY-8021/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete")
        self.assertContains(response, "disabled")
        self.assertContains(response, "Cannot delete")
