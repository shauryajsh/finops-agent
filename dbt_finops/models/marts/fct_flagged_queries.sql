-- Cost estimated from bytes billed at on-demand pricing ($6.25/TB);
-- actual cost may differ under reservations/flat-rate pricing.

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

-- Labels are stored as repeated key/value pairs.
labeled as (

    select
        jobs.*,
        (select value from unnest(labels) where key = 'simulated_user') as simulated_user
    from jobs

),

-- Excludes this project's own dbt/tooling queries, keeping only simulated
-- traffic from traffic_generator.py.
scoped as (

    select *
    from labeled
    where simulated_user is not null

),

costed as (

    select
        *,
        total_bytes_billed / power(1024, 4) as tb_billed,
        (total_bytes_billed / power(1024, 4)) * 6.25 as estimated_cost_usd
    from scoped

),

benchmarked as (

    select
        *,
        avg(estimated_cost_usd) over () as avg_cost_usd,
        stddev(estimated_cost_usd) over () as stddev_cost_usd
    from costed

)

select
    job_id,
    simulated_user as query_owner,
    query,
    total_bytes_billed,
    round(tb_billed, 6) as tb_billed,
    round(estimated_cost_usd, 6) as estimated_cost_usd,
    round(avg_cost_usd, 6) as avg_cost_usd,
    creation_time,
    estimated_cost_usd > avg_cost_usd + coalesce(stddev_cost_usd, 0) as is_flagged

from benchmarked
order by estimated_cost_usd desc