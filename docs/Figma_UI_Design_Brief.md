# HyDR8 - Comprehensive High-Fidelity UI Design Brief & Figma Prompt

**Project:** HyDR8 (Water Refilling Station Management System)
**Target Platform:** Desktop Web Application & Touch-enabled POS Displays
**Role:** Expert UX/UI Designer
**Design System Name:** HydroLogic Fluidity

---

## 1. Core Design Philosophy & Aesthetic

This application operates in a high-utility, industrial SaaS environment (logistics, inventory, point-of-sale). 

*   **Vibe:** Corporate / Modern with a strict "Utility-First" philosophy. It must look crisp, professional, precise, and clean to evoke institutional trust and reliability. 
*   **Density vs. Clarity:** The UI will display dense data, but it must not feel cluttered. Achieve organization through subtle tonal layering, white space, and alignment, rather than heavy borders or drop shadows.
*   **Touch-Ready Ergonomics:** Even though this is a desktop view, it will frequently be used on touchscreen POS monitors by operators. **Enforce a strict 44px minimum touch target** for all interactive elements.

## 2. Global Styling Rules

### 2.1 Color Palette
The palette is intentionally blue-centric to evoke cleanliness, water, and technical precision.
*   **Background / Canvas (Level 0):** `#f7f9ff` or `#f9f9ff` (A very light, cool, airy blue-gray).
*   **Surface / Cards (Level 1):** `#ffffff` (Pure white for high contrast data containers).
*   **Primary (Water Blue):** `#005e97` (Use for primary actions, active states, main branding).
*   **Secondary (Ocean):** `#296290` (Use for deep-contrast elements, critical navigation, active sidebar states).
*   **Tertiary (Slate):** `#35454e` (Metadata, subtle background accents, table headers).
*   **Destructive / Error:** `#ba1a1a` (Critical alerts, low-stock warnings, destructive actions).
*   **Success:** `#006c49` (or a similar harmonious emerald/green for "Paid" or "Completed" statuses).

### 2.2 Typography (Inter)
*   **Font Family:** `Inter` for everything.
*   **Hierarchy Mechanism:** Differentiate hierarchy using font weight (e.g., `400` vs. `600`) and color contrast (Primary text vs. Slate gray metadata text), rather than massive leaps in font size.
*   **Tabular Data:** All numerical data (prices, inventory counts, liters) MUST use a monospace or tabular number setting (`font-variant-numeric: tabular-nums`) to ensure strict vertical alignment in tables.

### 2.3 Shapes, Borders & Elevation
*   **Corner Radii:** 
    *   `8px` (0.5rem) for standard UI elements (buttons, inputs, dropdowns).
    *   `16px` (1rem) for large structural containers, panels, and metric cards.
    *   `Full / Pill-shape` for status chips and badges.
*   **Borders:** Use low-contrast 1px outlines (`#c0c7d2` or `#dbe3ef`) to define cards.
*   **Shadows:** Avoid heavy, traditional drop shadows. Use a subtle 2px blur at 5% opacity for standard cards. For dropdowns and modals, use a 12px blur to separate them from the canvas.

---

## 3. Screen Specifications (11 Core Modules)

Generate the following 11 distinct screens, adhering strictly to the design system outlined above.

### Screen 1: Public Landing Portal (Marketing)
**Purpose:** High-converting, enterprise-grade public interface to attract franchise owners and consumers.
*   **Top Navigation:** Clean top bar with Logo, Home, Pricing, About Us, Contact, and a prominent "Login / Get Started" primary button.
*   **Hero Section:** A sleek, animated/illustration placeholder of a water refilling dashboard. Large headline (e.g., "Streamline Your Water Station Operations").
*   **Pricing Section:** Three distinct, 16px-radius pricing tier cards ("Basic", "Pro", "Enterprise"). Highlight the "Pro" tier with a primary blue border.
*   **Contact/Location:** An interactive map component (radius 16px) showing branch locations alongside a lead-generation form (inputs: Name, Email, Inquiry).

### Screen 2: Command Center Dashboard
**Purpose:** The central hub offering real-time visibility into daily operations.
*   **Global Filters:** A sticky top bar or top-right card containing date shortcuts (Today, Yesterday, Last 7 Days) and a Branch dropdown.
*   **Metric Cards (Top Row):** 4 clean cards showing: Active Riders, Containers Dispatched, Expected Receivables (₱), and Low Stock Alerts.
*   **Charts & Visuals:** A large line chart ("Dispatch Rate / Hourly") with a comparative overlay (dotted line) for yesterday's data.
*   **Order Queue List:** A scrollable card showing the live queue (Requester, Qty, Status Badge).
*   **AI Insight Trigger:** A floating action button (FAB) at the bottom right with a spark/magic icon, opening a side-panel chat interface for AI analytics.

### Screen 3: Dispatch & Logistics Management
**Purpose:** Robust engine for handling rider assignments and container lifecycles.
*   **Top Summary:** Metric cards for Total Deliveries, Pending Count, Dispatched, Total Receivables, Total Sold.
*   **Kanban / Drag-and-Drop View:** 
    *   *Column 1 (Pending Requests):* Auto-generated queue cards (time, address, quantity).
    *   *Column 2 & 3 (Riders - e.g., "Rider John", "Rider Mark"):* Areas where dispatcher can drag pending requests.
*   **Bulk Dispatch Modal:** An elevated overlay (12px blur shadow) for assigning 50+ containers to a truck, with a status tracker (Pending -> Dispatched -> Completed) and input fields for final reconciliation (remitted cash, borrowed containers).

### Screen 4: Point of Sale (POS) & Accounts Receivable
**Purpose:** Rapid order entry for walk-in customers and debt management.
*   **Left Pane (Products):** High-density grid of tappable product cards (5-Gallon, Alkaline 1L, etc.) with image placeholder, name, and price.
*   **Right Pane (Checkout):** 
    *   List of active cart items with +/- steppers.
    *   A "Discount Engine" dropdown (Apply % or fixed amount).
    *   "Checkout as Credit" secondary button and a massive "Complete Sale" primary button.
*   **Repayment Module (Tab/Overlay):** A list of creditors (Name, Unpaid Amount). Includes checkboxes for multi-select to settle multiple debts at once.
*   **Receipt Modal:** A clean, printable-looking PDF preview modal with a "Download/Share Image" button.

### Screen 5: Pricing & Product Settings
**Purpose:** Managing products, historical pricing, and intelligent price adjustments.
*   **Product List (Table):** Image, SKU, Name, Category, Price, "Discount Eligible" toggle switch.
*   **Pricing Intelligence:** A visual trend chart showing the historical price curve of a selected item (e.g., 5-Gallon Refill over 3 years).
*   **Safe Price Adjustment:** A prominent card/form to change a price. Include an informational alert (yellow/blue tinted background) explaining that the new price applies *only* to future sales.

### Screen 6: Consumer Database
**Purpose:** Managing customer profiles and geospatial data.
*   **Customer Table:** Name, Phone, Address, Lifetime Value (₱), Account Status.
*   **Profile Detail Panel (Slide-out from right):** 
    *   Customer photo/avatar.
    *   Geospatial Data: A mini-map showing their exact GPS coordinate and "Distance from Branch (e.g., 2.4 km)".
    *   Recent Purchase History list.

### Screen 7: Branch & Organization Management
**Purpose:** Setup and localization for different franchise locations.
*   **Branch List:** Cards representing different branches (e.g., "Manila Main", "Quezon City Hub") showing employee count and active status.
*   **Branch Edit Form:** Inputs for Name, Contact, Email, Facebook Link.
*   **Location/GPS Config:** A section with a map and a button labeled "Use My Current Device Location" alongside manual coordinate inputs.

### Screen 8: Employee & Access Management
**Purpose:** RBAC and employee lifecycle tracking.
*   **Employee Table:** Photo, Name, Department, Role (Admin, Manager, Driver), Status (Active, Terminated).
*   **Permissions Matrix (Card):** A grid showing Roles on the X-axis and Permissions (Read, Edit, Delete, Create) on the Y-axis with checkmarks.
*   **Security Actions:** On an employee's detail view, prominent buttons for "Reset PIN", "Lock Account", and a red destructive button for "Terminate Employee".

### Screen 9: Inventory Control
**Purpose:** Dense data view for tracking raw materials and QA.
*   **Inventory Table (Compact Mode):** 8px cell padding. Columns: SKU, Item, Qty, Reorder Point, Expiry Date (if applicable), Status (Green "Full", Red "Low").
*   **Quality Assurance Highlight:** Any item near its expiry date (e.g., Alkaline filters) should have a yellow warning icon next to it.
*   **Adjust Stock Form:** Inputs for Qty change, a Reason dropdown (Damaged, Audit, Restock), and submit buttons.

### Screen 10: Reports & Analytics
**Purpose:** Deep-dive data exploration and immutable audit logs.
*   **Tabbed Navigation:** Branch Performance | Sales | Consumers | Audit Log.
*   **Sales Report Tab:** Pie charts for "Payment Method Distribution" and "Revenue vs. Discounts".
*   **Consumer Analysis Tab:** A "Leaderboard" of highest-value customers and a bar chart showing debt concentration.
*   **Audit/Action Log Tab:** A very dense, secure-looking table: Timestamp, Actor (User), Action (e.g., "Updated Price", "Deleted Record"), Status.

### Screen 11: System Settings
**Purpose:** User preferences, billing, and data sovereignty.
*   **Preferences Section:** Toggle for dark/light mode (optional), lock-screen duration slider (e.g., "Lock after 5 mins idle").
*   **Billing Section:** A card showing the current plan ("Pro Tier"), Next Billing Date, and a button to "Update Payment Method".
*   **Data Sovereignty (Danger Zone):** At the very bottom, a bordered red box containing options for "Export All Data" and "Request Complete Data Deletion".

---

## 4. Component Checklist for the Designer
Please ensure the following specific components are clearly represented in the designs:

*   [ ] **Primary Button:** Solid `#005e97`, white text, 8px radius. Minimum 44px height.
*   [ ] **Secondary Button:** Outlined `#005e97`, transparent background, 8px radius.
*   [ ] **Destructive Button:** Solid or outlined `#ba1a1a`.
*   [ ] **Text Inputs:** 44px height, label positioned *above* the input, subtle blue glow on focus.
*   [ ] **Status Badges:** Fully rounded pills. High contrast text against a tinted background (e.g., dark red text on light red background for errors).
*   [ ] **Data Tables:** Clear column alignment (numbers right-aligned, text left-aligned), sticky headers, zebra striping.
*   [ ] **Cards:** 16px radius, 1px border, extremely subtle shadow.

**Export Requirements:**
Provide the final screens as high-resolution PNGs/JPEGs and ensure all components are organized neatly in the Figma layer tree.
