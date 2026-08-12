# Plan: Server-Side Search + Pagination Fix

**Status:** In progress
**Date:** 2026-08-12
**Scope:** Fix broken/dead search inputs and missing pagination on table views.
Use `__icontains` (not pg_trgm) — datasets are small (single-branch water station).

---

## Why Not pg_trgm (Yet)

pg_trgm is installed in both DBs but not worth the complexity at current scale:
- ~100-500 customers, ~5-20 riders, ~5-15 staff per tenant
- `__icontains` with B-tree indexes is sufficient at this volume
- pg_trgm's fuzzy matching (typo tolerance) is a nice-to-have, not a correctness fix
- The GIN index migration + `TrigramSimilarity` query complexity is premature optimization

**Future enhancement:** When a tenant exceeds ~1000 rows or users complain about
typo sensitivity, add GIN trigram indexes and swap `__icontains` for
`TrigramSimilarity` in the selectors. The template/delivery work is identical
either way, so this is a purely additive change.

---

## Problems Being Fixed

| # | Surface | Problem | Fix |
|---|---------|---------|-----|
| 1 | Customer table search | **Dead input** — no `hx-get`, no `x-model`, no wiring | Wire up with HTMX → `customers:table?q=` |
| 2 | Customer table pagination | **Fake pagination** — `_pagination(1, total)` hardcodes `total_pages: 1`, loads ALL rows | Real `Paginator` with `per_page=25` |
| 3 | Employee directory search | **Dead input** — same as customer table | Wire up with HTMX → `employees:search?q=` |
| 4 | Employee directory pagination | **Fake pagination** — same as customer table | Real `Paginator` with `per_page=25` |
| 5 | Audit log search | **Broken** — Alpine `matchesSearch()` only filters current page's 50 entries; cross-page searches return nothing | Server-side `__icontains` across full queryset |

## Out of Scope (Working Fine)

| Surface | Why It Stays |
|---------|-------------|
| Remittance Add → Rider combobox | Alpine `.filter()` on pre-loaded array. Rider count is ~5-20. Fine. |
| Remittance History → Rider filter | Alpine `filteredRiders()` on seed data. Same small dataset. Fine. |
| Modal `<select>` dropdowns | Customer/product selects in record-debt/record-borrowed modals. At current scale, a `<select>` with 100-500 options is acceptable. Combobox refactor when count exceeds ~500. |

---

## Implementation

### Phase 1 — Customer Table (search + pagination)

**Selector** (`apps/customers/selectors.py`):
- `get_customer_table_context` accepts `query`, `page` params
- Filter: `Customer.objects.for_user(user).filter(deleted_at__isnull=True, name__icontains=query)` when query is non-empty
- Sort: push sorting into the DB query via `order_by()` instead of Python-side `list.sort()`
- Pagination: use `Paginator(qs, 25)` — return real `page_obj` with `has_next`, `has_previous`, etc.

**View** (`apps/customers/views.py`):
- `customer_table_view` reads `q` and `page` from `request.GET`

**Template** (`apps/customers/partials/customer_table.html`):
- Wire up `#customerSearch` input with `hx-get`, `hx-trigger="keyup changed delay:300ms, search"`, `hx-target="#customer-table"`, `hx-swap="outerHTML"`
- Replace fake pagination with real page navigation (HTMX buttons hitting `customers:table?page=N&q=...`)

### Phase 2 — Employee Directory (search + pagination)

**Selector** (`apps/employees/selectors.py`):
- `get_employee_directory_context` accepts `query`, `page` params
- Filter: `Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q)`
- Pagination: `Paginator(qs, 25)`

**View** (`apps/employees/views.py`):
- New `employees_search_view` — returns `users_table.html` partial with filtered+paginated results
- Existing `employees_directory_view` stays as the full page render

**URL** (`apps/employees/urls.py`):
- Add `path("search/", views.employees_search_view, name="search")`

**Template** (`apps/employees/partials/users_table.html`):
- Wire up search input with HTMX → `employees:search`
- Wrap table in `#users-table` div as the HTMX target
- Add real pagination

### Phase 3 — Audit Log (server-side search)

**Selector** (`apps/audit/selectors.py`):
- `list_log_entries` accepts `query` param
- Filter: `Q(object_repr__icontains=q) | Q(cid__icontains=q) | Q(remote_addr__icontains=q) | Q(actor__username__icontains=q) | Q(actor__first_name__icontains=q) | Q(actor__last_name__icontains=q)`
- Pagination stays as-is (already uses `Paginator`)

**View** (`apps/audit/views.py`):
- `audit_log_view` reads `q` from `request.GET`, passes to `list_log_entries`

**Template** (`apps/audit/audit_log.html`):
- Replace Alpine `searchQuery` / `matchesSearch()` with HTMX-driven search
- Search input: `hx-get="{% url 'audit:list' %}?q=..."`, `hx-trigger="keyup changed delay:300ms, search"`, `hx-target="#audit-log-content"`, `hx-swap="outerHTML"`
- Keep Alpine for action filter and date range (exact-match filters on current page — fine)
- Remove `matchesSearch()` from Alpine component

### Phase 4 — Verification

- `uv run python manage.py check`
- `uv run python manage.py test`
- Manual: load each page, type in search, verify results update, verify pagination works
