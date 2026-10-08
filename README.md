# Hydr8 — Water Refilling Station Operations & Management Platform

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0-green.svg)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)](https://www.postgresql.org/)
[![HTMX](https://img.shields.io/badge/HTMX-1.9.10-orange.svg)](https://htmx.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-CDN-38B2AC.svg)](https://tailwindcss.com/)

**Hydr8** is an operations and financial management platform designed specifically for water refilling stations. It delivers a hypermedia-driven, server-rendered interface that unifies point-of-sale activities, driver deliveries, container tracking, credit lines, multi-staff payroll, daily expense reconciliation, and cryptographic PIN-verified remittance auditing.

---

## Architecture & Core Philosophy

### 1. Server-Rendered Hypermedia (HATEOAS)
Hydr8 avoids bloated single-page application (SPA) architectures. It uses **Django 6**, **HTMX**, and **Alpine.js**:
- **Server as Source of Truth:** HTML fragments are generated on the server and swapped into the DOM via HTMX.
- **Minimal Client-Side State:** Alpine.js is restricted to ephemeral UI states (dialogs, drawers, dropdowns, offline synchronization queues). Business rules and financial math reside exclusively on the server.
- **Responsive Presentation:** Styled with Tailwind CSS via CDN using Material Design 3 tokens.

### 2. Domain-Driven Layering
The codebase is structured into isolated domain applications inside `server/apps/`:
```
HTTP Request
  └── View (Authentication, rate-limiting, and permission orchestration)
        ├── Selector (Optimized ORM queries: select_related, prefetch_related, annotate)
        └── Service (Atomic state mutations, financial transactions, validation)
              └── Model (Schema definitions, constraints, indexes)
                    └── PostgreSQL
```
- **Views:** Orchestrate requests, enforce guards, and return templates or HTMX partials. No business logic or direct queries.
- **Services:** Execute state mutations, handle financial transactions atomically (`@transaction.atomic`), and enforce domain invariants.
- **Selectors:** Dedicated query paths. Returns typed data or evaluated QuerySets without N+1 bottlenecks.
- **Models:** Schema definitions, soft-delete indexes, and metadata.

### 3. Financial Integrity & Invariants
- **Immutable Historical Snapshots:** Remittance records snapshot mutable pricing and commission rates (`unit_price_snapshot`, `commission_rate_snapshot`) at creation time.
- **Atomic Balance Updates:** Debt and container balances are modified using PostgreSQL `F()` expressions (`debt_balance = F('debt_balance') - payment`) to eliminate race conditions.
- **Immutability Enforcement:** Finalized remittance records are locked at the database level via PostgreSQL triggers (`status = 'FINALIZED'`); child rows cannot be added, mutated, or deleted once finalized.
- **PIN Verification:** Remittance finalization requires administrative authorization via an Argon2/PBKDF2-hashed PIN with progressive lockout (5 failed attempts locks the IP/user for 15 minutes).
- **Exact Math:** All monetary calculations use Python `Decimal` and PostgreSQL `DecimalField(max_digits=12, decimal_places=2)`. Floating-point values are strictly forbidden for financial logic.

### 4. Privacy & Regulatory Compliance (RA 10173)
Hydr8 is designed in strict compliance with the **Philippine Data Privacy Act of 2012 (RA 10173)** and National Privacy Commission (NPC) mandates:
- **No PII/SPI in Server Logs:** Logs only record anonymized actor IDs and entity IDs (`[user_id] Action. entity_id=X`). Names, addresses, contact details, and financial balances are never written to application logs.
- **Purpose Limitation & Soft Deletes:** Customer data is retained strictly for operational station tracking with soft-delete lifecycles (`deleted_at`) preserving financial auditability.
- **Audit Trails:** Model modifications are tracked via `django-auditlog` tagged with request-scoped correlation IDs.

---

## Repository Structure

```
hydr8/
├── AGENTS.md                  # Contributor and agent governance conventions
├── docs/                      # Architectural specifications & requirements
│   ├── ARCHITECTURE.md        # Comprehensive system architecture guide
│   ├── DESIGN.md              # Semantic design system & UI token definitions
│   ├── PROJECT_PLAN.md        # Feature roadmap & scope boundaries
│   └── Admin_User_Stories.md  # Domain operational user stories
├── server/                    # Django monolith
│   ├── apps/                  # Domain applications
│   │   ├── analytics/         # Station performance metrics & daily snapshots
│   │   ├── audit/             # Audit log viewing and filtering UI
│   │   ├── core/              # Multi-tenant middleware, system configuration, products
│   │   ├── customers/         # Customer profiles, credit ledger, container tracking
│   │   ├── employees/         # Employee profiles, daily rates, attendance
│   │   ├── products/          # Station product catalog & offering tiers
│   │   ├── remittance/        # End-of-day reconciliation, commissions, audits
│   │   ├── settings/          # Tenant company settings & lock-screen context
│   │   └── users/             # User accounts, canonical roles, PIN auth
│   ├── config/                # Django project settings & URL routing
│   │   └── settings/          # base.py, local.py, test.py, production.py
│   ├── static/                # Static assets (CSS, JS icons, WebGPU weights)
│   ├── templates/             # Global templates and reusable components
│   ├── Dockerfile             # Multi-stage production container definition
│   ├── entrypoint.sh          # Container initialization and migration runner
│   ├── manage.py              # Django management script
│   └── pyproject.toml         # Python dependencies managed by uv
└── README.md                  # Repository documentation (this file)
```

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Runtime & Language** | Python 3.12+ | Core programming runtime |
| **Package Management** | `uv` | Deterministic, high-speed dependency resolution |
| **Framework** | Django 6.0 | Web application framework & ORM |
| **Database** | PostgreSQL 14+ | Primary ACID relational database |
| **Cache & Lockout** | Redis (production) / LocMem (dev) | Rate limiting, session cache, failed-login lockout |
| **Frontend Hypermedia**| HTMX 1.9.10 | Server-driven DOM swaps and partial updates |
| **Client UI Logic** | Alpine.js 3.x | Lightweight UI state (modals, dropdowns, tabs) |
| **CSS Framework** | Tailwind CSS (CDN) | Semantic responsive design |
| **Audit Logging** | `django-auditlog` | Entity-level change tracking |
| **Rate Limiting** | `django-ratelimit` | IP and user rate limiting across endpoints |
| **WSGI Server** | Gunicorn | Production application server |
| **Static Assets** | WhiteNoise | Static file compression and caching |
| **Code Hygiene** | Ruff | Linting and code formatting |

---

## Local Development Setup

### 1. Prerequisites
- Python 3.12 or later installed.
- [uv](https://docs.astral.sh/uv/) installed:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- PostgreSQL 14+ running locally with an initialized database:
  ```sql
  CREATE DATABASE hydr8;
  ```

### 2. Clone and Configure Environment
Clone the repository and prepare the configuration:
```bash
git clone https://github.com/marcusAlmo/hydr8.git
cd hydr8/server
```

Create a `.env` file in `server/` with your local PostgreSQL credentials:
```env
# server/.env
DEBUG=True
SECRET_KEY=local-dev-insecure-secret-key-at-least-50-characters-long
DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/hydr8
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

### 3. Install Dependencies
Synchronize dependencies with `uv`:
```bash
uv sync
```

### 4. Apply Migrations & Seed Default Data
Run database migrations:
```bash
uv run python manage.py migrate
```

Create a superuser account for administration:
```bash
uv run python manage.py createsuperuser
```

### 5. Start the Development Server
Launch the development server:
```bash
uv run python manage.py runserver
```

The application will be accessible at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

---

## Testing & Quality Assurance

The project enforces comprehensive test coverage across models, services, selectors, and views:

```bash
# Run the entire test suite
uv run python manage.py test

# Run tests for specific domain apps
uv run python manage.py test apps.remittance apps.customers apps.users

# Run linting and code formatting checks
uv run ruff check .
uv run ruff format --check .
```

---

## Authorization & Security

Hydr8 uses the `Role` model (`apps.users.models.Role`) as the **single source of truth** for user permissions:
- **Admin:** Full station operations, company settings, employee role management, and remittance finalization.
- **Staff:** Counter sales, customer ledger updates, container tracking, and draft remittance preparation.
- **Driver:** Delivery route fulfillment and bottle returns. No back-office administrative access.

> **Rule:** Never check `user.is_staff` for authorization. Always use the canonical helpers from `apps.users.permissions`:
> ```python
> from apps.users.permissions import is_admin, is_back_office
> ```

---

## Rate Limiting Standards

All mutation endpoints and sensitive queries are rate-limited via `django-ratelimit`:

| Surface | Limit | Key | Behavior |
|---|---|---|---|
| Unauthenticated Auth | `10/m` | `ip` | Blocks on exceeded rate; 5-failure account lockout for 60s |
| PIN Verification | `5/15m` | `user_or_ip`| Enforces PIN lockout after 5 consecutive failures |
| Write / Mutations (HTMX) | `30/m` | `user` | Returns HTTP 403 / HTMX error toast |
| Read / Partial Lists (HTMX) | `120/m` | `user` | Throttles excessive hypermedia pollers |
| Search / Autocomplete | `60/m` | `user` | Protects database indexing against rapid keystroke triggers |

---

## Production Deployment

Hydr8 is production-ready via Docker:
```bash
cd server
docker build -t hydr8:latest .
docker run -p 8000:8000 --env-file .env.production hydr8:latest
```

The container's `entrypoint.sh` automatically collects static assets via WhiteNoise, applies PostgreSQL migrations, and launches Gunicorn with worker pooling.

For full architectural details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For contributor policies, review [AGENTS.md](AGENTS.md).
