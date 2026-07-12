# Branch Admin User Stories: Water Refilling Station Management System

### Epic 1: Daily Branch Command & Monitoring
**User Story 1.1: Localized Dashboard Overview**
> **As a Branch Admin**, I want to view a real-time dashboard restricted to my specific branch's data, complete with date shortcuts and custom ranges, **so that** I can track my daily metrics, order queues, and receivables without being distracted by network-wide data.
*   **Acceptance Criteria:**
    *   The system must enforce strict multi-tenant data isolation; the Branch Admin cannot access or view data from other branches.
    *   The interface must remain highly responsive and cache recent data to handle intermittent connectivity gracefully.
    *   Summary cards (total deliveries, pending count, dispatched, receivables, containers sold) must update dynamically based on the selected date filter.

**User Story 1.2: Real-Time Ledger Alerts**
> **As a Branch Admin**, I want to see immediate previews of my branch's Credit List, Borrowed Containers, and active notification alerts on the dashboard, **so that** I can quickly identify outstanding customer debts and unreturned assets.
*   **Acceptance Criteria:**
    *   Clicking on a ledger preview navigates directly to the full detailed list.
    *   Borrowed container counts must automatically adjust when drivers reconcile their bulk dispatches.

### Epic 2: Dispatch & Logistics Control
**User Story 2.1: Granular Order Queue Management**
> **As a Branch Admin**, I want to view an auto-generated list of consumer requests sorted by time, and filter them by quantity and status (Pending, Rejected, Success), **so that** I can prioritize urgent or large volume deliveries.
*   **Acceptance Criteria:**
    *   Must feature a drag-and-drop UI to effortlessly assign pending queue requests to available delivery riders.
    *   Queue numbers must be generated sequentially per day.

**User Story 2.2: Bulk Truck Dispatch & Reconciliation**
> **As a Branch Admin**, I want to assign a bulk load of containers (e.g., 100 units) to a delivery rider and reconcile the exact metrics upon their return, **so that** inventory and cash remittances perfectly match the physical dispatch.
*   **Acceptance Criteria:**
    *   The dispatch status must follow a strict flow: Pending (Loading) -> Dispatched (Departed) -> Completed.
    *   Before marking "Completed", the UI must mandate input fields for: Containers Sold, Credited Amount, Borrowed Containers, and Remitted Cash.
    *   The system must automatically calculate expected remittance versus actual remitted cash to flag discrepancies.

### Epic 3: Point of Sale (POS) & Debt Management
**User Story 3.1: High-Speed Counter Transactions**
> **As a Branch Admin**, I want to quickly search for water products, adjust quantities, apply custom discounts, and process cash or credit sales, **so that** I can serve walk-in customers rapidly without causing bottlenecks.
*   **Acceptance Criteria:**
    *   The POS must utilize an optimized frontend state to instantly calculate subtotals and discounts.
    *   Discounts can be applied as either a flat amount or a percentage based on user preference.
    *   Sales marked as "Add as Credit" must instantly populate the branch's Credit List ledger.

**User Story 3.2: Bulk Debt Repayment**
> **As a Branch Admin**, I want to search for specific creditors and use a multi-select feature to pay off several outstanding credit lines in a single transaction, **so that** I can easily reconcile accounts when a customer settles their weekly or monthly bill.
*   **Acceptance Criteria:**
    *   The creditor list must cleanly separate "Paid" and "Unpaid" balances.
    *   Multi-select checkout must generate a single unified receipt for all selected credit lines.

**User Story 3.3: Digital Receipt Generation**
> **As a Branch Admin**, I want to generate a digital PDF receipt modal at the end of a transaction that can be saved as an image, **so that** I can easily send proof of payment to customers via messaging apps.
*   **Acceptance Criteria:**
    *   The receipt modal must contain the branch's localized logo and contact info.
    *   The save-to-image function must capture the modal perfectly without UI clutter.

### Epic 4: Local Inventory Control
**User Story 4.1: Stock Management & Expiry Tracking**
> **As a Branch Admin**, I want to update physical quantities of products and consumable materials (with optional expiry dates), **so that** my digital inventory accurately reflects the stock room.
*   **Acceptance Criteria:**
    *   Adding or updating quantities logs an event in the audit trail.
    *   Items designated for soft deletion are removed from active POS views but retained in historical sales data.

**User Story 4.2: Automated Restock Warnings**
> **As a Branch Admin**, I want to see a severity-based inventory warning panel on my dashboard, **so that** I am alerted when critical items (like seals or filters) fall below their restock threshold.
*   **Acceptance Criteria:**
    *   Alerts are color-coded (e.g., Yellow, Red) based on how close the item is to zero.

### Epic 5: Local Consumer & Staff Directory
**User Story 5.1: Consumer Geolocation Profiling**
> **As a Branch Admin**, I want to maintain a list of regular consumers, including optional physical locations, GPS coordinates, and distances from the branch, **so that** dispatch routing can be optimized for my delivery riders.
*   **Acceptance Criteria:**
    *   Consumer profiles can be quickly searched or added during a POS transaction or when manually entering a dispatch request.

**User Story 5.2: Branch Staff Management**
> **As a Branch Admin**, I want to add, edit, or disable local employee accounts (drivers, cleaners) and reset their PINs, **so that** I can manage my shift roster securely.
*   **Acceptance Criteria:**
    *   The Branch Admin can only assign roles lower than or equal to their own permissions (e.g., cannot grant Admin access).
    *   Disabled accounts immediately block the employee from logging into the POS or dispatch modules.

### Epic 6: Localized Reporting
**User Story 6.1: Branch Analytics & Auditing**
> **As a Branch Admin**, I want to access tabbed reports for sales, consumer analysis, and action logs specifically for my branch, **so that** I can audit daily performance and staff actions.
*   **Acceptance Criteria:**
    *   Date filters set in the main dashboard must carry over to all report tabs to prevent resetting.
    *   The Action/Audit log must accurately timestamp all manual edits made by branch staff (e.g., inventory updates, voided sales).
    *   The AI Insight tab must analyze only the data generated within this specific branch.
