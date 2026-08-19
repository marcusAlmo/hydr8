from django.db import models


class TenantQuerySet(models.QuerySet):
    """QuerySet that can auto-filter by the current tenant.

    Usage in selectors/views::

        Model.objects.for_user(request.user)   # tenant-scoped
        Model.objects.all()                     # unfiltered (superuser, commands)

    We do NOT override ``get_queryset()`` — that would break management
    commands, migrations, and admin superuser views that need cross-tenant
    access.  ``for_user()`` is the explicit entry point for tenant-scoped
    queries.
    """

    def for_user(self, user):
        if user.is_superuser or not hasattr(user, 'company_id') or user.company_id is None:
            return self.all()
        return self.filter(company_id=user.company_id)


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Manager that exposes :class:`TenantQuerySet` methods."""
