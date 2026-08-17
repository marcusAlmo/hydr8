"""Signal handlers for the Customers app.

Currently enforces the soft-delete safety net: a customer cannot be
soft-deleted (``deleted_at`` set) while they still have outstanding debt
or unreturned containers, regardless of how the deletion is initiated
(service layer, Django admin, shell, etc.).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver

from .models import Customer


@receiver(pre_save, sender=Customer)
def prevent_soft_delete_with_pending_items(
    sender, instance: Customer, **kwargs
) -> None:
    """Blocks soft-deletion when debt or unreturned containers remain.

    Only fires when an existing row is being transitioned from
    ``deleted_at IS NULL`` to ``deleted_at IS NOT NULL`` — the service
    layer's ``delete_customer`` already validates this, but the signal
    catches direct ORM/admin mutations that bypass the service.
    """
    if not instance.deleted_at or not instance.pk:
        return

    # Skip inserts (no pk yet) and rows that were already soft-deleted.
    try:
        previous = Customer.objects.filter(pk=instance.pk).values("deleted_at").first()
    except Exception:
        # If the lookup fails (e.g. during raw test DB setup), don't
        # block the save — the service layer is the primary guard.
        return
    if previous is None or previous["deleted_at"] is not None:
        return

    # The instance is being soft-deleted right now.  Validate that no
    # pending items remain.  We re-read the live DB values rather than
    # trusting the in-memory instance, since a caller might have
    # constructed the instance from stale data.
    live = Customer.objects.filter(pk=instance.pk).first()
    if live is None:
        return

    has_debt = live.debt_balance > 0
    has_containers = (
        live.borrowed_round_8gal + live.borrowed_slim_8gal + live.borrowed_other
    ) > 0
    if has_debt or has_containers:
        raise ValidationError(
            "Cannot delete a customer with pending debt or unreturned containers."
        )
