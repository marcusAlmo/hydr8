# Hydr8 — Stitch Design Prompt (v2 — Final)
> Architecture-aware. User-centric. Scoped for 1-week delivery.

---

## Project Context

**Hydr8** is an internal day-operations management tool for a water refilling and delivery business. It is used by a business owner (Admin) and a counter staff member (Dispatcher). Delivery riders do not use the system at all — they receive their load and report back verbally.

**The core daily loop:**
1. Open session → 2. Dispatch bulk loads to riders → 3. Record delivery outcomes when riders return → 4. Log expenses → 5. Close session (PIN-protected) → 6. Review financials, mark tithes/offering paid

**Users and their real frustrations:**
- **Admin** — Drowns in mental math at end of day. Needs to see net profit, commissions per rider, tithes due, and offering status at a glance without a calculator. Also needs to know if tithes from last Tuesday were ever paid.
- **Dispatcher** — Needs to build a rider's load fast, record their return quickly, and keep the order queue Kanban tidy. Hates switching screens.
- **Driver/Rider** — Has **no system access**. They are registered in the system but do not log in.

---

## Technical Constraints (Architecture-Aware)

- **Backend:** Django + HTMX. Hypermedia-driven — server renders HTML partials, no SPA or React.
- **Styling:** Tailwind CSS.
- **Charts:** Chart.js (deferred to Week 2).
- **Auth/RBAC:** Role FK on User model. Strictly enforced via Django `PermissionRequiredMixin` at the view level AND sidebar visibility.
- **Session Model:** A `dispatch_session` table, not calendar-day based. Exactly one session is open at a time. The session owns all dispatches, delivery records, expenses, and the financial close.
- **Debt Payment:** Paid per container (not per peso). Each container payment triggers retroactive commission for the original rider.
- **Commission:** Per-rider × per-product rate matrix (`users_drivercommission`). Not a flat rate.

---

## Role Access Matrix (Strict)

| Screen | Admin | Dispatcher | Driver |
|---|---|---|---|
| Dashboard | ✓ | ✓ | ✗ |
| Order Queue (Kanban) | ✓ | ✓ | ✗ |
| Dispatch (Create Load + Record Return) | ✓ | ✓ | ✗ |
| Session Close & Finance Summary | ✓ | ✗ | ✗ |
| Session History | ✓ | ✗ | ✗ |
| Customer Debts & Containers | ✓ | ✓ | ✗ |
| Settings | ✓ | ✗ | ✗ |
| Analytics | ✓ | ✗ | ✗ |

---

## Week 1 Screens

### Screen 1: Login
**Goal:** Single form. No friction. Role-based redirect after authentication.

- Split layout: left = brand panel (dark, `#0F172A`, logo + tagline "Water. Delivered. Managed."), right = login form.
- Fields: `Username`, `Password`. One "Sign In" button.
- Error: Inline below form — "Invalid credentials." No toast or modal.
- Mobile: Brand panel hidden. Form fills full screen.
- **Anti-patterns:** No hero copy. No social login. No "Forgot password."

---

### Screen 2: Dashboard
**Goal:** The operational heartbeat of the open session, readable in under 3 seconds.

**Layout:** Left sidebar nav (icon-only on mobile) + main content.

**Session Status Bar (top of main content):**
- If session is open: Green pill "Session Open" + opened time + "Close Session" button (right-aligned, destructive amber color).
- If no session open: Full-width amber banner: "No active session. Open a new session to begin operations." with an "Open Session" button.
- "Close Session" opens a PIN entry modal with a confirmation summary before finalizing.

**Stats Row (asymmetric, not 3 equal cards):**
- Today's Gross Sales (large, Geist Mono, blue accent border)
- Open Dispatches (riders still out — count, amber if > 0)
- Active Customer Debt (₱ total, red accent border if > 0)

**Order Queue Kanban (Kanban board — 3 columns):**
- Columns: `Pending`, `Dispatched`, `Delivered`
- Each card shows: Customer name, Product, Qty, assigned (optional note)
- Cards drag is **not required** in Week 1 — status buttons on each card move it forward
- At session close, Delivered column cards are cleared (archived)
- Add Order button opens a quick-add modal: Customer (searchable), Product, Qty, Notes

**Active Dispatches Panel (below Kanban or right column on wide screens):**
- Compact list of riders still out (status = DISPATCHED)
- Shows: Rider name, dispatch time, products loaded (condensed), total expected collectible
- "Record Return" button per row — opens the return reconciliation form

**Driver Leaderboard (bottom):**
- Compact ranked list: Rider name, containers delivered, commission earned this session
- Text-first, no charts in Week 1

---

### Screen 3: Dispatch — Create Bulk Load
**Goal:** Dispatcher builds a rider's physical load and sends them out in under 90 seconds.

- Select Rider: dropdown of active drivers
- Add products: repeating row — `Product` dropdown (shows name + variation), `Qty` stepper
- "Add Another Product" adds a new row (HTMX partial append)
- **Expected Collectible Preview (live, right panel or below on mobile):** Updated via HTMX as rows change. Shows each line: `Product × Qty = ₱[amount]` and a total.
- Notes: Optional textarea
- Submit: "Create Dispatch" button → rider is immediately `DISPATCHED`, no pending state
- Defensiveness: If no riders are active, disable form and show: "No active riders. Add riders in Settings → Users."

---

### Screen 4: Dispatch — Record Return
**Goal:** When a rider returns, the dispatcher records exactly who got what and how they paid.

**Context header (read-only):** Rider name, dispatch time, products loaded (from `dispatch_bulkdispatchitem`)

**Per-Customer Delivery Entry (repeating rows, HTMX append):**
Each row:
- `Customer` — searchable dropdown (can create new customer inline)
- `Product` — dropdown limited to products in this dispatch
- `Qty Delivered` — stepper
- `Payment Type` — Toggle button: `Cash` (green) / `Debt` (amber)
- `Borrowed Containers` — two small steppers: `Round 8Gal`, `Slim 8Gal`

**Running reconciliation sidebar/panel (live HTMX update):**
```
Loaded:        30 Purified 8-Gal
Recorded:      22 Purified 8-Gal
Unaccounted:    8 Purified 8-Gal  ← shown in amber until = 0
```

Submit: "Finalize Return" button — only enabled when all loaded qty is accounted for
Defensiveness: Block submission if `unaccounted > 0` with error: "You have 8 unaccounted Purified 8-Gal. Record remaining deliveries or mark as returned stock."

---

### Screen 5: Session Close & Financial Summary
**Goal:** Admin closes the session with full financial clarity and zero ambiguity. Admin-only.

**Triggered by:** "Close Session" button on dashboard → PIN modal → summary screen.

**PIN Modal:**
- Numeric PIN input (4–6 digits)
- If wrong: "Incorrect PIN. Session remains open."
- If correct: Load the Session Summary page

**Session Finance Summary (read-only once confirmed):**

```
─── Revenue ────────────────────────────────────────────
Gross Expected      ₱[amount]   (all deliveries + debts repaid)
  Less: New Debt   -₱[amount]   (debt deliveries not yet paid)
                   ────────────
Gross Sales         ₱[amount]

─── Deductions ─────────────────────────────────────────
Total Commissions  -₱[amount]
Total Expenses     -₱[amount]
                   ────────────
Net Profit          ₱[amount]   ← Bold, large, primary display

─── Spiritual Obligations (separate visual card, amber/gold left border)
Tithes Due (10%)    ₱[amount]   ☐ Tithes Paid
Offering            ₱[input]    ☐ Offering Paid   ← Offering is manual input
```

**Per-Rider Breakdown (expandable rows below):**
Each rider:
- Containers (Cash): [N] × rate = ₱commission
- Containers (Debt Paid): [N] × rate = ₱commission (retroactive)
- Total Commission: ₱[X]
- Cash Expected: ₱[X] | Cash Remitted: ₱[X] | Variance: ₱[+/-]

**Expenses List (editable until finalized):**
- Table of expenses added this session (description, amount)
- "Add Expense" button (HTMX modal): description + amount

**"Finalize & Close Session" button:**
- Large, destructive. Requires explicit second click with confirmation: "This will lock all records for this session. Continue?"
- Once finalized: entire page becomes read-only. Badge shows "Finalized [date/time] by [user]"

---

### Screen 6: Session History
**Goal:** Admin reviews all past sessions, tracks outstanding tithes/offerings.

- Table: `Date/Time Opened`, `Opened By`, `Gross Sales`, `Net Profit`, `Tithes Due`, `☑ Tithes Paid`, `☑ Offering Paid`, `View Details`
- Tithes Paid and Offering Paid are **inline toggleable checkboxes** — clicking them updates the record immediately via HTMX (no page reload)
- Row highlight: amber left border if `tithes_paid = FALSE` or `offering_paid = FALSE`
- "View Details" opens the full Session Finance Summary in read-only mode
- Filter: date range picker
- Empty state: "No sessions recorded yet."

---

### Screen 7: Customer Debts & Borrowed Containers
**Goal:** See who owes what, in money and containers. Log payments per-container.

**Filters (quick chips):** `All`, `Has Debt`, `Has Borrowed Containers`, `Clear Accounts`

**Table:** `Customer Name`, `Address`, `Monetary Debt (₱)`, `Borrowed Round 8Gal`, `Borrowed Slim 8Gal`, `Actions`
- Row amber highlight if debt > 0 or any borrowed containers > 0

**"Record Payment" modal (per customer):**
- Shows list of debt delivery records for that customer (session date, product, qty_owed, qty_remaining)
- For each debt record with remaining containers: `[input: containers to pay]` field (max = remaining)
- Amount auto-calculates: `containers × unit_price`
- Submit records payment, updates customer debt balance atomically
- Important: No fractional payments. Input is container count only.

**"Update Containers" modal:**
- Per container type (Round 8Gal, Slim 8Gal): current count + decrease/increase stepper
- Notes field: "Customer returned 2 slim containers"

**Mobile:** Collapses to per-customer card layout.

---

### Screen 8: Settings (Admin Only — Tabbed)

**Tab 1: Products**
- Table: Product Name, Variation, Price, Status, Edit/Deactivate
- "Add Product" → inline row (HTMX). Fields: name, variation, price.
- Edit price inline. Deactivate hides from dispatch dropdowns.

**Tab 2: Users / Staff**
- Table: Name, Username, Role, Status, Actions
- "Add Staff" modal: Full Name, Username, Email, Password, Role (Admin/Dispatcher/Driver)
- Deactivate = soft delete. Cannot deactivate the last active Admin.

**Tab 3: Commission Rates**
- Matrix view: Rows = Drivers, Columns = Products
- Each cell: editable ₱ rate input (inline HTMX save on blur)
- "Set rate for all drivers" per product column → updates all cells in that column simultaneously (bulk UPDATE), then refreshes the matrix

**Tab 4: System Config**
- `Tithe Rate (%)`: numeric input, default 10%
- `Late Threshold (minutes)`: numeric input, default 30
- `Session Close PIN`: masked input (change requires current PIN first)
- Save button per field.

---

## Design System (Stitch DESIGN.md Directives)

**Visual Atmosphere:** Operational cockpit. Dense but structured. Clinical but human. Like the back office of a well-run business, not a tech startup.
- **Density:** 7/10 — data tables, real numbers, compact rows
- **Variance:** 4/10 — predictable layouts, stressed users need familiarity
- **Motion:** 4/10 — subtle HTMX swap transitions, no animations for their own sake

**Color Palette:**
- `Abyss` (`#0F172A`) — Sidebar, dark canvas
- `Navy Surface` (`#1E293B`) — Cards, modals, elevated containers
- `Slate Border` (`rgba(148,163,184,0.15)`) — 1px structural lines
- `Muted Slate` (`#94A3B8`) — Secondary labels, metadata, timestamps
- `Off-White` (`#F1F5F9`) — Primary body text on dark surfaces
- `Hydr8 Blue` (`#0EA5E9`) — CTAs, active nav, focus rings (Sky-500)
- `Amber Warning` (`#F59E0B`) — Late, debt, pending, session tithes card
- `Emerald Success` (`#10B981`) — Cash payment, delivered, positive variance
- `Rose Danger` (`#F43F5E`) — Negative variance, errors, destructive actions

**Typography:**
- `Geist` — Headlines, nav labels, body
- `Geist Mono` — ALL monetary values, quantities, timestamps, container counts
- **Banned:** `Inter`, serif fonts, pure black `#000000`

**Components:**
- Status badges: pill, 15% tint background, full-color text
- Table rows: 52px min-height, 1px `Slate Border` bottom, hover `Navy Surface`
- Stats cards: `Navy Surface` bg, `2px` top border in semantic color, `1rem` radius, NO box-shadow
- Primary button: `Hydr8 Blue` fill, `-1px` translateY on active
- Inputs: `Navy Surface` bg, `Slate Border` border, `2px Hydr8 Blue` focus ring
- Sidebar: `Abyss` bg, active item = `3px Hydr8 Blue` left border + `rgba(14,165,233,0.1)` bg
- Kanban cards: `Navy Surface`, `1px` border, status color as left accent `3px`
- Tithes/Offering card: amber/gold `3px` left border to signal spiritual importance

**Anti-Patterns (BANNED):**
- No emojis
- No `Inter` font
- No purple/neon/glow
- No pure black `#000000`
- No 3-equal-card grids
- No fabricated data or metrics
- No "Seamless", "Elevate", "Unleash", "Next-Gen" copy
- No circular spinners — skeletal loaders only
- No horizontal scroll on mobile
- No centered hero layouts

---

## Deferred to Week 2

| Feature | Reason |
|---|---|
| Analytics / Chart.js (sales trends, best rider) | Needs real session data |
| PDF/Excel export | Build after analytics page is designed |
| Customer creation as a separate flow | MVP: create inline in dispatch return form |
| Forgot password | No email service |
| SMS/push notifications | Out of scope |
