from django.db import models

# ==========================================
# 1. THE CORE QUERYSET ABSTRACTION (DRY)
# ==========================================
class SoftDeleteQuerySet(models.QuerySet):
    """
    Standard chainable QuerySet for handling soft deletes across any model.
    """
    def active(self):
        return self.filter(deleted_at__isnull=True)
    
    def deleted(self):
        return self.filter(deleted_at__isnull=False)


# ==========================================
# 2. STANDARD MANAGERS (The Correct Way)
# ==========================================
class SoftDeleteManagerMixin:
    """
    Mixin for managers to expose SoftDeleteQuerySet methods without repetition.
    """
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def deleted(self):
        return self.get_queryset().deleted()
