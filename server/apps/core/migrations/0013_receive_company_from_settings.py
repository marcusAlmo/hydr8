"""Receive Company model from settings app (state only).

Adds Company to the core app's migration state without touching the
database. The physical table (settings_company) is unchanged.

This migration depends on settings.0003 (not 0004) so Company exists
in both apps' state simultaneously. The FK references in other apps
are then updated to point to 'core.company' (in migration 0014 and
companions). Finally, settings.0004 removes Company from the settings
state — by then all FKs point to core.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_remove_ai_systemconfig_keys'),
        ('settings', '0003_seed_jps2_company'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Company',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('name', models.CharField(max_length=255)),
                        ('contact_number', models.CharField(blank=True, max_length=20, null=True)),
                        ('email', models.EmailField(blank=True, null=True, max_length=254)),
                        ('address', models.TextField(blank=True, null=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('deleted_at', models.DateTimeField(blank=True, null=True)),
                    ],
                    options={
                        'verbose_name': 'company',
                        'verbose_name_plural': 'companies',
                        'db_table': 'settings_company',
                        'indexes': [models.Index(fields=['deleted_at'], name='settings_co_deleted_fa115f_idx')],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
