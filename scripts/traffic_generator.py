"""Generates synthetic BigQuery query activity for the FinOps agent to analyze.

Runs a mix of efficient and wasteful queries against a public dataset,
populating INFORMATION_SCHEMA.JOBS_BY_PROJECT with realistic billing history.
Each query is dry-run first; anything over MAX_BYTES_PER_QUERY is skipped.
"""

from google.cloud import bigquery
import time

# ---- CONFIG ----
PROJECT_ID = "finops-agent-505810"
DATASET = "bigquery-public-data.austin_311"
TABLE = "311_service_requests"
MAX_BYTES_PER_QUERY = 5 * 1024**3  # 5 GB safety cap per query

client = bigquery.Client(project=PROJECT_ID)

# Each entry: (label, sql, simulated_user)
QUERIES = [
    (
        "efficient_filtered",
        f"""
        SELECT complaint_description, status
        FROM `{DATASET}.{TABLE}`
        WHERE status = 'Closed'
        LIMIT 100
        """,
        "analyst_1",
    ),
    (
        "wasteful_select_star",
        f"""
        SELECT *
        FROM `{DATASET}.{TABLE}`
        """,
        "analyst_2",
    ),
]


def estimate_bytes(sql: str) -> int:
    """Returns bytes a query would process, without running it."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(sql, job_config=job_config)
    return query_job.total_bytes_processed


def run_query(label: str, sql: str, simulated_user: str):
    """Runs a query if it's under the safety cap, else skips it."""
    estimated = estimate_bytes(sql)
    estimated_gb = estimated / 1024**3
    print(f"[{label}] estimated: {estimated_gb:.3f} GB", end=" ")

    if estimated > MAX_BYTES_PER_QUERY:
        print("-> SKIPPED (over safety cap)")
        return

    job_config = bigquery.QueryJobConfig(
        labels={"simulated_user": simulated_user, "query_type": label}
    )
    query_job = client.query(sql, job_config=job_config)
    query_job.result()
    print(f"-> ran, job_id={query_job.job_id}")


if __name__ == "__main__":
    for label, sql, user in QUERIES:
        run_query(label, sql, user)
        time.sleep(1)