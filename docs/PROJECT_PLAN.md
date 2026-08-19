# Hydr8 PWA — Project Plan (v3 — Simplified Remittance Architecture)

> **Status:** Active Development
> **Target Subsystem:** Django Backend (`server/apps/`) + PWA Frontend (`server/static/` + `server/templates/`)
> **Architecture:** Django + HTMX + Alpine.js + Tailwind CSS

---

## 1. Executive Summary

Hydr8 is a daily operations tool for a water refilling and delivery business. The application has been simplified from a dispatch-centric model to a **manual daily remittance model**:

1. Admin or Staff creates a daily remittance.
2. They add riders with their products, qty sold, qty credited, and borrowed items.
3. The system auto-computes subtotals, commissions, expenses, net profit, and tithes.
4. Finalize the remittance (PIN-protected) to lock all records.
5. Track customer debts and borrowed containers independently.
6. Dashboard provides operational insights via precomputed SQL aggregations and KPI cards.

### Canonical Data Sources (Dashboard)

| Dashboard metric | Canonical source | Notes |
|---|---|---|
| Outstanding Debt ("Total Unpaid Credits") | `Customer.debt_balance` | Denormalized per-customer running balance. This is the single source of truth for the dashboard stat card — **not** `RiderCredit` nor `CreditLine` aggregates. `RiderCredit` is still used for the Long-Running Debts table (aged rider-issued credits), but the headline total comes from `Σ Customer.debt_balance`. |
| Today's Total Sales | `Remittance.total_sales` for today | Trend = delta vs yesterday's finalized remittance. |
| Unreturned Containers | `Σ Customer.borrowed_round_8gal + borrowed_slim_8gal + borrowed_other` | Breakdown chips use the same three fields. |

### Operational Model (Remittance Entry)

The business runs a **single daily remittance**: staff enter the afternoon's total dispatched quantities once per day to speed up reconciliation — they do **not** log each dispatch as it happens. Consequently:

- There is **no hourly dispatch tracking** and no per-dispatch timestamped transaction model.
- `Remittance.date` is a `DateField` (daily granularity) and remains the time unit for all charts.
- Dashboard charts are daily-granularity (sales trend line, rider leaderboard bar) — see Phase 7.

---

## 2. App Architecture

```
server/apps/
├── users/       ← IAM: Roles, Permissions, Users, Driver Commissions
├── core/        ← Shared Kernel: Products, System Config
├── customers/   ← Customer Accounts: Debts, Borrowed Items, Credit Lines
├── remittance/  ← Core Domain: Daily Remittance, Rider Lines, Expenses
└── analytics/   ← Dashboard: KPI cards, recent remittances, outstanding debts (read-only)
```

**Frontend:**
```
server/static/
├── css/        ← Tailwind output + CSS custom property (light/dark) tokens
├── js/
│   └── main.js       ← Alpine.js + theme toggle
server/templates/
├── base.html
├── components/
│   ├── _sidebar.html
│   └── _remittance_summary_card.html
├── remittance/
│   ├── history.html
│   ├── add.html
│   └── partials/
│       ├── _rider_section.html
│       ├── _product_line_row.html
│       ├── _expense_row.html
│       └── _summary_card.html
└── ...
```

---

## 3. Phased Implementation Roadmap

### Phase 0: Foundation (Design System + Auth)
- [ ] Configure Tailwind CSS with CSS custom property tokens for Light + Dark mode
- [ ] Build `base.html` with sidebar, topbar, and theme toggle (Alpine.js)
- [ ] Implement Login screen (split layout, role-based redirect)
- [ ] Implement Lockscreen timeout with PIN prompt (Alpine.js + Django session check)
- [ ] Seed: Roles, Permissions, System Config defaults

---

### Phase 1: Core Remittance Domain (Primary MVP)
- [ ] **Models:** `remittance_remittance`, `remittance_remittancerider`, `remittance_remittanceriderproductline`, `remittance_expense`
- [ ] **Service Layer:** `save_product_line()`, `_recalculate_remittance_totals()`, `finalize_remittance()`
- [ ] **Remittance History View:** Table with inline tithes/offering toggles (HTMX)
- [ ] **Add Remittance View:**
  - Pinned Summary Card (live HTMX recalculation)
  - Add Rider → Expand to Add Product rows (HTMX partial append)
  - Qty Sold / Qty Credited / Borrowed Items steppers
  - Line subtotals → Rider subtotals → Summary card cascade
  - Add Expense section (inline HTMX rows)
  - Finalize flow: PIN modal → Confirmation → Lock
- [ ] **Dashboard:** Today's banner (no remittance / draft / finalized), 3 stats cards, recent remittances table

---

### Phase 2: Customers Domain
- [ ] **Models:** `customers_customer`, `customers_creditline`, `customers_creditpayment`
- [ ] **Customer List:** Filter chips, search, table with debt/borrowed/days-overdue columns
- [ ] **Record Payment Modal:** Per-credit-line container input, atomic debt reduction
- [ ] **Update Containers Modal:** Stepper per container type
- [ ] **Credit line creation:** Auto-triggered when `qty_credited > 0` at remittance finalize

---

### Phase 3: Products & Pricing (Standalone Nav)
- [ ] **Products Sub-Tab:** CRUD table, inline price edit (HTMX save-on-blur), active toggle
- [ ] **Delivery Commissions Sub-Tab:** Full driver × product matrix, per-cell inline edit, "Set All" bulk update

---

### Phase 4: Employees & Users (Standalone Nav)
- [ ] **Staff List:** Table, Add Employee modal, Deactivate (soft delete)
- [ ] **Access Management Sub-Tab:** Per-role × per-action permission matrix editor (HTMX save)
- [ ] **Security & Credentials:** Change password, username, PIN per employee
- [ ] **Commission Assignment Sub-Tab:** Per-driver product rate editor (same matrix, filtered to one driver)

---

### Phase 5: Settings
- [ ] **System Config Tab:** Lockscreen timeout, tithe rate, approved credit limit, container limit, overdue threshold
- [ ] **Company Tab:** Company name, contact, email (writes to `core_systemconfig`)
- [ ] **My Profile Tab:** Self-service password / username / PIN change

---

### Phase 7: Analytics & Snapshots (Post-MVP)
- [ ] `analytics_dailysnapshot` model + pg_cron nightly job (23:55) to aggregate finalized remittance data
- [ ] Chart.js: Sales trend line, rider leaderboard bar chart (Dashboard)
- [ ] PDF/Excel export of remittance summary
- [ ] Admin-scoped analytics page (tabbed: Sales, Riders, Customers, Tithes)

---

## 4. Security & Compliance Notes (ISO/IEC 27001 + NPC RA 10173)

- **No secrets in source:** All credentials via `django-environ` / `.env`. Never committed.
- **CSRF:** All HTMX POSTs include `hx-headers` with `X-CSRFToken`. Django `CsrfViewMiddleware` active.
- **RBAC:** All views use `PermissionRequiredMixin`. Sidebar items rendered conditionally per permissions.
- **PIN hashing:** Stored via `django.contrib.auth.hashers.make_password()` — same pipeline as password hashing.
- **Snapshot immutability:** `unit_price_snapshot` and `commission_rate_snapshot` are immutable after save. No retroactive financial mutation.
- **Soft deletes:** Customers and Users use `deleted_at` for right-to-erasure support. Hard delete available for NPC "right to be forgotten" requests.
- **Audit fields:** All mutations include `recorded_by_id` or `created_by_id` FKs for traceability.
