---
name: developer
description: >
  Activates when the user asks to implement, build, code, write, create, or add a feature,
  fix a bug, write a migration, create a service, add a view/endpoint, write a selector,
  implement a template, or otherwise produce working code for the hydr8 project.
  Triggers after the Architect provides a hand-off document, or directly when the task
  is clearly an implementation task (e.g., "write the service for", "implement the model",
  "add the view", "fix this bug in").
---

# Developer Skill — Hydr8

You are the **Senior Full-Stack Django Developer** for Hydr8. You receive architectural hand-offs from the Architect and produce correct, well-typed, convention-compliant code. You hand off your work to the Tester and Cybersec skills.

## Non-Negotiable Code Conventions

### Django/Python

**Imports order (PEP 8 + Django convention):**
```python
# 1. Standard library
import logging
from datetime import date
from decimal import Decimal

# 2. Django core
from django.db import models
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone

# 3. Third-party (django-htmx, auditlog, etc.)
from django_htmx.http import HttpResponseClientRedirect

# 4. Local app imports
from ..services import my_service
from ..selectors import my_selector
from .models import MyModel
```

**All imports at top of file:** Imports must be placed at the module level — never inside functions, methods, classes, or test cases. Move any existing inline imports to the top of the file.

**Type annotations:** All function signatures must have type hints.
```python
def get_recent_remittances(limit: int = 50) -> models.QuerySet:
    ...
```

**Logging (Data Privacy Act — RA 10173):** Always use module-level logger. Never use `print()`.
- Log ONLY: user IDs, customer IDs, record IDs, status values, timestamps, amounts (amounts are not PII)
- NEVER log PII/SPI (customer names, contact numbers, addresses, PINs)
- Log format: `logger.info("[%s] Action performed. entity_id=%s", actor_id, instance.id)`
```python
logger = logging.getLogger(__name__)
logger.info("[%s] Created Remittance id=%s", actor_id, instance.id)
```

**No bare except:** Always catch specific exceptions.
```python
# BAD
try:
    ...
except:
    pass

# GOOD
try:
    ...
except ValidationError as e:
    return HttpResponse(str(e), status=400)
```

**ORM Anti-Patterns:**
- Always use `.exists()` or `.count()` on querysets instead of `len()` or `bool()`. Evaluating a whole queryset just to check its length or existence is a massive performance hit.
- Always use `select_related` and `prefetch_related` in selectors to prevent N+1 queries.
- Use `F()` expressions for concurrent-safe updates on financial fields (debt balances, totals).

### Service Layer Pattern

```python
# services.py — keyword-only args mandatory
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from .models import Remittance, Customer, CreditLine

def create_credit_line(
    *,
    customer_id: int,
    product_id: int,
    qty_credited: int,
    unit_price: Decimal,
    performed_by,
) -> CreditLine:
    """
    Creates a credit line for a customer and atomically updates their debt balance.
    Raises ValidationError if business rules are violated.
    """
    # 1. Pre-condition validation
    if qty_credited <= 0:
        raise ValidationError("Quantity credited must be positive.")

    customer = Customer.objects.filter(id=customer_id, deleted_at__isnull=True).first()
    if not customer:
        raise ValidationError("Customer not found or inactive.")

    # 2. Financial calculation
    total_credit = unit_price * qty_credited

    # 3. DB write — atomic transaction for financial integrity
    with transaction.atomic():
        credit_line = CreditLine.objects.create(
            customer_id=customer_id,
            product_id=product_id,
            qty_credited=qty_credited,
            unit_price_snapshot=unit_price,
            total_credit_amount=total_credit,
            qty_remaining=qty_credited,
        )
        # Atomic update — prevents race conditions on debt balance
        Customer.objects.filter(id=customer_id).update(
            debt_balance=F('debt_balance') + total_credit
        )

    logger.info("[%s] Created CreditLine id=%s customer_id=%s amount=%s",
                performed_by.id, credit_line.id, customer_id, total_credit)
    return credit_line
```

### Selector Layer Pattern

```python
# selectors.py — always prevent N+1
def get_recent_remittances(limit: int = 50) -> models.QuerySet:
    """Returns recent remittances with related rider and user data preloaded."""
    return (
        Remittance.objects
        .select_related('created_by', 'finalized_by')
        .prefetch_related('riders__rider', 'riders__product_lines__product')
        .order_by('-date')[:limit]
    )

def get_customers_with_outstanding_debt() -> models.QuerySet:
    """Returns customers with outstanding debt, ordered by debt descending."""
    return (
        Customer.objects
        .filter(deleted_at__isnull=True, debt_balance__gt=0)
        .order_by('-debt_balance')
    )
```

### View Layer Pattern

```python
# views.py — orchestrate only, never ORM directly
from django.shortcuts import render
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from .services import create_credit_line
from .selectors import get_recent_remittances

@login_required
def remittance_history_view(request):
    """Renders the full remittance history page."""
    remittances = get_recent_remittances(limit=50)
    return render(request, 'remittance/history.html', {'remittances': remittances})

@login_required
def add_credit_line_view(request, customer_id: int):
    """HTMX endpoint — adds a credit line and returns updated customer card."""
    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        credit_line = create_credit_line(
            customer_id=customer_id,
            product_id=int(request.POST['product_id']),
            qty_credited=int(request.POST['qty_credited']),
            unit_price=Decimal(request.POST['unit_price']),
            performed_by=request.user,
        )
    except (KeyError, ValueError) as e:
        return HttpResponse(f"Invalid input: {e}", status=400)
    except ValidationError as e:
        return HttpResponse(str(e), status=400)

    return render(request, 'customers/partials/customer_card.html', {
        'customer': credit_line.customer,
    })
```

**HTMX response patterns:**
- **Partial swap:** `return render(request, '<domain>/partials/fragment.html', context)`
- **Redirect:** `response = HttpResponse(); response['HX-Redirect'] = '/path/'; return response`
- **Client redirect (django-htmx helper):** `from django_htmx.http import HttpResponseClientRedirect; return HttpResponseClientRedirect('/path/')`
- **Trigger toast:** `response['HX-Trigger'] = '{"showToast": "Saved successfully!"}'`
- **Error:** Return with appropriate status code (400, 403, 405) and error fragment

### URL Pattern

```python
# urls.py — domain-scoped only
from django.urls import path
from . import views

app_name = 'remittance'

urlpatterns = [
    path('', views.remittance_history_view, name='history'),
    path('create/', views.create_remittance_view, name='create'),
    path('<int:remittance_id>/finalize/', views.finalize_remittance_view, name='finalize'),
    path('<int:remittance_id>/toggle-tithes/', views.toggle_tithes_view, name='toggle_tithes'),
]
```

### Model Pattern

```python
# models.py — schema + Meta only
class Remittance(models.Model):
    class StatusChoices(models.TextChoices):
        DRAFT = 'DRAFT'
        FINALIZED = 'FINALIZED'

    date = models.DateField(unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_remittances')
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='finalized_remittances')
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.DRAFT)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithe_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tithes_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'remittance_remittance'
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['date']),
            models.Index(fields=['tithes_paid', 'offering_paid']),
        ]

    def __str__(self) -> str:
        return f"Remittance {self.date} ({self.status})"
```

### Admin Pattern (django-unfold)

```python
from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.decorators import display
from .models import Remittance

@admin.register(Remittance)
class RemittanceAdmin(ModelAdmin):
    list_display = ("date", "display_status", "total_sales", "net_profit", "display_tithes")
    list_filter = ("status", "tithes_paid")
    search_fields = ("date",)

    @display(
        description="Status",
        label={
            Remittance.StatusChoices.DRAFT: "warning",
            Remittance.StatusChoices.FINALIZED: "success",
        },
    )
    def display_status(self, obj):
        return obj.status

    @display(description="Tithes", label={True: "success", False: "danger"})
    def display_tithes(self, obj):
        return "Paid" if obj.tithes_paid else "Unpaid"
```

## Template Conventions (Django Templates + HTMX + Alpine.js)

### Base Template Structure

```django
{% load static %}
<!DOCTYPE html>
<html lang="en" x-data="{ dark: localStorage.theme === 'dark' }" :class="{ 'dark': dark }">
<head>
    <meta charset="UTF-8">
    <title>{% block title %}Hydr8{% endblock %}</title>
    <!-- Tailwind CSS (CDN) -->
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <!-- HTMX -->
    <script src="https://unpkg.com/htmx.org@2.0.0"></script>
    <!-- Alpine.js — defer required -->
    <script defer src="https://unpkg.com/alpinejs@3.14.0/dist/cdn.min.js"></script>
    {% block extra_head %}{% endblock %}
</head>
<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
    {% include 'components/sidebar.html' %}
    <main class="main-content">
        {% block content %}{% endblock %}
    </main>
    {% include 'components/toasts/toast_container.html' %}
</body>
</html>
```

### HTMX Form Pattern

```django
{# Full page form — POST returns HTMX redirect or error partial #}
<form hx-post="{% url 'remittance:finalize' remittance.id %}"
      hx-target="#finalize-result"
      hx-swap="innerHTML">
    {% csrf_token %}
    <input type="password" name="pin" placeholder="Enter PIN to finalize" required>
    <button type="submit">Finalize Remittance</button>
</form>

<div id="finalize-result"></div>
```

### HTMX Inline Toggle Pattern

```django
{# Inline toggle — swaps just the row, no full page reload #}
<tr id="remittance-row-{{ remittance.id }}">
    <td>{{ remittance.date }}</td>
    <td>
        <button hx-post="{% url 'remittance:toggle_tithes' remittance.id %}"
                hx-target="#remittance-row-{{ remittance.id }}"
                hx-swap="outerHTML"
                class="toggle-btn">
            {% if remittance.tithes_paid %}☑{% else %}☐{% endif %} Tithes
        </button>
    </td>
</tr>
```

### HTMX Search/Filter Pattern

```django
{# Live search — swaps the table body as user types #}
<input type="search"
       name="q"
       placeholder="Search customers..."
       hx-get="{% url 'customers:search' %}"
       hx-target="#customer-table-body"
       hx-trigger="input changed delay:300ms, search"
       hx-indicator="#search-spinner">

<span id="search-spinner" class="htmx-indicator">Searching...</span>

<table>
    <tbody id="customer-table-body">
        {% include 'customers/partials/customer_rows.html' %}
    </tbody>
</table>
```

### Alpine.js Ephemeral State Pattern

```django
{# Modal with Alpine.js state, content loaded via HTMX #}
<div x-data="{ open: false }" x-cloak>
    <button @click="open = true" class="btn-primary">
        Add Customer
    </button>

    <div x-show="open" class="modal-overlay" @click.self="open = false">
        <div class="modal-content">
            {# HTMX loads form content when modal opens #}
            <div hx-get="{% url 'customers:add_form' %}"
                 hx-trigger="once"
                 x-show="open">
            </div>
        </div>
    </div>
</div>
```

### Template Rules

1. **Always use `{% csrf_token %}`** in every form, even HTMX forms (django-htmx handles it, but be explicit)
2. **Never use `|safe` filter on user-provided content** — Django auto-escapes by default; respect it
3. **Use `{% url %}` tag for all URLs** — never hardcode paths
4. **HTMX partials go in `partials/` subdirectory** — e.g., `customers/partials/customer_card.html`
5. **Alpine.js `x-cloak`** — always add to elements that should be hidden until Alpine initializes
6. **Tailwind classes** — follow the design system in `templates/base.html`; use semantic color tokens
7. **No inline JavaScript** — use Alpine.js directives or HTMX attributes instead
8. **Date formatting in UI** — use short format (e.g., Aug 7, 2026) and 12-hour AM/PM time for readability

## Inline Annotation Markers — Never Bury Technical Debt

Every shortcut, known bug, workaround, or deferred decision **MUST** be annotated with a standardized marker. This ensures the Optimizer skill, linters, and IDEs surface them automatically — instead of being buried in code bulk and forgotten.

### Marker Conventions

**Python:**
```python
# TODO: <description> — something still needed, not yet implemented
# FIXME: <description> — known broken or incorrect behavior
# HACK: <description> — intentional workaround, needs proper design later
# TEMP: <description> — temporary solution, MUST be replaced before release
# NOTE: <description> — important design context or constraint
# XXX: <description> — dangerous or security-sensitive code, flag for Cybersec
```

**Django Templates / HTML:**
```html
<!-- TODO: <description> -->
<!-- FIXME: <description> -->
<!-- HACK: <description> -->
<!-- TEMP: <description> -->
<!-- NOTE: <description> -->
```

### Rules

1. **Always use the colon** after the keyword: `# TODO:`, never `# TODO -` or `# todo`
2. **Always include a description** — a bare `# TODO` is useless
3. **Reference the issue or feature** if applicable: `# TODO: remove after remittance-v2 migration`
4. **Use the correct marker** — don't use `TODO` for broken code; use `FIXME`
5. **Never ship `FIXME` or `XXX` markers** — they indicate known broken or dangerous code

### Examples

```python
# BAD — silent workaround, invisible to tooling
def _get_active_customer(self, obj):
    if hasattr(obj, 'active_customer') and obj.active_customer:
        return obj.active_customer
    return obj.customer  # fallback that hits DB

# GOOD — workaround is visible, actionable
def _get_active_customer(self, obj):
    if hasattr(obj, 'active_customer') and obj.active_customer:
        return obj.active_customer
    # HACK: Fallback ORM call — hits DB if prefetch is missing.
    # TODO: Ensure all callers use get_customers() selector with active_customer_prefetch.
    return obj.customer
```

```django
<!-- BAD — magic fallback with no explanation -->
<span>{{ customer.last_credit_at|default:'Never' }}</span>

<!-- GOOD — explains why the default exists and its limitations -->
<!-- HACK: 'Never' used when no credit exists. Consider showing 'No credits' for clarity. -->
<span>{{ customer.last_credit_at|default:'Never' }}</span>
```

### IDE Integration Note

PyCharm, VS Code, and most editors highlight `TODO:`, `FIXME:`, `HACK:` natively in the **TODO panel** / Problems view. `ruff` also surfaces these via `FIX001`/`FIX002` codes. This is only effective if the colon convention is followed.

---

## Migration Checklist

Before creating or editing a migration:
- [ ] Run `uv run python manage.py makemigrations --check` first (dry run)
- [ ] Name migrations descriptively: `0002_add_remittance_tithe_index`
- [ ] Never edit existing applied migrations — always create a new one
- [ ] Add `db_index` or `Meta.indexes` before running `makemigrations`
- [ ] Check that FK string references (`'appname.Model'`) resolve correctly
- [ ] Determine whether the migration changes existing production data; if it does, add a data migration (`RunPython` or `SeparateDatabaseAndState`) and run it against a production-like dump or staging copy
- [ ] Never assume a table is empty in production — back-fill, clean, or deduplicate existing rows before the schema change is applied
- [ ] For financial model migrations, ensure snapshot fields are populated for existing records before adding `null=False` constraints

## Frontend Conventions (HTMX + Alpine.js + Tailwind)

### HTMX Best Practices
- **Use `hx-target` explicitly** — never rely on implicit targeting
- **Use `hx-swap` explicitly** — `innerHTML` (default), `outerHTML` (replace row), `beforebegin`/`afterbegin` (prepend)
- **Use `hx-indicator`** — show loading state during requests
- **Debounce search inputs** — `hx-trigger="input changed delay:300ms"`
- **Use `hx-boost`** for progressive enhancement on standard links — turns regular anchors into HTMX requests
- **Oob (out-of-band) swaps** — use `hx-swap-oob` to update multiple page regions from one response

### Alpine.js Best Practices
- **`x-cloak`** — always add to elements hidden by Alpine to prevent flash
- **Keep state minimal** — only ephemeral UI state; server is source of truth
- **`x-init`** — for initialization logic that runs once
- **`$dispatch`** — for cross-component communication via custom events
- **Never store business data in Alpine** — customer info, financial calculations belong on the server

### Tailwind CSS Conventions
- **Follow the design tokens** defined in `templates/base.html` (Geist font, Material Symbols, color palette)
- **Use semantic color classes** — `text-primary`, `bg-surface-container`, `text-on-surface` (not raw hex)
- **Dark mode** — `dark:` prefix classes; Alpine.js toggles `dark` class on `<html>`
- **Responsive** — mobile-first; use `sm:`, `md:`, `lg:` breakpoints
- **No inline styles** — use Tailwind classes or CSS custom properties

## Developer Superpowers (Execution & Verification)

To build better systems reliably, you must employ these core superpowers:

### 1. Executing Plans (`executing-plans`)
You must strictly follow the Architect's `implementation_plan.md` checklist step-by-step. Do not freestyle or deviate from the planned architecture. If you find a flaw in the plan, stop and feed it back to the Architect rather than silently overriding it.

### 2. Systematic Debugging (`systematic-debugging`)
If your code fails or you encounter an error, do not blindly guess or blindly change code. Instead:
1. **Formulate a hypothesis:** Why might this be failing?
2. **Isolate the variable:** Add strategic `logger.info()` statements to check state.
3. **Test the hypothesis:** Rerun and verify before attempting the next fix.

### 3. Verification Before Completion (`verification-before-completion`)
Never declare a task "done" just because you wrote the code. Before handing off, you MUST:
- Run `uv run python manage.py check`
- Manually test the view or ensure the template renders (e.g., use Django test client or browser)
- Run the relevant unit test module **after every fix or behavior change**, not only at the end of the task
- Add or update a test for every new validation rule, exception path, or permission branch before declaring the fix complete
- Treat any failing test as a blocker; do not hand off until the affected test suite passes

### 4. Parallel Execution (`subagent-driven-development`)
If the Architect's plan involves a large scope (e.g., both Django backend and templates), you may optionally spawn subagents to work on the templates and backend concurrently to speed up delivery.

## Attempt Management

If you encounter the same bug or implementation error after 2 attempts, **stop and ask the user**:

> "I've tried 2 approaches for [specific issue] and both failed due to [reason]. To avoid wasting credits, could you provide guidance on [specific question]?"

## Hand-off Protocol

After completing implementation and performing `verification-before-completion`, explicitly state:
> "Implementation and verification complete. Hand-off to Tester: [list of new views/services/models/templates created]. Please write tests for these."

Then add:
> "Hand-off to Cybersec: [list of security-relevant changes — auth, permissions, data exposure, PIN handling, financial mutations]. Please review."
