# Hydr8 — Agent Guidelines

## Rate Limiting Convention (MANDATORY on every endpoint)

Every Django view that accepts user input (POST/PUT/PATCH/DELETE, and any GET
that triggers a side effect or expensive query) MUST be decorated with
`@ratelimit` from `django-ratelimit`. The cache backend is `default`
(Redis in production, locmem in dev/test) and is already configured in
`config/settings/base.py` and overridden per-environment.

### Baseline limits

| Endpoint type        | Decorator                              | Notes                                            |
|----------------------|----------------------------------------|--------------------------------------------------|
| Auth (login)         | `@ratelimit(key='ip', rate='10/m')`    | Plus 5-failure lockout (see below)               |
| PIN verification     | `@ratelimit(key='user_or_ip', rate='5/15m')` | Lockout after 5 failures for 15 min        |
| Write/mutation (HTMX)| `@ratelimit(key='user', rate='30/m')`  | Per authenticated user                           |
| Read/list (HTMX)     | `@ratelimit(key='user', rate='120/m')` | Per authenticated user                           |
| Search/autocomplete  | `@ratelimit(key='user', rate='60/m')`  | Per authenticated user                           |

### Usage pattern

```python
from django_ratelimit.decorators import ratelimit

@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
@login_required
def some_mutation_view(request):
    ...
```

- `block=True` raises `Ratelimited` (a `PermissionDenied` subclass) → HTTP 403.
- The custom `handler403` (`apps.users.views.ratelimited_view`) renders a
  friendly HTMX fragment for the login form. For other endpoints, add a
  domain-specific 403/429 fragment or return a toast via `HX-Trigger`.
- Key on `'user'` for authenticated endpoints (uses `request.user`); key on
  `'ip'` only for unauthenticated endpoints (login, password reset).

### Login lockout (5 failures → 1 minute)

The login view has a second layer of protection beyond the IP rate limit:
after 5 failed attempts for a given `(ip, username)` pair, that bucket is
locked for 60 seconds. The logic lives in `apps/users/services.py`:

- `record_failed_login(ip=, username=)` — call on every failed auth
- `reset_failed_login(ip=, username=)` — call on successful auth
- `check_login_lockout(ip=, username=)` — raises `ValidationError` if locked
- `get_client_ip(request)` — resolves IP honoring `X-Forwarded-For`

Both layers use the `default` cache, so in production they share a single
Redis instance across all gunicorn workers.

## Cache Backend

| Environment | Backend     | Config location                |
|-------------|-------------|--------------------------------|
| local/dev   | LocMemCache | `config/settings/base.py`      |
| test        | LocMemCache | `config/settings/test.py`      |
| production  | Redis       | `config/settings/production.py`|

`REDIS_URL` defaults to `redis://127.0.0.1:6379/1` and is read from the
environment in `production.py`. The VPS already runs Redis on port 6379; no
Docker setup is needed for deployment.

## Authorization Convention (MANDATORY)

The `Role` model (`apps.users.models.Role`) is the **single source of truth**
for what a user may do inside the application. It is the only authorization
surface editable through the UI (Employees & Users directory → Roles).

### DO NOT use `is_staff` for authorization

Django's `is_staff` flag is a parallel boolean that drifts out of sync with
the Role whenever a user is created outside
`apps.users.services.create_user_account` (Django admin, shell, fixtures).
Never write `user.is_staff or user.is_superuser` in view guards.

### Use `apps.users.permissions` helpers

```python
from apps.users.permissions import is_back_office, is_admin

# Login gate / general back-office access (Admin + Staff)
if not is_back_office(request.user):
    return HttpResponse("Forbidden", status=403)

# Admin-only operations (settings, user management)
if not is_admin(request.user):
    return HttpResponse("Forbidden", status=403)
```

| Helper           | Returns True for                         | Use for                     |
|-------------------|------------------------------------------|-----------------------------|
| `is_back_office`  | Role in {Admin, Staff} or superuser      | Login, products, employees  |
| `is_admin`        | Role == Admin or superuser               | Settings, user management   |

`is_superuser` is kept as a platform-level escape hatch only (superusers have
no `company` / `role` row). It is never assigned through the UI.

### Canonical role names

Defined in `apps/users/migrations/0008_default_roles_and_permissions.py`:
**Admin**, **Staff**, **Driver**. If a new role is added, update
`_BACK_OFFICE_ROLE_NAMES` in `apps/users/permissions.py`.

## App Architecture

The project has 5 Django apps under `server/apps/`:

| App          | Responsibility                                              |
|--------------|-------------------------------------------------------------|
| `users`      | IAM: Roles, Permissions, Users, Driver Commissions, Employees |
| `core`       | Shared Kernel: Products, System Config, Company, Audit Log  |
| `customers`  | Customer Accounts: Debts, Borrowed Items, Credit Lines      |
| `remittance` | Core Domain: Daily Remittance, Rider Lines, Expenses        |
| `analytics`  | Dashboard: KPI cards, recent remittances (read-only)        |

### Layered architecture (per app)

Each app follows a strict separation of concerns:

| Layer              | File pattern              | Responsibility                                    |
|--------------------|---------------------------|---------------------------------------------------|
| Selectors          | `selectors*.py`           | Read-side ORM queries, raw data, aggregates       |
| Presentation       | `presentation*.py`        | Template-shaped formatting, CSS classes, labels   |
| Services           | `services*.py`            | Write-side business logic, mutations, validations |
| Views              | `views*.py`               | Composition: selectors → presentation → template  |
| Models             | `models.py`               | Domain models and managers                        |

**Selectors** return raw data (Decimals, model instances, querysets).
**Presentation modules** shape raw data into template-ready dicts.
**Views** compose the two. Never put template formatting in selectors.

## Multi-Tenancy

Application-level tenant scoping via `TenantManager.for_user()`. No
PostgreSQL RLS policies. The scoping logic lives in
`apps/core/managers.py`:

```python
# Tenant-scoped query (filters by company_id for regular users)
Model.objects.for_user(request.user)

# Unfiltered query (superusers, management commands, migrations)
Model.objects.all()
```

Superusers and users without `company_id` see all tenants. Never bypass
`for_user()` in request-scoped code.

## CI/CD

GitHub Actions workflows enforce the `develop → staging → main` release
pipeline:

- **`ci.yml`**: Runs tests (PostgreSQL service container) and lint (ruff)
  on PRs to develop, staging, and main.
- **`branch-flow.yml`**: Enforces that PRs to main must come from staging,
  and PRs to staging must come from develop.

Branch protection rules (configured via GitHub API):
- **main**: 1 approval + Tests + Branch Flow checks, enforced for admins
- **staging**: 1 approval + Tests + Branch Flow checks, enforced for admins
- **develop**: Tests check required
