# Generated manually to purge audit logs older than 3 months and configure decongestion function

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('auditlog', '0017_add_actor_email'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- 1. One-time hard delete of auditlog records older than 3 months
            DELETE FROM auditlog_logentry
            WHERE "timestamp" < NOW() - INTERVAL '3 months';

            -- 2. Create PostgreSQL procedure for recurring hard-delete decongestion
            CREATE OR REPLACE FUNCTION fn_purge_old_audit_logs()
            RETURNS integer
            LANGUAGE plpgsql
            AS $$
            DECLARE
                deleted_count integer;
            BEGIN
                DELETE FROM auditlog_logentry
                WHERE "timestamp" < NOW() - INTERVAL '3 months';
                GET DIAGNOSTICS deleted_count = ROW_COUNT;
                RETURN deleted_count;
            END;
            $$;

            -- 3. Schedule job in pg_cron if extension/schema is available
            DO $cron_setup$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'
                ) OR EXISTS (
                    SELECT 1 FROM information_schema.schemata WHERE schema_name = 'cron'
                ) THEN
                    -- Purpose: Hard deletes audit_log records older than 3 months to decongest the database.
                    -- Schedule: '0 3 * * *' (Runs daily at 3:00 AM)
                    -- Flow:
                    --   1. Identify log entries in auditlog_logentry older than 3 months.
                    --   2. Hard delete the identified records from auditlog_logentry.
                    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'job_purge_old_audit_logs') THEN
                        PERFORM cron.unschedule('job_purge_old_audit_logs');
                    END IF;

                    PERFORM cron.schedule(
                        'job_purge_old_audit_logs',
                        '0 3 * * *',
                        'SELECT fn_purge_old_audit_logs();'
                    );
                END IF;
            END $cron_setup$;
            """,
            reverse_sql="""
            DO $cron_teardown$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.schemata WHERE schema_name = 'cron'
                ) THEN
                    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'job_purge_old_audit_logs') THEN
                        PERFORM cron.unschedule('job_purge_old_audit_logs');
                    END IF;
                END IF;
            END $cron_teardown$;

            DROP FUNCTION IF EXISTS fn_purge_old_audit_logs();
            """
        ),
    ]
