"""Tests for the Customers ranking selectors and HTMX view endpoints."""
from datetime import date, timedelta
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
from apps.customers.selectors import (
    get_prompt_returner_count,
    get_prompt_returners,
    get_prompt_returners_paginated,
    get_top_payer_count,
    get_top_payers,
    get_top_payers_paginated,
)
from apps.users.models import Role, User


def _make_staff_user(**kwargs) -> User:
    """Creates a test user with the canonical Staff back-office role."""
    staff_role, _ = Role.objects.get_or_create(name="Staff", company=None)
    return User.objects.create_user(role=staff_role, **kwargs)


class RankingSelectorTests(TestCase):
    """Tests for the top-payer and prompt-returner selector functions."""

    def setUp(self):
        cache.clear()
        self.user = _make_staff_user(
            username="rankingstaff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )

        self.big_payer = Customer.objects.create(name="Big Payer Store")
        self.small_payer = Customer.objects.create(name="Small Payer Store")
        self.no_payer = Customer.objects.create(name="No Payer Store")

        big_line = CreditLine.objects.create(
            customer=self.big_payer,
            product=self.product,
            qty_credited=10,
            qty_remaining=0,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("400.00"),
        )
        small_line = CreditLine.objects.create(
            customer=self.small_payer,
            product=self.product,
            qty_credited=5,
            qty_remaining=0,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )

        CreditPayment.objects.create(
            credit_line=big_line,
            amount=Decimal("400.00"),
            containers_paid=10,
            paid_at=date.today(),
            recorded_by=self.user,
        )
        CreditPayment.objects.create(
            credit_line=small_line,
            amount=Decimal("200.00"),
            containers_paid=5,
            paid_at=date.today(),
            recorded_by=self.user,
        )

        self.fast_returner = Customer.objects.create(name="Fast Returner")
        self.slow_returner = Customer.objects.create(name="Slow Returner")

        BorrowedContainer.objects.create(
            customer=self.fast_returner,
            container_key="round_8gal",
            qty_borrowed=5,
            qty_returned=5,
            transaction_date=date.today() - timedelta(days=10),
            returned_at=date.today() - timedelta(days=7),
            recorded_by=self.user,
        )
        BorrowedContainer.objects.create(
            customer=self.slow_returner,
            container_key="round_8gal",
            qty_borrowed=5,
            qty_returned=5,
            transaction_date=date.today() - timedelta(days=20),
            returned_at=date.today() - timedelta(days=7),
            recorded_by=self.user,
        )

    def tearDown(self):
        cache.clear()

    def test_top_payers_sorted_by_total_paid_descending(self):
        """Payers are ordered from highest to lowest total paid."""
        payers = get_top_payers(self.user, limit=None)

        self.assertEqual(len(payers), 2)
        self.assertEqual(payers[0]["name"], "Big Payer Store")
        self.assertEqual(payers[0]["rank"], 1)
        self.assertEqual(payers[1]["name"], "Small Payer Store")
        self.assertEqual(payers[1]["rank"], 2)

    def test_top_payers_respects_limit(self):
        """The limit parameter truncates the result list."""
        payers = get_top_payers(self.user, limit=1)

        self.assertEqual(len(payers), 1)
        self.assertEqual(payers[0]["name"], "Big Payer Store")

    def test_top_payer_count_excludes_no_payer(self):
        """Only customers with at least one payment are counted."""
        count = get_top_payer_count(self.user)

        self.assertEqual(count, 2)

    def test_top_payers_paginated_includes_count_and_pagination(self):
        """The paginated selector returns the list plus pagination metadata."""
        data = get_top_payers_paginated(self.user, page=1)

        self.assertIn("top_payers", data)
        self.assertIn("payer_count", data)
        self.assertIn("pagination", data)
        self.assertEqual(data["payer_count"], 2)
        self.assertEqual(len(data["top_payers"]), 2)

    def test_prompt_returners_sorted_by_fastest_return(self):
        """Returners are ordered by the fewest average return days."""
        returners = get_prompt_returners(self.user, limit=None)

        self.assertEqual(len(returners), 2)
        self.assertEqual(returners[0]["name"], "Fast Returner")
        self.assertEqual(returners[0]["avg_return_days"], 3)
        self.assertEqual(returners[1]["name"], "Slow Returner")
        self.assertEqual(returners[1]["avg_return_days"], 13)

    def test_prompt_returner_count(self):
        """Only customers with at least one returned container are counted."""
        count = get_prompt_returner_count(self.user)

        self.assertEqual(count, 2)

    def test_prompt_returners_paginated(self):
        """The paginated selector returns the list plus pagination metadata."""
        data = get_prompt_returners_paginated(self.user, page=1)

        self.assertIn("prompt_returners", data)
        self.assertIn("returner_count", data)
        self.assertIn("pagination", data)
        self.assertEqual(data["returner_count"], 2)

    def test_selectors_use_constant_queries(self):
        """Ranking selectors must not trigger N+1 queries."""
        with self.assertNumQueries(1):
            _ = get_top_payers(self.user, limit=None)

        with self.assertNumQueries(1):
            _ = get_prompt_returners(self.user, limit=None)


class RankingViewTests(TestCase):
    """Tests for the HTMX top-payers and prompt-returners endpoints."""

    def setUp(self):
        cache.clear()
        self.user = _make_staff_user(
            username="rankingviewstaff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )

        self.payer = Customer.objects.create(name="Payer Store")
        line = CreditLine.objects.create(
            customer=self.payer,
            product=self.product,
            qty_credited=5,
            qty_remaining=0,
            unit_price_snapshot=Decimal("40.00"),
            total_credit_amount=Decimal("200.00"),
        )
        CreditPayment.objects.create(
            credit_line=line,
            amount=Decimal("200.00"),
            containers_paid=5,
            paid_at=date.today(),
            recorded_by=self.user,
        )

        self.returner = Customer.objects.create(name="Returner Store")
        BorrowedContainer.objects.create(
            customer=self.returner,
            container_key="round_8gal",
            qty_borrowed=3,
            qty_returned=3,
            transaction_date=date.today() - timedelta(days=5),
            returned_at=date.today() - timedelta(days=2),
            recorded_by=self.user,
        )

        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_top_payers_view_requires_login(self):
        """Anonymous users are redirected, not shown the partial."""
        self.client.logout()
        response = self.client.get(reverse("customers:top_payers"))
        self.assertEqual(response.status_code, 302)

    def test_top_payers_view_returns_fragment(self):
        """The endpoint renders the Top Payers card partial."""
        response = self.client.get(reverse("customers:top_payers"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customers/partials/top_payers_card.html")
        self.assertContains(response, "Payer Store")

    def test_top_payers_view_handles_page_param(self):
        """A ?page= query parameter is accepted without error."""
        response = self.client.get(
            reverse("customers:top_payers") + "?page=1"
        )
        self.assertEqual(response.status_code, 200)

    def test_prompt_returners_view_returns_fragment(self):
        """The endpoint renders the Prompt Returners card partial."""
        response = self.client.get(reverse("customers:prompt_returners"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "customers/partials/prompt_returners_card.html"
        )
        self.assertContains(response, "Returner Store")

    def test_prompt_returners_view_requires_login(self):
        """Anonymous users are redirected from the returner partial."""
        self.client.logout()
        response = self.client.get(reverse("customers:prompt_returners"))
        self.assertEqual(response.status_code, 302)

    def test_prompt_returners_view_rejects_post(self):
        """The ranking endpoints are GET-only."""
        response = self.client.post(reverse("customers:prompt_returners"))
        self.assertEqual(response.status_code, 405)

    def test_top_payers_view_pagination_context(self):
        """The view passes a pagination dict to the template."""
        response = self.client.get(reverse("customers:top_payers"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("pagination", response.context)
        pag = response.context["pagination"]
        self.assertEqual(pag["current_page"], 1)
        self.assertEqual(pag["total_pages"], 1)

    def test_top_payers_view_invalid_page_defaults_to_one(self):
        """A non-numeric page query falls back to page 1."""
        response = self.client.get(
            reverse("customers:top_payers") + "?page=not-a-number"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pagination"]["current_page"], 1)

    def test_prompt_returners_view_pagination_context(self):
        """The prompt returners view passes pagination context."""
        response = self.client.get(reverse("customers:prompt_returners"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("pagination", response.context)
        pag = response.context["pagination"]
        self.assertEqual(pag["current_page"], 1)


class RankingPaginationViewTests(TestCase):
    """Tests for actual multi-page pagination on the ranking endpoints."""

    def setUp(self):
        cache.clear()
        self.user = _make_staff_user(
            username="paginationstaff",
            password="securepassword123",
        )
        self.product = Product.objects.create(
            name="Alkaline Water",
            variation="Round",
            price=Decimal("40.00"),
        )

        # 12 payers so page 1 has 10 and page 2 has 2.
        for i in range(12):
            customer = Customer.objects.create(name=f"Payer {i:02d}")
            line = CreditLine.objects.create(
                customer=customer,
                product=self.product,
                qty_credited=1,
                qty_remaining=0,
                unit_price_snapshot=Decimal("40.00"),
                total_credit_amount=Decimal("40.00"),
            )
            CreditPayment.objects.create(
                credit_line=line,
                amount=Decimal("40.00"),
                containers_paid=1,
                paid_at=date.today(),
                recorded_by=self.user,
            )

        self.client.force_login(self.user)

    def tearDown(self):
        cache.clear()

    def test_top_payers_view_page_two(self):
        """Page 2 of the paginated endpoint renders the remaining customers."""
        response = self.client.get(
            reverse("customers:top_payers") + "?page=2"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "customers/partials/top_payers_card.html")
        self.assertEqual(response.context["pagination"]["current_page"], 2)
        self.assertEqual(len(response.context["top_payers"]), 2)
        self.assertContains(response, "Payer 10")

    def test_top_payers_view_page_out_of_range_returns_last_page(self):
        """A page beyond the last page falls back to the last page."""
        response = self.client.get(
            reverse("customers:top_payers") + "?page=999"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["pagination"]["current_page"], 2)
