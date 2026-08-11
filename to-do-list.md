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

## Notes

- Order is intentional: skeletons + theme first (foundation), then caching
  (depends on stable page structure), then hash middleware (depends on caching
  layer being in place to invalidate).
- Each top-level item should get its own branch: `feat/skeletons-theme`,
  `feat/frontend-cache`, `feat/payload-hash-middleware`.
- Update this file in the same commit as the work it tracks.
