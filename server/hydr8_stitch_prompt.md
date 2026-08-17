# Hydr8 — Stitch Design Prompt (v4 — Rider Credit & Repayment)
> Manual remittance-first. Rider-issued credits. Repayment tracking with commission. Edge AI insights. Light + Dark mode. One week delivery.

---

## Project Context

**Hydr8** is an internal daily operations tool for a water refilling and delivery business. The core daily loop is simple:

1. Admin opens the day → 2. Create a daily remittance → 3. Add riders with their sold/credited products → 4. Log expenses → 5. Finalize remittance (PIN-protected) → 6. Monitor outstanding customer debts and borrowed containers → 7. Ask AI for insights on demand.

**Users and their real contexts:**
- **Admin** — Needs to enter remittance data fast, see net profit, tithes due, and commission breakdown at a glance. Manages products, employees, and system config.
- **Staff** — Assists with data entry (remittance, customers). Cannot access employee management or sensitive settings.
- **Driver/Rider** — Has **no system access**. They are registered for commission tracking only.

**Removed from v2:** Dispatch, bulk loads, Kanban order queue, session open/close lifecycle. These are replaced entirely by the manual daily remittance.

---

## Technical Constraints

- **Backend:** Django + HTMX. Hypermedia-driven. Server renders HTML partials. No SPA.
- **Styling:** Tailwind CSS.
- **Charts:** Chart.js (deferred to post-MVP).
- **Theme:** Light + Dark mode via CSS custom properties. Alpine.js controls `data-theme` on `<html>`, persisted in `localStorage`.
- **Auth/RBAC:** Role FK on User model. Permission matrix is Admin-assignable at runtime. Enforced via Django `PermissionRequiredMixin` and sidebar visibility.
- **AI:** Gemma 2B (`gemma-2-2b-it-q4f16_1-MLC`) via `@mlc-ai/web-llm` WebGPU. Client-side only. Read-only tool calling. Background download with progress written to server config via PATCH API.

---

## Navigation Structure (7 Items)

```
Sidebar (always dark — brand consistency)
├── Dashboard          (icon: grid/home)
├── Remittance         (icon: receipt/layers)
├── Customers          (icon: users)
├── Products & Pricing (icon: tag/box)
├── Employees & Users  (icon: user-cog)
├── Settings           (icon: gear)
└── [Theme Toggle]     (sun/moon — bottom of sidebar)
```

---

## Role Access Matrix (Admin-Assignable Defaults)

| Screen | Admin | Staff | Driver |
|---|---|---|---|
| Dashboard | Full | Read | — |
| Remittance (Add + History) | Full | Add/Edit DRAFT | — |
| Customers | Full | Add/Edit | — |
| Products & Pricing | Full | Read-only | — |
| Employees & Users | Full | — | — |
| Settings | Full | Profile only | — |
| AI Chatbot | Full | Full | — |

> These defaults are seeded but the Admin can adjust per-role permissions at any time via the Employees & Users screen.

---

## Screen 1: Login
**Goal:** Single form. Zero friction. Role-based redirect after auth.

**Layout:** Split — left panel (dark `Abyss` bg, logo + tagline "Water. Delivered. Managed.") + right panel (login form on light bg in Light mode; elevated surface in Dark mode).

**Fields:** `Username`, `Password`. One "Sign In" button. Optional PIN login button below for returning users.

**Error:** Inline below form — "Invalid credentials." No toast, no modal.

**Mobile:** Left panel hidden. Form fills full screen with centered logo above.

**Anti-patterns:** No hero copy. No social login. No "Forgot password" link.

---

## Screen 2: Dashboard
**Goal:** Operational heartbeat. Readable in under 3 seconds. Shows today's financial state and AI insights.

**Layout:** Sidebar (always dark) + main content area (themed).

**Theme toggle:** Sun/Moon icon pinned at the bottom of the sidebar. Clicking toggles `data-theme="light"` / `data-theme="dark"` on `<html>`. State persists via `localStorage`. No page reload.

---

### Dashboard — Today's Remittance Banner
- **If no remittance today:** Full-width amber banner: "No remittance for today yet." + prominent "Create Today's Remittance" button (right-aligned).
- **If DRAFT remittance exists:** Teal/blue pill "Remittance — Draft" + date + "Continue Editing" button.
- **If FINALIZED:** Green pill "Remittance Finalized" + date + "View Summary" button.

---

### Dashboard — Stats Row (Asymmetric, 3 Cards)
Cards are NOT 3 equal columns. Use a weighted layout:

1. **Today's Total Sales** — Large (`2xl` Geist Mono), 2px top `Hydr8 Blue` border, shows `₱X,XXX.XX`. Below: small credit sales sub-label.
2. **Unpaid Credits** — Medium, 2px top `Amber Warning` border, shows `₱X,XXX.XX`. Red if > ₱0.
3. **Outstanding Customer Debt** — Medium, 2px top `Rose Danger` border, shows `₱X,XXX.XX` + `N customers` count label below.

---

### Dashboard — AI Insights Panel
This section appears below the stats row. It has a subtle animated gradient header bar (slow horizontal shimmer, `Hydr8 Blue` → `Emerald` gradient).

**Header:** "AI Insights" with a small Gemma badge (version label). Right side: model status chip — `Ready`, `Initializing...`, or `Downloading XX%`.

**Insight Cards (3–4 auto-generated chips, horizontal scroll on mobile):**
- Each chip is a compact card with an icon, one-line insight text, and a subtle category label.
- Examples:
  - "Rider Dela Cruz contributed 38% of this week's net sales."
  - "3 customers overdue 7+ days — ₱4,800 in unpaid credits."
  - "Tithes for last Monday are still unpaid."
- Chips are **read-only display** — clicking one opens the AI chatbot pre-filled with a follow-up question.
- If AI model is not ready: chips show skeleton loaders with label "AI insights will appear once model is ready."

**"Ask Hydr8 AI" button** — right-aligned, opens the global AI chatbot bubble.

---

### Dashboard — Recent Remittances (Table, Last 5)
Compact table below AI Insights:
- Columns: `Date`, `Total Sales`, `Net Profit`, `Commission`, `Tithes`, `☑ Paid`, `Actions`
- Row amber left border if tithes or offering is unpaid
- `View` button links to the Remittance History detail

---

## Screen 3: Remittance
**Goal:** The primary data-entry screen. Add riders, products, quantities, and expenses. See real-time financial summary.

### Tab A: Remittance History (Default View)

**Table (full width):**
- Columns: `Date`, `Created By`, `Total Sales`, `Credit Sales`, `Commission`, `Net Profit`, `Tithes`, `☑ Tithes Paid`, `☑ Offering Paid`, `Actions`
- `☑ Tithes Paid` and `☑ Offering Paid` are **inline toggleable checkboxes** — clicking updates immediately via HTMX (no page reload)
- Row amber left border if either is unchecked on a finalized remittance
- `View` — opens FINALIZED remittance in read-only mode
- `Edit` — available only for DRAFT remittances; opens the Add Remittance sub-tab
- Filter: date range picker (top right)
- Empty state: "No remittances recorded yet. Create today's remittance to get started."

**"Add Remittance" button** — top right. Opens the Add Remittance sub-tab (slide-in, not a modal).

---

### Tab B: Add Remittance (Slide-In Sub-Tab)

**Sub-tab header:**
- "New Remittance — [Today's Date]" (date field, pre-filled, editable for backfill)
- Right side: status badge (`DRAFT`) + "Save Draft" + "Finalize Remittance" buttons

---

#### Pinned Summary Card (top of form, live-updated via HTMX on every input change)
```
┌────────────────────────────────────────────────────────────────────┐
│  Remittance Summary                    Date: [________]            │
│────────────────────────────────────────────────────────────────────│
│  Total Sales:      ₱  0.00  │  Credit Sales:     ₱  0.00          │
│  Total Commission: ₱  0.00  │  Borrowed Items:   0                 │
│  Total Expenses:   ₱  0.00  │  Net Profit:       ₱  0.00          │
│  Tithes (10%):     ₱  0.00  │  Credits Extended: ₱  0.00 ▲ (amber)│
└────────────────────────────────────────────────────────────────────┘
```
This card is sticky/pinned at top while scrolling the form below.

> "Credits Extended" is shown in **amber** in the summary card to signal it is a separate tracking number — NOT part of net profit. It represents money owed back to the business, not a deduction.

---

#### Rider Sections (HTMX-driven, expandable)

**Empty state:** "No riders added yet." with a prominent "+ Add Rider" button.

**Rider Section Structure (repeating per rider):**
```
┌──────────────────────────────────────────────────────────────────┐
│  Rider: [Dropdown — Driver users only]           [Remove Rider]  │
│──────────────────────────────────────────────────────────────────│
│  Product Lines:                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Product: [dropdown] │ Sold: [±stepper] │ Credited:[±stepper]│  │
│  │ Borrowed Items: [±stepper]                                │    │
│  │ Subtotal Payable: ₱X.XX  │  Commission: ₱X.XX            │    │
│  └──────────────────────────────────────────────────────────┘    │
│  [+ Add Product]                                                  │
│──────────────────────────────────────────────────────────────────│
│  Rider Subtotals:  Payable ₱X.XX  │  Commission ₱X.XX           │
└──────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Clicking a Rider dropdown auto-expands the product section below it.
- "+ Add Product" appends a new product line row via HTMX partial append.
- Each qty change triggers an HTMX partial recalculation of: line subtotals → rider subtotals → summary card.
- Rider dropdown only shows users with `Driver` role and `ACTIVE` status.
- Product dropdown only shows `is_active = True` products.
- A rider can only be added once per remittance (duplicate check on dropdown).

**"+ Add Rider" button** — below all existing rider sections. Appends a new rider block via HTMX.

---

#### Expenses Section (below all rider sections)

**Header:** "Expenses" with an "+ Add Expense" button (right-aligned).

```
┌────────────────────────────────────────────────────────────────┐
│ Description                          │ Amount      │ Actions   │
│──────────────────────────────────────│─────────────│───────────│
│ [Fuel — Rider A motorcycle     ]     │ ₱[150.00]   │ [Delete]  │
│ [Seal replacement               ]    │ ₱[ 80.00]   │ [Delete]  │
└────────────────────────────────────────────────────────────────┘
│ Total Expenses:                                      ₱230.00   │
```

Each expense row is editable inline. Deleting an expense triggers a summary card recalculation via HTMX.

---

#### Credits Extended Section (below Expenses, before Finalize)

**Header:** "Credits Extended" with a `[+ Add Credit]` button (right-aligned). Section has a **rose/amber 3px left border card** to signal it is financially separate.

```
─── Credits Extended ─────────────────────── [+ Add Credit]
┌────────────────────────────────────────────────────────────────┐
│ Rider:     [Combobox — Driver users only            ]         │
│ Recipient: [Combobox — free-text, autocomplete from customers] │
│ Amount:    ₱[__________]                        [Delete]      │
└────────────────────────────────────────────────────────────────┘
│ Total Credits Extended:                              ₱ 0.00  │
│ ⚠ These credits are NOT counted in sales or commission.       │
```

**Behavior:**
- `[+ Add Credit]` appends a new credit row via HTMX partial append.
- Rider combobox shows only `Driver` role users with `ACTIVE` status.
- Recipient combobox is a free-text input with **autocomplete** backed by existing customer names (HTMX debounced `GET` for suggestions). The value does NOT need to be a registered customer.
- Amount is a plain peso input.
- Adding or deleting a credit row updates the `Total Credits Extended` display via HTMX — this does **NOT** recalculate Net Profit or any financial totals.
- Editable only while remittance is `DRAFT`.
- The warning label `⚠ These credits are NOT counted in sales or commission.` is always visible in the section footer.

---

#### Repayments Received Section (below Credits Extended, before Finalize)

**Header:** "Repayments Received" with a `[+ Record Repayment]` button (right-aligned). Section has a **teal/emerald 3px left border card** to signal it IS part of the financial totals.

```
─── Repayments Received ──────────────────── [+ Record Repayment]
┌────────────────────────────────────────────────────────────────┐
│ Credit: [Dropdown — open credits: Rider • Recipient • ₱bal]  │
│ Rider:  [auto-filled from selected credit]                   │
│ Amount Repaid:  ₱[__________]                                │
│ Commission Applied: ₱ [auto-computed, read-only]  [Delete]  │
└────────────────────────────────────────────────────────────────┘
│ Total Repaid This Session: ₱ 0.00  │ Commission: ₱ 0.00      │
│ ℹ Repayments are added to today’s sales and commission.      │
```

**Behavior:**
- `Credit` dropdown shows only **open (not fully repaid)** rider credits. Display format: `"[Rider Name] → [Recipient] (₱[outstanding balance])"`. Fetched via HTMX `GET` on click.
- On credit selection: `Rider` field auto-fills (read-only), `Commission Applied` auto-computes as `Amount × commission_rate_snapshot` (live HTMX recalculation on amount change).
- Adding or deleting a repayment row triggers a full HTMX summary card recalculation — Total Sales, Commission, and Net Profit all update.
- `Commission Applied` is **read-only** — it is computed from the original credit's snapshotted rate, not the current rate matrix.
- Validation: Amount Repaid cannot exceed the outstanding balance on the selected credit. Show inline error if exceeded.
- Editable only while remittance is `DRAFT`.

---

#### Finalize Remittance

At the bottom of the form, after the expenses section:

```
─── Spiritual Obligations ────────────────────────── (amber/gold left border card)
Offering Amount:  ₱ [__________]  (manual input)
Tithes (10% of Net Profit):  ₱ X,XXX.XX  (read-only, computed)

[Save as Draft]                         [Finalize Remittance ⚠]
```

Clicking "Finalize Remittance":
1. Opens PIN entry modal (4–6 digits).
2. If wrong PIN: "Incorrect PIN. Remittance remains as Draft."
3. If correct: Confirmation dialog — "This will lock all entries for [date]. This cannot be undone. Continue?"
4. On confirm: Status → `FINALIZED`. All fields become read-only. Badge shows "Finalized [date/time] by [user]".

---

## Screen 4: Customers
**Goal:** See who owes money or has borrowed containers. Track and log payments.

### Customer List View

**Filter chips (top):** `All` · `Has Debt` · `Has Borrowed Items` · `Clear Accounts`

**Search bar:** Live search by customer name (HTMX debounced).

**Table / Card View (responsive):**
| Column | Description |
|---|---|
| `Name` | Customer name |
| `Balance` | `debt_balance` in ₱, rose text if > 0 |
| `Borrowed Items` | Total borrowed containers count |
| `Payable Amount` | Total outstanding monetary debt |
| `Last Credit` | "X days ago" computed from `last_credit_at` — amber if > 7 days |
| `Actions` | Pay, Update Containers, View History |

Row amber left border if `debt_balance > 0` or borrowed items > 0.

**"Add Customer" button** — top right. Opens modal with: Name, Address, Contact Number, Notes.

**Mobile:** Collapses to per-customer card layout (name bold, debt prominent, action buttons below).

---

### "Record Payment" Modal (per customer)

- Shows list of open credit lines for that customer (remittance date, product, qty owed, qty remaining, amount)
- Per credit line: `[input: containers to pay now]` (max = `qty_remaining`)
- Amount auto-calculates: `containers × unit_price_snapshot`
- Submit: updates `customers_creditline.qty_remaining`, decrements `customers_customer.debt_balance` atomically
- Defensiveness: block submit if any input exceeds `qty_remaining`

---

### "Update Containers" Modal (per customer)

- Per container type (Round 8-Gal, Slim 8-Gal, Other): current count + increase/decrease stepper
- Notes field: "Customer returned 2 slim containers"
- Updates `customers_customer.borrowed_*` atomically

---

## Screen 5: Products & Pricing
**Goal:** Manage product catalog and delivery commission rates. Standalone nav item.

### Sub-Tab 1: Products

**Table:**
| Column | Notes |
|---|---|
| `Name` | Product name, e.g. Purified |
| `Variation` | e.g. 8-Gallon Round |
| `Price (₱)` | Editable inline — save on blur via HTMX |
| `Active` | Toggle switch — inactive hides from remittance dropdowns |
| `Actions` | Edit row, Deactivate |

**"Add Product" button** → inline row append via HTMX. Fields: Name, Variation, Price.

> [!NOTE]
> Price changes apply only to new remittance entries. All saved lines use `unit_price_snapshot` — immutable from the moment of entry.

---

### Sub-Tab 2: Delivery Commissions

**Matrix View:**
- Rows = Active Drivers (from `users_user` where role = Driver, status = ACTIVE)
- Columns = Active Products (from `core_product` where `is_active = TRUE`)
- Each cell: editable `₱ rate` input. Save on blur via HTMX.
- Empty cell = `₱0.00` (commission not set for that combination)

**Bulk action per column:** "Set rate for all drivers" input at column header → bulk UPDATE via Django ORM → matrix refreshes.

---

## Screen 6: Employees & Users
**Goal:** Full employee lifecycle management. Standalone nav item. Admin only.

### Sub-Tab 1: Staff List

**Table:**
| Column | Notes |
|---|---|
| `Full Name` | |
| `Username` | |
| `Role` | Admin / Staff / Driver |
| `Status` | `ACTIVE` or `DEACTIVATED` |
| `Actions` | Edit, Deactivate, Reset Credentials |

**"Add Employee" button** → modal. Fields: Full Name, Username, Email (optional), Password, PIN (optional), Role.

**Deactivate** = soft delete. Cannot deactivate the last active Admin.

---

### Sub-Tab 2: Access Management

Per-role permission matrix editor:
- Rows = Actions (`dashboard`, `remittance`, `customers`, `products`, `employees`, `settings`, `analytics`)
- Columns = Roles (`Admin`, `Staff`, `Driver`)
- Each cell: checkboxes for `Read`, `Write`, `Update`, `Delete`
- Save button per row. Changes apply immediately to sidebar visibility and view-level access.

---

### Sub-Tab 3: Security & Credentials

Per-employee actions (accessible via "Reset Credentials" in Staff List):
- Change Password
- Change Username
- Change PIN (4–6 digit numeric)
- Lock Account (temporary — blocks login without deactivating)

---

### Sub-Tab 4: Commission Assignment

Per-employee commission editor (only for users with `Driver` role):
- Shows the commission matrix rows for the selected driver
- Editable ₱ rate per product
- Same save-on-blur HTMX behavior as the Products & Pricing commission tab

---

## Screen 7: Settings
**Goal:** System configuration and personal profile management. Admin-only (Staff sees Profile tab only).

### Tab 1: System Config

| Setting | Input | Notes |
|---|---|---|
| Lockscreen Timeout | Number input (minutes) | Idle minutes before PIN prompt |
| Password Policy | Toggle (`is_password_strict`) | Requires uppercase, numbers, symbols |
| Tithe Rate | `%` input | Default 10% — applies to net profit |

---

### Tab 2: Company

| Setting | Input |
|---|---|
| Company Name | Text input |
| Contact Number | Text input |
| Email Address | Email input |

---

### Tab 3: My Profile

- Update own: First Name, Last Name, Email, Username, Password, PIN
- Current password required to change password or PIN

---

### Tab 4: AI Model

**Shows:**
- Model Name: `Gemma 2B (gemma-2-2b-it-q4f16_1-MLC)`
- Download Status: `Ready` / `Downloading (XX%)` / `Not Started`
- Progress bar (if downloading)
- Model size: ~1.2 GB (stored in browser IndexedDB — device-local)
- "The AI model downloads once per device. It never leaves your browser."
- [Trigger Download] button — starts background download if not started

**Behavior:** Model download happens in the background. The main system operates normally. Only the AI Insights panel and chatbot show "AI initializing..." while downloading. This tab shows live progress (HTMX polling or SSE).

---

## Global: AI Chatbot Bubble

**Trigger:** Fixed bottom-right floating action button (chat icon). Visible on all screens.

**Bubble states:**
- **Model not ready:** FAB shows an amber pulsing ring. Clicking shows: "AI model is downloading in the background (XX%). Insights will be available shortly."
- **Model ready:** FAB is static `Hydr8 Blue`. Clicking opens the chat drawer.

**Chat Drawer (slide-in from right, 400px wide):**
- Header: "Hydr8 AI" + Gemma badge + Close button
- Message thread (scrollable)
- Input box + Send button
- "Ask me about today's sales, commissions, customer debts, or unpaid tithes."

**Available tools (read-only, JSON mode):**
- `fetch_remittance_summary(start_date, end_date)` — Sales, commission, net, tithes across date range
- `fetch_rider_performance(rider_id, start_date, end_date)` — Per-rider breakdown
- `fetch_customer_debts(filter)` — Customers with outstanding balances
- `fetch_tithe_status()` — Unpaid tithes/offering list

**On close:** `engine.unload()` called — 100% VRAM freed.

**Fallback:** If `navigator.gpu` is unavailable → graceful message: "AI chatbot requires WebGPU. Please use Chrome 113+ or Edge 113+. Your other data is unaffected."

---

## Design System — Light + Dark Mode

### Mode Architecture

- CSS custom properties defined on `:root` (light defaults) and `[data-theme="dark"]` override block.
- Alpine.js: `x-data` on `<body>` with `theme: localStorage.getItem('theme') || 'light'`, bound to `document.documentElement.dataset.theme`.
- Sidebar always uses `Abyss` dark palette regardless of theme (brand consistency).

### Color Tokens

| Token | Light Mode | Dark Mode |
|---|---|---|
| `--bg-canvas` | `#F8FAFC` | `#0F172A` |
| `--bg-surface` | `#FFFFFF` | `#1E293B` |
| `--bg-elevated` | `#F1F5F9` | `#263248` |
| `--border` | `rgba(15,23,42,0.10)` | `rgba(148,163,184,0.15)` |
| `--text-primary` | `#0F172A` | `#F1F5F9` |
| `--text-secondary` | `#64748B` | `#94A3B8` |
| `--text-mono` | `#1E293B` | `#E2E8F0` |
| `--accent-blue` | `#0EA5E9` | `#38BDF8` |
| `--accent-amber` | `#D97706` | `#F59E0B` |
| `--accent-emerald` | `#059669` | `#10B981` |
| `--accent-rose` | `#E11D48` | `#F43F5E` |
| `--sidebar-bg` | `#0F172A` | `#0F172A` |
| `--sidebar-text` | `#94A3B8` | `#94A3B8` |
| `--sidebar-active-bg` | `rgba(14,165,233,0.10)` | `rgba(14,165,233,0.10)` |
| `--sidebar-active-border` | `#0EA5E9` | `#38BDF8` |

### Typography

- `Geist` — All body, nav, labels, headings
- `Geist Mono` — **ALL** monetary values, quantities, timestamps, percentages, container counts
- **Banned:** `Inter`, serif fonts, pure black `#000000`, pure white `#FFFFFF`

### Icons

- Use **Google Material Symbols Rounded**.
- **CRITICAL:** You MUST include the CDN link in the `<head>` of your HTML to prevent broken text icons: `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" />`
- Usage: `<span class="material-symbols-rounded">grid_view</span>`

### Component Standards

| Component | Spec |
|---|---|
| Stats cards | `var(--bg-surface)` bg, `2px` top border in semantic color, `0.75rem` radius, no box-shadow |
| Table rows | 52px min-height, `1px var(--border)` bottom, hover `var(--bg-elevated)` |
| Status badges | Pill shape, 15% tint bg, full-color text, `Geist` weight 500 |
| Primary button | `var(--accent-blue)` fill, white text, `-1px` translateY on active |
| Danger button | `var(--accent-rose)` fill, white text, explicit confirmation required |
| Inputs | `var(--bg-surface)` bg, `1px var(--border)` border, `2px var(--accent-blue)` focus ring |
| Sidebar | `var(--sidebar-bg)` bg, active item = `3px left border var(--sidebar-active-border)` + `var(--sidebar-active-bg)` |
| Tithes card | `3px amber/gold left border` + `rgba(245,158,11,0.08)` bg tint to signal spiritual importance |
| Remittance summary card | `var(--bg-surface)`, `2px top border var(--accent-blue)`, sticky on scroll |
| Rider section | `var(--bg-elevated)`, `1px border var(--border)`, `0.5rem radius` |
| Expense row | Alternating `var(--bg-surface)` / `var(--bg-elevated)`, no border |
| AI Insights panel | Animated shimmer header (`Hydr8 Blue` → Emerald gradient, 3s loop), `var(--bg-surface)` body |
| Chatbot drawer | `var(--bg-surface)` bg, `1px var(--border)` left border, slide-in `0.25s ease` |
| Progress bars | `var(--accent-blue)` fill, `var(--bg-elevated)` track, `4px` height, smooth transition |
| Skeleton loaders | `var(--bg-elevated)` base, shimmer animation — NO circular spinners |

### Motion & Density

- **Density:** 7/10 — data tables, real numbers, compact rows. Not a dashboard wallpaper.
- **Variance:** 4/10 — consistent layouts. Stressed operators need familiarity.
- **Motion:** 4/10 — HTMX swap fades (`150ms opacity`), pinned card live updates, AI shimmer header. No decorative animations.

### Anti-Patterns (BANNED)

- No emojis anywhere in the interface
- No `Inter` font
- No purple, neon, or glow effects
- No pure black `#000000` or pure white `#FFFFFF`
- No 3-equal-card grid layouts
- No fabricated or placeholder data
- No "Seamless", "Elevate", "Unleash", "Next-Gen" copy
- No circular spinners — skeleton loaders only
- No horizontal scroll on mobile
- No centered hero section layouts
- No toast for form validation errors — inline only

---

## Deferred to Post-MVP

| Feature | Reason |
|---|---|
| Analytics charts (Chart.js — sales trends, rider leaderboard) | Needs real session data |
| PDF / Excel export of remittance | Build after analytics page is complete |
| Customer creation as a separate full-page flow | MVP: inline modal |
| Forgot password / email reset | No email service configured |
| SMS / push notifications | Out of scope |
| AI write tools (create remittance via voice) | Requires stronger guardrails and validation |
| Branch / multi-tenant support | Single-branch MVP first |
| Offline-first IndexedDB sync | Phase 2 when connectivity SLA is confirmed |
