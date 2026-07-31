# Project Description: Hydr8 — Water Refilling Station Operations & AI Management System

## 1. Executive Summary

Hydr8 is an **internal daily operations management tool** for a single-branch water refilling and delivery business. It is purpose-built for the real frustrations of the business owner and counter staff: mental-math overload at end-of-day, unclear commission records, unpaid customer debts, and forgotten tithes.

The system is deliberately focused — it replaces a dispatcher's notebook and end-of-day calculator, not an enterprise ERP. Every screen was designed for speed, clarity, and minimal cognitive load.

**Core daily loop:**
1. Create today's remittance → 2. Add riders + products sold/credited → 3. Log rider credits extended and any repayments received → 4. Log expenses → 5. Finalize (PIN-protected) → 6. Track customer debts → 7. Review AI insights

**Technology:** Django + HTMX + Alpine.js + Tailwind CSS + PostgreSQL. PWA-capable. Gemma 2B running locally in the browser via WebGPU for private, offline-capable AI insights.

---

## 2. Technical Architecture

| Layer | Technology | Rationale |
|---|---|---|
| **Backend** | Django + HTMX | Server-rendered HTML partials. No SPA overhead. Fast to build, easy to maintain. |
| **Database** | PostgreSQL | Relational integrity for financial data. Atomic `F()` updates for debt tracking. pg_cron for nightly snapshots. |
| **Frontend state** | Alpine.js | Ephemeral UI state only (theme toggle, modals, offline queue). Server is the source of truth. |
| **Styling** | Tailwind CSS + CSS Custom Properties | Light + Dark mode via `data-theme` token system. Geist + Geist Mono typography. |
| **AI Engine** | Gemma 2B via `@mlc-ai/web-llm` (WebGPU) | Edge-local inference. Prompts never leave the device. ~1.2 GB one-time download. Read-only tool calling. |
| **Caching** | Redis | Session caching, HTMX response caching for high-frequency reads. |

**Design Philosophy:** Hypermedia-first. The server renders everything. HTMX handles dynamic updates without writing a JavaScript framework. Alpine.js handles only what truly cannot be server-rendered (theme state, drawer open/close, modal visibility).

---

## 3. Core Modules & Feature Specifications

### 3.1 Dashboard

The central hub for the Admin and Staff. Readable in under 3 seconds.

- **Today's Remittance Banner:** Context-aware — shows "No remittance yet" with CTA, or the current remittance status (Draft / Finalized) with a link to continue or view.
- **Stats Cards (Asymmetric):** Today's Total Sales (large, primary), Unpaid Credits (amber), Outstanding Customer Debt (rose).
- **AI Insights Panel:** 3–4 auto-generated insight chips powered by Gemma 2B edge inference. Shows rider performance, overdue customers, unpaid tithes. Model downloads in the background — system operates normally while initializing.
- **Recent Remittances Table:** Last 5 remittances with quick-glance financial columns and tithes status.

---

### 3.2 Remittance

The primary operational module. Replaces the old dispatch session lifecycle.

**Remittance History:**
- Full table of all remittances: date, totals, tithes status.
- Inline `☑ Tithes Paid` / `☑ Offering Paid` toggles — update in place via HTMX.
- Row highlight if spiritual obligations are unpaid.

**Add Remittance (Daily, one per day):**
- **Pinned Summary Card:** Total Sales, Credit Sales, Commission, Expenses, Net Profit, Tithes, Credits Extended (amber) — live-updated as data is entered. Stays visible while scrolling.
- **Rider Sections:** Add a rider → select rider (Driver role) → add product rows (product dropdown + qty sold stepper + qty credited stepper + borrowed items stepper). Each row auto-computes subtotals. Rider subtotals update. Summary card updates.
- **Credits Extended Section:** Add credits a rider extended during their route. Enter the rider (combobox, Driver role), recipient name (free-text combobox with customer autocomplete), and amount (₱). Credits are **NOT** counted in sales, commission, or net profit. They are session-independent records displayed separately. Editable until finalized.
- **Repayments Received Section:** Record when a customer repays a prior credit to a rider during today's route. Select from open credits, enter the amount repaid. The repayment **IS added to today's Total Sales**. Commission **IS applied** at the rate snapshotted when the original credit was created. Repayments update the summary card in real time.
- **Expenses Section:** Add operational expenses (description + amount) below the rider section. Affects net profit and therefore tithes.
- **Finalize:** PIN-protected. Locks all records. Sets `tithe_amount = net_profit × 10%`. Creates customer credit lines for all `qty_credited > 0` lines.

**Financial Model:**
```
Total Sales          (qty_sold × price across all riders)
                   + Repayments Received (from prior rider credits — DOES add to sales)
+ Credit Sales       (qty_credited × price — creates customer debt)
─ Commissions        (qty_sold × commission rate per rider/product matrix)
                   + Commission on Repayments (snapshotted rate from original credit)
─ Expenses           (manually entered)
= Net Profit
= Tithes (10% of Net Profit)
+ Offering (manual)

[SEPARATE DISPLAY — NOT in financial totals]
Credits Extended by Riders  (standalone, session-independent)
  — Linked to a session only when repaid
  — NOT deducted from sales or net profit
  — Tracked per rider and recipient for the customer ledger
```

---

### 3.3 Customers

Debt and borrowed-container management.

- **List View:** Name, Balance, Borrowed Item Count, Payable Amount, Days Since Last Unpaid Credit. Filter chips and live search.
- **Record Payment:** Per-credit-line, per-container payment entry. Atomic debt reduction. Commission is NOT retroactive in this model (simplified from v2).
- **Update Containers:** Stepper per container type (Round 8-Gal, Slim 8-Gal, Other). Notes field.
- **Mobile:** Card layout. Debt amount prominent. Action buttons below each card.

---

### 3.4 Products & Pricing

Standalone nav section for full catalog management.

- **Products Tab:** CRUD (inline HTMX rows), price editing (save-on-blur), active/inactive toggle.
- **Delivery Commissions Tab:** Full matrix view — Riders × Products × ₱ rate. Inline editable. "Set all" bulk column update.

> Safe price adjustment: price changes apply only to future remittance entries. All saved lines use snapshot values, preserving financial audit integrity.

---

### 3.5 Employees & Users

Standalone nav section for full staff management. Admin-only.

- **Staff List:** Add/Edit/Deactivate employees. Roles: Admin, Staff, Driver.
- **Access Management:** Admin-configurable per-role permission matrix for all modules (dashboard, remittance, customers, products, employees, settings).
- **Security:** Change password, username, and PIN per employee. Lock account without deactivating.
- **Commission Assignment:** Per-driver commission rate editor (filtered view of the commission matrix).

---

### 3.6 Settings

System configuration and personal profile management.

- **System Config:** Lockscreen timeout (idle minutes before PIN prompt), password policy toggle, tithe rate.
- **Company:** Company name, contact number, email address (displayed in header/receipts).
- **My Profile:** Self-service updates: name, email, username, password, PIN.
- **AI Model:** Shows Gemma 2B model version, download status, and progress bar. Trigger or monitor background download. Download is ~1.2 GB stored in browser IndexedDB — device-local, one-time.

---

### 3.7 AI Chatbot (Edge — Read-Only)

A floating chatbot powered by Gemma 2B running locally via WebGPU. **No prompts leave the device.**

- **Architecture:** `@mlc-ai/web-llm` → JSON Mode tool selection → Django REST data enrichment → Gemma synthesizes response locally.
- **Tools:** Remittance summary, rider performance, customer debts, tithe status.
- **Background Download:** ~1.2 GB, one-time per device. System operates normally while downloading. Progress shown in Settings → AI Model.
- **Memory Safety:** `engine.unload()` called on drawer close — 100% VRAM freed.
- **Fallback:** Non-WebGPU browsers see a graceful message (Chrome 113+ or Edge 113+ required).

---

## 4. Light + Dark Mode

The UI supports both Light and Dark themes, switchable via a sidebar toggle.

- **Implementation:** CSS custom properties (HSL-calibrated tokens) on `:root` (light) and `[data-theme="dark"]`.
- **Sidebar:** Always dark (`#0F172A`) regardless of theme — brand consistency.
- **Persistence:** User preference stored in `localStorage`, applied by Alpine.js on page load.
- **Typography:** `Geist` (body/headings) + `Geist Mono` (all monetary values, counts, timestamps).

---

## 5. Service Level Agreement (SLA)

- **Core operations unaffected by AI model state.** Remittance entry, customer records, product management all function independently of whether Gemma is downloaded.
- **Mobile-first UI.** All screens are responsive. Customers list collapses to cards. Remittance form remains usable on tablet. Sidebar collapses to icon-only on mobile.
- **Data integrity.** Financial snapshots are immutable once saved. Totals propagate atomically using Django `F()` expressions — no race conditions.
- **Access control.** Every view is gated by Django `PermissionRequiredMixin`. Sidebar items are rendered conditionally per the active user's role permissions.
- **Audit trail.** All creation, finalization, and payment events include `created_by_id` / `recorded_by_id` for traceability.

---

## 6. What Is Out of Scope (v1)

| Feature | Reason |
|---|---|
| Real-time dispatch tracking (Kanban, bulk loads) | Replaced by manual remittance model |
| Session open/close lifecycle | No longer needed |
| Multi-branch / multi-tenant | Single branch MVP |
| SMS / push notifications | No carrier integration |
| PDF export of remittance | Post-MVP (Phase 7) |
| AI write tools (voice remittance) | Requires stronger guardrails — deferred |
| Offline-first IndexedDB sync | Phase 2 connectivity SLA assessment |
| Forgot password / email reset | No email service |
