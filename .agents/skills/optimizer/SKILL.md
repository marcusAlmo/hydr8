---
name: optimizer
description: >
  Activates ONLY when the user explicitly calls for optimization analysis, such as
  "run the optimizer", "optimizer check", "run db optimization", "optimize the codebase",
  "check for dead code", "directory cleanup", or "convention audit".
  This skill does NOT activate automatically — it is triggered manually by the user.
  It produces a structured report with actionable suggestions to feed back to the Architect.
---

# Optimizer Skill — Hydr8

You are the **System Optimizer** for Hydr8. This skill is invoked **manually by the user** to perform a deep analysis pass across the codebase. You produce a structured report covering database optimizations, directory hygiene, and convention compliance. Your output is designed to feed directly into the Architect skill for planning remediation.

**This skill DOES NOT make code changes.** It produces reports and suggestions only.

## Scope of Analysis

1. **Database & Query Optimization** — N+1 risks, missing indexes, suboptimal queryset patterns
2. **Directory & File Hygiene** — empty files, dead code, orphaned migrations, inconsistent structure
3. **Django Convention Compliance** — layering violations, misplaced logic, naming inconsistencies
4. **PostgreSQL Schema Review** — constraint gaps, index strategy, field type appropriateness
5. **Dependency Health** — unpinned versions, unused dependencies, security-relevant updates
6. **Template & HTMX Audit** — template efficiency, HTMX pattern correctness, Alpine.js misuse
7. **Code Lints & Type Checking** — identifying type-hint violations, syntax errors, and proposing systematic changes

---

## Phase 1: Database & Query Optimization Audit

### 1.1 N+1 Detection

Scan all `selectors.py` and `views.py` files for queryset patterns:

```python
# FLAG: Iterating over FK relations without select_related
for remittance in Remittance.objects.all():
    print(remittance.created_by.username)  # N+1 — each iteration hits DB
    for rider in remittance.riders.all():  # N+1 — reverse FK without prefetch
        print(rider.rider.username)

# REQUIRED: Use select_related / prefetch_related
Remittance.objects.select_related('created_by', 'finalized_by').prefetch_related(
    'riders__rider', 'riders__product_lines__product'
).all()
```

Check for:
- [ ] ForeignKey traversals in loops without `select_related`
- [ ] Reverse FK access (`.related_name.all()`) in loops without `prefetch_related`
- [ ] `.count()` calls where `exists()` is sufficient
- [ ] `filter().first()` where `get_or_none()` pattern is cleaner
- [ ] Template loops accessing related objects without prefetch (e.g., `{% for rider in remittance.riders.all %}` without prefetch in the selector)

### 1.2 Missing Index Audit

For each model, evaluate:
- **Frequently filtered fields** (used in `filter()`, `get()`, `order_by()`)
- **FK fields** — Django adds these automatically, but verify join targets
- **Soft-delete pattern** — `deleted_at__isnull=True` used in many filters; should have partial index
- **Status fields** used in list queries — consider partial index per status value
- **Date range fields** (`date`, `created_at`, `last_credit_at`) — common in reporting queries

```sql
-- Example: Expected indexes for Remittance
-- idx_remittance_status (status) — already present
-- idx_remittance_date (date) — for history queries
-- idx_remittance_tithes_offering (tithes_paid, offering_paid) — already present

-- Example: Expected indexes for Customer
-- idx_customer_debt_balance (debt_balance) — already present
-- idx_customer_last_credit_at (last_credit_at) — already present
-- idx_customer_active (deleted_at) WHERE deleted_at IS NULL — partial index for active customers
```

Report format:
```
Model: Customer
Missing Index: (deleted_at) WHERE deleted_at IS NULL — partial index for active customer queries
Query Pattern: selector get_customers_with_outstanding_debt() — filters by deleted_at__isnull=True
Recommendation: Add Meta.indexes entry with condition=Q(deleted_at__isnull=True)
```

### 1.3 DecimalField Precision Audit

For all `DecimalField` instances:
- [ ] `max_digits=12, decimal_places=2` is standard for totals (sales, net profit, debt balance)
- [ ] `max_digits=10, decimal_places=2` is standard for unit prices and commission rates
- [ ] `max_digits=5, decimal_places=4` for percentage rates (tithe_rate_snapshot)
- [ ] Flag any `FloatField` used for monetary values — MUST be migrated to `DecimalField`
- [ ] Flag `IntegerField` for money (e.g., storing cents) — document the convention explicitly

### 1.4 Queryset Efficiency Patterns

```python
# INEFFICIENT
len(queryset)           # Loads all records into memory
if queryset:            # Evaluates entire queryset
not queryset.filter()   # Multiple DB hits

# EFFICIENT
queryset.count()        # SQL COUNT()
queryset.exists()       # SQL EXISTS — for boolean checks
queryset.filter().exists()
```

### 1.5 F() Expression Audit (Financial Integrity)

```python
# FLAG: Reading debt_balance into Python and updating — race condition risk
customer = Customer.objects.get(id=customer_id)
customer.debt_balance += amount
customer.save()  # RACE CONDITION — concurrent updates will overwrite

# REQUIRED: Use F() expression for atomic updates
Customer.objects.filter(id=customer_id).update(debt_balance=F('debt_balance') + amount)
```

Check all service functions that modify financial fields for F() expression usage.

---

## Phase 2: Directory & File Hygiene Audit

### 2.1 Empty File Detection

Scan for empty or stub-only files:

```python
# apps/<domain>/selectors.py — empty (0 bytes or only pass/comment)
# apps/<domain>/services.py — empty (0 bytes or only pass/comment)
# apps/<domain>/views.py — empty
```

Report:
```
EMPTY FILE: apps/customers/services.py — 0 bytes
EMPTY FILE: apps/customers/views.py — 63 bytes (only a comment)
Action: Confirm intentional or remove/stub with TODO comments
```

### 2.2 Orphaned Migration Detection

```bash
# Check for unapplied migrations
uv run python manage.py showmigrations --list | grep '\[ \]'

# Check for migration squash opportunities (migrations older than 10)
ls -la apps/*/migrations/*.py | wc -l
```

Report:
```
UNAPPLIED: apps/customers/migrations/0002_add_credit_line.py
Action: Run makemigrations --check to confirm state
```

### 2.3 `__pycache__` and `.pyc` in Tracked Files

Check `.gitignore` covers:
- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `.env`
- `staticfiles/`
- `.venv/`
- `node_modules/` (if any JS tooling is added)
- `*.sqlite3` (dev database)

### 2.4 App Structure Compliance

Every `apps/<domain>/` must have:
```
Required: __init__.py, apps.py, models.py, services.py, selectors.py,
          admin.py, urls.py, views.py, migrations/__init__.py
Required: tests/ directory with test_services.py, test_views.py at minimum
Required: templates/<domain>/ directory for page templates
Optional: templates/<domain>/partials/ for HTMX fragments
```

Report any app missing required files.

### 2.5 Unused Import Detection

Patterns to flag:
```python
from django.utils.http import MAX_URL_LENGTH  # Imported but never used
from datetime import date  # Imported but only referenced as string
from django.conf import settings  # Imported but settings not referenced
```

---

## Phase 3: Django Convention Compliance Audit

### 3.1 Layering Violations

Scan for:

```python
# FLAG: ORM call in views.py
@login_required
def my_view(request):
    customers = Customer.objects.filter(deleted_at__isnull=True)  # VIOLATION: use selector

# FLAG: Business logic in models.py
class Remittance(models.Model):
    def finalize(self):
        self.status = 'FINALIZED'
        self.save()  # VIOLATION: belongs in services.py

# FLAG: Financial calculation in template
{{ remittance.total_sales|floatformat:2 }}  # OK — formatting only
{{ remittance.total_sales|add:remittance.total_expenses }}  # FLAG — calculation in template, move to service
```

### 3.2 Service Function Signature Audit

All service functions MUST use keyword-only args:

```python
# VIOLATION: positional args allow silent bugs
def create_credit_line(customer_id, product_id, qty_credited, unit_price):

# CORRECT: keyword-only enforces explicit call sites
def create_credit_line(*, customer_id: int, product_id: int, qty_credited: int, unit_price: Decimal, performed_by):
```

### 3.3 Model `__str__` Audit

Every model must have `__str__` returning a meaningful string:
```python
def __str__(self) -> str:
    return f"{self.model_field}"  # Type-annotated return
```

Flag: models without `__str__`, or `__str__` returning `None`-possible values without safety, or `__str__` exposing PII (customer names in financial models — use IDs only per privacy rules).

### 3.4 Missing `db_table` Audit

Every model's `Meta` class MUST explicitly set `db_table`:
```python
class Meta:
    db_table = 'remittance_remittance'  # Explicit, not relying on Django default
```

Flag any model without explicit `db_table`.

### 3.5 Missing `verbose_name_plural` Audit

Every model's `Meta` class SHOULD have `verbose_name_plural` for admin readability.

### 3.6 Permission Decorator Audit

Scan all `views.py` files:
```python
# FLAG: Missing @login_required
def my_view(request):
    ...  # No @login_required — anyone can access
```

Report every view without `@login_required` or `LoginRequiredMixin` (except the login view itself).

### 3.7 `unique_together` Audit

Scan all `models.py` files for deprecated `unique_together`:
```python
# FLAG: unique_together is deprecated and not soft-delete-aware
class Meta:
    unique_together = ('remittance', 'rider')

# REQUIRED: Use UniqueConstraint with condition for soft-delete models
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['remittance', 'rider'],
            condition=models.Q(deleted_at__isnull=True),
            name='unique_active_remittance_rider',
        ),
    ]
```

---

## Phase 4: PostgreSQL Schema Review

### 4.1 Constraint Gap Analysis

For each model:
- [ ] Are all `unique_together` converted to `UniqueConstraint`?
- [ ] Are FK `on_delete` choices appropriate?
  - `CASCADE` — deletes children when parent deleted (verify intentional)
  - `SET_NULL` — nullifies FK (verify field is `null=True`)
  - `PROTECT` — prevents parent deletion if children exist (use for financial data)
  - `RESTRICT` — similar to PROTECT but allows deletion if referenced in same transaction

### 4.2 Temporal Data Patterns

- [ ] `DateTimeField(auto_now_add=True)` correctly used for immutable creation timestamps
- [ ] `DateTimeField(auto_now=True)` correctly used for mutable update timestamps
- [ ] `deleted_at` is consistently present across soft-delete models
- [ ] `finalized_at` is present on Remittance (immutable after finalize)

### 4.3 Choices Field Consistency

- [ ] All `CharField` with limited values use `TextChoices`
- [ ] `max_length` on choices fields exactly matches the longest choice value
  - e.g., `StatusChoices.FINALIZED = "FINALIZED"` (10 chars) with `max_length=20` — acceptable, but flag if oversized

---

## Phase 5: Dependency Health Audit

Review `pyproject.toml`:
```
MINIMUM PINS (good):  django>=6.0.7, django-htmx>=1.28.0
EXACT PINS (best):    django==6.0.7, django-htmx==1.28.0
MISSING PINS (bad):   any package without version constraint
```

Check for unused dependencies:
```bash
# Packages in pyproject.toml that are never imported in the codebase
grep -r "import djangorestframework" apps/  # Is DRF actually used? (Hydr8 is server-rendered)
grep -r "import corsheaders" apps/  # Is CORS needed for server-rendered app?
```

**Hydr8-specific note:** DRF and django-cors-headers are installed but may not be needed if the app is purely server-rendered. Flag if they are unused — they add attack surface and dependency maintenance burden.

---

## Phase 6: Template & HTMX Audit

### 6.1 Template Efficiency

Scan templates for:
- [ ] Template loops that access related objects without prefetch (N+1 in template)
  ```django
  {# FLAG: N+1 — riders.all() hits DB for each remittance if not prefetched #}
  {% for remittance in remittances %}
      {% for rider in remittance.riders.all %}
          {{ rider.rider.username }}
      {% endfor %}
  {% endfor %}
  ```
- [ ] Repeated complex calculations in templates (move to service/selector)
- [ ] Missing `{% csrf_token %}` in forms
- [ ] `|safe` filter usage (verify content is server-trusted)

### 6.2 HTMX Pattern Audit

- [ ] HTMX attributes use `{% url %}` tag — never hardcoded paths
  ```django
  {# GOOD #}
  hx-post="{% url 'remittance:finalize' remittance.id %}"

  {# BAD — hardcoded path, breaks if URL changes #}
  hx-post="/remittance/{{ remittance.id }}/finalize/"
  ```
- [ ] HTMX mutation endpoints have `hx-target` and `hx-swap` explicitly set
- [ ] HTMX search inputs have debounce (`hx-trigger="input changed delay:300ms"`)
- [ ] HTMX indicators (`hx-indicator`) are present for long-running requests
- [ ] `HX-Redirect` responses use `reverse()` — never user input

### 6.3 Alpine.js Misuse Audit

- [ ] Alpine.js is NOT storing business data (customer info, financial calculations)
- [ ] Alpine.js is NOT making API calls (use HTMX instead)
- [ ] Alpine.js `x-cloak` is present on elements hidden until Alpine initializes
- [ ] `localStorage` usage is limited to theme/UI preferences — never auth or business data

### 6.4 Tailwind CSS Audit

- [ ] No inline styles — use Tailwind classes or CSS custom properties
- [ ] Semantic color tokens used (`text-primary`, `bg-surface-container`) — not raw hex
- [ ] Dark mode classes (`dark:`) present where needed
- [ ] CDN version is pinned (not `@latest`)

---

## Phase 7: Technical Debt Marker Audit

Scan the entire codebase for inline annotations that signal unfinished work, temporary solutions, known bugs, or deferred decisions. These are high-value signals because they were left intentionally by developers.

### 7.1 Marker Types to Scan

```python
# TODO: Something still needs to be done
# FIXME: Known broken behavior that needs a fix
# HACK: Workaround — not the correct solution, revisit later
# TEMP / TEMPORARY: Short-lived solution that must be replaced
# NOTE: Developer warning or clarification that may indicate a design gap
# XXX: Severe concern or dangerous code
```

Django Template / HTML equivalents:
```html
<!-- TODO: -->
<!-- FIXME: -->
<!-- HACK: -->
<!-- TEMP: -->
<!-- NOTE: -->
```

### 7.2 Shell Commands

```bash
# Scan all Python files for debt markers
grep -rn --include="*.py" -E "#\s*(TODO|FIXME|HACK|TEMP|XXX|NOTE):" apps/ 2>/dev/null

# Scan all HTML templates for debt markers
grep -rn --include="*.html" -E "<!--\s*(TODO|FIXME|HACK|TEMP|XXX|NOTE):" templates/ apps/*/templates/ 2>/dev/null

# Count markers per file to find hotspots
grep -rn --include="*.py" -E "#\s*(TODO|FIXME|HACK|TEMP)" apps/ | awk -F: '{print $1}' | sort | uniq -c | sort -rn | head -20
```

### 7.3 Categorization Rules

Once collected:

| Marker | Default Severity | Action |
|---|---|---|
| `FIXME` | Critical | Flag for Developer — known broken code |
| `XXX` | Critical | Flag for Cybersec review |
| `HACK` | High | Flag for Architect — needs proper design |
| `TEMP` / `TEMPORARY` | High | Flag for Developer — replace before release |
| `TODO` | Medium | Inventory and backlog |
| `NOTE` | Informational | Document as context |

### 7.4 Report Format

```
File: apps/customers/views.py
Line: 45
Type: TODO
Content: # TODO: add role-based filtering for driver vs admin
Recommendation: Add role check in selector, filter customers by rider access
```

---

## Phase 8: Stub & Placeholder Audit

Scan for incomplete implementations and placeholder values.

### 8.1 What to Scan

```bash
# Find stub/placeholder values in Python
grep -rn --include="*.py" -E "(pass$|\.\.\.$|raise NotImplementedError|# STUB|# MOCK|# PLACEHOLDER)" apps/ 2>/dev/null

# Find hardcoded test/demo data in views or services
grep -rn --include="*.py" -E "(\"test\"|\"demo\"|\"dummy\"|\"placeholder\")" apps/ 2>/dev/null

# Find empty model methods (create, save overrides that do nothing)
grep -rn --include="*.py" -E "def (create|save|delete)\(.*\):\s*$" apps/ 2>/dev/null
```

### 8.2 Incomplete Model Methods

Flag cases where a model method is defined but does nothing:
```python
# FLAG: Product.create is defined but incomplete
@classmethod
def create(cls, **kwargs):
    name = str(kwargs['name']).title()
    variation = str(kwargs['variation']).title()
    # FIXME: method doesn't actually create or return anything
```

---

## Optimizer Report Format

```markdown
# Hydr8 Optimizer Report
**Generated:** YYYY-MM-DD HH:MM
**Triggered by:** User request

---

## Critical (fix before next feature)
| # | Category | Location | Issue | Recommendation |
|---|---|---|---|---|

## High (plan in next sprint)
| # | Category | Location | Issue | Recommendation |
|---|---|---|---|---|

## Medium (backlog)
| # | Category | Location | Issue | Recommendation |
|---|---|---|---|---|

## Informational
| # | Category | Location | Note |
|---|---|---|---|

---

## DB Index Recommendations
| Model | Suggested Index | Fields | Condition | Rationale |
|---|---|---|---|---|

## Convention Violations
| File | Violation | Severity | Fix |
|---|---|---|---|

## Template & HTMX Findings
| File | Issue | Severity | Fix |
|---|---|---|---|

## Dependency Health
| Package | Current | Status | Action |
|---|---|---|---|

---

## Technical Debt Register
| # | File | Line | Marker | Content | Priority |
|---|---|---|---|---|---|

## Stub/Placeholder Findings
| # | File | Type | Finding | Recommendation |
|---|---|---|---|---|

---

## Feed to Architect
The following items require architectural decisions before implementation:
- [item]: [description + options]
- [Lints]: [Summarize major linting or type-hinting issues that require architectural refactoring or systematic changes, and propose changes]
- [Stub findings]: [Describe incomplete implementations that need proper design]

## Feed to Developer
The following items are ready for direct implementation:
- [item]: [file + specific change]

## Feed to Cybersec
The following items have security implications:
- [item]: [description + OWASP category]
```

## Running the Optimizer

When this skill is triggered, execute the following shell commands to gather data before producing the report:

```bash
# 1. Find empty files
find apps -name "*.py" -empty -not -path "*/migrations/*" -not -name "__init__.py"

# 2. Check unapplied migrations
uv run python manage.py showmigrations --list 2>/dev/null | grep '^\s*\[ \]'

# 3. Check for unused imports (requires pyflakes or ruff)
uv run python -m pyflakes apps/ 2>/dev/null | grep "imported but unused"

# 4. Check for missing __pycache__ in gitignore
cat .gitignore | grep pycache

# 5. List all migration files per app
for app in apps/*/migrations; do echo "$app: $(ls $app/*.py 2>/dev/null | wc -l) migrations"; done

# 6. Find ORM calls in views.py (layering violation detection)
grep -rn "\.objects\." apps/*/views.py 2>/dev/null

# 7. Find missing @login_required
grep -L "login_required" apps/*/views.py 2>/dev/null

# 8. Find FloatField (should be DecimalField for money)
grep -rn "FloatField" apps/ 2>/dev/null

# 9. Find unique_together (deprecated — should be UniqueConstraint)
grep -rn "unique_together" apps/ 2>/dev/null

# 10. Find F() expression usage (should be used for financial updates)
grep -rn "F(" apps/*/services.py 2>/dev/null

# 11. Examine lints and type-checking issues
uv run ruff check apps/ 2>/dev/null
uv run pyright apps/ 2>/dev/null

# 12. Scan for technical debt markers (Python)
grep -rn --include="*.py" -E "#\s*(TODO|FIXME|HACK|TEMP|XXX|NOTE):" apps/ 2>/dev/null

# 13. Scan for technical debt markers (HTML templates)
grep -rn --include="*.html" -E "<!--\s*(TODO|FIXME|HACK|TEMP|XXX|NOTE):" templates/ apps/*/templates/ 2>/dev/null

# 14. Find |safe filter usage in templates (XSS risk audit)
grep -rn --include="*.html" "\|safe" templates/ apps/*/templates/ 2>/dev/null

# 15. Find hardcoded paths in HTMX attributes (should use {% url %})
grep -rn --include="*.html" -E "hx-(post|get)=\"/" templates/ apps/*/templates/ 2>/dev/null | grep -v "{% url"

# 16. Find empty/stub service and selector files
find apps -name "services.py" -empty -o -name "selectors.py" -empty 2>/dev/null

# 17. Find Python stubs (pass-only or raise NotImplementedError)
grep -rn --include="*.py" -E "(^\s*pass$|raise NotImplementedError)" apps/ 2>/dev/null

# 18. Check for Alpine.js localStorage misuse (should be theme only)
grep -rn --include="*.html" "localStorage" templates/ apps/*/templates/ 2>/dev/null

# 19. Check for missing db_table in Meta
grep -rn --include="*.py" -A5 "class Meta:" apps/*/models.py 2>/dev/null | grep -B1 "verbose_name" | grep -v "db_table"
```

Use the output to populate the report. Do not guess — only report what the data confirms.
