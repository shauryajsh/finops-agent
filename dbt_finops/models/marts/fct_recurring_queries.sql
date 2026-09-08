-- Groups queries by literal text to find repeated patterns.
-- Total accumulated cost across runs matters more than any single run's cost.

with jobs as (

    select
        job_id,
        user_email,
        query,
        total_bytes_billed,
        creation_time,
        labels
    from {{ ref('stg_bigquery_jobs') }}
    where had_error = false

),

labeled as (

    select
        jobs.*,
        (select value from unnest(labels) where key = 'simulated_user') as simulated_user
    from jobs

),

scoped as (

    select *
    from labeled
    where simulated_user is not null

),

costed as (

    select
        *,
        -- Normalize whitespace first, so formatting differences don't split
        -- what is otherwise the exact same query into separate groups.
        farm_fingerprint(regexp_replace(trim(query), r'\s+', ' ')) as query_fingerprint,
        (total_bytes_billed / power(1024, 4)) * 6.25 as estimated_cost_usd
    from scoped

),

grouped as (

    select
        query_fingerprint,
        any_value(query) as sample_query,
        array_agg(simulated_user order by creation_time desc limit 1)[offset(0)] as most_recent_owner,
        count(*) as run_count,
        sum(estimated_cost_usd) as total_cost_usd,
        avg(estimated_cost_usd) as avg_cost_per_run_usd,
        min(creation_time) as first_seen,
        max(creation_time) as last_seen
    from costed
    group by query_fingerprint

)

select
    query_fingerprint,
    sample_query,
    most_recent_owner,
    run_count,
    round(total_cost_usd, 6) as total_cost_usd,
    round(avg_cost_per_run_usd, 6) as avg_cost_per_run_usd,
    first_seen,
    last_seen,
    run_count >= {{ var('recurring_min_runs', 2) }}
        and total_cost_usd >= {{ var('cost_flag_min_usd', 0.002) }} as is_recurring_flagged

from grouped
order by total_cost_usd desc