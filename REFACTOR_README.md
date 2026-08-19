# Architecture Refactor — Quick Reference

> **Branch:** `refactor/architecture-cleanup`  
> **Status:** Planning Complete — Ready for Execution  
> **Estimated Time:** 22-31 hours (3-4 working days)

---

## What This Refactor Does

Based on the brutal architecture review, this refactor addresses:

1. **Over-engineering removal**
   - Delete AI integration (Gemma 2B, analytics app, DRF)
   - Simplify multi-tenancy (app-level only, remove RLS)
   - Consolidate 9 apps → 5 apps

2. **Separation of concerns**
   - Extract presentation logic from selectors
   - Clear data layer vs template-shaping boundary

3. **Quality gates**
   - CI/CD with automated testing
   - Branch protection (develop → staging → main)
   - Professional documentation standards

**Impact:**
- ~30% reduction in cross-app imports
- ~1200 lines of code removed
- Clear architectural boundaries
- Automated quality checks on every merge

---

## Documentation Structure

| Document | Purpose |
|---|---|
| **`REFACTOR_README.md`** (this file) | Quick reference and navigation |
| **`docs/REFACTOR_PLAN.md`** | Detailed 7-phase execution plan (835 lines) |
| **`docs/REFACTOR_EXECUTION.md`** | Step-by-step execution instructions |
| **`docs/COMMENT_STYLE_GUIDE.md`** | Professional comment standards |

---

## Execution Phases

| Phase | Goal | Time | Status |
|---|---|---|---|
| **1. Remove AI** | Delete analytics app, DRF, Gemma references | 2-3h | Pending |
| **2. Consolidate Apps** | Merge employees→users, settings+audit→core, products→core | 6-8h | Pending |
| **3. Extract Presentation** | Move template-shaping out of selectors | 4-6h | Pending |
| **4. Simplify Tenancy** | App-level only, remove RLS middleware | 3-4h | Pending |
| **5. CI/CD** | GitHub Actions + branch protection | 2-3h | Pending |
| **6. Documentation** | Remove AI-style comments, add professional docs | 3-4h | Pending |
| **7. Update Docs** | Sync all docs with new architecture | 2-3h | Pending |

**Execute in strict order** (dependencies enforced).

---

## Quick Start

### 1. Review the Plan
```bash
# Read the full plan (835 lines, comprehensive)
cat docs/REFACTOR_PLAN.md

# Read the execution guide (311 lines, step-by-step)
cat docs/REFACTOR_EXECUTION.md

# Read the comment style guide (487 lines, before/after examples)
cat docs/COMMENT_STYLE_GUIDE.md
```

### 2. Start Phase 1
```bash
cd /Users/dasher/SoftDev/hydr8

# Ensure you're on the refactor branch
git checkout refactor/architecture-cleanup

# Begin Phase 1: Remove AI Integration
# Follow docs/REFACTOR_PLAN.md Phase 1 steps
```

### 3. Test After Each Commit
```bash
cd server

# Run test suite
python manage.py test

# Check migrations
python manage.py makemigrations --check

# Verify imports
python manage.py check
```

### 4. Commit and Continue
```bash
git add .
git commit -m "refactor: [phase description]"

# Move to next phase
```

---

## Architecture Before vs After

### Before (9 apps)
```
server/apps/
├── users/       ← IAM
├── core/        ← Shared kernel (Product, utilities)
├── customers/   ← Customer domain
├── remittance/  ← Operations domain
├── analytics/   ← AI chatbot + dashboard (DRF endpoints)
├── employees/   ← Employee views (no models)
├── products/    ← Product CRUD (thin)
├── settings/    ← Company, SystemConfig (shared kernel)
└── audit/       ← Audit log viewer (thin wrapper)
```

**Problems:**
- 9 apps for 1 bounded context
- `analytics` exists for unused AI feature
- `employees` has no models (just views over `users.User`)
- `settings` is shared kernel but separate from `core`
- `products` is catalog data (belongs in `core`)
- `audit` is a thin wrapper around `django-auditlog`

### After (5 apps)
```
server/apps/
├── users/       ← IAM + Employees (Role, User, DriverCommission, employee views)
├── core/        ← Shared Kernel (Product, Company, SystemConfig, Dashboard, Settings, Audit)
├── customers/   ← Customer Domain (Customer, CreditLine, CreditPayment, borrowed items)
└── remittance/  ← Operations Domain (Remittance, RemittanceRider, Expenses, RiderCredit)
```

**Benefits:**
- Clear dependency flow: `users → core → customers → remittance`
- Each app has a clear purpose (not just a view surface)
- Shared kernel consolidated in `core`
- ~30% fewer cross-app imports

---

## Multi-Tenancy Before vs After

### Before (Dual Mechanism)
- **RLS:** `TenantMiddleware` set `app.current_tenant` (Postgres session variable), but no RLS policies ever existed — dead code
- **App-level:** `TenantManager.for_user()` (explicit, the actual scoping mechanism)
- **Problem:** Two parallel mechanisms, false confidence from the unused RLS path

### After (App-Level Only)
- **Single mechanism:** `TenantManager.for_user()` explicitly scopes by `company_id`
- **Escape hatch:** superusers and users without `company_id` see all rows
- **Benefit:** One source of truth, no dead middleware, no false confidence

---

## CI/CD Before vs After

### Before
- No CI (tests exist but don't run on push)
- No branch protection
- Manual testing only

### After
```
develop (feature branches merge here)
   ↓ (CI: run tests)
staging (only develop can merge; runs full test suite)
   ↓ (CI: deploy to staging, manual QA)
main (only staging can merge; production-ready)
   ↓ (CI: deploy to production)
```

**Benefits:**
- Automated testing on every push
- Staging environment validates before production
- Branch protection prevents bad merges

---

## Comment Style Before vs After

### Before (AI-style)
```python
def finalize_remittance():
    # 🚀 Lock it down!
    # ✨ Magic happens here
    # TODO: This is a bit hacky but it works for now
```

### After (Professional)
```python
def finalize_remittance(remittance_id, user, pin):
    """
    Locks a remittance and all related records atomically.
    
    Finalization is a one-way state transition (DRAFT → FINALIZED) that
    recomputes all denormalized totals and prevents further edits.
    
    Invariants:
        - Status transitions DRAFT → FINALIZED (one-way, no rollback)
        - All denormalized totals match sum of related records
    
    Raises:
        ValidationError: If PIN is incorrect or already finalized
    """
    # Prevent double-finalization. This check is also in the UI, but we
    # guard at the service layer to prevent race conditions.
    if remittance.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError("Remittance has already been finalized.")
```

**Benefits:**
- Explains WHY, not WHAT
- Documents invariants and edge cases
- Professional tone

---

## Success Criteria

Before merging to `develop`:

- [ ] All 38 test files passing
- [ ] Zero import errors
- [ ] Zero migration conflicts
- [ ] All URLs resolve correctly
- [ ] CI passing on all branches
- [ ] Documentation updated
- [ ] Code review approved

---

## Rollback Plan

Each phase is independently committed. If a phase introduces regressions:

```bash
# Revert specific commits
git revert <commit-hash>

# Or reset to before phase
git reset --hard <commit-before-phase>
```

Branch protection on `staging` and `main` prevents bad code from reaching production.

---

## Next Steps

1. **Read the full plan:** `docs/REFACTOR_PLAN.md`
2. **Read execution guide:** `docs/REFACTOR_EXECUTION.md`
3. **Start Phase 1:** Remove AI integration
4. **Test after each commit**
5. **Proceed through phases 2-7**
6. **Merge to develop** after all phases complete

---

## Questions?

- **Full plan:** `docs/REFACTOR_PLAN.md` (835 lines, comprehensive)
- **Execution steps:** `docs/REFACTOR_EXECUTION.md` (311 lines, step-by-step)
- **Comment guide:** `docs/COMMENT_STYLE_GUIDE.md` (487 lines, examples)

---

## Timeline

**Estimated:** 22-31 hours (3-4 working days)  
**Status:** 0% complete (planning done, ready to execute)

---

## Commit History (Planning Phase)

```
fc16f4a docs: Add professional comment style guide
dbb93ea docs: Add refactor execution instructions
b744d99 docs: Add comprehensive architecture refactor plan
```

**Next commit:** `refactor: Remove AI integration (analytics app, DRF)`
