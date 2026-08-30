from decimal import Decimal

from django.test import SimpleTestCase

from apps.core.models import Product
from apps.remittance.models import (
    Expense,
    Remittance,
    RemittanceRider,
    RemittanceRiderProductLine,
    RiderCredit,
    RiderCreditRepayment,
)
from apps.tests.fakes import FakeRemittanceRepository
from apps.users.models import User


class RemittanceModelTests(SimpleTestCase):
    def test_remittance_str(self):
        """Test Remittance string representation."""
        remittance = Remittance(date="2026-08-02", status=Remittance.StatusChoices.DRAFT)
        self.assertEqual(str(remittance), "Remittance 2026-08-02 (DRAFT)")

    def test_remittance_rider_str(self):
        """Test RemittanceRider string representation."""
        rider_user = User(username="driver1")
        remittance = Remittance(date="2026-08-02")
        rider = RemittanceRider(remittance=remittance, rider=rider_user)
        self.assertEqual(str(rider), "Rider driver1 for 2026-08-02")

    def test_remittance_rider_product_line_str(self):
        """Test RemittanceRiderProductLine string representation."""
        rider_user = User(username="driver1")
        remittance = Remittance(date="2026-08-02")
        rider = RemittanceRider(remittance=remittance, rider=rider_user)
        product = Product(name="Gallon Water", variation="8 Gal Round")
        line = RemittanceRiderProductLine(remittance_rider=rider, product=product)
        self.assertEqual(str(line), f"Gallon Water line for {rider!s}")

    def test_expense_str(self):
        """Test Expense string representation."""
        expense = Expense(description="Gasoline", amount=Decimal("500.00"))
        self.assertEqual(str(expense), "Expense: Gasoline (500.00)")

    def test_rider_credit_str_and_defaults(self):
        """Test RiderCredit string representation and default states."""
        rider_user = User(username="driver2")
        credit = RiderCredit(rider=rider_user, recipient_name="Alice", amount=Decimal("200.00"))
        self.assertFalse(credit.is_repaid)
        self.assertEqual(str(credit), "RiderCredit (unsaved)")

    def test_rider_credit_repayment_str(self):
        """Test RiderCreditRepayment string representation."""
        rider_user = User(username="driver2")
        credit = RiderCredit(rider=rider_user, recipient_name="Alice", amount=Decimal("200.00"))
        repayment = RiderCreditRepayment(rider_credit=credit, amount_repaid=Decimal("100.00"))
        self.assertEqual(str(repayment), "RiderCreditRepayment (unsaved)")

    def test_fake_remittance_repository(self):
        """Test FakeRemittanceRepository in-memory store operations."""
        repo = FakeRemittanceRepository()
        rem = repo.create_remittance(date_str="2026-08-02", created_by_id=10, total_sales=1500.0, net_profit=1200.0)

        self.assertEqual(rem['date'], "2026-08-02")
        self.assertEqual(rem['status'], "DRAFT")
        self.assertEqual(rem['total_sales'], 1500.0)
        self.assertEqual(len(repo.filter(status="DRAFT")), 1)
