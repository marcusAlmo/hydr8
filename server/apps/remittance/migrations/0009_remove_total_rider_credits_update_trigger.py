"""Remove the unused ``total_rider_credits`` field and update the
FINALIZED-immutability trigger to:

1. Drop the ``total_rider_credits`` column check (the field no longer
   exists).
2. Add checks for ``total_salary`` and ``total_other_sales`` — two
   financial columns that were added in migrations 0006 and 0007 but
   were never registered in the trigger, meaning a finalized remittance's
   salary / other-sales totals could be silently mutated.

Also adds a composite index on ``(company, date, status)`` to speed up
the most common query pattern (looking up a remittance by tenant + date).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('remittance', '0008_add_commission_override'),
    ]

    operations = [
        # --- Remove the unused field -----------------------------------
        migrations.RemoveField(
            model_name='remittance',
            name='total_rider_credits',
        ),

        # --- Add composite index for the most common lookup ------------
        migrations.AddIndex(
            model_name='remittance',
            index=models.Index(
                fields=['company', 'date', 'status'],
                name='remittance__company_bb4a5f_idx',
            ),
        ),

        # --- Update the immutability trigger ---------------------------
        # Replaces the function created in 0005 to drop the
        # total_rider_credits check and add total_salary +
        # total_other_sales checks.
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION fn_lock_finalized_remittance()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.status = 'FINALIZED' THEN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED and cannot be deleted',
                            OLD.id;
                    END IF;

                    IF NEW.status <> 'FINALIZED' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED; status cannot be reverted',
                            OLD.id;
                    END IF;

                    IF NEW.date IS DISTINCT FROM OLD.date
                        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
                        OR NEW.finalized_by_id IS DISTINCT FROM OLD.finalized_by_id
                        OR NEW.total_sales IS DISTINCT FROM OLD.total_sales
                        OR NEW.total_credit_sales IS DISTINCT FROM OLD.total_credit_sales
                        OR NEW.total_commission IS DISTINCT FROM OLD.total_commission
                        OR NEW.total_salary IS DISTINCT FROM OLD.total_salary
                        OR NEW.total_expenses IS DISTINCT FROM OLD.total_expenses
                        OR NEW.total_other_sales IS DISTINCT FROM OLD.total_other_sales
                        OR NEW.total_borrowed_items IS DISTINCT FROM OLD.total_borrowed_items
                        OR NEW.net_profit IS DISTINCT FROM OLD.net_profit
                        OR NEW.total_repayments_received IS DISTINCT FROM OLD.total_repayments_received
                        OR NEW.tithe_rate_snapshot IS DISTINCT FROM OLD.tithe_rate_snapshot
                        OR NEW.tithe_amount IS DISTINCT FROM OLD.tithe_amount
                        OR NEW.offering_amount IS DISTINCT FROM OLD.offering_amount
                        OR NEW.notes IS DISTINCT FROM OLD.notes
                        OR NEW.company_id IS DISTINCT FROM OLD.company_id
                        OR NEW.created_at IS DISTINCT FROM OLD.created_at
                        OR NEW.finalized_at IS DISTINCT FROM OLD.finalized_at
                    THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED; financial fields are immutable',
                            OLD.id;
                    END IF;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            reverse_sql="""
            -- Revert to the original function from migration 0005.
            CREATE OR REPLACE FUNCTION fn_lock_finalized_remittance()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.status = 'FINALIZED' THEN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED and cannot be deleted',
                            OLD.id;
                    END IF;

                    IF NEW.status <> 'FINALIZED' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED; status cannot be reverted',
                            OLD.id;
                    END IF;

                    IF NEW.date IS DISTINCT FROM OLD.date
                        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
                        OR NEW.finalized_by_id IS DISTINCT FROM OLD.finalized_by_id
                        OR NEW.total_sales IS DISTINCT FROM OLD.total_sales
                        OR NEW.total_credit_sales IS DISTINCT FROM OLD.total_credit_sales
                        OR NEW.total_commission IS DISTINCT FROM OLD.total_commission
                        OR NEW.total_expenses IS DISTINCT FROM OLD.total_expenses
                        OR NEW.total_borrowed_items IS DISTINCT FROM OLD.total_borrowed_items
                        OR NEW.net_profit IS DISTINCT FROM OLD.net_profit
                        OR NEW.total_repayments_received IS DISTINCT FROM OLD.total_repayments_received
                        OR NEW.tithe_rate_snapshot IS DISTINCT FROM OLD.tithe_rate_snapshot
                        OR NEW.tithe_amount IS DISTINCT FROM OLD.tithe_amount
                        OR NEW.offering_amount IS DISTINCT FROM OLD.offering_amount
                        OR NEW.notes IS DISTINCT FROM OLD.notes
                        OR NEW.company_id IS DISTINCT FROM OLD.company_id
                        OR NEW.created_at IS DISTINCT FROM OLD.created_at
                        OR NEW.finalized_at IS DISTINCT FROM OLD.finalized_at
                    THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED; financial fields are immutable',
                            OLD.id;
                    END IF;
                END IF;

                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
        ),
    ]
