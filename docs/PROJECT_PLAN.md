# Hydr8 PWA — Project Plan (v3 — Simplified Remittance Architecture)

> **Status:** Active Development
> **Target Subsystem:** Django Backend (`server/apps/`) + PWA Frontend (`server/static/` + `server/templates/`) + Edge AI (`static/js/ai/`)
> **Architecture:** Django + HTMX + Alpine.js + Tailwind CSS + Gemma 2B (WebGPU, client-side)

---

## 1. Executive Summary

Hydr8 is a daily operations tool for a water refilling and delivery business. The application has been simplified from a dispatch-centric model to a **manual daily remittance model**:

1. Admin or Staff creates a daily remittance.
2. They add riders with their products, qty sold, qty credited, and borrowed items.
3. The system auto-computes subtotals, commissions, expenses, net profit, and tithes.
4. Finalize the remittance (PIN-protected) to lock all records.
5. Track customer debts and borrowed containers independently.
6. Get AI-powered operational insights via a Gemma 2B edge model running locally in the browser (WebGPU).

---

## 2. App Architecture

```
server/apps/
├── users/       ← IAM: Roles, Permissions, Users, Driver Commissions
├── core/        ← Shared Kernel: Products, System Config
├── customers/   ← Customer Accounts: Debts, Borrowed Items, Credit Lines
├── remittance/  ← Core Domain: Daily Remittance, Rider Lines, Expenses
└── analytics/   ← AI Tools API: Lightweight read-only REST endpoints for Gemma
```

**Frontend:**
```
server/static/
├── css/        ← Tailwind output + CSS custom property (light/dark) tokens
├── js/
│   ├── main.js       ← Alpine.js + theme toggle
│   └── ai/
│       ├── edge_router.js    ← WebLLM engine + JSON mode tool router
│       ├── tool_registry.json ← JSON Schemas for Gemma tools
│       └── ai_progress.js    ← Background download + PATCH to server
server/templates/
├── base.html
├── components/
│   ├── _sidebar.html
│   ├── _ai_chat_drawer.html
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
- [ ] **System Config Tab:** Lockscreen timeout, `is_password_strict`, tithe rate
- [ ] **Company Tab:** Company name, contact, email (writes to `core_systemconfig`)
- [ ] **My Profile Tab:** Self-service password / username / PIN change
- [ ] **AI Model Tab:** Shows model status, download progress bar, trigger-download button

---

### Phase 6: AI Chatbot — Edge Inference (Gemma 2B WebGPU)

#### 6.1 Tool Registry & Django Analytics API
- [ ] Create `server/static/js/ai/tool_registry.json` with JSON Schemas for:
  - `fetch_remittance_summary(start_date, end_date)`
  - `fetch_rider_performance(rider_id, start_date, end_date)`
  - `fetch_customer_debts(filter)`
  - `fetch_tithe_status()`
- [ ] Implement Django REST endpoints in `server/apps/analytics/api.py` — strict RBAC, minimal field selection, no `SELECT *`
- [ ] Add `PATCH /api/analytics/ai-status/` endpoint for PWA progress reporting

#### 6.2 WebGPU Engine & JSON Mode Router
- [ ] Implement `server/static/js/ai/edge_router.js`:
  - Load `@mlc-ai/web-llm` engine with `gemma-2-2b-it-q4f16_1-MLC`
  - Enforce structural JSON grammar constraints for deterministic tool selection
  - Parse tool call output → dispatch to Django REST endpoint → return data to Gemma for synthesis
- [ ] Implement `server/static/js/ai/ai_progress.js`:
  - `initProgressCallback` → PATCH server config with `ai_download_percent`
  - Background download (does not block app usage)

#### 6.3 PWA UI Components
- [ ] AI Chatbot Drawer: `server/templates/components/_ai_chat_drawer.html`
  - Slide-in from right, message thread, input box
  - Model loading state with progress bar
- [ ] AI Insights Panel: Insight chip cards on Dashboard
  - Skeleton loaders while model initializing
  - Pre-fill chatbot on chip click
- [ ] Floating Action Button (FAB): fixed bottom-right, amber pulsing ring while downloading
- [ ] `engine.unload()` on drawer close to free VRAM
- [ ] `navigator.gpu` detection → fallback message for non-WebGPU browsers

#### 6.4 Service Worker Cache
- [ ] Update `server/static/sw.js` to cache `tool_registry.json` and AI JS modules
- [ ] Do NOT cache model weights in service worker (too large — stored in IndexedDB by WebLLM)

---

### Phase 7: Analytics & Snapshots (Post-MVP)
- [ ] `analytics_dailysnapshot` model + pg_cron nightly job (23:55) to aggregate finalized remittance data
- [ ] Chart.js: Sales trend line, rider leaderboard bar chart (Dashboard)
- [ ] PDF/Excel export of remittance summary
- [ ] Admin-scoped analytics page (tabbed: Sales, Riders, Customers, Tithes)

---

## 4. Architectural Tradeoff Matrix (AI Integration)

| Metric | Proposed: Hybrid Edge-Cloud | Alternative: Pure Cloud API |
|:---|:---|:---|
| **Time-to-Value** | Moderate (WebGPU setup) | Fast (Standard fetch) |
| **Server GPU Cost** | None (0 GPU inference server-side) | High (cloud token fees per turn) |
| **Client Footprint** | ~1.2 GB disk, ~1.5 GB RAM (freed on close) | ~0 MB |
| **Data Privacy** | High (prompts stay on device) | Low (prompts sent to cloud) |
| **Offline Capability** | Partial (routing works; Django API needed for data) | Zero |
| **Model Version Control** | Pinned to `q4f16_1-MLC` via config | Cloud-managed |

> **Rationale for Edge:** Hydr8 handles sensitive business financials (sales, tithes, commissions). Keeping prompts and inference on-device avoids exposing PII to a third-party cloud API. The ~1.2 GB one-time download is acceptable for an internal business tool on a known device. The background download model ensures zero disruption to core operations.

---

## 5. Security & Compliance Notes (ISO/IEC 27001 + NPC RA 10173)

- **No secrets in source:** All credentials via `django-environ` / `.env`. Never committed.
- **CSRF:** All HTMX POSTs include `hx-headers` with `X-CSRFToken`. Django `CsrfViewMiddleware` active.
- **RBAC:** All views use `PermissionRequiredMixin`. Sidebar items rendered conditionally per permissions.
- **PIN hashing:** Stored via `django.contrib.auth.hashers.make_password()` — same pipeline as password hashing.
- **Snapshot immutability:** `unit_price_snapshot` and `commission_rate_snapshot` are immutable after save. No retroactive financial mutation.
- **Soft deletes:** Customers and Users use `deleted_at` for right-to-erasure support. Hard delete available for NPC "right to be forgotten" requests.
- **Audit fields:** All mutations include `recorded_by_id` or `created_by_id` FKs for traceability.
- **AI read-only:** Gemma tools have zero write access to the Django ORM. All analytics endpoints are GET-only (except the AI status PATCH).
