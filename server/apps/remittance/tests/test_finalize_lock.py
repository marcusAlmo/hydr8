"""Tests for the draft -> finalize transition and the database-level
immutability guard on FINALIZED remittances.

Covers:
  - ``create_remittance(finalize=True)`` replacing an existing DRAFT
    (the bug where finalizing after a staff draft raised "a draft
    already exists").
  - The PostgreSQL trigger installed by migration 0005: financial
    fields, status revert, DELETE, and child-record mutations are
    blocked on FINALIZED rows, while the tithes_paid / offering_paid
    toggle remains allowed.
"""
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import InternalError
from django.test import TestCase

from apps.remittance.models import Expense, Remittance
from apps.remittance.services import (
    create_remittance,
    finalize_remittance,
    save_remittance_draft,
    update_remittance_paid_status,
)
from apps.users.models import Role, User


class DraftToFinalizeTransitionTests(TestCase):
    """The admin finalize flow must replace an existing DRAFT, not error."""

    def setUp(self):
        cache.clear()
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")

        self.staff = User.objects.create_user(
            username="staff",
            password="securepassword123",
            role=self.staff_role,
        )
        self.admin = User.objects.create_user(
            username="admin",
            password="securepassword123",
            role=self.admin_role,
        )
        self.admin.set_pin("1234")
        self.admin.save()

    def tearDown(self):
        cache.clear()

    def test_finalize_replaces_existing_draft(self):
        """Staff saves a draft, then admin finalizes — the draft is
        replaced by a FINALIZED remittance instead of raising."""
        save_remittance_draft(
            performed_by=self.staff,
            remittance_date=date(2026, 8, 12),
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
        )
        # The draft exists.
        self.assertEqual(
            Remittance.objects.filter(date=date(2026, 8, 12)).count(), 1
        )
        draft_id = Remittance.objects.get(date=date(2026, 8, 12)).id

        finalized = create_remittance(
            performed_by=self.admin,
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=date(2026, 8, 12),
            finalize=True,
        )
        self.assertEqual(finalized.status, Remittance.StatusChoices.FINALIZED)
        self.assertEqual(finalized.finalized_by, self.admin)
        self.assertIsNotNone(finalized.finalized_at)
        # The old draft row is gone — exactly one row remains, finalized.
        self.assertEqual(
            Remittance.objects.filter(date=date(2026, 8, 12)).count(), 1
        )
        self.assertNotEqual(finalized.id, draft_id)

    def test_finalize_on_fresh_date_creates_finalized(self):
        """With no existing draft, finalize creates a FINALIZED row directly."""
        rem = create_remittance(
            performed_by=self.admin,
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=date(2026, 8, 13),
            finalize=True,
        )
        self.assertEqual(rem.status, Remittance.StatusChoices.FINALIZED)

    def test_finalize_raises_when_already_finalized(self):
        """Finalizing twice (two create_remittance finalize calls) raises."""
        create_remittance(
            performed_by=self.admin,
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
            remittance_date=date(2026, 8, 14),
            finalize=True,
        )
        with self.assertRaises(ValidationError):
            create_remittance(
                performed_by=self.admin,
                riders_data=[],
                expenses_data=[],
                manual_offering="0",
                tithe_rate="0.10",
                remittance_date=date(2026, 8, 14),
                finalize=True,
            )

    def test_draft_mode_still_errors_on_existing_draft(self):
        """A plain create_remittance (draft) still rejects an existing draft."""
        save_remittance_draft(
            performed_by=self.staff,
            remittance_date=date(2026, 8, 15),
            riders_data=[],
            expenses_data=[],
            manual_offering="0",
            tithe_rate="0.10",
        )
        with self.assertRaises(ValidationError):
            create_remittance(
                performed_by=self.staff,
                riders_data=[],
                expenses_data=[],
                manual_offering="0",
                tithe_rate="0.10",
                remittance_date=date(2026, 8, 15),
                finalize=False,
            )


class FinalizedLockTriggerTests(TestCase):
    """Database-level immutability guard on FINALIZED remittances."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_superuser(
            username="admin",
            password="securepassword123",
        )
        self.user.set_pin("1234")
        self.user.save()
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

    def tearDown(self):
        cache.clear()

    def test_paid_flags_can_still_toggle(self):
        """tithes_paid / offering_paid remain editable on a FINALIZED row."""
        update_remittance_paid_status(
            performed_by=self.user,
            remittance_id=self.remittance.id,
            tithes_paid=True,
            offering_paid=True,
        )
        self.remittance.refresh_from_db()
        self.assertTrue(self.remittance.tithes_paid)
        self.assertTrue(self.remittance.offering_paid)

    def test_financial_field_update_is_blocked(self):
        """Updating total_sales on a FINALIZED row raises a DB error."""
        with self.assertRaises(InternalError), transaction.atomic():
            Remittance.objects.filter(id=self.remittance.id).update(
                total_sales=Decimal("9999.00")
            )
        # Value unchanged.
        self.remittance.refresh_from_db()
        self.assertEqual(self.remittance.total_sales, Decimal("1000.00"))

    def test_status_revert_is_blocked(self):
        """Reverting FINALIZED -> DRAFT is blocked by the trigger."""
        with self.assertRaises(InternalError), transaction.atomic():
            Remittance.objects.filter(id=self.remittance.id).update(
                status=Remittance.StatusChoices.DRAFT
            )

    def test_delete_finalized_is_blocked(self):
        """DELETE on a FINALIZED row raises."""
        with self.assertRaises(InternalError), transaction.atomic():
            self.remittance.delete()
        # Row still present.
        self.assertTrue(Remittance.objects.filter(id=self.remittance.id).exists())

    def test_child_insert_is_blocked(self):
        """Adding an expense to a FINALIZED remittance is blocked."""
        with self.assertRaises(InternalError), transaction.atomic():
            Expense.objects.create(
                remittance=self.remittance,
                description="late addition",
                amount=Decimal("50.00"),
                recorded_by=self.user,
            )

    def test_draft_can_still_be_finalized(self):
        """The DRAFT -> FINALIZED transition (OLD.status = DRAFT) is allowed."""
        draft = Remittance.objects.create(
            date=date(2026, 8, 9),
            created_by=self.user,
            status=Remittance.StatusChoices.DRAFT,
        )
        finalize_remittance(
            performed_by=self.user,
            remittance_id=draft.id,
            pin="1234",
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, Remittance.StatusChoices.FINALIZED)
