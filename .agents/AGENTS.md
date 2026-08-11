# Hydr8 Development Governance Rules

These rules apply to all AI agents working in this repository. They govern the development workflow, communication protocol, and quality gates.

## Project Identity

- **Project:** Hydr8 — Water Refilling Station Operations & AI Management System
- **Stack:** Django 6 / HTMX / Alpine.js / Tailwind CSS / PostgreSQL
- **Style:** Domain-Driven Design with service-oriented layering (server-rendered, hypermedia-first)
- **Database:** PostgreSQL (psycopg2-binary) — all schema decisions must be PSQL-aware
- **Frontend:** HTMX + Alpine.js + Tailwind CSS (CDN) + Django Templates — no SPA, no React, no Vite
- **AI:** Gemma 2B via `@mlc-ai/web-llm` (WebGPU, browser-local) — prompts never leave the device

---

## Mandatory Workflow Order

When implementing a new feature, the workflow MUST follow this sequence:

```
0. CHANGE MANAGER  →  Assesses impact, cost, benefit; issues triage decision (optional but recommended)
1. ARCHITECT       →  Produces architectural design + hand-off document (if PROCEED)
2. DEVELOPER       →  Implements the design exactly as specified
3. TESTER          →  Writes and runs tests for all new code
4. CYBERSEC        →  Security reviews all changes before sign-off
5. PRIVACY         →  Data Privacy Officer reviews for NPC/RA 10173 compliance
```

**No step may be skipped** (except Change Manager for trivial single-file changes). If the user requests implementation without a design, the agent must produce a brief architecture decision first (even if inline) before writing code.

The **Change Manager** is a pre-architecture gate that is optional but recommended for:
- Any change touching more than one layer (template + view, view + DB, DB + infra)
- Any change that introduces new dependencies, new infrastructure, or new patterns
- Any change where the business value is unclear or the effort seems disproportionate
- Any request that arrives as a vague idea rather than a concrete specification
- Any change touching financial calculation logic (remittance, credits, tithes, commissions)

For trivial, single-file changes (e.g., "fix the typo in the label"), the Change Manager can be skipped — go directly to Architect or Developer.

The **OPTIMIZER** is a separate, manually-invoked skill that runs outside this chain.

---

## Attempt Limit Rule — Credit Conservation

**All skills must observe this rule:**

If you have attempted to solve the same problem **2 times and failed**, you MUST stop and ask the user for input instead of attempting a third iteration. State clearly:

> "I've reached 2 attempts on [specific issue]. To avoid wasting credits, could you clarify: [specific question]?"

This applies to:
- Ambiguous or vague requests (Change Manager)
- Design conflicts (Architect)
- Implementation bugs (Developer)
- Failing tests (Tester)
- Unclear security findings (Cybersec)
- Ambiguous privacy findings (Privacy Officer)
- Ambiguous optimizer output (Optimizer)

---

## Django Layering — Hard Rules

These are non-negotiable for all code generated in this project:

| Layer | File | Allowed Operations |
|---|---|---|
| View | `views.py` | Permission check, call service/selector, render template or return HTMX partial |
| Service | `services.py` | Write logic, validation, ORM writes, financial calculations, raise exceptions |
| Selector | `selectors.py` | ORM reads only, return querysets or typed values |
| Model | `models.py` | Schema definition, Meta, `__str__`, `@property` helpers only |
| Template | `templates/<domain>/*.html` | Presentational only — no ORM, no business logic, HTMX attrs + Alpine.js directives |

**Violations are bugs.** Flag them in any review.

**Note:** There is no serializer layer in hydr8 (no DRF for primary UI). Views render Django templates or return HTMX partial fragments — not JSON responses.

---

## HTMX & Alpine.js Conventions

- **HTMX** handles all server-driven dynamic updates. Views return HTML partials, not JSON.
- **Alpine.js** is for ephemeral UI state ONLY (modals, drawers, theme toggle). Never store business data or make API calls.
- **Server is always the source of truth.** No client-side duplication of business logic.
- **HTMX attributes** must use `{% url %}` tag — never hardcoded paths.
- **CSRF:** `CSRF_COOKIE_HTTPONLY` must remain `False` so HTMX can read the token. `django_htmx.middleware.HtmxMiddleware` must be in `MIDDLEWARE`.

---

## PostgreSQL Naming Conventions

- Table names: explicitly set via `db_table = '<appname>_<modelname>'` (lowercase snake_case)
- Index names: `idx_<tablename>_<columns>` — e.g., `idx_remittance_status`
- Constraint names: `unique_<tablename>_<columns>` or `chk_<tablename>_<rule>`
- FK `related_name`: always descriptive and plural

---

## Financial Data Integrity — Hard Rules

1. **Snapshot pattern:** Financial records MUST snapshot mutable values (`unit_price_snapshot`, `commission_rate_snapshot`). Never recompute from live values after creation.
2. **Atomic updates:** Debt balance updates MUST use `F()` expressions to prevent race conditions.
3. **PROTECT on financial FKs:** Financial records use `on_delete=models.PROTECT`. `SET_NULL` acceptable for `recorded_by` user references.
4. **Immutable after finalize:** Once a `Remittance` is `FINALIZED`, no child records may be added, modified, or deleted.
5. **PIN-protected operations:** Finalizing a remittance requires PIN verification with rate limiting.
6. **DecimalField only:** All financial fields use `DecimalField` — NEVER `FloatField`.

---

## Security Non-Negotiables

1. **Every view must have `@login_required`** — no exceptions except the login view itself
2. **Role-based authorization** via `request.user.role` — Admin, Staff, Driver roles
3. **No auth tokens, passwords, or PINs in logs** — ever
4. **No ORM string formatting** — use `params=[]` for any raw SQL
5. **Financial fields are always `DecimalField`** — never `FloatField`
6. **Session auth only** — no JWT, no tokens in `localStorage` or `sessionStorage`
7. **`unique_together` is forbidden** — always use `UniqueConstraint(condition=Q(deleted_at__isnull=True))` for soft-delete models
8. **No `|safe` filter on user input** in templates — Django auto-escapes by default; respect it
9. **PIN hashing** via `make_password()` — never store plaintext PINs
10. **Rate limiting on PIN attempts** — lockout after 5 failures for 15 minutes

---

## Privacy Non-Negotiables (RA 10173 — Data Privacy Act of 2012)

1. **No PII in logs** — log only IDs (`user_id`, `customer_id`, `record_id`); never names, contact numbers, addresses
2. **No SPI in logs** — Sensitive Personal Information includes: PINs, tithes/offerings (religious financial data), debt details, customer notes (may contain personal context)
3. **`performed_by` is mandatory** — every service function that mutates data must accept and log `performed_by` (actor ID only)
4. **Purpose limitation** — customer data collected only for water refilling business operations
5. **Data subject rights** — architecture must allow customers to access, correct, and request deletion of their own data
6. **Log format** — `"[actor_id] Action. entity_id=X"` — never `"[actor_name] Action. customer_name=X"`
7. **Tithe/offering data is SPI** — religious financial contributions reveal religious affiliation; restrict to Admin role only

---

## Optimizer Rules

- The Optimizer skill runs **only when explicitly called** by the user (e.g., "run the optimizer", "run optimization check")
- It produces **reports only** — no code changes
- Its output should be fed to the Architect to plan remediation
- Run it periodically (e.g., before major releases, after a sprint of feature work)

---

## Code Quality Standards

- **ORM Optimization:** Always use `.exists()` or `.count()` instead of `len()` on QuerySets. Always use `select_related`/`prefetch_related` in selectors.
- **Migration Hygiene:** Never manually edit existing migration files. Always use `makemigrations` to generate new schema changes.
- **Test Coverage (Mandatory):** Tests must ALWAYS be updated to cover any new changes or features as a default step in the workflow.
- All Python code must have type annotations on function signatures
- All service functions use keyword-only arguments (`def fn(*, arg: type):`)
- All service functions that mutate data accept `performed_by` as a required keyword argument
- All log messages include the actor ID (`performed_by.id`) and entity ID — no PII or SPI
- Log format: `logger.info("[%s] Action. entity_id=%s", performed_by.id, entity_id)`
- All soft-delete models include `created_at`, `updated_at`, `deleted_at`
- All models include `__str__` with return type annotation `-> str:`
- All models explicitly set `db_table` in `Meta`
- All models include `verbose_name_plural` in `Meta`
- All uniqueness on soft-delete models uses `UniqueConstraint(condition=Q(deleted_at__isnull=True))` — `unique_together` is forbidden
- No bare `except:` clauses — always catch specific exceptions
- No `print()` statements — use `logging.getLogger(__name__)`
- Terminal operations: Always use `uv run python` instead of bare `python` or `python3` when interacting with the terminal.

## Commit Message Attribution

- Do **not** include `Generated with [Devin](https://devin.ai)` in commit messages.
- If AI assistance needs to be acknowledged, use `Assisted by Devin` instead.

---

## Workspace Learning Rules

- STRICT: **Never open a browser preview automatically.** The user keeps a dedicated browser open at all times. Auto-opening `browser_preview` after every fix or feature creates workspace clutter. Only open a browser preview when the user explicitly asks (e.g., "open the browser", "show me the page"). For verification, use the Django test client, `manage.py check`, or `curl` instead.
- STRICT: Always ask the user for permission before taking any actions that are more than read-only (e.g., modifying, creating, deleting, restarting) on their VPS.
- ALWAYS: Always use the user's private VPS or the provided VPS credentials when asked to deploy, test, or manage the application on a remote server.
- NEVER: Never use localhost or the current machine (i.e., your own VPS) when the user explicitly requests actions on *their* production or staging environment.
- STRICT: Always clean up any temporary or ad-hoc files created in production or locally after use, especially when a solution fails, to avoid clutter. This is a strict post-code/implementation rule.
- ALWAYS: Do not make assumptions when answering questions. Always provide an answer with absolute certainty, and if you are unsure or lack the information, explicitly say "I don't know."
- ALWAYS: Treat this project as a learning project. All actions, solutions, and commands you provide should be explicitly framed for teaching purposes.
- ALWAYS: After each fix or new coding of a feature, your response MUST include a detailed teaching or lesson, explaining the underlying concepts and 'why' behind the solution as if you are a dedicated tutor.
- ALWAYS: When presenting technical alternatives or tool recommendations, you must provide a detailed justification for your choice. Your justification should explicitly discuss tradeoffs such as "Time-to-Value", "Architectural Overhead", and the "Cost of State", comparing why your proposed solution is more pragmatic or scalable than the alternatives.
- ALWAYS: Upon completing any significant coding task, feature implementation, or architectural change, automatically execute `npx repomix` in the `server` directory to ensure the codebase graph remains up-to-date for future context.
- ALWAYS: Prioritize standard, robust coding practices and established framework conventions. Avoid providing risky, fragile, or "hacky" methods to ensure the user learns safe, production-ready patterns.

## Dev Credentials (DO NOT CHANGE)

The local dev database has a superuser account that the user logs in with:

- **Username:** `admin`
- **Password:** `admin`

**NEVER change this user's password or username.** Not for testing, not for
"convenience", not for any reason. If you need an authenticated client for
verification, use these exact credentials:

```python
from django.test import Client
c = Client(HTTP_HOST='127.0.0.1')
c.login(username='admin', password='admin')
```

If a test suite needs a fresh user, create a *separate* one with a clearly
non-default username (e.g. `test_runner`). Do not touch `admin`.
