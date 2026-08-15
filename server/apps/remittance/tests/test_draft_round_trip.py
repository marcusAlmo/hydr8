"""Round-trip tests for the "Save as Draft" flow.

Verifies that EVERY field the Add Remittance form sends is persisted by
``save_remittance_draft`` and faithfully restored by
``_load_draft_state`` (the selector used to re-hydrate the form after a
page refresh or "Load draft" click).

Fields covered:
  - Rider: sold qty, commission_override, remitted, expenses, deductions
  - Staff: salary_override, deductions
  - Top-level: other_sales, manual_offering, tithe_rate
  - Remittance parent: date, status, created_by
"""
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Product
from apps.remittance.models import (
    Expense,
    Remittance,
    RemittanceRider,
    RemittanceRiderProductLine,
    RemittanceStaff,
    RiderDeduction,
    StaffDeduction,
)
from apps.remittance.selectors import _load_draft_state
from apps.remittance.services import save_remittance_draft
from apps.users.models import DriverCommission, Role, User


class DraftRoundTripTests(TestCase):
    """End-to-end: save → reload → verify every field round-trips."""

    def setUp(self):
        cache.clear()
        self.admin_role, _ = Role.objects.get_or_create(name="Admin")
        self.staff_role, _ = Role.objects.get_or_create(name="Staff")
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

        self.staff = User.objects.create_user(
            username="staff1",
            password="securepassword123",
            first_name="St",
            last_name="Aff",
            role=self.staff_role,
            daily_rate=Decimal("500.00"),
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

        self.remittance_date = timezone.localdate()

    def tearDown(self):
        cache.clear()

    # --- helpers ------------------------------------------------------------

    def _full_payload(self):
        """Returns a payload mirroring exactly what the Alpine.js
        ``saveDraft()`` method sends to the backend."""
        return {
            "riders": [
                {
                    "id": str(self.rider.pk),
                    "commission_override": "150.00",
                    "remitted": "300.00",
                    "product_lines": [
                        {
                            "product_key": str(self.product.pk),
                            "sold": 10,
                            "credited": 0,
                            "borrowed": 0,
                            "repaid": 0,
                        },
                    ],
                    "expenses": [
                        {"description": "Gas", "amount": "50.00"},
                        {"description": "Parking", "amount": "20.00"},
                    ],
                    "deductions": [
                        {"description": "Cash advance", "amount": "30.00"},
                    ],
                },
            ],
            # General expenses array is always [] from the frontend —
            # per-rider expenses travel inside each rider payload.
            "expenses": [],
            "otherSales": "100.00",
            "staff": [
                {
                    "id": str(self.staff.pk),
                    "salary_override": "600.00",
                    "deductions": [
                        {"description": "Late", "amount": "25.00"},
                    ],
                },
            ],
            "manualOffering": "50.00",
            "titheRate": "0.10",
            "remittanceDate": self.remittance_date.isoformat(),
        }

    # --- tests --------------------------------------------------------------

    def test_draft_persists_all_parent_fields(self):
        """The Remittance parent row stores date, status, offering, and
        tithe rate."""
        payload = self._full_payload()
        rem = save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        self.assertEqual(rem.date, self.remittance_date)
        self.assertEqual(rem.status, Remittance.StatusChoices.DRAFT)
        self.assertEqual(rem.created_by, self.admin)
        self.assertEqual(rem.offering_amount, Decimal("50.00"))
        self.assertEqual(rem.tithe_rate_snapshot, Decimal("0.10"))
        self.assertEqual(rem.total_other_sales, Decimal("100.00"))

    def test_draft_persists_rider_product_line(self):
        """Rider product line stores qty_sold and snapshots."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        line = RemittanceRiderProductLine.objects.get(
            remittance_rider__rider=self.rider,
            product=self.product,
        )
        self.assertEqual(line.qty_sold, 10)
        self.assertEqual(line.unit_price_snapshot, Decimal("40.00"))
        self.assertEqual(line.commission_rate_snapshot, Decimal("5.00"))

    def test_draft_persists_rider_commission_override_and_remitted(self):
        """Rider commission_override and remitted are persisted."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        rr = RemittanceRider.objects.get(
            remittance__date=self.remittance_date,
            rider=self.rider,
        )
        self.assertEqual(rr.commission_override, Decimal("150.00"))
        self.assertEqual(rr.remitted, Decimal("300.00"))

    def test_draft_persists_rider_expenses(self):
        """Per-rider expenses are persisted with remittance_rider set."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        expenses = list(
            Expense.objects.filter(
                remittance__date=self.remittance_date,
                remittance_rider__rider=self.rider,
            ).order_by("id")
        )
        self.assertEqual(len(expenses), 2)
        self.assertEqual(expenses[0].description, "Gas")
        self.assertEqual(expenses[0].amount, Decimal("50.00"))
        self.assertEqual(expenses[1].description, "Parking")
        self.assertEqual(expenses[1].amount, Decimal("20.00"))

    def test_draft_persists_rider_deductions(self):
        """Per-rider deductions are persisted."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        deductions = list(
            RiderDeduction.objects.filter(
                remittance_rider__rider=self.rider,
            ).order_by("id")
        )
        self.assertEqual(len(deductions), 1)
        self.assertEqual(deductions[0].description, "Cash advance")
        self.assertEqual(deductions[0].amount, Decimal("30.00"))

    def test_draft_persists_staff_salary_override(self):
        """Staff salary_override is persisted on RemittanceStaff."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        rs = RemittanceStaff.objects.get(
            remittance__date=self.remittance_date,
            staff=self.staff,
        )
        self.assertEqual(rs.salary_override, Decimal("600.00"))
        self.assertEqual(rs.daily_rate_snapshot, Decimal("500.00"))

    def test_draft_persists_staff_deductions(self):
        """Staff deductions are persisted."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        deductions = list(
            StaffDeduction.objects.filter(
                remittance_staff__staff=self.staff,
            ).order_by("id")
        )
        self.assertEqual(len(deductions), 1)
        self.assertEqual(deductions[0].description, "Late")
        self.assertEqual(deductions[0].amount, Decimal("25.00"))

    # --- round-trip (save → reload) -----------------------------------------

    def test_round_trip_rider_sold_quantities(self):
        """Sold quantities survive a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        self.assertIsNotNone(state)
        sold = state["rider_sold"][str(self.rider.pk)][str(self.product.pk)]
        self.assertEqual(sold, 10)

    def test_round_trip_rider_expenses(self):
        """Per-rider expenses survive a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        expenses = state["rider_expenses"][str(self.rider.pk)]
        self.assertEqual(len(expenses), 2)
        self.assertEqual(expenses[0]["description"], "Gas")
        self.assertEqual(expenses[0]["amount"], "50.00")
        self.assertEqual(expenses[1]["description"], "Parking")
        self.assertEqual(expenses[1]["amount"], "20.00")

    def test_round_trip_rider_deductions(self):
        """Per-rider deductions survive a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        deductions = state["rider_deductions"][str(self.rider.pk)]
        self.assertEqual(len(deductions), 1)
        self.assertEqual(deductions[0]["description"], "Cash advance")
        self.assertEqual(deductions[0]["amount"], "30.00")

    def test_round_trip_rider_commission_override(self):
        """Rider commission_override survives a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        self.assertEqual(
            state["rider_commission_overrides"][str(self.rider.pk)],
            "150.00",
        )

    def test_round_trip_rider_remitted(self):
        """Rider remitted amount survives a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        self.assertEqual(
            state["rider_remittances"][str(self.rider.pk)],
            "300.00",
        )

    def test_round_trip_staff_salary_override(self):
        """Staff salary_override survives a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        staff_data = state["staff_data"][str(self.staff.pk)]
        self.assertEqual(staff_data["salary_override"], "600.00")

    def test_round_trip_staff_deductions(self):
        """Staff deductions survive a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        staff_data = state["staff_data"][str(self.staff.pk)]
        self.assertEqual(len(staff_data["deductions"]), 1)
        self.assertEqual(staff_data["deductions"][0]["description"], "Late")
        self.assertEqual(staff_data["deductions"][0]["amount"], "25.00")

    def test_round_trip_other_sales(self):
        """other_sales survives a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        self.assertEqual(state["other_sales"], 100.0)

    def test_round_trip_offering_amount(self):
        """manual_offering survives a save → reload cycle."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )
        state = _load_draft_state(self.admin, self.remittance_date)
        self.assertEqual(state["offering_amount"], "50.00")

    # --- upsert (save → save again) -----------------------------------------

    def test_upsert_replaces_all_data(self):
        """Saving a draft twice replaces all child rows — no orphans,
        no duplicates, and new values are persisted."""
        payload = self._full_payload()
        rem1 = save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )

        # Save again with different values.
        payload2 = self._full_payload()
        payload2["riders"][0]["product_lines"][0]["sold"] = 20
        payload2["riders"][0]["commission_override"] = "200.00"
        payload2["riders"][0]["remitted"] = "400.00"
        payload2["riders"][0]["expenses"] = [
            {"description": "Fuel", "amount": "60.00"},
        ]
        payload2["riders"][0]["deductions"] = []
        payload2["otherSales"] = "200.00"
        payload2["manualOffering"] = "75.00"
        payload2["staff"][0]["salary_override"] = "650.00"
        payload2["staff"][0]["deductions"] = []

        rem2 = save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload2["riders"],
            expenses_data=payload2["expenses"],
            manual_offering=payload2["manualOffering"],
            tithe_rate=payload2["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload2["otherSales"],
            staff_data=payload2["staff"],
        )

        # Old draft deleted, new one created.
        self.assertNotEqual(rem1.id, rem2.id)
        self.assertFalse(
            Remittance.objects.filter(id=rem1.id).exists()
        )

        # No orphaned child rows from the old draft.
        self.assertEqual(
            Expense.objects.filter(remittance_id=rem1.id).count(), 0
        )
        self.assertEqual(
            RiderDeduction.objects.filter(
                remittance_rider__remittance_id=rem1.id
            ).count(), 0
        )

        # New values persisted.
        line = RemittanceRiderProductLine.objects.get(
            remittance_rider__rider=self.rider,
            product=self.product,
        )
        self.assertEqual(line.qty_sold, 20)
        rr = RemittanceRider.objects.get(
            remittance__date=self.remittance_date,
            rider=self.rider,
        )
        self.assertEqual(rr.commission_override, Decimal("200.00"))
        self.assertEqual(rr.remitted, Decimal("400.00"))

        # Only 1 expense (the new one), not 3 (old 2 + new 1).
        self.assertEqual(
            Expense.objects.filter(
                remittance=rem2,
                remittance_rider__rider=self.rider,
            ).count(), 1
        )

        # No rider deductions (cleared in payload2).
        self.assertEqual(
            RiderDeduction.objects.filter(
                remittance_rider__remittance=rem2,
            ).count(), 0
        )

        # Staff override updated, deductions cleared.
        rs = RemittanceStaff.objects.get(
            remittance=rem2,
            staff=self.staff,
        )
        self.assertEqual(rs.salary_override, Decimal("650.00"))
        self.assertEqual(
            StaffDeduction.objects.filter(
                remittance_staff=rs,
            ).count(), 0
        )

        # Top-level fields updated.
        rem2.refresh_from_db()
        self.assertEqual(rem2.total_other_sales, Decimal("200.00"))
        self.assertEqual(rem2.offering_amount, Decimal("75.00"))

    def test_upsert_reloads_new_values_via_selector(self):
        """After saving twice, _load_draft_state returns the NEW values,
        not the old ones."""
        payload = self._full_payload()
        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload["riders"],
            expenses_data=payload["expenses"],
            manual_offering=payload["manualOffering"],
            tithe_rate=payload["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload["otherSales"],
            staff_data=payload["staff"],
        )

        # Save again with different values.
        payload2 = self._full_payload()
        payload2["riders"][0]["product_lines"][0]["sold"] = 20
        payload2["riders"][0]["commission_override"] = "200.00"
        payload2["riders"][0]["remitted"] = "400.00"
        payload2["riders"][0]["expenses"] = [
            {"description": "Fuel", "amount": "60.00"},
        ]
        payload2["riders"][0]["deductions"] = []
        payload2["otherSales"] = "200.00"
        payload2["manualOffering"] = "75.00"
        payload2["staff"][0]["salary_override"] = "650.00"
        payload2["staff"][0]["deductions"] = []

        save_remittance_draft(
            performed_by=self.admin,
            riders_data=payload2["riders"],
            expenses_data=payload2["expenses"],
            manual_offering=payload2["manualOffering"],
            tithe_rate=payload2["titheRate"],
            remittance_date=self.remittance_date,
            other_sales=payload2["otherSales"],
            staff_data=payload2["staff"],
        )

        state = _load_draft_state(self.admin, self.remittance_date)

        # New sold qty
        self.assertEqual(
            state["rider_sold"][str(self.rider.pk)][str(self.product.pk)],
            20,
        )
        # New commission override
        self.assertEqual(
            state["rider_commission_overrides"][str(self.rider.pk)],
            "200.00",
        )
        # New remitted
        self.assertEqual(
            state["rider_remittances"][str(self.rider.pk)],
            "400.00",
        )
        # Only the new expense
        expenses = state["rider_expenses"][str(self.rider.pk)]
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0]["description"], "Fuel")
        self.assertEqual(expenses[0]["amount"], "60.00")
        # No deductions
        self.assertEqual(
            state["rider_deductions"][str(self.rider.pk)], []
        )
        # New other_sales
        self.assertEqual(state["other_sales"], 200.0)
        # New offering
        self.assertEqual(state["offering_amount"], "75.00")
        # New staff override
        staff_data = state["staff_data"][str(self.staff.pk)]
        self.assertEqual(staff_data["salary_override"], "650.00")
        # No staff deductions
        self.assertEqual(staff_data["deductions"], [])
