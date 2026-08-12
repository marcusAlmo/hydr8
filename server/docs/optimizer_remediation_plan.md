# Feature: Optimizer Remediation — Critical & High Priority Fixes

## Background

The Optimizer skill was run across all 10 domains of the Hydr8 Django application
(`users`, `customers`, `remittance`, `products`, `employees`, `analytics`, `audit`,
`settings`, `core`, + cross-cutting `config/templates/dependencies`). This plan
addresses the **Critical** and **High-priority** findings that are ready for direct
implementation. Large convention sweeps (keyword-only args across 50+ functions,
`verbose_name_plural` across all models, admin.py registrations, missing test files)
are deferred to separate batch-refactor plans.

### Architect's Corrections to Subagent Findings

After verifying the subagent reports against the actual code, the following
corrections are noted:

1. **F() expressions in remittance/services.py — FALSE POSITIVE.** The service
   computes totals from scratch in Python (accumulating from child records), then
   writes them once. This is a write-only pattern (`obj.field = computed_value`),
   not a read-modify-write pattern (`obj.field += value`). F() expressions are only
   needed for the latter. The DB trigger also locks FINALIZED records. No change needed.

2. **`|safe` on `alpine_seed` and `trends_seed` — SAFE.** These are JSON-serialized
   server-generated data passed to Alpine.js `x-data` attributes. Django's auto-escaping
   would break the JSON. This is a standard pattern. No change needed.

3. **`|safe` on `ai_insight` and `insight.html` — REAL XSS RISK.** These render
   AI-generated HTML content. Must be sanitized or the `|safe` removed.

4. **HTMX CDN is pinned** (`htmx.org@1.9.10`). Only **Alpine.js** is floating
   (`@3.x.x`). Only Alpine.js needs pinning.

## User Review Required

> **WARNING**: Removing the `SECRET_KEY` default will cause the application to fail
> to start if the `SECRET_KEY` environment variable is not set. Ensure `.env` has
> `SECRET_KEY=your-key-here` before deploying this change.

> **WARNING**: Removing `|safe` from `ai_insight` and `insight.html` will cause
> AI-generated HTML to be auto-escaped (displayed as raw text). This is the desired
> behavior until a proper HTML sanitizer is implemented. The AI insights feature
> appears to be a "Coming Soon" placeholder, so this should have no user impact.

> **WARNING**: Adding `is_back_office` guard to audit log views will restrict access
> to Admin and Staff roles only. Drivers will no longer be able to view audit logs.
> This is the correct behavior per `AGENTS.md` authorization conventions.

---

## Proposed Changes

### Phase 1 — Security Critical Fixes

#### [MODIFY] config/settings/base.py (line 14)
**What changes:** Remove hardcoded `SECRET_KEY` default so the app fails fast if the env var is missing.

BEFORE:
```python
SECRET_KEY = env('SECRET_KEY', default='django-insecure-5=0nbp%kzp8ln(#g!y5692oj(ah9v!8pj#txu)wd3*1&2e6rea')
```

AFTER:
```python
SECRET_KEY = env('SECRET_KEY')
```

#### [MODIFY] templates/base.html (line 130)
**What changes:** Pin Alpine.js CDN to a specific version instead of floating `@3.x.x`.

BEFORE:
```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
```

AFTER:
```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"></script>
```

#### [MODIFY] apps/analytics/templates/analytics/partials/ai_insights_panel.html (line 39)
**What changes:** Remove `|safe` filter from AI-generated HTML content to prevent XSS.

BEFORE:
```html
{{ insight.html|safe }}
```

AFTER:
```html
{{ insight.html }}
```

#### [MODIFY] apps/remittance/templates/remittance/remittance_history.html (line 208)
**What changes:** Remove `|safe` filter from AI-generated insight content to prevent XSS.

BEFORE:
```html
{{ ai_insight|safe }}
```

AFTER:
```html
{{ ai_insight }}
```

#### [MODIFY] apps/audit/views.py (lines 102-105, 124-127)
**What changes:** Add `is_back_office` authorization guard to both audit log views.

BEFORE (lines 1-10):
```python
import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.audit.selectors import (
    build_logs_json,
    get_log_entry,
    list_log_entries,
)
```

AFTER (lines 1-11):
```python
import json
import logging
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.audit.selectors import (
    build_logs_json,
    get_log_entry,
    list_log_entries,
)
from apps.users.permissions import is_back_office
```

BEFORE (lines 102-105):
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def audit_log_view(request):
```

AFTER (lines 102-106):
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='120/m', method='GET', block=True)
def audit_log_view(request):
    if not is_back_office(request.user):
        return HttpResponse("Forbidden", status=403)
```

BEFORE (lines 124-127):
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def audit_log_detail_view(request, entry_id: int):
```

AFTER (lines 125-129):
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def audit_log_detail_view(request, entry_id: int):
    if not is_back_office(request.user):
        return HttpResponse("Forbidden", status=403)
```

#### [MODIFY] apps/users/views.py (lines 140-145)
**What changes:** Remove TEMP DEBUG logging that logs password field shape.

BEFORE:
```python
        # TEMP DEBUG: log submitted field shapes (never the raw password value).
        submitted_pw = request.POST.get('password', '')
        logger.warning(
            "DEBUG login submit. username=%r pw_len=%r pw_first_char=%r",
            username, len(submitted_pw), submitted_pw[:1],
        )

        if form.is_valid():
```

AFTER:
```python
        if form.is_valid():
```

---

### Phase 2 — CSRF Token Fixes

#### [MODIFY] apps/settings/templates/settings/partials/system_config.html (line 67)
**What changes:** Add CSRF token to the system config form.

BEFORE:
```html
    <form id="system-config-form" class="contents">
```

AFTER:
```html
    <form id="system-config-form" class="contents">
        {% csrf_token %}
```

#### [MODIFY] apps/settings/templates/settings/partials/company.html (line 17)
**What changes:** Add CSRF token to the company form.

BEFORE:
```html
    <form id="company-form"
          hx-post="{% url 'settings:save_company' %}"
```

AFTER:
```html
    <form id="company-form"
          hx-post="{% url 'settings:save_company' %}"
```

Then add `{% csrf_token %}` on the next line after the form tag's opening attributes. Read the file to find the exact closing `>` of the form tag and insert `{% csrf_token %}` immediately after it.

#### [MODIFY] apps/settings/templates/settings/partials/profile.html (lines 25, 87, 156)
**What changes:** Add CSRF token to all 3 forms (profile, username, password-change).

For each of the 3 `<form>` tags, add `{% csrf_token %}` on the line immediately after the form tag's opening `>`.

#### [MODIFY] apps/customers/templates/customers/partials/add_customer_modal.html (line 53)
**What changes:** Add CSRF token to the add customer form.

#### [MODIFY] apps/customers/templates/customers/partials/edit_customer_modal.html (line 51)
**What changes:** Add CSRF token to the edit customer form.

#### [MODIFY] apps/customers/templates/customers/partials/record_debt_modal.html (line 71)
**What changes:** Add CSRF token to the record debt form.

#### [MODIFY] apps/customers/templates/customers/partials/record_borrowed_modal.html (line 58)
**What changes:** Add CSRF token to the record borrowed form.

For each of the 4 customer modal forms, read the file to find the exact closing `>` of the `<form>` tag, then insert `{% csrf_token %}` on the next line. The pattern is the same as `collect_modal.html` line 73 which already has it correctly.

---

### Phase 3 — Convention & Privacy Fixes

#### [MODIFY] apps/customers/views.py (lines 118-123)
**What changes:** Remove duplicate decorators on `customer_edit_view`.

BEFORE:
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_edit_view(request, customer_id: str):
```

AFTER:
```python
@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def customer_edit_view(request, customer_id: str):
```

#### [MODIFY] apps/customers/models.py (lines 69-70)
**What changes:** Change `Customer.__str__` to return display ID instead of customer name (PII protection per RA 10173).

BEFORE:
```python
    def __str__(self):
        return self.name
```

AFTER:
```python
    def __str__(self) -> str:
        # RA 10173: Never expose customer names in __str__ for financial models.
        # __str__ appears in admin list views, logs, and repr() output.
        return f"HY-{self.pk:04d}"
```

#### [MODIFY] apps/users/models.py (line 67)
**What changes:** Replace deprecated `unique_together` with `UniqueConstraint` in the Permission model.

BEFORE:
```python
    class Meta:
        db_table = 'users_permission'
        unique_together = ('role', 'action')
```

AFTER:
```python
    class Meta:
        db_table = 'users_permission'
        constraints = [
            models.UniqueConstraint(
                fields=['role', 'action'],
                name='unique_permission_role_action',
            ),
        ]
```

WARNING: This requires a migration. The Developer must run `makemigrations` after this change. The migration will drop the old `unique_together` constraint and create the new `UniqueConstraint`. This is safe for existing data since the constraint is identical.

---

### Phase 4 — Infrastructure Fixes

#### [MODIFY] config/urls.py (lines 30-35)
**What changes:** Add `handler404` and `handler500` custom error handlers.

BEFORE:
```python
# Custom error handler — renders a friendly HTMX form fragment when a login
# attempt is blocked by django-ratelimit (Ratelimited is a PermissionDenied
# subclass, which Django routes to handler403).
handler403 = 'apps.users.views.ratelimited_view'
```

AFTER:
```python
# Custom error handlers — render friendly fragments for common errors.
handler403 = 'apps.users.views.ratelimited_view'
handler404 = 'apps.core.views.handler404_view'
handler500 = 'apps.core.views.handler500_view'
```

#### [NEW] apps/core/views.py — append handler404 and handler500
**What changes:** Add two simple error handler views to the existing `apps/core/views.py` file. These should be appended to the end of the file (after the existing toast helper functions). Read the file first to see its current content, then append the following functions.

```python
def handler404_view(request, exception=None):
    """Renders a friendly 404 page for both HTMX and full-page requests."""
    if request.headers.get("HX-Request") == "true":
        return render(request, "core/404_fragment.html", status=404)
    return render(request, "core/404.html", status=404)


def handler500_view(request):
    """Renders a friendly 500 page for both HTMX and full-page requests."""
    if request.headers.get("HX-Request") == "true":
        return render(request, "core/500_fragment.html", status=500)
    return render(request, "core/500.html", status=500)
```

#### [NEW] apps/core/templates/core/404.html
**What changes:** Simple 404 error page matching the Hydr8 design system.

```html
{% extends "base.html" %}
{% block title %}Not Found — Hydr8{% endblock %}
{% block main_class %}flex-1 flex items-center justify-center{% endblock %}
{% block content %}
<div class="text-center px-6">
    <span class="material-symbols-outlined text-outline text-[64px]">error_outline</span>
    <h1 class="font-headline-lg text-headline-lg font-bold text-on-surface mt-4">Page Not Found</h1>
    <p class="text-body-md text-on-surface-variant mt-2">The page you're looking for doesn't exist or has been moved.</p>
    <a href="{% url 'analytics:dashboard' %}" class="inline-flex items-center gap-2 mt-6 px-4 py-2 bg-primary text-on-primary rounded-lg font-body-md hover:bg-primary/90 transition-colors">
        <span class="material-symbols-outlined text-[18px]">home</span>
        Back to Dashboard
    </a>
</div>
{% endblock %}
```

#### [NEW] apps/core/templates/core/404_fragment.html
**What changes:** HTMX fragment version of the 404 error.

```html
<div class="text-center px-6 py-12">
    <span class="material-symbols-outlined text-outline text-[48px]">error_outline</span>
    <p class="font-body-md font-bold text-on-surface mt-2">Not Found</p>
    <p class="text-body-sm text-on-surface-variant mt-1">This content could not be found.</p>
</div>
```

#### [NEW] apps/core/templates/core/500.html
**What changes:** Simple 500 error page matching the Hydr8 design system.

```html
{% extends "base.html" %}
{% block title %}Server Error — Hydr8{% endblock %}
{% block main_class %}flex-1 flex items-center justify-center{% endblock %}
{% block content %}
<div class="text-center px-6">
    <span class="material-symbols-outlined text-error text-[64px]">crisis_alert</span>
    <h1 class="font-headline-lg text-headline-lg font-bold text-on-surface mt-4">Something Went Wrong</h1>
    <p class="text-body-md text-on-surface-variant mt-2">An unexpected error occurred. Please try again or contact support if the problem persists.</p>
    <a href="{% url 'analytics:dashboard' %}" class="inline-flex items-center gap-2 mt-6 px-4 py-2 bg-primary text-on-primary rounded-lg font-body-md hover:bg-primary/90 transition-colors">
        <span class="material-symbols-outlined text-[18px]">home</span>
        Back to Dashboard
    </a>
</div>
{% endblock %}
```

#### [NEW] apps/core/templates/core/500_fragment.html
**What changes:** HTMX fragment version of the 500 error.

```html
<div class="text-center px-6 py-12">
    <span class="material-symbols-outlined text-error text-[48px]">crisis_alert</span>
    <p class="font-body-md font-bold text-on-surface mt-2">Server Error</p>
    <p class="text-body-sm text-on-surface-variant mt-1">An unexpected error occurred. Please try again.</p>
</div>
```

#### [MODIFY] config/settings/production.py
**What changes:** Add `CONN_MAX_AGE` for database connection pooling.

Read the file first to find the `DATABASES` setting, then add `CONN_MAX_AGE` to the `OPTIONS` or top-level of the default database config. The exact insertion point depends on the current file structure.

BEFORE (approximate — read the actual file):
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        ...
    }
}
```

AFTER:
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        ...
        'CONN_MAX_AGE': 600,  # 10-minute persistent connections
    }
}
```

---

### Phase 5 — Query Optimization (select_related / prefetch_related)

#### [MODIFY] apps/employees/selectors.py (line 590)
**What changes:** Add `.select_related('role')` to the user lookup in the `get_user_detail_context` selector to prevent N+1 when accessing `target.role.name`.

Read the file around line 590 to find the exact queryset, then add `.select_related('role')` to it.

#### [MODIFY] apps/employees/selectors.py (line 158)
**What changes:** Add `.select_related('role')` to the user queryset in `get_employee_directory_context` to prevent N+1 on `user.role.name` access in `_user_row`.

#### [MODIFY] apps/employees/selectors.py (line 281)
**What changes:** Add `.prefetch_related('permissions')` to the Role queryset in `get_roles_permissions_context` to prevent N+1 on `role.permissions.all()` in a loop.

#### [MODIFY] apps/products/selectors.py (line 159)
**What changes:** Add `.select_related('role')` to `riders_qs` to prevent N+1 on `driver.role.name` access in the loop.

#### [MODIFY] apps/remittance/selectors.py (line 226-244)
**What changes:** Add `.select_related("recorded_by")` to the Expense query in `_load_draft_state()`.

#### [MODIFY] apps/users/selectors.py (line 25)
**What changes:** Add `.select_related('company')` to `get_roles_for_user` queryset.

---

## Hand-off Checklist (Executor: SWE 1.7)

EXECUTOR: SWE 1.7 — Read before starting
------------------------------------------
1. Execute phases in order. Do not start Phase N+1 before Phase N passes its gate.
2. Run the gate command after each phase. Stop if it fails.
3. If a gate command fails, STOP. Report the exact error. Do not guess at a fix.
4. If an instruction is ambiguous with no code template, STOP. Do not invent behavior.
5. Two-attempt rule: If you fail the same gate twice, stop and ask.
6. Never use `python` or `python3` — always `uv run python`.
7. Never edit existing migrations — run `makemigrations` for schema changes.

Phase 1 — Security Critical Fixes
[ ] 1.1  Remove SECRET_KEY default in config/settings/base.py:14
[ ] 1.2  Pin Alpine.js CDN to 3.14.1 in templates/base.html:130
[ ] 1.3  Remove |safe from ai_insights_panel.html:39
[ ] 1.4  Remove |safe from remittance_history.html:208
[ ] 1.5  Add is_back_office import and guards to apps/audit/views.py
[ ] 1.6  Remove TEMP DEBUG logging in apps/users/views.py:140-145
Gate: `uv run python manage.py check` — must pass with 0 errors

Phase 2 — CSRF Token Fixes
[ ] 2.1  Add {% csrf_token %} to system_config.html form (line 67)
[ ] 2.2  Add {% csrf_token %} to company.html form (line 17)
[ ] 2.3  Add {% csrf_token %} to profile.html forms (lines 25, 87, 156)
[ ] 2.4  Add {% csrf_token %} to add_customer_modal.html form (line 53)
[ ] 2.5  Add {% csrf_token %} to edit_customer_modal.html form (line 51)
[ ] 2.6  Add {% csrf_token %} to record_debt_modal.html form (line 71)
[ ] 2.7  Add {% csrf_token %} to record_borrowed_modal.html form (line 58)
Gate: `uv run python manage.py check` — must pass with 0 errors

Phase 3 — Convention & Privacy Fixes
[ ] 3.1  Remove duplicate decorators in apps/customers/views.py:121-123
[ ] 3.2  Change Customer.__str__ to return display ID in apps/customers/models.py:69-70
[ ] 3.3  Replace unique_together with UniqueConstraint in apps/users/models.py:67
[ ] 3.4  Run makemigrations for the Permission constraint change
Gate: `uv run python manage.py makemigrations --check --dry-run` — must show the expected migration
Gate: `uv run python manage.py makemigrations` — must create the migration
Gate: `uv run python manage.py check` — must pass with 0 errors

Phase 4 — Infrastructure Fixes
[ ] 4.1  Add handler404/handler500 to config/urls.py
[ ] 4.2  Append handler404_view and handler500_view to apps/core/views.py
[ ] 4.3  Create apps/core/templates/core/404.html
[ ] 4.4  Create apps/core/templates/core/404_fragment.html
[ ] 4.5  Create apps/core/templates/core/500.html
[ ] 4.6  Create apps/core/templates/core/500_fragment.html
[ ] 4.7  Add CONN_MAX_AGE to config/settings/production.py DATABASES config
Gate: `uv run python manage.py check` — must pass with 0 errors

Phase 5 — Query Optimization
[ ] 5.1  Add .select_related('role') to user queryset in apps/employees/selectors.py:158
[ ] 5.2  Add .prefetch_related('permissions') to Role queryset in apps/employees/selectors.py:281
[ ] 5.3  Add .select_related('role') to user lookup in apps/employees/selectors.py:590
[ ] 5.4  Add .select_related('role') to riders_qs in apps/products/selectors.py:159
[ ] 5.5  Add .select_related("recorded_by") to Expense query in apps/remittance/selectors.py:226-244
[ ] 5.6  Add .select_related('company') to get_roles_for_user in apps/users/selectors.py:25
Gate: `uv run python manage.py check` — must pass with 0 errors

## Verification Plan

### Automated Tests
```bash
# Full test suite — must pass with 0 failures (433 tests expected)
cd /Users/dasher/SoftDev/hydr8/server && uv run python manage.py test

# Per-domain tests for changed areas
uv run python manage.py test apps.audit
uv run python manage.py test apps.customers
uv run python manage.py test apps.users
uv run python manage.py test apps.remittance
uv run python manage.py test apps.employees
uv run python manage.py test apps.products
```

### Manual Verification
1. **SECRET_KEY**: Confirm `.env` has `SECRET_KEY` set, then `uv run python manage.py check` passes
2. **CSRF tokens**: Open each settings and customers modal in the browser, submit a form, confirm no 403 CSRF error
3. **Audit AuthZ**: Log in as a Driver role user, navigate to `/audit/`, confirm 403 Forbidden
4. **404/500 pages**: Navigate to a non-existent URL, confirm the 404 page renders
5. **Alpine.js**: Confirm all Alpine.js components still initialize (modals, theme toggle, etc.)

## Out of Scope
| Item | Reason Deferred |
|---|---|
| Keyword-only args sweep (50+ functions) | Large mechanical refactor — separate batch plan needed |
| verbose_name_plural sweep (all models) | Large mechanical refactor — separate batch plan needed |
| admin.py registrations (7 stub files) | Design decision needed per-model — separate plan needed |
| Missing test_services.py files (4 domains) | Large test-writing effort — separate plan needed |
| Hardcoded #D97706 hex color replacement | Design system token decision needed — separate plan needed |
| F() expressions in remittance/services.py | False positive — service uses write-only pattern, not read-modify-write |
| UniqueConstraint soft-delete conditions (remittance) | Needs careful analysis of which constraints need conditions — separate plan |
| DailySnapshot model (analytics) | Architectural decision: implement or remove — separate plan |
| Audit log retention/partitioning | Infrastructure design decision — separate plan |
| DRF/django-cors-headers removal | Architectural decision: keep for future API or remove — separate plan |
| requirements/ vs pyproject.toml sync | Migration strategy decision — separate plan |
| AppConfig default_auto_field sweep | Low-priority mechanical change — separate batch plan |
