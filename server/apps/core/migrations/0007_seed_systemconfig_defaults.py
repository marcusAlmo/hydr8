"""Data migration — seeds default SystemConfig keys.

Adds the operational and AI-model keys that the Settings page reads.
Idempotent: uses get_or_create per (company, key) so re-running is safe
and existing values are never overwritten.
"""
from django.db import migrations


def seed_defaults(apps, schema_editor):
    SystemConfig = apps.get_model('core', 'SystemConfig')
    Company = apps.get_model('settings', 'Company')

    # Default seeds. company=None means platform-global (the common case
    # for a single-tenant deployment). Per-tenant overrides can be added
    # later by creating rows with a non-null company_id.
    defaults = [
        # --- Operational (System Config tab) ---
        ('lockscreen_timeout_minutes', '5',
         'Minutes of inactivity before force logout / PIN prompt.'),
        ('tithe_rate', '0.10',
         'Decimal fraction of net profit allocated to tithes (0.10 = 10%).'),
        ('approved_credit_limit', '3000.00',
         'Maximum outstanding debt (PHP) a customer can accrue before '
         'further credit is blocked.'),
        ('approved_container_limit', '20',
         'Maximum total containers a customer may have unreturned at once.'),
        # --- AI Model tab (read-only display; PWA writes progress) ---
        ('ai_model_id', 'gemma-2-2b-it-q4f16_1-MLC',
         'Currently loaded AI model identifier (WebGPU / @mlc-ai/web-llm).'),
        ('ai_model_version', '2b-q4f16',
         'Display label for the AI model shown in Settings.'),
        ('ai_download_status', 'not_started',
         'PWA-driven: not_started | downloading | ready.'),
        ('ai_download_percent', '0',
         'PWA-driven: 0-100 integer download progress.'),
    ]

    # Seed a global row (company=NULL) for each key. If a Company row
    # exists, also seed a tenant-scoped copy so the UniqueConstraint on
    # (company, key) is satisfied per-tenant and the selector can read
    # tenant-scoped values.
    companies = list(Company.objects.all())

    for key, value, description in defaults:
        # Global / platform-default row.
        SystemConfig.objects.get_or_create(
            company=None,
            key=key,
            defaults={'value': value, 'description': description},
        )
        # Per-tenant rows (only if companies already exist at migrate time).
        for company in companies:
            SystemConfig.objects.get_or_create(
                company=company,
                key=key,
                defaults={'value': value, 'description': description},
            )


def remove_defaults(apps, schema_editor):
    SystemConfig = apps.get_model('core', 'SystemConfig')
    keys = [
        'lockscreen_timeout_minutes', 'tithe_rate',
        'approved_credit_limit', 'approved_container_limit',
        'ai_model_id', 'ai_model_version',
        'ai_download_status', 'ai_download_percent',
    ]
    SystemConfig.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_alter_product_unique_together_product_category_and_more'),
        ('settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_defaults, remove_defaults),
    ]
