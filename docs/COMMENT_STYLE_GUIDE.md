# Professional Comment Style Guide

> **Purpose:** Replace AI-generated casual comments with professional instructional documentation  
> **Audience:** Future developers (including yourself in 6 months)  
> **Principle:** Explain WHY, not WHAT

---

## Anti-Patterns (Remove These)

### 1. Emoji Comments
```python
# ❌ REMOVE
def finalize_remittance():
    # 🚀 Lock it down!
    # ✨ Magic happens here
    # 🔥 Hot path — optimize this!
```

**Why:** Emojis add noise without information. They're unprofessional in production code.

---

### 2. Enthusiastic Language
```python
# ❌ REMOVE
def calculate_commission():
    # Awesome! This is super cool!
    # Let's do some magic math here!
    # This is the best part of the code!
```

**Why:** Enthusiasm doesn't explain the code. It wastes the reader's time.

---

### 3. Hedging / Apologizing
```python
# ❌ REMOVE
def process_payment():
    # This is a bit hacky but it works for now
    # Not sure if this is the best way, but...
    # TODO: Clean this up later (it's ugly)
    # I know this looks weird, but trust me
```

**Why:** If code is hacky, fix it or document the constraint that forces the hack. Don't apologize.

---

### 4. Redundant Docstrings
```python
# ❌ REMOVE
def get_customer(customer_id):
    """Gets a customer."""
    return Customer.objects.get(id=customer_id)

def save_remittance(remittance):
    """Saves a remittance."""
    remittance.save()
```

**Why:** The function name already says what it does. The docstring adds zero information.

---

### 5. Obvious Comments
```python
# ❌ REMOVE
# Increment counter
counter += 1

# Loop through riders
for rider in riders:
    # Process each rider
    process_rider(rider)

# Return the result
return result
```

**Why:** These comments restate the code. Any developer can read `counter += 1` and understand it increments the counter.

---

## Professional Patterns (Add These)

### 1. Document Business Logic (WHY)
```python
# ✅ GOOD
def calculate_tithe(net_profit, tithe_rate):
    """
    Computes the tithe amount based on net profit (after commissions and expenses).
    
    Per company policy, tithes are calculated on net profit rather than gross
    sales to ensure the business remains sustainable. This differs from the
    traditional 10%-of-gross model used by most churches.
    
    Args:
        net_profit: Decimal amount after subtracting commissions and expenses
        tithe_rate: Decimal fraction (e.g., 0.10 for 10%)
    
    Returns:
        Decimal tithe amount, rounded to 2 decimal places
    """
    return (net_profit * tithe_rate).quantize(Decimal('0.01'))
```

**Why:** Explains the business rule (net vs gross) that isn't obvious from the code.

---

### 2. Document Invariants
```python
# ✅ GOOD
def finalize_remittance(remittance_id, user, pin):
    """
    Locks a remittance and all related records atomically.
    
    Invariants enforced:
        - Status transitions DRAFT → FINALIZED (one-way, no rollback)
        - All denormalized totals match sum of related records
        - finalized_by and finalized_at are set atomically with status change
        - Once finalized, no edits are permitted (enforced at service + UI layers)
    
    Raises:
        ValidationError: If remittance is already finalized or PIN is incorrect
        PermissionDenied: If user lacks remittance write permission
    """
    # Prevent double-finalization. This check is also in the UI, but we guard
    # at the service layer to prevent race conditions from concurrent requests.
    if remittance.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError("Remittance has already been finalized.")
```

**Why:** Documents the state machine and explains why we check finalization status despite UI guards.

---

### 3. Document Edge Cases
```python
# ✅ GOOD
def calculate_commission(rider, product, qty_sold, qty_credited):
    """
    Computes rider commission for a product line.
    
    Commission is calculated on sold quantity only — credited items do not
    earn commission until they are repaid. This prevents riders from inflating
    their commission by issuing credits to friends/family.
    
    Edge case: If a rider has no commission rate configured for this product,
    we fall back to 0.00 rather than raising an error. This allows new products
    to be added without requiring immediate commission setup.
    """
    rate = DriverCommission.objects.filter(
        rider=rider, product=product
    ).first()
    
    if rate is None:
        # No commission configured for this product — default to zero.
        # This is intentional: new products can be dispatched before the
        # admin configures commission rates.
        return Decimal('0.00')
    
    return (qty_sold * product.price * rate.commission_rate).quantize(Decimal('0.01'))
```

**Why:** Explains the non-obvious fallback behavior and the business reason for it.

---

### 4. Document Performance Considerations
```python
# ✅ GOOD
def get_remittance_history(user, year, month):
    """
    Returns all remittances for a given month, with related data prefetched.
    
    Performance note: We prefetch riders, product lines, and expenses in a
    single query to avoid N+1 problems. For a typical month (30 remittances,
    5 riders each, 10 products each), this reduces queries from ~1500 to ~4.
    
    Do not add filters to the prefetch queryset without updating the template
    logic — the template assumes all related records are present.
    """
    return Remittance.objects.filter(
        date__year=year,
        date__month=month,
    ).prefetch_related(
        'riders__rider',
        'riders__product_lines__product',
        'expenses',
    ).order_by('-date')
```

**Why:** Explains the prefetch strategy and warns about coupling with template logic.

---

### 5. Document External References
```python
# ✅ GOOD
def validate_pin(user, pin):
    """
    Verifies a user's PIN for sensitive operations.
    
    PIN validation is required for:
        - Finalizing remittances (financial lock-in)
        - Deleting customers (data loss prevention)
        - Changing user roles (privilege escalation)
    
    See AGENTS.md "Authorization Convention" for the full list of PIN-protected
    operations and the rationale for PIN-based verification vs password re-entry.
    
    Raises:
        ValidationError: If PIN is incorrect or user has no PIN configured
    """
```

**Why:** Links to external documentation for the broader context.

---

### 6. Document Constraints / Assumptions
```python
# ✅ GOOD
def create_remittance(date, created_by):
    """
    Creates a new draft remittance for the given date.
    
    Constraint: Only one remittance per (company, date) is allowed. This is
    enforced by a unique constraint at the database level. If a remittance
    already exists for this date, this function raises IntegrityError.
    
    Assumption: The caller has already checked that the user has write
    permission for the remittance module. This function does NOT perform
    authorization checks — that's the view layer's responsibility.
    """
```

**Why:** Makes the contract explicit: what this function guarantees and what it assumes.

---

## Docstring Template

Use this template for all service functions:

```python
def function_name(arg1, arg2, kwarg1=None):
    """
    One-line summary of what this function does.
    
    Longer explanation of the business logic, if needed. Focus on WHY this
    function exists and what problem it solves, not HOW it works (the code
    shows the HOW).
    
    Args:
        arg1: Description of arg1, including type and constraints
        arg2: Description of arg2
        kwarg1: Optional. Description of kwarg1 and its default behavior
    
    Returns:
        Description of return value, including type
    
    Raises:
        ExceptionType: When this exception is raised and why
        AnotherException: Another case
    
    Invariants (optional):
        - State that must be true before and after this function
        - Constraints enforced by this function
    
    Performance (optional):
        - Notes about query optimization, caching, etc.
    
    See also (optional):
        - Links to related functions, docs, or tickets
    """
```

---

## Inline Comment Guidelines

### When to Add Inline Comments

1. **Non-obvious business rules**
   ```python
   # Tithes are calculated on net profit, not gross sales, per company policy.
   tithe = net_profit * tithe_rate
   ```

2. **Workarounds for external constraints**
   ```python
   # Django's select_for_update() doesn't work with prefetch_related, so we
   # lock the parent row first, then fetch related records in a separate query.
   remittance = Remittance.objects.select_for_update().get(id=remittance_id)
   riders = remittance.riders.all()
   ```

3. **Edge case handling**
   ```python
   if rate is None:
       # No commission configured — default to zero rather than raising an error.
       # This allows new products to be dispatched before commission setup.
       return Decimal('0.00')
   ```

4. **Performance optimizations**
   ```python
   # Batch-update debt balances to avoid N queries (one per customer).
   Customer.objects.bulk_update(customers, ['debt_balance'])
   ```

### When NOT to Add Inline Comments

1. **Restating the code**
   ```python
   # ❌ BAD
   counter += 1  # Increment counter
   ```

2. **Obvious control flow**
   ```python
   # ❌ BAD
   for rider in riders:  # Loop through riders
       process_rider(rider)  # Process each rider
   ```

3. **Type information (use type hints instead)**
   ```python
   # ❌ BAD
   def calculate_total(items):  # items is a list of dicts
       ...
   
   # ✅ GOOD
   def calculate_total(items: list[dict]) -> Decimal:
       ...
   ```

---

## Migration Checklist

For each file in `server/apps/`:

- [ ] Remove all emoji comments
- [ ] Remove enthusiastic language ("Awesome!", "Magic!", etc.)
- [ ] Remove hedging/apologizing comments
- [ ] Remove redundant docstrings (function name = docstring)
- [ ] Remove obvious inline comments
- [ ] Add docstrings to all service functions (use template above)
- [ ] Add inline comments for non-obvious business logic
- [ ] Add inline comments for edge cases
- [ ] Add inline comments for performance optimizations
- [ ] Add references to external docs where relevant

---

## Examples from Hydr8 Codebase

### Before (AI-style)
```python
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
    
    # Calculate all the things!
    total_sales = sum(line.subtotal for rider in remittance.riders.all() for line in rider.product_lines.all())
    
    # Lock it down! 🔒
    remittance.status = 'FINALIZED'
    remittance.finalized_by = user
    remittance.finalized_at = timezone.now()
    remittance.save()
    
    # We did it! 🎉
    return remittance
```

### After (Professional)
```python
def finalize_remittance(remittance_id, user, pin):
    """
    Locks a remittance and all related records atomically.
    
    Finalization is a one-way state transition (DRAFT → FINALIZED) that
    recomputes all denormalized totals and prevents further edits. This
    operation is PIN-protected because it has financial implications.
    
    Args:
        remittance_id: Primary key of the Remittance to finalize
        user: User performing the finalization (must have write permission)
        pin: User's PIN for verification (required for financial operations)
    
    Returns:
        The finalized Remittance instance
    
    Raises:
        ValidationError: If PIN is incorrect or remittance is already finalized
        PermissionDenied: If user lacks remittance write permission
    
    Invariants:
        - Status transitions DRAFT → FINALIZED (one-way, no rollback)
        - All denormalized totals match sum of related records
        - finalized_by and finalized_at are set atomically with status change
    """
    validate_user_pin(user, pin)
    
    remittance = Remittance.objects.select_for_update().get(id=remittance_id)
    
    # Prevent double-finalization. This check is also in the UI, but we guard
    # at the service layer to prevent race conditions from concurrent requests.
    if remittance.status == Remittance.StatusChoices.FINALIZED:
        raise ValidationError("Remittance has already been finalized.")
    
    # Recompute all denormalized totals from related records. We do this on
    # every finalization (rather than trusting the draft values) to ensure
    # the locked totals are always correct, even if the draft was corrupted.
    total_sales = sum(
        line.subtotal
        for rider in remittance.riders.all()
        for line in rider.product_lines.all()
    )
    
    remittance.status = Remittance.StatusChoices.FINALIZED
    remittance.finalized_by = user
    remittance.finalized_at = timezone.now()
    remittance.total_sales = total_sales
    remittance.save()
    
    return remittance
```

---

## Enforcement

After Phase 6 (Comment Migration):
- All service functions must have docstrings following the template
- No emoji comments allowed
- No hedging/apologizing language
- Code review will reject PRs with AI-style comments

---

## Tools

Optional: Use `ruff` or `pylint` to enforce docstring presence:

```toml
# pyproject.toml
[tool.ruff.lint]
select = ["D"]  # Enable docstring checks

[tool.ruff.lint.pydocstyle]
convention = "google"  # or "numpy" or "pep257"
```

Run: `ruff check apps/ --select D`

---

## Summary

**Remove:**
- Emojis, enthusiasm, hedging, redundancy, obviousness

**Add:**
- Business logic (WHY)
- Invariants (state guarantees)
- Edge cases (non-obvious behavior)
- Performance notes (optimization rationale)
- External references (links to docs/tickets)

**Goal:** Every comment should teach the reader something they couldn't learn from reading the code alone.
