# Admin User Stories: Water Refilling Station Management System

### Epic 1: High-Level Operational Oversight (Dashboard & Reports)
**User Story 1.1: Global Command Dashboard**
> **As an Admin**, I want to view a centralized dashboard with global filters for specific branches and custom date shortcuts (today, last 7 days, this month), **so that** I can track macro-level performance metrics, daily remittance totals, and receivables across the entire operation.
*   **Acceptance Criteria:**
    *   Filters applied on the dashboard must persist when navigating to the Reports section to prevent redundant data entry.
    *   The dashboard reflects a **single daily remittance model**: staff enter the afternoon's total dispatched quantities once per day (not per-dispatch), so charts are daily-granularity (sales trend, rider leaderboard) — there is no hourly dispatch tracking.
    *   The dashboard must display aggregated ledger previews (credit lists, borrowed containers) that update in real-time.

**User Story 1.2: AI-Powered Analytics**
> **As an Admin**, I want to trigger an AI insight chat assistant from the dashboard and reports pages, **so that** I can rapidly query operational bottlenecks, interpret complex sales data, and generate instant executive summaries.
*   **Acceptance Criteria:**
    *   The AI chat must launch instantly via a floating action button.
    *   The backend (Django) must securely pass the currently filtered dashboard context to the AI module to ensure relevant insights.

### Epic 2: Multi-Tenant & Access Governance (Branches & Employees)
**User Story 2.1: Branch Fleet Management**
> **As an Admin**, I want to add, edit, and configure multiple branch locations, including setting their exact GPS coordinates and uploading custom branding, **so that** I can manage a multi-tenant franchise network from a single system.
*   **Acceptance Criteria:**
    *   GPS coordinates can be captured automatically using the Admin's current device location.
    *   Each branch must operate in data isolation, ensuring branch managers only see their respective data.

**User Story 2.2: Granular Role-Based Access Control (RBAC)**
> **As an Admin**, I want to create and configure custom roles using a strict permissions matrix (read, edit, delete, create), **so that** I can enforce zero-trust security and limit access based on the employee's job function.
*   **Acceptance Criteria:**
    *   The permissions payload must be securely generated and validated by the backend, not just hidden in the UI.
    *   Default roles (Admin, Branch Manager, Delivery Driver, Cleaner) must be pre-configured upon system deployment.

**User Story 2.3: Employee Lifecycle Management**
> **As an Admin**, I want to manage employee profiles, including the ability to reset credentials, lock accounts temporarily, or execute formal terminations, **so that** I maintain complete control over who can access the system.
*   **Acceptance Criteria:**
    *   Terminating an employee triggers a soft delete and immediately revokes all active session tokens.
    *   Account locks must take effect instantly across all connected terminals.

### Epic 3: Financial Integrity & Pricing (Pricing Settings & Audit)
**User Story 3.1: Safe Pricing Adjustments**
> **As an Admin**, I want to update product pricing and view historical price trends, with the guarantee that new prices only apply to future transactions, **so that** active dispatch ledgers and current POS carts are not financially corrupted.
*   **Acceptance Criteria:**
    *   The database (PostgreSQL) must handle price versioning or apply adjusted rates strictly to timestamps post-update.
    *   A warning modal must appear before saving, noting that changes only affect the next dispatch/sale.

**User Story 3.2: Immutable Audit Logging**
> **As an Admin**, I want to view a detailed Action/Audit Log that records the timestamp, action, actor, and status of critical system events, **so that** I can trace operational errors, deleted transactions, or permission changes back to the source.
*   **Acceptance Criteria:**
    *   Audit logs cannot be edited or hard-deleted by any user, including the Admin.
    *   The log must clearly identify the specific branch and user responsible for the action.

### Epic 4: Supply Chain Control (Inventory)
**User Story 4.1: Network-Wide Inventory Warnings**
> **As an Admin**, I want to receive color-coded severity warnings for low-stock items across all branches, **so that** I can proactively authorize restocking for critical supplies (e.g., seals, filters) before a branch is forced to halt operations.
*   **Acceptance Criteria:**
    *   Warnings are triggered dynamically based on custom "restock quantity thresholds" defined per product.
    *   The dashboard alert panel must prioritize warnings based on severity level (e.g., Red for critical shortage, Yellow for approaching threshold).

### Epic 5: System Configuration (Settings & Public Portal)
**User Story 5.1: Subscription & Data Sovereignty**
> **As an Admin**, I want to view my active SaaS subscription plan, upcoming due dates, and have the option to safely unsubscribe and request data deletion, **so that** I have full autonomy over my billing and proprietary operational data.
*   **Acceptance Criteria:**
    *   The billing dashboard must clearly display the current tier.
    *   Data deletion requests must initiate a secure, compliant wipe of the tenant's relational data.

**User Story 5.2: Terminal Security Configuration**
> **As an Admin**, I want to configure the global lock-screen duration for idle devices, **so that** unattended POS terminals or dispatch tablets do not expose sensitive financial data.
*   **Acceptance Criteria:**
    *   The timer must accurately track inactivity and force a PIN/password prompt upon expiration.
