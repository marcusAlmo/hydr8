"""Data migration — removes AI model SystemConfig keys.

The Gemma 2B edge-AI feature has been discarded. These keys were seeded by
migration 0007 but never read by the application (the Settings UI only
exposes operational keys: lockscreen timeout, tithe rate, credit limit,
container limit, overdue threshold). Removing them cleans up the database
and the Settings seed data.

Removes keys:
    - ai_model_id
    - ai_model_version
    - ai_download_status
    - ai_download_percent

Idempotent: safe to run multiple times. The reverse operation re-seeds the
removed keys with their original default values (kept for completeness in
case the migration is rolled back).
"""
from django.db import migrations

_REMOVED_KEYS = (
    'ai_model_id',
    'ai_model_version',
    'ai_download_status',
    'ai_download_percent',
)

# Original seed values from migration 0007 — kept here so the reverse
# operation can restore them if this migration is rolled back.
_REMOVED_DEFAULTS = {
    'ai_model_id': ('gemma-2-2b-it-q4f16_1-MLC',
                    'Currently loaded AI model identifier (WebGPU / @mlc-ai/web-llm).'),
    'ai_model_version': ('2b-q4f16',
                         'Display label for the AI model shown in Settings.'),
    'ai_download_status': ('not_started',
                           'PWA-driven: not_started | downloading | ready.'),
    'ai_download_percent': ('0',
                            'PWA-driven: 0-100 integer download progress.'),
}


def remove_ai_keys(apps, schema_editor):
    """Delete all SystemConfig rows whose key is an AI-model key."""
    SystemConfig = apps.get_model('core', 'SystemConfig')
    SystemConfig.objects.filter(key__in=_REMOVED_KEYS).delete()


def restore_ai_keys(apps, schema_editor):
    """Re-seed the AI-model keys with their original defaults.

    Mirrors the seeding logic in 0007: a global row (company=NULL) plus a
    per-tenant row for every existing Company.
    """
    SystemConfig = apps.get_model('core', 'SystemConfig')
    Company = apps.get_model('settings', 'Company')
    companies = list(Company.objects.all())

    for key in _REMOVED_KEYS:
        value, description = _REMOVED_DEFAULTS[key]
        SystemConfig.objects.get_or_create(
            company=None,
            key=key,
            defaults={'value': value, 'description': description},
        )
        for company in companies:
            SystemConfig.objects.get_or_create(
                company=company,
                key=key,
                defaults={'value': value, 'description': description},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_alter_product_options_alter_systemconfig_options'),
        ('settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(remove_ai_keys, restore_ai_keys),
    ]
