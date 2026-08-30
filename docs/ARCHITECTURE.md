# Hydr8 — Architecture README

This document describes the high-level architecture, design philosophy, and conventions used by **Hydr8**, a Water Refilling Station Operations & AI Management System.

For day-to-day contributor rules, see [`AGENTS.md`](../AGENTS.md). For product planning, see [`PROJECT_PLAN.md`](PROJECT_PLAN.md) and [`DESIGN.md`](DESIGN.md).

---

## 1. What Hydr8 Is

Hydr8 is a web-based operations management platform for water refilling stations. It covers branch management, employees, customers, products, sales, remittance, credit, analytics, and an in-browser AI assistant that runs locally.

It is built as a **server-rendered, hypermedia-driven Django application**. The server is the source of truth; the frontend is HTML over the wire, progressively enhanced with HTMX and Alpine.js.

---

## 2. Technology Stack

| Layer | Technology |
|-------|------------|
| Language | Python 3.12+ |
| Backend framework | Django 6 |
| Package manager | `uv` (pyproject.toml) |
| Database | PostgreSQL (psycopg2-binary) |
| Cache | Redis in production; LocMemCache in dev/test |
| Admin UI | django-unfold |
| Audit logging | django-auditlog |
| Rate limiting | django-ratelimit |
| Static files | WhiteNoise |
| Frontend | HTMX + Alpine.js + Tailwind CSS (CDN) |
| Templating | Django Templates |
| Monitoring | Sentry (production) |
| Linting / formatting | Ruff |
| AI engine | Gemma 2B via `@mlc-ai/web-llm` (WebGPU, browser-local) |

---

## 3. Design Philosophy

### Hypermedia-first

The server renders everything. HTMX handles dynamic updates without a separate JavaScript SPA. Alpine.js is used only for ephemeral UI state (theme toggles, modals, drawers, offline queue). The server is always the source of truth.

### Domain-Driven Django Apps

Each bounded domain lives under `server/apps/<domain>/`. Apps own their models, services, selectors, views, templates, and tests.

### Explicit, maintainable code

Business logic lives in services. Read logic lives in selectors. Views only orchestrate. Templates only present. Models only define schema.

---

## 4. Project Structure

```
hydr8/
├── docs/                         # Product & architecture documentation
├── server/                       # Django monolith
│   ├── apps/                     # Bounded domains
│   │   ├── analytics/
│   │   ├── audit/
│   │   ├── core/
│   │   ├── customers/
│   │   ├── employees/
│   │   ├── products/
│   │   ├── remittance/
│   │   ├── settings/
│   │   ├── tests/
│   │   └── users/
│   ├── config/                   # Django settings & URLs
│   │   ├── settings/             # base, local, test, production
│   │   └── urls.py
│   ├── docs/
│   │   └── plans/                # Agent-readable implementation plans
│   ├── requirements/             # Environment-specific requirement files
│   ├── static/                   # Static assets
│   ├── templates/                # Shared templates & reusable components
│   └── manage.py
└── AGENTS.md                     # Mandatory agent/contributor conventions
```

---

## 5. Standard App Layout

Every Django app follows this exact structure:

```
apps/<domain>/
├── __init__.py
├── apps.py
├── models.py          # Pure data schema — no business logic
├── services.py        # Write/mutation logic (command side)
├── selectors.py       # Read/query logic (query side)
├── admin.py           # django-unfold ModelAdmin registrations
├── urls.py            # Domain-specific URL routing
├── views.py           # View orchestration, rendering, and HTMX partials
├── tests/
│   ├── test_models.py
│   ├── test_services.py
│   ├── test_selectors.py
│   └── test_views.py
├── migrations/
└── templates/<domain>/
    ├── *.html                 # Full page templates
    └── partials/*.html        # HTMX fragment responses
```

There is no `api/` folder. Hydr8 is server-rendered. DRF is installed only for edge cases requiring JSON, such as the AI tool-calling endpoints.

---

## 6. Strict Layering Rule

```
HTTP Request
  → View
    → Service (write) OR Selector (read)
      → Model
        → PostgreSQL
  → Django Template
    → HTML + HTMX + Alpine.js
```

| Layer | Responsibility |
|-------|---------------|
| **Views** | Permission checks, call services/selectors, render templates or HTMX partials. No ORM calls. No business logic. |
| **Services** | Create, update, delete, state transitions, and financial calculations. Return domain objects or raise typed exceptions. |
| **Selectors** | Read queries. Return querysets or typed values. Use `select_related`/`prefetch_related` to avoid N+1. |
| **Models** | Schema, `Meta` constraints/indexes, and `__str__`. No business logic beyond simple `@property` helpers. |
| **Templates** | Presentation only. No business logic, no ORM calls. HTMX attributes drive interactivity; Alpine.js for ephemeral state only. |

---

## 7. Frontend Architecture

### Full Page View

```python
return render(request, '<domain>/page.html', context)
```

### HTMX Partial

```python
return render(request, '<domain>/partials/fragment.html', context)
```

HTMX fragments are returned for swaps. Shared reusable components live in `server/templates/components/`. The application uses Tailwind CSS for styling, loaded via CDN.

---

## 8. Database Conventions

- PostgreSQL is the only supported database.
- Money is stored as `DecimalField(max_digits=12, decimal_places=2)`; never `FloatField`.
- Quantities use `SmallIntegerField` where appropriate.
- Statuses use `CharField` with `models.TextChoices`.
- Business entities include soft-delete timestamps:

  ```python
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  deleted_at = models.DateTimeField(null=True, blank=True)
  ```

- Soft-delete-aware uniqueness uses `models.UniqueConstraint(condition=Q(deleted_at__isnull=True))`.
- Cross-app foreign keys use string notation to avoid circular imports.
- Financial records use `on_delete=models.PROTECT` and are immutable once finalized.

---

## 9. Financial Data Integrity

Hydr8 handles sales, commissions, credits, repayments, and tithes. These rules are non-negotiable:

1. **Snapshot pattern** — Financial records snapshot mutable values (`unit_price_snapshot`, `commission_rate_snapshot`) at creation time.
2. **Atomic updates** — Debt balances update with `F()` expressions to prevent race conditions.
3. **PROTECT on financial FKs** — Prevent accidental cascading deletes.
4. **Immutable after finalize** — Once a `Remittance` is `FINALIZED`, child records cannot be added, modified, or deleted.
5. **PIN-protected operations** — Finalizing a remittance requires a verified PIN.

---

## 10. Authorization

The `Role` model in `apps.users` is the single source of truth for authorization. Do not use `user.is_staff` or `user.is_superuser` for permission checks.

Use the canonical helpers in `apps.users.permissions`:

```python
from apps.users.permissions import is_back_office, is_admin

if not is_back_office(request.user):
    return HttpResponse("Forbidden", status=403)
```

| Helper | True for |
|--------|---------|
| `is_back_office` | Admin, Staff, or superuser |
| `is_admin` | Admin or superuser |

Canonical roles are **Admin**, **Staff**, and **Driver**.

---

## 11. Rate Limiting & Caching

Every view accepting user input or expensive queries MUST be decorated with `@ratelimit` from `django-ratelimit`. Baselines are documented in [`AGENTS.md`](../AGENTS.md).

| Environment | Cache backend |
|-------------|---------------|
| local/dev | LocMemCache |
| test | LocMemCache |
| production | Redis |

---

## 12. AI Engine

The AI assistant runs entirely in the browser using WebGPU and `@mlc-ai/web-llm` with a Gemma 2B model. No model calls go to the server; privacy is preserved and no API keys are required for inference.

---

## 13. Local Development & Launch

### Prerequisites

- Python 3.12+
- `uv` package manager
- PostgreSQL 14+ (a running server and an empty database for Hydr8)
- (Optional) Redis — only needed for production caching; local dev uses `LocMemCache`

### 1. Configure the environment

From the `server/` directory, create a `.env` file with at least these values:

```bash
# server/.env
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgres://<user>:<password>@<host>:<port>/<dbname>
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1
```

`DATABASE_URL` must point to a PostgreSQL database. The local settings default `DEBUG=True` and allow `localhost`, `127.0.0.1`, and `0.0.0.0`.

### 2. Install dependencies

```bash
cd server
uv sync
```

### 3. Run migrations and collect static files

```bash
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
```

### 4. Create an admin user

```bash
uv run python manage.py createsuperuser
```

### 5. Launch the development server

```bash
uv run python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`.

### Run the test suite

```bash
uv run python manage.py test
```

Or, if a dedicated `pytest`/`coverage` workflow is configured:

```bash
uv run coverage run manage.py test
uv run coverage report
```

### Production launch

For deployment, set `DJANGO_SETTINGS_MODULE=config.settings.production`, provide a `DATABASE_URL` and `SECRET_KEY`, and run:

```bash
python manage.py collectstatic --noinput
python manage.py migrate --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

A ready-made `Dockerfile` and `entrypoint.sh` automate this. See `server/Dockerfile` and `server/config/settings/production.py`.

---

## 14. Related Documentation

- [`AGENTS.md`](../AGENTS.md) — Contributor conventions
- [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — Product roadmap & scope
- [`DESIGN.md`](DESIGN.md) — UI/UX design system
- [`Water_Refilling_Station_Project_Description.md`](Water_Refilling_Station_Project_Description.md) — Problem domain background
