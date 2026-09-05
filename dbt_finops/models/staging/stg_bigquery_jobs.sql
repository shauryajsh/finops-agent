-- Cleaned view over INFORMATION_SCHEMA.JOBS_BY_PROJECT.
-- Downstream models should read from this, not query INFORMATION_SCHEMA directly.

select
    job_id,
    user_email,
    query,
    total_bytes_billed,
    total_bytes_processed,
    creation_time,
    start_time,
    end_time,
    labels,
    state,
    error_result is not null as had_error

-- region-us must match your BigQuery dataset's actual region, or this
-- returns empty results with no error.
from `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT

where
    job_type = 'QUERY'
    and creation_time >= timestamp_sub(current_timestamp(), interval 30 day)