# Architecture Refactor — Execution Checklist

> **Branch:** `refactor/architecture-cleanup`  
> **Status:** Planning Complete — Ready for Execution

---

## Planning Phase ✅

- [x] Brutal architecture review completed
- [x] Refactor branch created (`refactor/architecture-cleanup`)
- [x] Comprehensive plan written (835 lines)
- [x] Execution instructions written (311 lines)
- [x] Comment style guide written (487 lines)
- [x] Quick reference created (293 lines)
- [x] Executive summary written (369 lines)
- [x] Branch pushed to origin

**Planning Documentation:** 2295 lines across 5 files

---

## Phase 1: Remove AI Integration (2-3 hours)

### 1.1 Remove Analytics App
- [ ] Remove `apps.analytics` from `INSTALLED_APPS` (base.py)
- [ ] Remove `path('analytics/', ...)` from root URLconf
- [ ] Delete `server/apps/analytics/` directory
- [ ] Remove `djangorestframework` from pyproject.toml
- [ ] Remove `djangorestframework` from requirements/base.txt
- [ ] Remove `django-cors-headers` from pyproject.toml
- [ ] Remove `django-cors-headers` from requirements/base.txt

### 1.2 Move Dashboard to Core
- [ ] Create `apps/core/views_dashboard.py`
- [ ] Move dashboard view from analytics to core
- [ ] Create `apps/core/templates/core/dashboard.html`
- [ ] Move dashboard template from analytics to core
- [ ] Add dashboard route to `apps/core/urls.py`
- [ ] Update `LOGIN_REDIRECT_URL` in settings (analytics:dashboard → core:dashboard)

### 1.3 Update References
- [ ] Update all `analytics:*` URL references in templates
- [ ] Update sidebar navigation links
- [ ] Update any imports from `apps.analytics.*`

### 1.4 Test
- [ ] Run test suite: `python manage.py test`
- [ ] Check migrations: `python manage.py makemigrations --check`
- [ ] Verify imports: `python manage.py check`
- [ ] Manual smoke test: Login → Dashboard

### 1.5 Commit
- [ ] `git add .`
- [ ] `git commit -m "refactor: Remove AI integration (analytics app, DRF)"`
- [ ] `git push`

---

## Phase 2: Consolidate Apps (6-8 hours)

### 2.1 Merge employees → users
- [ ] Move `apps/employees/selectors.py` → `apps/users/selectors_employees.py`
- [ ] Move `apps/employees/views.py` → `apps/users/views_employees.py`
- [ ] Move `apps/employees/urls.py` → `apps/users/urls_employees.py`
- [ ] Move `apps/employees/templates/` → `apps/users/templates/users/employees/`
- [ ] Move `apps/employees/tests/` → `apps/users/tests/test_employees_*.py`
- [ ] Update `apps/users/urls.py` to include employees routes
- [ ] Remove `apps.employees` from `INSTALLED_APPS`
- [ ] Remove `path('employees/', ...)` from root URLconf
- [ ] Update all imports from `apps.employees.*`
- [ ] Delete `apps/employees/` directory
- [ ] Test: `python manage.py test`
- [ ] Commit: `git commit -m "refactor: Merge employees app into users"`

### 2.2 Merge settings + audit → core
- [ ] Move `apps/settings/models.py` → `apps/core/models.py` (merge)
- [ ] Move `apps/settings/services.py` → `apps/core/services_settings.py`
- [ ] Move `apps/settings/selectors.py` → `apps/core/selectors_settings.py`
- [ ] Move `apps/settings/views.py` → `apps/core/views_settings.py`
- [ ] Move `apps/settings/urls.py` → `apps/core/urls_settings.py`
- [ ] Move `apps/settings/templates/` → `apps/core/templates/core/settings/`
- [ ] Move `apps/settings/tests/` → `apps/core/tests/test_settings_*.py`
- [ ] Move `apps/audit/selectors.py` → `apps/core/selectors_audit.py`
- [ ] Move `apps/audit/views.py` → `apps/core/views_audit.py`
- [ ] Move `apps/audit/urls.py` → `apps/core/urls_audit.py`
- [ ] Move `apps/audit/templates/` → `apps/core/templates/core/audit/`
- [ ] Move `apps/audit/tests/` → `apps/core/tests/test_audit_*.py`
- [ ] Update `apps/core/urls.py` to include settings + audit routes
- [ ] Remove `apps.settings` and `apps.audit` from `INSTALLED_APPS`
- [ ] Remove settings/audit URL includes from root URLconf
- [ ] Update all ForeignKey references: `'settings.Company'` → `'core.Company'`
- [ ] Create migration to rename tables (settings_company → core_company, etc.)
- [ ] Update all imports from `apps.settings.*` and `apps.audit.*`
- [ ] Delete `apps/settings/` and `apps/audit/` directories
- [ ] Test: `python manage.py test`
- [ ] Commit: `git commit -m "refactor: Merge settings and audit apps into core"`

### 2.3 Merge products → core
- [ ] Move `apps/products/services.py` → `apps/core/services_products.py`
- [ ] Move `apps/products/selectors.py` → `apps/core/selectors_products.py`
- [ ] Move `apps/products/views.py` → `apps/core/views_products.py`
- [ ] Move `apps/products/urls.py` → `apps/core/urls_products.py`
- [ ] Move `apps/products/templates/` → `apps/core/templates/core/products/`
- [ ] Move `apps/products/tests/` → `apps/core/tests/test_products_*.py`
- [ ] Update `apps/core/urls.py` to include products routes
- [ ] Remove `apps.products` from `INSTALLED_APPS`
- [ ] Remove products URL include from root URLconf
- [ ] Update all imports from `apps.products.*`
- [ ] Delete `apps/products/` directory
- [ ] Test: `python manage.py test`
- [ ] Commit: `git commit -m "refactor: Merge products app into core"`

---

## Phase 3: Extract Presentation Logic (4-6 hours)

### 3.1 Create Presentation Modules
- [ ] Create `apps/remittance/presentation.py`
- [ ] Create `apps/customers/presentation.py`
- [ ] Create `apps/core/presentation.py`

### 3.2 Migrate Remittance Presentation
- [ ] Move `avatar_classes`, `initials`, `driver_code` logic to presentation
- [ ] Move `alpine_seed` construction to presentation
- [ ] Move `selected` flag logic to presentation
- [ ] Update selectors to return plain data (not template-shaped dicts)
- [ ] Update views to use presentation layer
- [ ] Test: `python manage.py test apps.remittance`

### 3.3 Migrate Customers Presentation
- [ ] Move template-shaping logic from selectors to presentation
- [ ] Update selectors to return plain data
- [ ] Update views to use presentation layer
- [ ] Test: `python manage.py test apps.customers`

### 3.4 Migrate Core Presentation
- [ ] Move template-shaping logic from selectors to presentation
- [ ] Update selectors to return plain data
- [ ] Update views to use presentation layer
- [ ] Test: `python manage.py test apps.core`

### 3.5 Commit
- [ ] Test: `python manage.py test`
- [ ] Commit: `git commit -m "refactor: Extract presentation logic from selectors"`

---

## Phase 4: Simplify Multi-Tenancy (3-4 hours)

### 4.1 Remove RLS Middleware
- [x] Remove `TenantMiddleware` from `MIDDLEWARE` list (base.py)
- [x] Delete `TenantMiddleware` class from `apps/core/middleware.py`
- [x] Remove RLS references from schema documentation

### 4.2 Decision: Keep explicit `for_user()` (no CurrentUserMiddleware)
The original plan proposed a `CurrentUserMiddleware` that would auto-scope
querysets via `get_queryset()`. That was rejected because overriding
`get_queryset()` breaks management commands, migrations, and admin views
that need cross-tenant access. The explicit `for_user()` pattern is
retained as the single tenant-scoping entry point.

- [x] No `CurrentUserMiddleware` added — `for_user()` stays explicit
- [x] `TenantManager.for_user()` remains the sole scoping mechanism
- [x] Misleading RLS comments in code updated to reference app-level scoping

### 4.3 Test
- [ ] Test: `python manage.py test`

### 4.4 Commit
- [ ] Commit: `git commit -m "refactor: Remove dead RLS middleware, app-level tenancy only"`

---

## Phase 5: Establish CI/CD (2-3 hours)

### 5.1 Create Workflows
- [ ] Create `.github/workflows/test.yml`
- [ ] Create `.github/workflows/staging.yml`
- [ ] Create `.github/workflows/deploy.yml`

### 5.2 Configure Branch Protection
- [ ] Set up `develop` branch protection (require test workflow)
- [ ] Set up `staging` branch protection (require PR + test, only from develop)
- [ ] Set up `main` branch protection (require PR + staging workflow, only from staging)

### 5.3 Test
- [ ] Push to trigger test workflow
- [ ] Verify workflow passes

### 5.4 Commit
- [ ] Commit: `git commit -m "ci: Add GitHub Actions workflows and branch protection"`

---

## Phase 6: Professional Documentation (3-4 hours)

### 6.1 Audit Comments (apps/remittance)
- [ ] Remove emoji comments
- [ ] Remove enthusiastic language
- [ ] Remove hedging/apologizing
- [ ] Remove redundant docstrings
- [ ] Remove obvious inline comments
- [ ] Add docstrings to service functions (use template)
- [ ] Add inline comments for business logic
- [ ] Add inline comments for edge cases

### 6.2 Audit Comments (apps/customers)
- [ ] Same checklist as 6.1

### 6.3 Audit Comments (apps/core)
- [ ] Same checklist as 6.1

### 6.4 Audit Comments (apps/users)
- [ ] Same checklist as 6.1

### 6.5 Test
- [ ] Test: `python manage.py test`
- [ ] Manual review: Read through updated docstrings

### 6.6 Commit
- [ ] Commit: `git commit -m "docs: Replace AI-style comments with professional documentation"`

---

## Phase 7: Update Documentation (2-3 hours)

### 7.1 Update Architecture Docs
- [ ] Update `docs/PROJECT_PLAN.md` (4-app structure)
- [ ] Update `server/hydr8_schema.md` (remove analytics)
- [ ] Update dependency flow diagram
- [ ] Update app descriptions

### 7.2 Update AGENTS.md
- [ ] Remove analytics references
- [ ] Document new app structure
- [ ] Update multi-tenancy convention
- [ ] Add CI/CD workflow documentation
- [ ] Add presentation layer convention

### 7.3 Create Migration Guide
- [ ] Create `docs/MIGRATION_GUIDE.md`
- [ ] Document import path changes
- [ ] Document URL name changes
- [ ] Document model changes
- [ ] Document selector pattern changes

### 7.4 Clean Up Repository
- [ ] Remove `learning_guide/` directory
- [ ] Remove `to-do-list.md`
- [ ] Remove `server/repomix-output.xml`
- [ ] Remove orphaned `package-lock.json`
- [ ] Update `.gitignore` for tool artifacts

### 7.5 Commit
- [ ] Commit: `git commit -m "docs: Update architecture documentation to reflect refactor"`

---

## Final Validation

### Code Quality
- [ ] All 38 test files passing
- [ ] Zero import errors (`python manage.py check`)
- [ ] Zero migration conflicts (`python manage.py makemigrations --check`)
- [ ] All URLs resolve correctly

### CI/CD
- [ ] CI passing on refactor branch
- [ ] Test workflow configured
- [ ] Staging workflow configured
- [ ] Deploy workflow configured
- [ ] Branch protection rules active

### Documentation
- [ ] Architecture diagram matches codebase
- [ ] All import paths documented in migration guide
- [ ] AGENTS.md reflects new conventions
- [ ] Professional comment standards enforced

---

## Merge to Develop

- [ ] Create PR: `refactor/architecture-cleanup` → `develop`
- [ ] Add PR description with summary of changes
- [ ] Attach test results
- [ ] Request code review
- [ ] CI passes
- [ ] Merge to `develop`

---

## Deploy to Staging

- [ ] `develop` auto-deploys to staging (via CI)
- [ ] Manual QA on staging environment
- [ ] Verify all features work
- [ ] Verify no regressions

---

## Merge to Main

- [ ] Create PR: `staging` → `main`
- [ ] Add PR description
- [ ] Request approval
- [ ] Staging workflow passes
- [ ] Merge to `main`
- [ ] Production deployment

---

## Success Metrics

### Code Metrics
- [ ] Total apps: 9 → 5 (44% reduction)
- [ ] Lines of code removed: ~1200
- [ ] Cross-app imports: ~30% reduction
- [ ] Test coverage: Maintained (38 test files)

### Quality Metrics
- [ ] CI passing on all branches
- [ ] Zero import errors
- [ ] Zero migration conflicts
- [ ] All URLs resolve correctly

### Documentation Metrics
- [ ] Architecture diagram matches codebase
- [ ] All import paths documented
- [ ] AGENTS.md reflects new conventions
- [ ] Professional comment standards enforced

---

## Timeline Tracking

| Phase | Estimated | Actual | Status |
|---|---|---|---|
| Planning | — | 2h | ✅ Complete |
| Phase 1: Remove AI | 2-3h | — | ⏳ Pending |
| Phase 2: Consolidate Apps | 6-8h | — | ⏳ Pending |
| Phase 3: Extract Presentation | 4-6h | — | ⏳ Pending |
| Phase 4: Simplify Tenancy | 3-4h | — | ⏳ Pending |
| Phase 5: CI/CD | 2-3h | — | ⏳ Pending |
| Phase 6: Documentation | 3-4h | — | ⏳ Pending |
| Phase 7: Update Docs | 2-3h | — | ⏳ Pending |
| **Total** | **22-31h** | **2h** | **8% Complete** |

---

## Notes

- Update this checklist as you complete each item
- Commit after each major phase
- Test after every commit
- Document any deviations in commit messages

---

**Ready to Execute!** Begin with Phase 1: Remove AI Integration.
