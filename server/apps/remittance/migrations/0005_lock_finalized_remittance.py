"""Database-level immutability guard for FINALIZED remittances.

Once a remittance is finalized it becomes a permanent financial record.
This migration installs PostgreSQL triggers that:

1. On ``remittance_remittance`` — block DELETE and any UPDATE that touches
   a financial/structural column.  Only ``tithes_paid``, ``offering_paid``
   and ``updated_at`` may still change on a finalized row (so the
   "mark tithes/offering as paid" toggle keeps working).  The status
   itself cannot be reverted away from FINALIZED.

2. On the child tables (``remittance_remittance_rider``,
   ``remittance_remittance_rider_productline``, ``remittance_expense``) —
   block INSERT, UPDATE and DELETE when the parent remittance is
   FINALIZED, so children cannot be mutated behind the parent's back.

The DRAFT -> FINALIZED transition (an UPDATE where OLD.status = 'DRAFT')
is unaffected because the guard only fires when OLD.status is already
'FINALIZED'.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('remittance', '0004_remove_expense_remittance__remitta_2c0d46_idx_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- ------------------------------------------------------------------
            -- 1. Parent-table guard: lock FINALIZED remittance rows.
            -- ------------------------------------------------------------------
            CREATE OR REPLACE FUNCTION fn_lock_finalized_remittance()
            RETURNS TRIGGER AS $$
            BEGIN
                -- The guard only applies once the row is ALREADY finalized.
                -- The DRAFT -> FINALIZED transition (OLD.status = 'DRAFT') is
                -- therefore allowed to proceed untouched.
                IF OLD.status = 'FINALIZED' THEN
                    IF TG_OP = 'DELETE' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED and cannot be deleted',
                            OLD.id;
                    END IF;

                    -- Status may not be reverted away from FINALIZED.
                    IF NEW.status <> 'FINALIZED' THEN
                        RAISE EXCEPTION
                            'remittance id=% is FINALIZED; status cannot be reverted',
                            OLD.id;
                    END IF;

                    -- Only the payment-tracking flags + updated_at may change.
                    -- Every financial/structural column is compared with IS
                    -- DISTINCT FROM so NULLs are handled correctly.
                    IF NEW.date IS DISTINCT FROM OLD.date
                        OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
                        OR NEW.finalized_by_id IS DISTINCT FROM OLD.finalized_by_id
                        OR NEW.total_sales IS DISTINCT FROM OLD.total_sales
                        OR NEW.total_credit_sales IS DISTINCT FROM OLD.total_credit_sales
                        OR NEW.total_commission IS DISTINCT FROM OLD.total_commission
                        OR NEW.total_expenses IS DISTINCT FROM OLD.total_expenses
                        OR NEW.total_borrowed_items IS DISTINCT FROM OLD.total_borrowed_items
                        OR NEW.net_profit IS DISTINCT FROM OLD.net_profit
                        OR NEW.total_rider_credits IS DISTINCT FROM OLD.total_rider_credits
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

            DROP TRIGGER IF EXISTS trg_lock_finalized_remittance
                ON remittance_remittance;
            CREATE TRIGGER trg_lock_finalized_remittance
            BEFORE UPDATE OR DELETE ON remittance_remittance
            FOR EACH ROW
            EXECUTE FUNCTION fn_lock_finalized_remittance();

            -- ------------------------------------------------------------------
            -- 2. Child-table guard: block mutation of children whose parent
            --    remittance is FINALIZED.
            -- ------------------------------------------------------------------
            CREATE OR REPLACE FUNCTION fn_guard_remittance_child()
            RETURNS TRIGGER AS $$
            DECLARE
                p_remittance_id INT;
                p_status TEXT;
            BEGIN
                p_remittance_id := NULL;

                IF TG_TABLE_NAME = 'remittance_remittance_rider_productline' THEN
                    -- Product lines reference the parent via remittance_rider_id.
                    SELECT rr.remittance_id INTO p_remittance_id
                    FROM remittance_remittance_rider rr
                    WHERE rr.id = COALESCE(NEW.remittance_rider_id, OLD.remittance_rider_id);
                ELSE
                    -- rider / expense tables carry remittance_id directly.
                    IF TG_OP = 'DELETE' THEN
                        p_remittance_id := OLD.remittance_id;
                    ELSE
                        p_remittance_id := NEW.remittance_id;
                    END IF;
                END IF;

                IF p_remittance_id IS NULL THEN
                    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                    RETURN NEW;
                END IF;

                SELECT status INTO p_status
                FROM remittance_remittance
                WHERE id = p_remittance_id;

                IF FOUND AND p_status = 'FINALIZED' THEN
                    RAISE EXCEPTION
                        'remittance id=% is FINALIZED; child records are immutable',
                        p_remittance_id;
                END IF;

                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_guard_finalized_rider
                ON remittance_remittance_rider;
            CREATE TRIGGER trg_guard_finalized_rider
            BEFORE INSERT OR UPDATE OR DELETE ON remittance_remittance_rider
            FOR EACH ROW
            EXECUTE FUNCTION fn_guard_remittance_child();

            DROP TRIGGER IF EXISTS trg_guard_finalized_product_line
                ON remittance_remittance_rider_productline;
            CREATE TRIGGER trg_guard_finalized_product_line
            BEFORE INSERT OR UPDATE OR DELETE ON remittance_remittance_rider_productline
            FOR EACH ROW
            EXECUTE FUNCTION fn_guard_remittance_child();

            DROP TRIGGER IF EXISTS trg_guard_finalized_expense
                ON remittance_expense;
            CREATE TRIGGER trg_guard_finalized_expense
            BEFORE INSERT OR UPDATE OR DELETE ON remittance_expense
            FOR EACH ROW
            EXECUTE FUNCTION fn_guard_remittance_child();
            """,
            reverse_sql="""
            DROP TRIGGER IF EXISTS trg_guard_finalized_expense ON remittance_expense;
            DROP TRIGGER IF EXISTS trg_guard_finalized_product_line ON remittance_remittance_rider_productline;
            DROP TRIGGER IF EXISTS trg_guard_finalized_rider ON remittance_remittance_rider;
            DROP FUNCTION IF EXISTS fn_guard_remittance_child();

            DROP TRIGGER IF EXISTS trg_lock_finalized_remittance ON remittance_remittance;
            DROP FUNCTION IF EXISTS fn_lock_finalized_remittance();
            """
        ),
    ]
