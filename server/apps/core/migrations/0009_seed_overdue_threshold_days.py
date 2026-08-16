"""Data migration — seeds the overdue_threshold_days SystemConfig key.

Adds the configurable overdue threshold (default: 7 days) used by the
customer detail modal and debt-management table to determine when an
unpaid credit or unreturned container is considered "overdue".

Idempotent: uses get_or_create per (company, key) so re-running is safe
and existing values are never overwritten.
"""
from django.db import migrations


def seed_overdue_threshold(apps, schema_editor):
    SystemConfig = apps.get_model('core', 'SystemConfig')
    Company = apps.get_model('settings', 'Company')

    key = 'overdue_threshold_days'
    value = '7'
    description = (
        'Number of days after which an unpaid credit or unreturned '
        'container is considered overdue.'
    )

    # Global / platform-default row.
    SystemConfig.objects.get_or_create(
        company=None,
        key=key,
        defaults={'value': value, 'description': description},
    )
    # Per-tenant rows (only if companies already exist at migrate time).
    for company in Company.objects.all():
        SystemConfig.objects.get_or_create(
            company=company,
            key=key,
            defaults={'value': value, 'description': description},
        )


def remove_overdue_threshold(apps, schema_editor):
    SystemConfig = apps.get_model('core', 'SystemConfig')
    SystemConfig.objects.filter(key='overdue_threshold_days').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_add_product_is_default_and_deleted_at'),
        ('settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_overdue_threshold, remove_overdue_threshold),
    ]
