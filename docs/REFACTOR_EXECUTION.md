# Refactor Execution Instructions

> **Branch:** `refactor/architecture-cleanup`  
> **Plan:** See `docs/REFACTOR_PLAN.md` for full details  
> **Status:** Complete — All phases delivered, 724 tests passing

---

## Quick Start

This refactor addresses the architectural debt identified in the brutal review:
- **Remove over-engineering:** AI integration, dual tenant mechanisms, excessive app decomposition
- **Improve separation of concerns:** Extract presentation logic from data layer
- **Establish quality gates:** CI/CD with automated testing on every merge

---

## Execution Phases

Execute in strict order (dependencies enforced):

### Phase 1: Remove AI Integration (2-3 hours)
**Goal:** Delete analytics app, remove DRF/CORS dependencies, move dashboard to core

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 1 for detailed steps
# Key actions:
# - Remove apps.analytics from INSTALLED_APPS
# - Delete server/apps/analytics/
# - Remove djangorestframework, django-cors-headers from deps
# - Move dashboard view to apps.core
# - Update all analytics:* URL references
```

**Commit:** `refactor: Remove AI integration (analytics app, DRF)`

---

### Phase 2: Consolidate Apps (6-8 hours)
**Goal:** Merge employees→users, settings+audit→core, products→core (9 apps → 5 apps)

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 2 for detailed steps
# Key actions:
# - Move employees/* → users/
# - Move settings/* + audit/* → core/
# - Move products/* → core/
# - Update all import paths
# - Merge migrations
# - Update ForeignKey references
```

**Commits:**
- `refactor: Merge employees app into users`
- `refactor: Merge settings and audit apps into core`
- `refactor: Merge products app into core`

---

### Phase 3: Extract Presentation Logic (4-6 hours)
**Goal:** Create presentation.py modules, move template-shaping out of selectors

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 4 for detailed steps
# Key actions:
# - Create apps/remittance/presentation.py
# - Create apps/customers/presentation.py
# - Create apps/core/presentation.py
# - Move avatar_classes, initials, alpine_seed logic
# - Update views to use presentation layer
```

**Commit:** `refactor: Extract presentation logic from selectors`

---

### Phase 4: Simplify Multi-Tenancy (3-4 hours)
**Goal:** Remove dead RLS middleware, keep explicit `for_user()` as sole mechanism

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 3 for detailed steps
# Key actions:
# - Remove TenantMiddleware from MIDDLEWARE
# - Delete TenantMiddleware class from middleware.py
# - Update misleading RLS comments in code
# - Keep TenantManager.for_user() as the explicit scoping entry point
```

**Commit:** `refactor: Simplify multi-tenancy to app-level only`

---

### Phase 5: Establish CI/CD (2-3 hours)
**Goal:** GitHub Actions workflows with branch protection (develop→staging→main)

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 5 for detailed steps
# Key actions:
# - Create .github/workflows/test.yml
# - Create .github/workflows/staging.yml
# - Create .github/workflows/deploy.yml
# - Configure branch protection rules in GitHub UI
```

**Commit:** `ci: Add GitHub Actions workflows and branch protection`

---

### Phase 6: Professional Documentation (3-4 hours)
**Goal:** Remove AI-style comments, add instructional comments

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 6 for detailed steps
# Key actions:
# - Remove emoji comments, hedging language
# - Add "why not what" comments
# - Document invariants, edge cases, business logic
# - Add proper docstrings with Args/Raises/Invariants
```

**Commit:** `docs: Replace AI-style comments with professional documentation`

---

### Phase 7: Update Documentation (2-3 hours)
**Goal:** Sync all docs with new architecture

**Commands:**
```bash
# See REFACTOR_PLAN.md Phase 7 for detailed steps
# Key actions:
# - Update docs/PROJECT_PLAN.md (4-app structure)
# - Update server/hydr8_schema.md (remove analytics)
# - Update AGENTS.md (new conventions)
# - Create docs/MIGRATION_GUIDE.md
# - Clean up repo root (remove learning_guide/, to-do-list.md, etc.)
```

**Commit:** `docs: Update architecture documentation to reflect refactor`

---

## Testing Checklist (After Each Phase)

Run after every commit:

```bash
cd server

# 1. Run test suite
python manage.py test

# 2. Check for missing migrations
python manage.py makemigrations --check --dry-run

# 3. Verify no import errors
python manage.py check

# 4. Manual smoke test
# - Start dev server: python manage.py runserver
# - Login → Dashboard → Add Remittance → Customers
# - Verify no console errors
```

---

## Final Validation (After All Phases)

Before merging to `develop`:

```bash
# 1. Full test suite with coverage
cd server
coverage run --source='apps' manage.py test
coverage report

# 2. Type checking (if mypy configured)
mypy apps/ --config-file=pyproject.toml

# 3. Code style
ruff check apps/

# 4. Migration check
python manage.py makemigrations --check

# 5. Verify all URLs resolve
python manage.py show_urls  # or manually test all routes

# 6. Load test (optional)
# Test remittance finalization under load
```

---

## Merge Strategy

```
refactor/architecture-cleanup
   ↓ (PR with full test results)
develop
   ↓ (CI runs, staging deployment)
staging
   ↓ (manual QA, production deployment)
main
```

**Steps:**
1. Push `refactor/architecture-cleanup` to origin
2. Create PR to `develop` with test results and migration guide
3. After review + CI pass, merge to `develop`
4. `develop` auto-deploys to staging (via CI)
5. Manual QA on staging environment
6. Create PR from `staging` to `main`
7. After approval, merge to `main` (production deployment)

---

## Rollback Plan

If any phase introduces regressions:

```bash
# Option 1: Revert specific commits
git revert <commit-hash>

# Option 2: Reset to before phase
git reset --hard <commit-before-phase>
git push --force-with-lease origin refactor/architecture-cleanup

# Option 3: Cherry-pick successful phases to new branch
git checkout -b refactor/architecture-cleanup-v2
git cherry-pick <good-commit-1> <good-commit-2>
```

Branch protection on `staging` and `main` prevents bad code from reaching production.

---

## Success Criteria

Before marking refactor complete:

- [ ] All 38 test files passing
- [ ] Zero import errors (`python manage.py check`)
- [ ] Zero migration conflicts
- [ ] All URLs resolve correctly
- [ ] CI passing on all branches
- [ ] Documentation updated (PROJECT_PLAN.md, hydr8_schema.md, AGENTS.md)
- [ ] Migration guide created
- [ ] Code review approved
- [ ] Staging environment validated

---

## Communication

**For each phase completion:**
1. Run test checklist
2. Commit with descriptive message
3. Update this document with completion status
4. Document any deviations from plan in commit message

**For blockers:**
1. Document the issue in GitHub Issues
2. Tag with `refactor` label
3. Pause phase, move to next independent phase if possible
4. Return to blocked phase after resolution

---

## Timeline

| Phase | Estimated | Actual | Status |
|---|---|---|---|
| Phase 1: Remove AI | 2-3 hours | — | Pending |
| Phase 2: Consolidate Apps | 6-8 hours | — | Pending |
| Phase 3: Extract Presentation | 4-6 hours | — | Pending |
| Phase 4: Simplify Multi-Tenancy | 3-4 hours | — | Pending |
| Phase 5: CI/CD | 2-3 hours | — | Pending |
| Phase 6: Documentation | 3-4 hours | — | Pending |
| Phase 7: Update Docs | 2-3 hours | — | Pending |
| **Total** | **22-31 hours** | — | **0% Complete** |

---

## Notes

- Each phase is independently committable
- Phases 1-4 modify code; phases 5-7 add infrastructure/docs
- Test suite must pass after every commit
- No direct commits to `staging` or `main` (enforced by branch protection)

---

## Ready to Execute

All planning complete. Begin with Phase 1 (Remove AI Integration).

**Next command:**
```bash
# Start Phase 1
cd /Users/dasher/SoftDev/hydr8/server
# Follow REFACTOR_PLAN.md Phase 1 steps
```
