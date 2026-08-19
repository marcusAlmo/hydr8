"""Tests for the tithes_paid / offering_paid status update flow.

Covers the service layer (:func:`update_remittance_paid_status`) and the
HTMX view (:func:`update_paid_status_view`).  Self-contained — creates
its own user and remittance fixtures so it does not depend on seed data.
"""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.remittance.models import Remittance
from apps.remittance.services import update_remittance_paid_status
from apps.remittance.presentation import build_remittance_row
from apps.users.models import Role, User


class UpdatePaidStatusServiceTests(TestCase):
    """Service-layer behaviour for the paid-status update."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="operator",
            password="securepassword123",
            first_name="Op",
            last_name="Erator",
        )
        self.remittance = Remittance.objects.create(
            date=date(2026, 8, 1),
            created_by=self.user,
            finalized_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            total_sales=Decimal("1000.00"),
            net_profit=Decimal("800.00"),
            tithe_amount=Decimal("80.00"),
            tithes_paid=False,
            offering_paid=False,
        )

    def test_marks_both_paid(self):
        """Both flags can be set to True in one call."""
        rem = update_remittance_paid_status(
            performed_by=self.user,
            remittance_id=self.remittance.id,
            tithes_paid=True,
            offering_paid=True,
        )
        self.assertTrue(rem.tithes_paid)
        self.assertTrue(rem.offering_paid)
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertTrue(self.remittance.offering_paid)

    def test_marks_one_paid_leaves_other_unchanged(self):
        """Setting tithes_paid=True does not flip offering_paid."""
        update_remittance_paid_status(
            performed_by=self.user,
            remittance_id=self.remittance.id,
            tithes_paid=True,
            offering_paid=False,
        )
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertFalse(self.remittance.offering_paid)

    def test_cannot_unset_paid_flag(self):
        """A paid flag is immutable — attempting to revert it to False
        raises ValidationError and leaves the flag True."""
        self.remittance.tithes_paid = True
        self.remittance.offering_paid = True
        self.remittance.save()
        with self.assertRaises(ValidationError):
            update_remittance_paid_status(
                performed_by=self.user,
                remittance_id=self.remittance.id,
                tithes_paid=False,
                offering_paid=True,
            )
        # Neither flag should have changed.
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertTrue(self.remittance.offering_paid)

    def test_cannot_unset_offering_paid_flag(self):
        """Specifically verifying the offering_paid immutability guard."""
        self.remittance.offering_paid = True
        self.remittance.save()
        with self.assertRaises(ValidationError):
            update_remittance_paid_status(
                performed_by=self.user,
                remittance_id=self.remittance.id,
                tithes_paid=False,
                offering_paid=False,
            )
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.offering_paid)

    def test_raises_for_nonexistent_remittance(self):
        """A missing remittance raises ValidationError, not DoesNotExist."""
        with self.assertRaises(ValidationError):
            update_remittance_paid_status(
                performed_by=self.user,
                remittance_id=999_999,
                tithes_paid=True,
                offering_paid=True,
            )

    def test_tenant_isolation_other_company_user_cannot_update(self):
        """A user from a different tenant cannot update another tenant's
        remittance — the for_user() filter returns no row, so
        ValidationError is raised.

        The company-scoped remittance is created with ``company`` set at
        creation time, because the DB immutability trigger (migration
        0005) blocks reassigning ``company`` on an already-FINALIZED row.
        """
        from apps.core.models import Company
        company_a = Company.objects.create(name="Company A")
        company_b = Company.objects.create(name="Company B")

        user_a = User.objects.create_user(
            username="op_a",
            password="securepassword123",
            company=company_a,
        )
        rem_a = Remittance.objects.create(
            date=date(2026, 8, 5),
            created_by=user_a,
            finalized_by=user_a,
            status=Remittance.StatusChoices.FINALIZED,
            company=company_a,
            tithes_paid=False,
            offering_paid=False,
        )

        other = User.objects.create_user(
            username="other_operator",
            password="securepassword123",
            company=company_b,
        )
        with self.assertRaises(ValidationError):
            update_remittance_paid_status(
                performed_by=other,
                remittance_id=rem_a.id,
                tithes_paid=True,
                offering_paid=True,
            )
        # Original remittance must be unchanged.
        rem_a.refresh_from_db()
        self.assertFalse(rem_a.tithes_paid)


class GetRemittanceRowSelectorTests(TestCase):
    """Selector behaviour for the single-row lookup used by the HTMX view."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="operator",
            password="securepassword123",
            first_name="Op",
            last_name="Erator",
        )
        self.remittance = Remittance.objects.create(
            date=date(2026, 8, 2),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            tithes_paid=True,
            offering_paid=False,
        )

    def test_returns_row_dict_with_id(self):
        row = build_remittance_row(self.user, self.remittance.id)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], self.remittance.id)
        self.assertTrue(row["tithes_paid"])
        self.assertFalse(row["offering_paid"])
        self.assertTrue(row["unpaid"])  # offering not paid → unpaid

    def test_returns_none_for_nonexistent(self):
        self.assertIsNone(build_remittance_row(self.user, 999_999))


class UpdatePaidStatusViewTests(TestCase):
    """HTMX view behaviour for the paid-status update endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="operator",
            password="securepassword123",
            first_name="Op",
            last_name="Erator",
        )
        self.remittance = Remittance.objects.create(
            date=date(2026, 8, 3),
            created_by=self.user,
            finalized_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            tithes_paid=False,
            offering_paid=False,
        )
        self.client.login(username="operator", password="securepassword123")

    def _url(self) -> str:
        return f"/remittance/{self.remittance.id}/paid-status/"

    def test_post_updates_both_flags_and_returns_row(self):
        """POST with both checkboxes 'on' persists True for both and
        returns the refreshed row partial."""
        response = self.client.post(self._url(), {
            "tithes_paid": "on",
            "offering_paid": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertTrue(self.remittance.offering_paid)
        # The response contains the row partial. The toast is sent via
        # HX-Trigger (client-side hydr8ShowToast), not in the body.
        self.assertContains(response, "rem-row")
        trigger = response.headers.get("HX-Trigger", "")
        self.assertIn("showToast", trigger)
        self.assertIn("Payment status updated.", trigger)

    def test_post_with_no_checkboxes_blocked_when_already_paid(self):
        """An empty POST (no checkboxes) attempts to clear both flags.
        Because both flags are already True (immutable), the service
        raises ValidationError and the view returns a 400 error toast."""
        self.remittance.tithes_paid = True
        self.remittance.offering_paid = True
        self.remittance.save()
        response = self.client.post(self._url(), {})
        self.assertEqual(response.status_code, 400)
        self.remittance.refresh_from_db()
        # Flags remain True — immutability enforced.
        self.assertTrue(self.remittance.tithes_paid)
        self.assertTrue(self.remittance.offering_paid)

    def test_post_updates_single_flag(self):
        """POST with only tithes_paid=on sets tithes True, offering False."""
        response = self.client.post(self._url(), {"tithes_paid": "on"})
        self.assertEqual(response.status_code, 200)
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertFalse(self.remittance.offering_paid)

    def test_get_method_not_allowed(self):
        """GET is rejected with 405."""
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 405)

    def test_requires_login(self):
        """Unauthenticated users are redirected to login."""
        self.client.logout()
        response = self.client.post(self._url(), {"tithes_paid": "on"})
        self.assertEqual(response.status_code, 302)

    def test_nonexistent_remittance_returns_error_toast(self):
        """POSTing to a nonexistent remittance returns a 400 error toast,
        not a 500."""
        response = self.client.post(
            "/remittance/999999/paid-status/",
            {"tithes_paid": "on"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Remittance not found.", status_code=400)


class RemittanceHistoryPageRenderTests(TestCase):
    """Smoke test — the history page renders with the new row partial,
    Actions column, and remittanceRow Alpine component."""

    def setUp(self):
        admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.user = User.objects.create_user(
            username="operator",
            password="securepassword123",
            first_name="Op",
            last_name="Erator",
            role=admin_role,
        )
        Remittance.objects.create(
            date=date(2026, 8, 4),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
            tithes_paid=False,
            offering_paid=False,
        )
        self.client.login(username="operator", password="securepassword123")

    def test_history_page_renders_with_row_partial(self):
        response = self.client.get("/remittance/history/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rem-row")
        self.assertContains(response, "remittanceRow")
        self.assertContains(response, "paid-status/")
