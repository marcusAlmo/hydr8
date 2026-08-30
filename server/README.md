# Hydr8 Server

This is the Django backend for **Hydr8**, a water refilling station management platform. It serves the HTMX-driven admin and operations UI, handles multi-tenant data, and coordinates sales, customers, remittances, analytics, and audit logging.

## Tech Stack

- **Python** 3.12+
- **Django** (pinned in `pyproject.toml`)
- **PostgreSQL** — `DATABASE_URL` is required; no SQLite fallback
- **HTMX** via `django-htmx`
- **Whitenoise** for static files
- **Gunicorn** in production/Docker
- **Redis** in production for cache, rate limiting, and login lockout
- **django-ratelimit**, **django-unfold**, **django-auditlog**

## Application Architecture

The project is split into a single `apps/` package of domain-driven Django apps and a `config/` package for settings, URLs, and WSGI.

### Domain apps

| App | Purpose |
|-----|---------|
| `users` | Custom `User`, `Role`, login/PIN, failed-login lockout, permission helpers |
| `core` | Product catalog, `SystemConfig`, tenant middleware, correlation ID, screen lock, shared utilities |
| `customers` | Customer accounts, credit lines, borrowed containers, credit payments |
| `remittance` | Driver remittance workflows |
| `products` | Product and offering management |
| `employees` | Employee records and role assignment |
| `analytics` | Dashboards, daily snapshots, reporting |
| `audit` | Audit log UI and search over `django-auditlog` records |
| `settings` | Company settings and lock-screen context processors |

### Key patterns

- **Services / Selectors**: business logic lives in `services.py`; read paths in `selectors.py`.
- **HTMX partials**: templates are organized under `apps/<app>/templates/<app>/partials/`.
- **Multi-tenancy**: `apps.core.middleware.TenantMiddleware` scopes requests by company.
- **Authorization**: `Role` is the single source of truth. Use `apps.users.permissions.is_back_office` / `is_admin` instead of `is_staff`. Superusers remain a platform escape hatch.
- **Rate limiting**: all user-input views are decorated with `django_ratelimit.decorators.ratelimit`. Login also uses a 5-failure lockout in `apps.users.services`.
- **Audit**: `django-auditlog` records model changes, tagged with a correlation ID from `apps.core.middleware.CorrelationIdMiddleware`.
- **Caching**: `LocMemCache` in `local.py` / `test.py`; `Redis` in `production.py`.

For a deeper architecture write-up, see `../docs/ARCHITECTURE.md`. For authoring conventions, see `../AGENTS.md`.

## Project Layout

```
server/
├── apps/                 # Domain Django apps
├── config/               # Settings, URLs, WSGI
├── requirements/         # base, local, production
├── templates/            # Shared templates
├── static/               # Static assets
├── manage.py
├── pyproject.toml
├── Dockerfile
└── entrypoint.sh
```

## Environment Variables

Create a `server/.env` file (or export them). `config/settings/base.py` reads `BASE_DIR / '.env'` automatically.

Required for any environment:

```bash
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgres://user:password@localhost:5432/hydr8
```

Optional / useful for local dev:

```bash
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1
# RATELIMIT_ENABLE defaults to True
```

Production/Docker also needs values from `config/settings/production.py` (e.g., `REDIS_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`).

## Running Locally

1. Install dependencies:

```bash
cd server
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements/local.txt
```

2. Create a PostgreSQL database and a `.env` file with `SECRET_KEY` and `DATABASE_URL`.

3. Apply migrations and create an admin user:

```bash
python manage.py migrate
python manage.py createsuperuser
```

4. Start the dev server:

```bash
python manage.py runserver
```

The default settings module is `config.settings.local`, so `manage.py` will pick it up automatically. Open http://127.0.0.1:8000/.

## Running with Docker

The included `Dockerfile` builds a production-style image using `config.settings.production`.

```bash
cd server
docker build -t hydr8-server .
docker run -p 8000:8000 --env-file .env hydr8-server
```

The image runs `entrypoint.sh`, which:

1. Collects static files
2. Applies migrations
3. Starts Gunicorn on `0.0.0.0:8000`

Make sure `.env` contains all values required by `config/settings/production.py` (especially `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, and `REDIS_URL`).

## Testing and Linting

```bash
# Run the Django test suite
python manage.py test

# Lint / format
ruff check .
ruff format .
```

`ruff`, `coverage`, and `django-stubs` are in the dev dependency group of `pyproject.toml` if you want to install them separately.

## Production Checklist

- Set `DJANGO_SETTINGS_MODULE=config.settings.production`.
- Point `REDIS_URL` at the Redis instance (port 6379).
- Provide `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`.
- Use the `Dockerfile` + `entrypoint.sh` or run `gunicorn config.wsgi:application`.
- Static files are served by Whitenoise after `collectstatic`.
