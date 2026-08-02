from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- 1. Reusable PL/pgSQL function to prevent deletion of default records
            CREATE OR REPLACE FUNCTION fn_restrict_delete()
            RETURNS TRIGGER AS $$
            DECLARE
                p_entity TEXT;
            BEGIN
                IF TG_NARGS > 0 THEN
                    p_entity := TG_ARGV[0];
                ELSE
                    p_entity := TG_TABLE_NAME;
                END IF;

                IF OLD.is_default IS TRUE THEN
                    RAISE EXCEPTION 'cannot delete a default value in %', p_entity;
                END IF;
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;

            -- 2. Trigger on users_role table calling fn_restrict_delete with entity parameter
            DROP TRIGGER IF EXISTS trg_restrict_delete_default_roles ON users_role;
            CREATE TRIGGER trg_restrict_delete_default_roles
            BEFORE DELETE ON users_role
            FOR EACH ROW
            EXECUTE FUNCTION fn_restrict_delete('users_role');
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_restrict_delete_default_roles ON users_role;
            DROP FUNCTION IF EXISTS fn_restrict_delete();
            """
        ),
    ]
