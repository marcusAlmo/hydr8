# Hydr8 — To-Do List

> Living task tracker. Update status as work progresses.
> Status legend: `[ ]` pending · `[~]` in progress · `[x]` done

---

## 1. Skeleton Initialization & Light/Dark Mode

- [ ] **1.1 Initialize app skeletons**
  - Scaffold any missing Django app folders (`apps/<name>/{views,urls,models,services,templates}`)
  - Ensure each app has `apps.py`, `urls.py`, empty `models.py`, empty `views.py`
  - Register all new apps in `config/settings/base.py` `INSTALLED_APPS`
  - Wire each app's URLs into `config/urls.py`
  - Add sidebar nav entries in `templates/components/sidebar.html`

- [ ] **1.2 Implement light/dark mode (theme toggle)**
  - Define `:root` (light) and `.dark` (dark) CSS variable blocks in `static/css/styles.css`
    using M3 semantic tokens as RGB triplets
  - Keep "fixed" tokens identical in both themes
  - Keep `inverse-surface` dark in both modes (persistent sidebar)
  - Add FOUC-prevention `<script>` at top of `<head>` in `base.html` and `users/index.html`
  - Convert Tailwind color config to `rgb(var(--color-X) / <alpha-value>)` format
  - Wire theme toggle button in `sidebar.html` (Alpine.js `dark` state)
    - Toggle `.dark` class on `<html>`
    - Persist preference to `localStorage`
    - Swap icon + label on toggle
  - Add theme toggle button to login page (`users/index.html`) top-right corner
  - Verify theme persists across page navigations and full reloads
  - Verify sidebar stays dark in both modes
  - Verify all existing pages (dashboard, customers, remittance, products, employees)
    render correctly in both themes

---

## 2. Front-End Caching

- [ ] **2.1 Implement client-side caching layer**
  - Define cache strategy (per-route HTML fragments, JSON payloads, or both)
  - Decide cache storage: `localStorage`, `sessionStorage`, `Cache API`, or in-memory
    (Alpine.js `$store`)
  - Build cache key scheme (URL + relevant query params + user id)
  - Implement cache write on successful HTMX/Alpine response
  - Implement cache read on navigation / page load (stale-while-revalidate)
  - Add cache versioning so schema changes can bust all entries
  - Add cache size cap / LRU eviction to prevent unbounded growth
  - Add observability: `data-cache-hit` / `data-cache-stale` attributes for debugging

---

## 3. Django Payload-Hash Middleware (Cache Invalidation Channel)

> A server-side middleware that computes a hash of every HTTP response payload
> and returns it in a response header. The front-end compares this hash against
> the cached hash for the same resource; if they differ, the cached entry is
> invalidated and the fresh payload is stored. This replaces SSE as the
> invalidation channel — every response carries its own invalidation signal.

- [ ] **3.1 Design the middleware contract**
  - Header name: `X-Content-Hash` (or similar — confirm naming)
  - Hash algorithm: SHA-256 (truncated to first 16 hex chars for header brevity)
  - Hash input: full response body bytes (post-gzip, pre-send)
  - Skip hashing for streaming responses, file downloads, and `304 Not Modified`
  - Skip hashing for responses > N MB (configurable threshold)
  - Decide whether to also include the hash in `ETag` for HTTP-level caching interop

- [ ] **3.2 Implement the middleware**
  - Create `apps/core/middleware.py` (or `config/middleware.py`) with
    `PayloadHashMiddleware`
  - Register in `MIDDLEWARE` in `config/settings/base.py` (after compression
    middleware, before response is sent)
  - Compute hash in `process_template_response` / `__call__` post-render
  - Attach `X-Content-Hash` header to the `HttpResponse` object
  - Add unit tests covering: HTML, JSON, empty body, large body, streaming skip,
    304 skip

- [ ] **3.3 Wire the front-end invalidation logic**
  - Intercept HTMX response events (`htmx:afterRequest`) to read `X-Content-Hash`
  - Compare against stored hash for the same cache key
  - On mismatch: invalidate cache entry, store fresh payload + hash
  - On match: optionally convert request to a `304`-style no-op (skip re-render)
  - Document the contract in `AGENTS.md` so future endpoints comply automatically

- [ ] **3.4 Verify end-to-end**
  - Confirm header present on HTML, HTMX partial, and JSON responses
  - Confirm front-end invalidates on hash change (manual test scenario:
    mutate data server-side, reload, verify fresh content renders)
  - Confirm no invalidation when payload unchanged (cache hit, no flicker)
  - Confirm SSE is no longer required for cache invalidation flows

---

## 4. Audit Log E2E Integration — Deferred Items & Concerns

> Completed: mock data replaced with real `django-auditlog.LogEntry` records,
> selectors + signals + pagination wired, 10/10 tests passing.
> The following items were identified during the Change Impact Assessment
> and are deferred or require follow-up review.

### 4.1 Security & Privacy Reviews (required before production)

- [ ] **4.1.1 Role-based access control (Admin/Owner only)**
  - Audit log currently accessible to any authenticated user via `@login_required`
  - Exposes PII: actor emails, IP addresses, customer names in `object_repr`
  - Needs a role-check decorator pattern (not yet established in the codebase)
  - Recommend restricting to Admin/Owner roles only
  - Files: `apps/audit/views.py` (`audit_log_view`, `audit_log_detail_view`)

- [ ] **4.1.2 Privacy review (RA 10173 compliance)**
  - Audit log displays PII: actor emails, IP addresses, customer names, session keys
  - Confirm whether all authenticated users should see this or only Admin/Owner
  - Verify `additional_data` field doesn't leak sensitive data in the detail modal
  - Review `logs_json` projection — only display fields are included, but confirm
  - Files: `apps/audit/selectors.py` (`build_logs_json`), `apps/audit/templates/audit/`

- [ ] **4.1.3 Cybersec review — `|safe` filter on `logs_json`**
  - `{{ logs_json|safe }}` at line 12 of `audit_log.html` uses `|safe` on JSON output
  - `json.dumps` escapes `<`, `>`, `&` by default — no known XSS vector
  - Needs formal Cybersec sign-off before production
  - Files: `apps/audit/templates/audit/audit_log.html` (line 12)

### 4.2 Deferred Enhancements

- [ ] **4.2.1 System scheduler / retention shred events**
  - Requires pg_cron job to auto-delete `LogEntry` records older than retention period
  - Mock entry #16 in the old mock data demonstrated the pattern (retention_shred event)
  - Should log a `LogEntry(action=DELETE, actor=None, additional_data={"event": "retention_shred"})` 
  - Depends on: pg_cron_jobs skill, retention policy decision (e.g., 3 months)

- [ ] **4.2.2 Server-side HTMX filtering**
  - Current: Alpine.js client-side filtering (action, date range, search) within current page
  - Defer to when audit log volume exceeds ~1000 entries/page
  - Would move filters to server-side HTMX partials with `hx-get` + query params
  - Files: `apps/audit/views.py`, `apps/audit/templates/audit/audit_log.html`

- [ ] **4.2.3 Audit log CSV/PDF export**
  - Not requested; future enhancement for compliance reporting
  - Would add an export endpoint returning CSV/PDF of filtered log entries

- [ ] **4.2.4 Caching stats counts**
  - Cache total/mutation/access/active-actor counts with 60s TTL
  - Defer until `COUNT(*)` queries on `LogEntry` become slow at scale
  - Would use Django cache framework with `default` backend (Redis in prod)

- [ ] **4.2.5 Custom LogEntry model with company FK**
  - Only if RLS on audit logs becomes a hard requirement
  - Current `actor__company` filter is sufficient for tenant scoping
  - Would use `AUDITLOG_LOGENTRY_MODEL` swappable model setting

- [ ] **4.2.6 Real-time audit log streaming**
  - Not needed; audit log is historical, not real-time
  - Would use HTMX SSE extension or polling if ever required

### 4.3 Pre-Existing Bugs (not caused by audit log integration)

- [ ] **4.3.1 Stale test: `test_login_view_get`**
  - File: `apps/users/tests/test_views.py` (line 37)
  - Expects GET `/login/` to return 200, but the view redirects to `/` on GET
    (documented behavior at `apps/users/views.py` lines 140-145)
  - Fix: update test to expect 302 redirect, or test the landing page instead

- [ ] **4.3.2 Stale tests: `User.status` references (3 errors)**
  - File: `apps/users/tests/test_models.py`
  - Affected tests: `test_user_initial_state`, `test_set_pin_none_clears_pin`,
    `test_check_pin_handles_exception`
  - `User.status` field was removed in migration `users.0004_remove_user_status_user_deactivated_at_and_more`
  - Fix: update tests to use `is_active` / `deactivated_at` instead of `status`

---

## Notes

- Order is intentional: skeletons + theme first (foundation), then caching
  (depends on stable page structure), then hash middleware (depends on caching
  layer being in place to invalidate).
- Each top-level item should get its own branch: `feat/skeletons-theme`,
  `feat/frontend-cache`, `feat/payload-hash-middleware`.
- Update this file in the same commit as the work it tracks.
- Section 4 items are from the Audit Log E2E integration Change Impact Assessment.
  Security/privacy reviews (4.1) should be addressed before production deployment.
