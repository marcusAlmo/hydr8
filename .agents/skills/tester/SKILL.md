---
name: tester
description: >
  Activates when the user asks to write tests, test a view, verify behavior,
  add unit tests, add integration tests, add test coverage, or when the Developer skill
  explicitly hands off to the tester. Also triggers on phrases like "write tests for",
  "add test coverage", "test this service", "verify this works", or "test cases for".
---

# Tester Skill — Hydr8

You are the **QA & Test Engineer** for Hydr8. You receive implementation hand-offs from the Developer and produce comprehensive test suites that verify correctness, edge cases, and security behavior. You hand off security-specific concerns to the Cybersec skill.

## Testing Philosophy

- **Test behavior, not implementation.** Tests should verify what the code does, not how.
- **Every service function** must have at least one happy-path and one failure-path test.
- **Every view** must have tests for: successful auth, unauthenticated access (redirect to login), forbidden (403 if role-restricted), invalid input (400), and the happy path.
- **Every HTMX partial view** must verify the returned fragment contains expected content and uses the correct template.
- **Every list selector and list view** that fetches related models must include query count assertions (e.g. `self.assertNumQueries(N)`) to catch and prevent N+1 queries.
- **Every model constraint** (unique, check) must have a test verifying it raises an error on violation.
- **Financial calculations** must be tested with `Decimal` precision — never use `float` in test assertions for money.

## Test Structure Convention

```
apps/<domain>/tests/
├── __init__.py
├── test_services.py    # Service layer — business logic, financial calculations
├── test_selectors.py   # Selector layer — query efficiency, N+1 prevention
├── test_views.py       # View layer — HTTP status, template rendering, HTMX responses
└── test_models.py      # Model constraints, soft-delete behavior, __str__
```

For small domains, a single `apps/<domain>/tests.py` is acceptable.

## Test Class Patterns

### View Tests (Django Client — not APIClient)

```python
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


class RemittanceHistoryViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='StrongTestPass123!',
            first_name='Test',
            last_name='User',
        )

    # --- Authentication Guard Tests (MANDATORY for every view) ---

    def test_unauthenticated_request_redirects_to_login(self):
        """Unauthenticated users must be redirected to login, not shown the page."""
        response = self.client.get(reverse('remittance:history'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_authenticated_user_can_access_page(self):
        """Authenticated users can access the history page."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.get(reverse('remittance:history'))
        self.assertEqual(response.status_code, 200)

    # --- Template Rendering Tests ---

    def test_uses_correct_template(self):
        """View must render the expected template."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.get(reverse('remittance:history'))
        self.assertTemplateUsed(response, 'remittance/history.html')

    def test_context_contains_remittances(self):
        """Context must include the remittances queryset."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.get(reverse('remittance:history'))
        self.assertIn('remittances', response.context)
```

### HTMX Partial View Tests

```python
class ToggleTithesViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='StrongTestPass123!',
        )
        self.remittance = Remittance.objects.create(
            date=date.today(),
            created_by=self.user,
            status=Remittance.StatusChoices.FINALIZED,
        )

    def test_htmx_partial_returns_fragment(self):
        """HTMX POST must return the row partial, not a full page."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.post(
            reverse('remittance:toggle_tithes', args=[self.remittance.id]),
            HTTP_HX_REQUEST='true',  # Simulate HTMX request header
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'remittance/partials/remittance_row.html')

    def test_htmx_partial_contains_updated_state(self):
        """Returned fragment must reflect the toggled state."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.post(
            reverse('remittance:toggle_tithes', args=[self.remittance.id]),
            HTTP_HX_REQUEST='true',
        )
        self.assertContains(response, '☑')  # Tithes now paid

    def test_get_request_returns_405(self):
        """HTMX mutation endpoints must reject GET requests."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        response = self.client.get(
            reverse('remittance:toggle_tithes', args=[self.remittance.id]),
        )
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_returns_redirect(self):
        """Unauthenticated POST must redirect, not mutate data."""
        response = self.client.post(
            reverse('remittance:toggle_tithes', args=[self.remittance.id]),
        )
        self.assertEqual(response.status_code, 302)
```

### HTMX Redirect View Tests

```python
class FinalizeRemittanceViewTests(TestCase):

    def test_successful_finalize_returns_hx_redirect(self):
        """Successful finalization must set HX-Redirect header."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        self.user.set_pin('1234')
        self.user.save()

        response = self.client.post(
            reverse('remittance:finalize', args=[self.remittance.id]),
            data={'pin': '1234'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['HX-Redirect'], reverse('analytics:dashboard'))

    def test_wrong_pin_returns_error_fragment(self):
        """Wrong PIN must return error partial with 400 status."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        self.user.set_pin('1234')
        self.user.save()

        response = self.client.post(
            reverse('remittance:finalize', args=[self.remittance.id]),
            data={'pin': '9999'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'remittance/partials/finalize_error.html')
```

### Service Layer Tests

```python
from django.test import TestCase
from django.core.exceptions import ValidationError
from decimal import Decimal
from apps.remittance.services import create_credit_line
from apps.customers.models import Customer


class CreateCreditLineServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='StrongTestPass123!',
        )
        self.customer = Customer.objects.create(name='Test Customer')
        self.product = Product.objects.create(name='Round 5gal', price=Decimal('50.00'))

    def test_creates_credit_line_successfully(self):
        """Happy path — valid inputs create a credit line."""
        result = create_credit_line(
            customer_id=self.customer.id,
            product_id=self.product.id,
            qty_credited=5,
            unit_price=Decimal('50.00'),
            performed_by=self.user,
        )
        self.assertIsNotNone(result.id)
        self.assertEqual(result.qty_remaining, 5)
        self.assertEqual(result.total_credit_amount, Decimal('250.00'))

    def test_updates_customer_debt_balance_atomically(self):
        """Credit line creation must update customer's debt balance."""
        create_credit_line(
            customer_id=self.customer.id,
            product_id=self.product.id,
            qty_credited=5,
            unit_price=Decimal('50.00'),
            performed_by=self.user,
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.debt_balance, Decimal('250.00'))

    def test_raises_when_qty_zero(self):
        """Zero quantity must raise ValidationError."""
        with self.assertRaises(ValidationError):
            create_credit_line(
                customer_id=self.customer.id,
                product_id=self.product.id,
                qty_credited=0,
                unit_price=Decimal('50.00'),
                performed_by=self.user,
            )

    def test_raises_when_customer_not_found(self):
        """Non-existent customer must raise ValidationError."""
        with self.assertRaises(ValidationError):
            create_credit_line(
                customer_id=99999,
                product_id=self.product.id,
                qty_credited=5,
                unit_price=Decimal('50.00'),
                performed_by=self.user,
            )

    def test_financial_precision_is_decimal_not_float(self):
        """Credit amount must be Decimal, not float — no precision loss."""
        result = create_credit_line(
            customer_id=self.customer.id,
            product_id=self.product.id,
            qty_credited=3,
            unit_price=Decimal('33.33'),
            performed_by=self.user,
        )
        self.assertIsInstance(result.total_credit_amount, Decimal)
        self.assertEqual(result.total_credit_amount, Decimal('99.99'))
```

### Model Constraint Tests

```python
from django.test import TestCase
from django.db import IntegrityError
from apps.users.models import Role


class RoleModelConstraintTests(TestCase):

    def test_duplicate_role_name_raises_integrity_error(self):
        """Unique role name constraint is enforced."""
        Role.objects.create(name='Admin', description='Admin role')
        with self.assertRaises(IntegrityError):
            Role.objects.create(name='Admin', description='Duplicate')

    def test_soft_deleted_role_allows_reuse_of_name(self):
        """Soft-deleted roles do not block new active roles with same name."""
        from django.utils import timezone
        old = Role.objects.create(name='Manager', description='Old')
        old.deleted_at = timezone.now()
        old.save()
        # Should not raise
        new = Role.objects.create(name='Manager', description='New active')
        self.assertIsNotNone(new.id)
```

### Session/Auth Tests

```python
class LoginViewTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='StrongTestPass123!',
        )

    def test_successful_login_redirects_via_htmx(self):
        """Successful HTMX login must set HX-Redirect header."""
        response = self.client.post(
            reverse('users:login'),
            data={'username': 'testuser', 'password': 'StrongTestPass123!'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('HX-Redirect', response.headers)

    def test_failed_login_returns_form_with_errors(self):
        """Failed login must re-render the form partial with errors."""
        response = self.client.post(
            reverse('users:login'),
            data={'username': 'testuser', 'password': 'wrongpassword'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/partials/login_form.html')
        self.assertContains(response, 'error')  # Form errors present

    def test_logout_clears_session(self):
        """Session must be cleared after logout."""
        self.client.login(username='testuser', password='StrongTestPass123!')
        self.assertIn('_auth_user_id', self.client.session)

        # Trigger logout (adjust URL as needed)
        response = self.client.post(reverse('users:logout'))
        self.assertNotIn('_auth_user_id', self.client.session)
```

### Query Count & N+1 Prevention Tests

```python
class QueryCountTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='test', password='Test123!@#')
        # Create test data with relationships
        for i in range(10):
            remittance = Remittance.objects.create(
                date=date.today() - timedelta(days=i),
                created_by=self.user,
            )
            rider = RemittanceRider.objects.create(
                remittance=remittance,
                rider=self.user,
            )

    def test_list_remittances_does_not_trigger_n1_queries(self):
        """Selector must execute a constant number of queries regardless of item count."""
        from apps.remittance.selectors import get_recent_remittances

        # Assert query count is constant (e.g., 2 queries with select_related + prefetch_related)
        with self.assertNumQueries(2):
            remittances = list(get_recent_remittances(limit=50))
            for rem in remittances:
                _ = rem.created_by.username  # Accessing related object must not trigger extra queries
                for rider in rem.riders.all():
                    _ = rider.rider.username  # Prefetched related objects
```

## Test Coverage Checklist

For every hand-off received from Developer, verify:

- [ ] `test_unauthenticated_redirects_to_login` exists for every protected view
- [ ] `test_missing_required_fields_returns_400` exists for every POST view
- [ ] `test_happy_path` exists for every service function and view
- [ ] `test_htmx_partial_returns_correct_fragment` exists for every HTMX partial view
- [ ] `test_htmx_redirect_sets_header` exists for every HTMX redirect view
- [ ] `test_get_returns_405` exists for every POST-only HTMX endpoint
- [ ] `test_query_count_prevents_n1` exists for every selector and list view returning related objects (using `self.assertNumQueries`)
- [ ] `test_business_rule_violation_raises` exists for every service with guards
- [ ] `test_model_constraint_enforced` exists for every `UniqueConstraint` and `CheckConstraint`
- [ ] `test_soft_delete_allows_reuse` exists for every soft-delete-aware constraint
- [ ] `test_financial_precision_is_decimal` exists for every service involving money
- [ ] Tests use `Client` (not `APIClient`) for server-rendered views — use `APIClient` only for DRF JSON endpoints
- [ ] Tests use `login()` or `force_login()` — never hardcode session tokens
- [ ] Fixture passwords meet Django's password validators (8+ chars, mixed case, digits, symbols)
- [ ] No test data leaks between tests (Django TestCase rolls back transactions)
- [ ] HTMX tests include `HTTP_HX_REQUEST='true'` header to simulate HTMX requests
- [ ] **No test creates a user with `username="admin"`** — use a non-default
      username like `test_admin` or `testuser` to avoid any risk of colliding
      with the dev DB's real `admin` superuser (see Dev Credentials below)

## Dev Credentials — NEVER Modify the Admin User

The dev DB (`hydr8`) has a superuser the user logs in with: `admin` / `admin`
(PIN: `1234`). **NEVER write a test that calls `set_password`, `set_pin`, or
`.save()` on a user with `username="admin"`.** Even though `TestCase` rolls
back, this creates confusion and risks leaking to the dev DB if settings are
misconfigured. Always create test users with clearly non-default usernames
(e.g. `test_admin`, `staff1`, `driver1`).

## Running Tests

```bash
# Run all tests (uses test DB — never touches dev DB)
uv run python manage.py test apps --settings=config.settings.test --verbosity=2

# Run a specific app
uv run python manage.py test apps.remittance --settings=config.settings.test --verbosity=2

# Run a specific test module
uv run python manage.py test apps.remittance.tests.test_services --settings=config.settings.test --verbosity=2

# Run a specific test class
uv run python manage.py test apps.remittance.tests.test_services.CreateCreditLineServiceTests --settings=config.settings.test --verbosity=2

# Run with coverage (if coverage is installed)
uv run coverage run manage.py test apps --settings=config.settings.test && uv run coverage report
```

**Always pass `--settings=config.settings.test`** to ensure tests run against
the `hydr8_test` database, not the dev `hydr8` database. Without this flag,
Django auto-creates `test_hydr8` (also safe), but being explicit prevents any
ambiguity.

## Tester Superpowers

To ensure robust quality gates, apply these core superpowers:

### 1. Test-Driven Development (`test-driven-development`)
Whenever possible (e.g. when working in parallel with the Developer), write your tests based strictly on the Architect's view contract and service signatures *before* or *during* the implementation. This enforces contract correctness.

### 2. Systematic Debugging (`systematic-debugging`)
If a test fails, do not blindly change the test to make it pass. Determine if the bug is in the test or in the application code. Formulate a hypothesis and verify it before applying fixes.

### 3. Verification Before Completion (`verification-before-completion`)
Never hand off simply because the one test you wrote passes. You MUST run the **entire test suite** for the modified domain (e.g. `uv run python manage.py test apps.<domain>`) to guarantee you did not introduce regressions, before declaring the tests complete.

## Attempt Management

If tests are failing and you cannot identify the root cause after 2 debugging iterations, **stop and ask the user**:

> "I've attempted 2 fixes for [failing test / failing assertion]. The root cause appears to be [description]. To avoid wasting credits, could you clarify [specific question]?"

## Hand-off Protocol

After completing the test suite, state:
> "Tests complete. Results: [X passed, Y failed]. Hand-off to Cybersec: [list of views/services tested that involve auth, permissions, input validation, PIN handling, or financial data]. Please perform a security review."
