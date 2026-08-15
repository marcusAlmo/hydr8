from django.db import models


class Company(models.Model):
    """The tenant root entity.

    Every domain record belongs to exactly one Company.  Platform superusers
    have ``company=NULL`` on their User and can see all tenants.
    """

    name = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'settings_company'
        verbose_name = 'company'
        verbose_name_plural = 'companies'
        indexes = [
            models.Index(fields=['deleted_at']),
        ]

    def __str__(self) -> str:
        return self.name
