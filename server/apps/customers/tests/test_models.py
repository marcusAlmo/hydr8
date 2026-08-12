from decimal import Decimal
from django.test import SimpleTestCase
from apps.customers.models import Customer, CreditLine, CreditPayment
from apps.core.models import Product
from apps.tests.fakes import FakeCustomerRepository


class CustomerModelTests(SimpleTestCase):
    def test_customer_str(self):
        """Test Customer string representation is a non-PII display ID."""
        customer = Customer(name="John Doe Store", pk=1)
        self.assertEqual(str(customer), "HY-0001")

    def test_customer_defaults(self):
        """Test Customer default balance and borrowed counts."""
        customer = Customer(name="Jane Smith")
        self.assertEqual(customer.debt_balance, Decimal("0.00") if isinstance(customer.debt_balance, Decimal) else 0.00)
        self.assertEqual(customer.borrowed_round_8gal, 0)
        self.assertEqual(customer.borrowed_slim_8gal, 0)
        self.assertEqual(customer.borrowed_other, 0)

    def test_credit_line_str(self):
        """Test CreditLine string representation."""
        customer = Customer(name="Store A")
        product = Product(name="Water 5G", variation="Slim")
        credit_line = CreditLine(customer=customer, product=product, qty_remaining=5)
        self.assertEqual(str(credit_line), "Store A - Water 5G (5 left)")

    def test_credit_payment_str(self):
        """Test CreditPayment string representation."""
        customer = Customer(name="Store B")
        product = Product(name="Water 5G", variation="Round")
        credit_line = CreditLine(customer=customer, product=product, qty_remaining=2)
        payment = CreditPayment(credit_line=credit_line, amount=Decimal("150.00"))
        self.assertEqual(str(payment), f"Payment of 150.00 for {str(credit_line)}")

    def test_fake_customer_repository(self):
        """Test FakeCustomerRepository in-memory operations."""
        repo = FakeCustomerRepository()
        cust = repo.create_customer(name="Reseller X", debt_balance=500.0, borrowed_round_8gal=3)

        self.assertEqual(cust['name'], "Reseller X")
        self.assertEqual(cust['debt_balance'], 500.0)
        self.assertEqual(cust['borrowed_round_8gal'], 3)
        self.assertEqual(len(repo.all()), 1)
