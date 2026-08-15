"""Core domain services.

The core app is intentionally read-only for day-to-day operations (products,
system configuration).  Create/update mutations are handled via the Django
admin interface, so this module is reserved for future core business logic.
"""
