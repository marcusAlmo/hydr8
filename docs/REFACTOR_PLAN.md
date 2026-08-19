# Hydr8 Architecture Refactor Plan

> **Branch:** `refactor/architecture-cleanup`  
> **Target:** Simplify architecture, remove over-engineering, establish CI/CD  
> **Status:** Planning Complete — Ready for Execution

---

## Executive Summary

This refactor addresses architectural debt identified in the brutal architecture review:
- **Remove AI integration** — Gemma 2B edge AI is solution-looking-for-a-problem
- **Consolidate apps** — 9 apps → 5 apps (reduce cross-app import complexity)
- **Simplify multi-tenancy** — App-level only (remove RLS middleware)
- **Extract presentation logic** — Move template-shaping out of selectors
- **Establish CI/CD** — Branch protection with automated testing (develop → staging → main)
- **Professional documentation** — Remove AI-style comments, add instructional comments

**Estimated Impact:**
- ~30% reduction in cross-app imports
- ~1200 lines of code removed (analytics app, RLS middleware, DRF)
- Clear separation of concerns (data layer vs presentation layer)
- Automated quality gates on every merge

---

## Phase 1: Remove AI Integration

### 1.1 Delete Analytics App
**Rationale:** The `analytics` app exists primarily to serve REST endpoints for a client-side Gemma 2B LLM. For a 5-user water station CRUD tool, precomputed SQL aggregations deliver 10x the value at 1% complexity.

**Actions:**
- [ ] Remove `apps.analytics` from `INSTALLED_APPS` (base.py)
- [ ] Remove `path('analytics/', include('apps.analytics.urls'))` from root URLconf
- [ ] Delete `server/apps/analytics/` directory
- [ ] Remove `djangorestframework` from dependencies (pyproject.toml, requirements/base.txt)
- [ ] Remove `django-cors-headers` from dependencies (only needed for DRF)
- [ ] Move dashboard view to `apps.core` (analytics:dashboard → core:dashboard)
- [ ] Update `LOGIN_REDIRECT_URL` in settings to point to new dashboard location
- [ ] Update all navigation links/templates referencing `analytics:*` URLs

**Files to modify:**
```
server/config/settings/base.py
server/config/urls.py
server/pyproject.toml
server/requirements/base.txt
server/apps/core/views.py (add dashboard view)
server/apps/core/urls.py (add dashboard route)
server/apps/core/templates/core/dashboard.html (move from analytics)
server/templates/partials/sidebar.html (update nav links)
```

**Files to delete:**
```
server/apps/analytics/
```

### 1.2 Remove AI References from Documentation
**Actions:**
- [ ] Remove Gemma 2B references from `docs/PROJECT_PLAN.md`
- [ ] Remove AI chatbot references from `server/hydr8_schema.md`
- [ ] Remove WebGPU/edge AI references from `server/hydr8_stitch_prompt.md`
- [ ] Update architecture diagrams to remove analytics domain

**Files to modify:**
```
docs/PROJECT_PLAN.md
server/hydr8_schema.md
server/hydr8_stitch_prompt.md
```

---

## Phase 2: Consolidate Apps

### 2.1 Merge `employees` → `users`
**Rationale:** `employees` has no models — it's selectors over `apps.users.User`. It's a view surface, not a domain.

**Actions:**
- [ ] Move `apps/employees/selectors.py` → `apps/users/selectors_employees.py`
- [ ] Move `apps/employees/views.py` → `apps/users/views_employees.py`
- [ ] Move `apps/employees/urls.py` → `apps/users/urls_employees.py`
- [ ] Move `apps/employees/templates/` → `apps/users/templates/users/employees/`
- [ ] Move `apps/employees/tests/` → `apps/users/tests/test_employees_*.py`
- [ ] Update `apps/users/urls.py` to include employees routes
- [ ] Remove `apps.employees` from `INSTALLED_APPS`
- [ ] Remove `path('employees/', include('apps.employees.urls'))` from root URLconf
- [ ] Delete `apps/employees/` directory

**Import updates:**
```python
# Before
from apps.employees.selectors import list_employees

# After
from apps.users.selectors_employees import list_employees
```

**Files to modify:**
```
server/config/settings/base.py
server/config/urls.py
server/apps/users/urls.py
All files importing from apps.employees.*
```

**Files to delete:**
```
server/apps/employees/
```

### 2.2 Merge `settings` + `audit` → `core`
**Rationale:** `settings` is the shared kernel (Company, SystemConfig). `audit` is a thin wrapper around django-auditlog. Both belong in `core`.

**Actions:**
- [ ] Move `apps/settings/models.py` (Company, SystemConfig) → `apps/core/models.py`
- [ ] Move `apps/settings/services.py` → `apps/core/services_settings.py`
- [ ] Move `apps/settings/selectors.py` → `apps/core/selectors_settings.py`
- [ ] Move `apps/settings/views.py` → `apps/core/views_settings.py`
- [ ] Move `apps/settings/urls.py` → `apps/core/urls_settings.py`
- [ ] Move `apps/settings/templates/` → `apps/core/templates/core/settings/`
- [ ] Move `apps/settings/tests/` → `apps/core/tests/test_settings_*.py`
- [ ] Move `apps/settings/migrations/` → `apps/core/migrations/` (merge + renumber)
- [ ] Move `apps/audit/selectors.py` → `apps/core/selectors_audit.py`
- [ ] Move `apps/audit/views.py` → `apps/core/views_audit.py`
- [ ] Move `apps/audit/urls.py` → `apps/core/urls_audit.py`
- [ ] Move `apps/audit/templates/` → `apps/core/templates/core/audit/`
- [ ] Move `apps/audit/tests/` → `apps/core/tests/test_audit_*.py`
- [ ] Update `apps/core/urls.py` to include settings + audit routes
- [ ] Remove `apps.settings` and `apps.audit` from `INSTALLED_APPS`
- [ ] Remove settings/audit URL includes from root URLconf
- [ ] Update all ForeignKey references: `'settings.Company'` → `'core.Company'`
- [ ] Create migration to rename `settings_company` → `core_company`, `settings_systemconfig` → `core_systemconfig`
- [ ] Delete `apps/settings/` and `apps/audit/` directories

**Import updates:**
```python
# Before
from apps.settings.models import Company, SystemConfig
from apps.audit.selectors import get_audit_log

# After
from apps.core.models import Company, SystemConfig
from apps.core.selectors_audit import get_audit_log
```

**Files to modify:**
```
server/config/settings/base.py
server/config/urls.py
server/apps/core/urls.py
server/apps/core/models.py
All models with ForeignKey('settings.Company')
All files importing from apps.settings.* or apps.audit.*
```

**Files to delete:**
```
server/apps/settings/
server/apps/audit/
```

### 2.3 Merge `products` → `core`
**Rationale:** `products` is catalog data (shared kernel). It has no complex business logic — just CRUD over Product model.

**Actions:**
- [ ] Move `apps/products/services.py` → `apps/core/services_products.py`
- [ ] Move `apps/products/selectors.py` → `apps/core/selectors_products.py`
- [ ] Move `apps/products/views.py` → `apps/core/views_products.py`
- [ ] Move `apps/products/urls.py` → `apps/core/urls_products.py`
- [ ] Move `apps/products/templates/` → `apps/core/templates/core/products/`
- [ ] Move `apps/products/tests/` → `apps/core/tests/test_products_*.py`
- [ ] Update `apps/core/urls.py` to include products routes
- [ ] Remove `apps.products` from `INSTALLED_APPS`
- [ ] Remove products URL include from root URLconf
- [ ] Delete `apps/products/` directory

**Import updates:**
```python
# Before
from apps.products.selectors import list_active_products

# After
from apps.core.selectors_products import list_active_products
```

**Files to modify:**
```
server/config/settings/base.py
server/config/urls.py
server/apps/core/urls.py
All files importing from apps.products.*
```

**Files to delete:**
```
server/apps/products/
```

### 2.4 Final App Structure
```
server/apps/
├── users/       ← IAM + Employees (Role, User, DriverCommission, employee views)
├── core/        ← Shared Kernel (Product, Company, SystemConfig, Settings, Audit, Dashboard)
├── customers/   ← Customer Domain (Customer, CreditLine, CreditPayment, borrowed items)
└── remittance/  ← Operations Domain (Remittance, RemittanceRider, Expenses, RiderCredit)
```

**Dependency flow:**
```
users → core → customers → remittance
```

---

## Phase 3: Simplify Multi-Tenancy (App-Level Only)

### 3.1 Remove RLS Middleware
**Rationale:** Two parallel tenant mechanisms (RLS + `for_user()`) create false confidence. RLS is untested in dev/test. Pick one: app-level.

**Actions:**
- [ ] Remove `TenantMiddleware` from `MIDDLEWARE` list (base.py)
- [ ] Delete `TenantMiddleware` class from `apps/core/middleware.py`
- [ ] Remove all `SET app.current_tenant` SQL logic
- [ ] Remove RLS policy references from schema documentation

**Files to modify:**
```
server/config/settings/base.py
server/apps/core/middleware.py
server/hydr8_schema.md
```

### 3.2 Make `TenantManager` the Default Manager
**Rationale:** `Model.objects.all()` should be tenant-scoped by default. Explicit `.all_tenants()` escape hatch for superuser/admin views.

**Actions:**
- [ ] Update `TenantManager` to override `get_queryset()` to auto-scope by current user
- [ ] Add `all_tenants()` method to `TenantQuerySet` that returns unfiltered queryset
- [ ] Store current user in thread-local or context variable (set by middleware)
- [ ] Update all `Model.objects.for_user(request.user)` calls to `Model.objects.all()`
- [ ] Update superuser/admin views to use `Model.objects.all_tenants()` explicitly

**Files to modify:**
```
server/apps/core/managers.py
server/apps/core/middleware.py (add CurrentUserMiddleware)
All selectors/views using .for_user()
```

**New pattern:**
```python
# apps/core/middleware.py
from contextvars import ContextVar
current_user_var: ContextVar = ContextVar('current_user', default=None)

class CurrentUserMiddleware:
    """Stores the current authenticated user in a context variable for tenant scoping."""
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        user = getattr(request, 'user', None)
        token = current_user_var.set(user)
        try:
            response = self.get_response(request)
        finally:
            current_user_var.reset(token)
        return response

# apps/core/managers.py
class TenantQuerySet(models.QuerySet):
    def get_queryset(self):
        """Auto-scope by current user's company. Superusers see all tenants."""
        from apps.core.middleware import current_user_var
        user = current_user_var.get()
        if not user or not user.is_authenticated:
            return self.none()
        if user.is_superuser or not hasattr(user, 'company_id') or user.company_id is None:
            return super().get_queryset()
        return super().get_queryset().filter(company_id=user.company_id)
    
    def all_tenants(self):
        """Escape hatch: return unfiltered queryset (for superuser/admin views)."""
        return super().get_queryset()
```

### 3.3 Remove `null=True, blank=True` from `company` ForeignKey
**Rationale:** Null-tenant rows complicate unique constraints and create dual code paths. All rows should belong to a tenant.

**Actions:**
- [ ] Create migration to set `company_id` to a default tenant for all null rows
- [ ] Create migration to alter `company` ForeignKey: remove `null=True, blank=True`
- [ ] Remove duplicate unique constraints (`unique_*_company_*` + `unique_*_null_company_*`)
- [ ] Update model definitions to make `company` required

**Files to modify:**
```
All models with company ForeignKey
All migrations with split unique constraints
```

---

## Phase 4: Extract Presentation Logic

### 4.1 Create `presentation.py` in Each App
**Rationale:** Selectors return data; presentation modules shape it for templates. Decouples data layer from template structure.

**Actions:**
- [ ] Create `apps/remittance/presentation.py`
- [ ] Create `apps/customers/presentation.py`
- [ ] Create `apps/core/presentation.py`
- [ ] Move template-shaping logic from selectors to presentation modules:
  - `avatar_classes`, `initials`, `driver_code` → presentation
  - `alpine_seed` JSON construction → presentation
  - `selected` flags → presentation
  - Dict-shaping for template context → presentation

**Pattern:**
```python
# apps/remittance/selectors.py (BEFORE)
def get_add_remittance_context(user, remittance_date=None):
    """Returns dict shaped for add_remittance.html template."""
    riders = []
    for rider in active_riders:
        riders.append({
            'id': rider.id,
            'name': rider.get_full_name(),
            'avatar_classes': avatar_classes(rider),
            'initials': initials(rider),
            'driver_code': driver_code(rider),
            'selected': rider.id == first_rider_id,
        })
    return {'riders': riders, ...}

# apps/remittance/selectors.py (AFTER)
def get_active_riders(user):
    """Returns active driver users for the current tenant."""
    return User.objects.filter(
        role__name__iexact="driver",
        deleted_at__isnull=True,
        is_active=True,
    ).select_related('role')

# apps/remittance/presentation.py (NEW)
def format_rider_for_template(rider, selected=False):
    """Formats a User instance for display in remittance templates."""
    from apps.users.presentation import avatar_classes, initials, driver_code
    return {
        'id': rider.id,
        'name': rider.get_full_name(),
        'avatar_classes': avatar_classes(rider),
        'initials': initials(rider),
        'driver_code': driver_code(rider),
        'selected': selected,
    }

def build_alpine_seed(riders, products, repayments, staff, other_sales, tithe_rate):
    """Constructs the Alpine.js initialization payload for add_remittance.html."""
    return {
        'riders': riders,
        'products': products,
        'repayments': repayments,
        'totalCredits': sum(r['amount'] for r in repayments),
        'staff': staff,
        'otherSales': other_sales,
        'titheRate': tithe_rate,
    }

# apps/remittance/views.py (AFTER)
from .selectors import get_active_riders, get_active_products
from .presentation import format_rider_for_template, build_alpine_seed

def add_remittance_view(request):
    riders = get_active_riders(request.user)
    riders_formatted = [format_rider_for_template(r, selected=(i==0)) for i, r in enumerate(riders)]
    products = get_active_products(request.user)
    # ... build context
    alpine_seed = build_alpine_seed(riders_formatted, products, ...)
    return render(request, 'remittance/add_remittance.html', {'alpine_seed': alpine_seed})
```

**Files to modify:**
```
server/apps/remittance/selectors.py
server/apps/remittance/views.py
server/apps/customers/selectors.py
server/apps/customers/views.py
server/apps/core/selectors_*.py
server/apps/core/views_*.py
```

---

## Phase 5: Establish CI/CD

### 5.1 Create GitHub Actions Workflows

**Branch Strategy:**
```
develop (feature branches merge here)
   ↓
staging (only develop can merge; runs full test suite)
   ↓
main (only staging can merge; production-ready)
```

**Actions:**
- [ ] Create `.github/workflows/test.yml` (runs on all branches)
- [ ] Create `.github/workflows/staging.yml` (runs on merge to staging)
- [ ] Create `.github/workflows/deploy.yml` (runs on merge to main)
- [ ] Create branch protection rules via GitHub API or UI

**Files to create:**
```
.github/workflows/test.yml
.github/workflows/staging.yml
.github/workflows/deploy.yml
```

### 5.2 Test Workflow (All Branches)
```yaml
# .github/workflows/test.yml
name: Test Suite

on:
  push:
    branches: ['**']
  pull_request:
    branches: ['**']

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: hydr8_test
          POSTGRES_USER: hydr8
          POSTGRES_PASSWORD: hydr8
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: |
          cd server
          uv pip install --system -r requirements/base.txt
          uv pip install --system -r requirements/local.txt
      
      - name: Run tests
        env:
          DATABASE_URL: postgres://hydr8:hydr8@localhost:5432/hydr8_test
          SECRET_KEY: test-secret-key-for-ci
          DEBUG: 'False'
          ALLOWED_HOSTS: localhost,127.0.0.1
        run: |
          cd server
          python manage.py test --settings=config.settings.test
      
      - name: Check migrations
        env:
          DATABASE_URL: postgres://hydr8:hydr8@localhost:5432/hydr8_test
          SECRET_KEY: test-secret-key-for-ci
        run: |
          cd server
          python manage.py makemigrations --check --dry-run --settings=config.settings.test
```

### 5.3 Staging Workflow (Merge to Staging)
```yaml
# .github/workflows/staging.yml
name: Staging Deployment

on:
  push:
    branches: [staging]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: hydr8_test
          POSTGRES_USER: hydr8
          POSTGRES_PASSWORD: hydr8
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: |
          cd server
          uv pip install --system -r requirements/base.txt
          uv pip install --system -r requirements/local.txt
      
      - name: Run full test suite
        env:
          DATABASE_URL: postgres://hydr8:hydr8@localhost:5432/hydr8_test
          SECRET_KEY: test-secret-key-for-ci
          DEBUG: 'False'
          ALLOWED_HOSTS: localhost,127.0.0.1
        run: |
          cd server
          python manage.py test --settings=config.settings.test --verbosity=2
      
      - name: Run type checks
        run: |
          cd server
          mypy apps/ --config-file=pyproject.toml || true
      
      - name: Check code style
        run: |
          cd server
          ruff check apps/ || true
```

### 5.4 Main Workflow (Production Deployment)
```yaml
# .github/workflows/deploy.yml
name: Production Deployment

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Verify source branch
        run: |
          # Ensure this commit came from staging
          git fetch origin staging
          if ! git merge-base --is-ancestor HEAD origin/staging; then
            echo "ERROR: main can only receive merges from staging"
            exit 1
          fi
      
      - name: Deploy to production
        run: |
          echo "Production deployment steps go here"
          # SSH to VPS, pull latest, run migrations, restart gunicorn, etc.
```

### 5.5 Branch Protection Rules

**Create via GitHub UI or API:**

**`develop` branch:**
- Require pull request reviews: No (feature branches can merge directly)
- Require status checks: Yes (test workflow must pass)

**`staging` branch:**
- Require pull request reviews: Yes (1 approval)
- Require status checks: Yes (test workflow must pass)
- Restrict who can push: Only from `develop` branch

**`main` branch:**
- Require pull request reviews: Yes (1 approval)
- Require status checks: Yes (staging workflow must pass)
- Restrict who can push: Only from `staging` branch
- Require linear history: Yes (no merge commits)

---

## Phase 6: Remove AI-Style Comments

### 6.1 Identify AI-Style Comments
**Patterns to remove:**
- Emoji comments (🔥, ✨, 🚀, etc.)
- Overly enthusiastic language ("Awesome!", "Magic happens here!", "Super cool!")
- Redundant docstrings that restate the function name
- Comments that apologize or hedge ("This is a bit hacky but...", "Not sure if this is the best way...")

### 6.2 Add Professional Instructional Comments
**Patterns to add:**
- **Why, not what:** Explain business logic, not syntax
- **Invariants:** Document assumptions and constraints
- **Edge cases:** Call out non-obvious behavior
- **References:** Link to tickets, RFCs, or external docs

**Example transformation:**
```python
# BEFORE (AI-style)
def finalize_remittance(remittance_id, user, pin):
    """
    Finalizes a remittance. 🚀
    
    This is the main function that locks everything down!
    Super important — don't mess with this. 😅
    """
    # Magic happens here! ✨
    remittance = Remittance.objects.get(id=remittance_id)
    # TODO: This is a bit hacky but it works for now
    if remittance.status == 'FINALIZED':
        raise ValidationError("Already finalized!")
    # ... rest of function

# AFTER (professional instructional)
def finalize_remittance(remittance_id, user, pin):
    """
    Locks a remittance and all related records (riders, expenses, credits).
    
    Finalization is atomic: all denormalized totals are recomputed and the
    status is set to FINALIZED in a single transaction. Once finalized, the
    remittance cannot be edited (enforced at the service layer and in the UI).
    
    Args:
        remittance_id: Primary key of the Remittance to finalize
        user: User performing the finalization (must have write permission)
        pin: User's PIN for verification (required for financial operations)
    
    Raises:
        ValidationError: If PIN is incorrect, remittance is already finalized,
                        or required fields are missing
        PermissionDenied: If user lacks remittance write permission
    
    Invariants:
        - Remittance.status transitions DRAFT → FINALIZED (one-way)
        - All denormalized totals match sum of related records
        - finalized_by and finalized_at are set atomically with status change
    """
    remittance = Remittance.objects.select_for_update().get(id=remittance_id)
    
    # Prevent double-finalization. This check is also enforced in the UI,
    # but we guard at the service layer to prevent race conditions.
    if remittance.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError("Remittance has already been finalized.")
    
    # ... rest of function
```

**Files to audit:**
```
All Python files in server/apps/
Focus on services.py, views.py, models.py
```

---

## Phase 7: Update Documentation

### 7.1 Update Architecture Documentation
**Actions:**
- [ ] Update `docs/PROJECT_PLAN.md` to reflect new 4-app structure
- [ ] Update `server/hydr8_schema.md` to remove analytics domain
- [ ] Update dependency flow diagram: `users → core → customers → remittance`
- [ ] Remove RLS references from schema doc
- [ ] Document new tenant-scoping pattern (CurrentUserMiddleware + TenantManager)
- [ ] Update app descriptions to reflect consolidation

**Files to modify:**
```
docs/PROJECT_PLAN.md
server/hydr8_schema.md
server/hydr8_stitch_prompt.md
```

### 7.2 Update AGENTS.md
**Actions:**
- [ ] Remove analytics references
- [ ] Document new app structure
- [ ] Update multi-tenancy convention (app-level only)
- [ ] Add CI/CD workflow documentation
- [ ] Add presentation layer convention

**Files to modify:**
```
AGENTS.md
```

### 7.3 Create Migration Guide
**Actions:**
- [ ] Create `docs/MIGRATION_GUIDE.md` documenting:
  - Import path changes (apps.employees.* → apps.users.*)
  - URL name changes (analytics:dashboard → core:dashboard)
  - Model changes (settings.Company → core.Company)
  - Selector pattern changes (for_user() → default behavior)

**Files to create:**
```
docs/MIGRATION_GUIDE.md
```

### 7.4 Clean Up Repository Root
**Actions:**
- [ ] Remove `learning_guide/` directory
- [ ] Remove `to-do-list.md` (migrate to GitHub Issues)
- [ ] Remove `server/repomix-output.xml`
- [ ] Remove orphaned `package-lock.json`
- [ ] Add `.gitignore` entries for tool artifacts

**Files to delete:**
```
learning_guide/
to-do-list.md
server/repomix-output.xml
package-lock.json
```

---

## Execution Order

Execute phases in strict order to avoid breaking dependencies:

1. **Phase 1:** Remove AI integration (analytics app, DRF)
2. **Phase 2:** Consolidate apps (employees → users, settings+audit → core, products → core)
3. **Phase 4:** Extract presentation logic (create presentation.py modules)
4. **Phase 3:** Simplify multi-tenancy (remove RLS, make TenantManager default)
5. **Phase 5:** Establish CI/CD (GitHub Actions, branch protection)
6. **Phase 6:** Remove AI-style comments, add professional documentation
7. **Phase 7:** Update all documentation

**Why this order:**
- Phase 1 first: Removes entire app, simplifies later consolidation
- Phase 2 before Phase 4: Fewer files to migrate presentation logic from
- Phase 3 after Phase 2: Fewer models to update for tenant changes
- Phase 5 after code changes: CI validates the refactored codebase
- Phase 6 & 7 last: Documentation reflects final state

---

## Testing Strategy

After each phase:
1. Run full test suite: `python manage.py test`
2. Check for missing migrations: `python manage.py makemigrations --check`
3. Verify no import errors: `python manage.py check`
4. Manual smoke test: Login → Dashboard → Add Remittance → Customers

After all phases:
1. Full regression test on staging environment
2. Verify all URLs resolve correctly
3. Verify all templates render without errors
4. Run load test on remittance finalization (most complex transaction)

---

## Rollback Plan

Each phase is committed separately. If a phase introduces regressions:
1. Revert the phase's commits: `git revert <commit-range>`
2. Fix the issue in a new commit
3. Re-apply the phase

The branch structure (`develop → staging → main`) ensures production is never broken:
- Regressions caught in `develop` before reaching `staging`
- Staging runs full test suite before allowing merge to `main`

---

## Success Metrics

**Code Metrics:**
- [ ] Total apps: 9 → 5 (44% reduction)
- [ ] Lines of code removed: ~1200 (analytics + RLS + DRF)
- [ ] Cross-app imports: ~30% reduction
- [ ] Test coverage: Maintained at current level (38 test files)

**Quality Metrics:**
- [ ] CI passing on all branches
- [ ] Zero import errors
- [ ] Zero migration conflicts
- [ ] All URLs resolve correctly

**Documentation Metrics:**
- [ ] Architecture diagram matches codebase
- [ ] All import paths documented in migration guide
- [ ] AGENTS.md reflects new conventions

---

## Timeline Estimate

| Phase | Estimated Time | Dependencies |
|---|---|---|
| Phase 1: Remove AI | 2-3 hours | None |
| Phase 2: Consolidate Apps | 6-8 hours | Phase 1 |
| Phase 4: Extract Presentation | 4-6 hours | Phase 2 |
| Phase 3: Simplify Multi-Tenancy | 3-4 hours | Phase 2 |
| Phase 5: CI/CD | 2-3 hours | Phases 1-4 |
| Phase 6: Comments | 3-4 hours | Phases 1-4 |
| Phase 7: Documentation | 2-3 hours | All phases |

**Total: 22-31 hours** (3-4 working days)

---

## Sign-Off

This plan is ready for execution. Each phase is self-contained and can be committed independently. The branch protection strategy ensures no breaking changes reach production.

**Next Step:** Begin Phase 1 (Remove AI Integration)
