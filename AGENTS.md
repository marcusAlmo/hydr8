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
