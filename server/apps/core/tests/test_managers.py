"""Tests for the TenantQuerySet / TenantManager tenant-scoping logic.

The ``for_user`` method is the single entry point for tenant-scoped
queries across the entire codebase. These tests verify that it correctly
filters by company for regular users and returns unfiltered querysets
for superusers and users without a company.
"""
from decimal import Decimal

from django.test import TestCase

from apps.core.models import Product
from apps.core.models import Company
from apps.users.models import User


class TenantQuerySetForUserTests(TestCase):
    """Tests for TenantQuerySet.for_user()."""

    def setUp(self):
        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")
        self.user_a = User.objects.create_user(
            username="user_a", password="pass123", company=self.company_a
        )
        self.user_b = User.objects.create_user(
            username="user_b", password="pass123", company=self.company_b
        )
        self.superuser = User.objects.create_superuser(
            username="super", password="pass123"
        )
        self.user_no_company = User.objects.create_user(
            username="no_company", password="pass123"
        )
        # Products in different companies
        Product.objects.create(
            name="Product A", variation="1L", price=Decimal("10.00"),
            company=self.company_a,
        )
        Product.objects.create(
            name="Product B", variation="1L", price=Decimal("10.00"),
            company=self.company_b,
        )

    def test_filters_by_company_for_regular_user(self):
        """A regular user only sees products in their company."""
        qs = Product.objects.for_user(self.user_a)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().company, self.company_a)

    def test_superuser_sees_all(self):
        """A superuser sees all products regardless of company."""
        qs = Product.objects.for_user(self.superuser)
        self.assertEqual(qs.count(), 2)

    def test_user_without_company_sees_all(self):
        """A user with no company sees all products."""
        qs = Product.objects.for_user(self.user_no_company)
        self.assertEqual(qs.count(), 2)

    def test_user_with_null_company_id_sees_all(self):
        """A user whose company_id is None sees all products."""
        self.user_a.company_id = None
        self.user_a.save(update_fields=["company"])
        qs = Product.objects.for_user(self.user_a)
        self.assertEqual(qs.count(), 2)

    def test_different_companies_are_isolated(self):
        """Users from different companies see only their own data."""
        qs_a = Product.objects.for_user(self.user_a)
        qs_b = Product.objects.for_user(self.user_b)
        self.assertEqual(qs_a.first().company, self.company_a)
        self.assertEqual(qs_b.first().company, self.company_b)
        self.assertNotEqual(qs_a.first(), qs_b.first())
