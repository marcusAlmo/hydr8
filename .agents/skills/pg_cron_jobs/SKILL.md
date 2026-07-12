---
name: pg_cron job scheduling
description: Guidelines and standards for defining and scheduling pg_cron jobs in the database.
---

# pg_cron Job Scheduling Standards

When generating, refactoring, or reviewing `pg_cron` jobs in this workspace, you MUST adhere to the following conventions to ensure consistency, maintainability, and clear documentation.

## 1. Job Naming Convention

- **Prefix Requirement**: All `pg_cron` jobs MUST use the standard prefix `job_`.
- **Descriptive Naming**: Use descriptive, lowercase snake_case names following the prefix (e.g., `job_archive_old_records`, `job_calculate_daily_metrics`).

## 2. Job Definition Structure

Every `pg_cron` job definition must be preceded by a structured comment block explaining its behavior. The comment block MUST include:

- **Purpose**: A clear explanation of what the job does.
- **Schedule**: When it runs, along with the human-readable cron expression.
- **Flow**: A step-by-step high-level breakdown of the operations within the job.

## 3. Example Implementation

Here is an example demonstrating the correct naming convention and comment structure:

```sql
-- Purpose: Archives records older than 30 days to the archive_table to keep main_table fast.
-- Schedule: '0 2 * * *' (Runs daily at 2:00 AM)
-- Flow:
--   1. Identify records in main_table older than 30 days.
--   2. Delete the identified records from main_table.
--   3. Insert the deleted records into archive_table.
SELECT cron.schedule(
    'job_archive_old_records',  -- Job name MUST start with job_
    '0 2 * * *',                -- Cron schedule
    $$
        WITH moved_rows AS (
            DELETE FROM main_table
            WHERE created_at < NOW() - INTERVAL '30 days'
            RETURNING *
        )
        INSERT INTO archive_table
        SELECT * FROM moved_rows;
    $$
);
```

## 4. Best Practices
- Keep the SQL inside the `$$ ... $$` block robust. Consider using `DO` blocks for more complex logic.
- Ensure that the operations within the job are optimized to avoid long-running transactions that could block other database operations.
