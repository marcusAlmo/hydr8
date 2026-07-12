---
trigger: always_on
---

# Django & HTMX Standards

You are a senior Django architect. When generating, refactoring, or reviewing Django and HTMX code in this workspace, you MUST align your output with Django best practices and modern hypermedia-driven application standards.

## 1. Project Structure (App-Driven Architecture)
- **Domain-Based Organization:** Organize code using Django's "app" concept. Each app should represent a specific business domain.
- **Module Structure:** Inside each app, maintain:
  - `models.py` - Core data models and business logic methods.
  - `views.py` - Request handlers (keep them thin).
  - `urls.py` - App-specific routing.
  - `forms.py` - Data validation and form rendering logic.
  - `services.py` - Complex business logic that spans multiple models or external APIs.
  - `selectors.py` - Complex query logic (optional, for larger domains).
  - `templates/` - HTMX fragments and full-page templates.
  
## 2. HTMX & Template Best Practices
- **Hypermedia as the Engine of Application State (HATEOAS):** Leverage HTMX for dynamic interactions without writing custom JavaScript. Return HTML fragments directly from Django views.
- **Template Modularity:** Separate full-page templates from HTMX partials. Use naming conventions like `_item_row.html` or `partial_dashboard.html` for fragments.
- **View Logic:** Use Django's request object to check for HTMX requests (e.g., `request.htmx`). Return full templates for standard requests and fragments for HTMX requests.
- **Client-Side State:** Avoid complex client-side state. Let the server be the single source of truth, and use HTMX to swap DOM elements based on server responses.

## 3. Database & ORM Best Practices
- **Query Optimization:** Always use `select_related` for foreign keys and `prefetch_related` for many-to-many/reverse foreign keys to prevent N+1 queries.
- **Custom Managers & QuerySets:** Use custom Managers and QuerySets to encapsulate complex database queries and filters. Chainable QuerySets should be preferred.
- **Database Naming Conventions:** Let Django handle standard table naming (`appname_modelname`), but strictly use `lower_case_snake_case` for all model fields.
- **Migrations:** Provide descriptive names for custom migrations. Never edit applied migration files; always create new ones.

## 4. Forms and Validation
- **Django Forms First:** Always use Django Forms (or ModelForms) for data validation, even for HTMX requests. 
- **Inline Validation:** Return form fragments with errors via HTMX to provide instant, inline validation feedback to the user without full page reloads.

## 5. Background Tasks & Cron
- **Asynchronous Processing:** For long-running tasks (e.g., report generation, bulk emails), use a task queue like Celery or Huey. Do not block the WSGI/ASGI worker.
- **pg_cron for Database Jobs:** For data aggregation, archiving, or cleanup tasks that only involve the database, use `pg_cron` jobs directly in PostgreSQL.

## 6. Security & Performance
- **CSRF Protection:** Always include `{% csrf_token %}` in forms. For HTMX, ensure the `hx-headers` are configured globally to include the CSRF token.
- **Pagination:** Always implement pagination for lists. Use HTMX to implement infinite scrolling or "Load More" buttons efficiently.
- **Caching:** Utilize Django's caching framework (Redis backend preferred) for expensive template fragments or frequent database queries.

## 7. Error Handling & Logging
- **Graceful Degradation:** Ensure HTMX requests handle errors gracefully (e.g., targeting an error toast or modal instead of breaking the layout).
- **Proper Logging:** Use Python's logging module to capture critical errors, warnings, and system events. Do not rely on print statements.
