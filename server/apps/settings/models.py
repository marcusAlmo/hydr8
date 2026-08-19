"""Company has been moved to apps.core.models.

This module is intentionally empty. The historical migrations in
apps.settings.migrations still reference the Company model and must
remain so Django can track migration history. The model itself now
lives in core with app_label='core' and db_table='settings_company'
(the physical table name is unchanged).
"""
