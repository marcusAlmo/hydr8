"""Remove Company from settings app state (state only).

This migration runs AFTER all FK references have been updated from
'settings.company' to 'core.company' (in core.0014, customers.0017,
remittance.0014, users.0015). It removes Company from the settings
app's migration state without touching the database.

Dependencies:
  - settings.0003: the last settings migration that references Company
  - core.0014: updates core's FK references to core.company
  - customers.0017: updates customers' FK references to core.company
  - remittance.0014: updates remittance's FK references to core.company
  - users.0015: updates users' FK references to core.company
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0003_seed_jps2_company'),
        ('core', '0014_alter_product_company_alter_systemconfig_company'),
        ('customers', '0017_alter_borrowedcontainer_company_and_more'),
        ('remittance', '0014_alter_expense_company_alter_remittance_company_and_more'),
        ('users', '0015_alter_drivercommission_company_alter_role_company_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='Company'),
            ],
            database_operations=[],
        ),
    ]
