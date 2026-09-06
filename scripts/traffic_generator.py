"""Generates synthetic BigQuery query activity for the FinOps agent to analyze.

Runs cheap and expensive query pairs against large, real public tables,
populating INFORMATION_SCHEMA.JOBS_BY_PROJECT with realistic billing history.
Each query is dry-run first; anything over MAX_BYTES_PER_QUERY is skipped.
"""

from google.cloud import bigquery
import time

# ---- CONFIG ----
PROJECT_ID = "finops-agent-505810"
MAX_BYTES_PER_QUERY = 50 * 1024**3  # 50 GB safety cap per query

HACKERNEWS = "bigquery-public-data.hacker_news.full"
CRYPTO = "bigquery-public-data.crypto_ethereum.transactions"
GITHUB = "bigquery-public-data.github_repos.commits"

client = bigquery.Client(project=PROJECT_ID)

# Each pair targets the same real, large table: one filtered/few-column
# query (cheap), one missing the same protection (expensive). Cost
# contrast comes from filtering and column selection, not table size alone.
QUERIES = [
    (
        "hackernews_few_columns",
        f"""
        SELECT title, score
        FROM `{HACKERNEWS}`
        """,
        "analyst_5",
    ),
    (
        "hackernews_select_star",
        f"""
        SELECT *
        FROM `{HACKERNEWS}`
        """,
        "analyst_6",
    ),
    (
        "crypto_partition_filtered",
        f"""
        SELECT `hash`, from_address, to_address, value
        FROM `{CRYPTO}`
        WHERE block_timestamp BETWEEN TIMESTAMP('2024-01-01') AND TIMESTAMP('2024-01-02')
        """,
        "analyst_1",
    ),
    (
        "crypto_wide_range",
        f"""
        SELECT `hash`, from_address, to_address, value
        FROM `{CRYPTO}`
        WHERE block_timestamp BETWEEN TIMESTAMP('2023-01-01') AND TIMESTAMP('2024-01-01')
        """,
        "analyst_2",
    ),
    (
        "github_few_columns",
        f"""
        SELECT commit, author.name
        FROM `{GITHUB}`
        LIMIT 100
        """,
        "analyst_3",
    ),
    (
        "github_select_star",
        f"""
        SELECT *
        FROM `{GITHUB}`
        """,
        "analyst_4",
    ),
]


def estimate_bytes(sql: str, label: str, simulated_user: str) -> int:
    """Returns bytes a query would process, without running it."""
    job_config = bigquery.QueryJobConfig(
        dry_run=True,
        use_query_cache=False,
        labels={"simulated_user": simulated_user, "query_type": label, "dry_run_only": "true"},
    )
    query_job = client.query(sql, job_config=job_config)
    return query_job.total_bytes_processed


def run_query(label: str, sql: str, simulated_user: str):
    """Runs a query if it's under the safety cap, else skips it."""
    estimated = estimate_bytes(sql, label, simulated_user)
    estimated_gb = estimated / 1024**3
    print(f"[{label}] estimated: {estimated_gb:.3f} GB", end=" ")

    if estimated > MAX_BYTES_PER_QUERY:
        print("-> SKIPPED (over safety cap)")
        return

    # Cache disabled so repeated queries still show real billed bytes.
    job_config = bigquery.QueryJobConfig(
        labels={"simulated_user": simulated_user, "query_type": label},
        use_query_cache=False,
    )
    query_job = client.query(sql, job_config=job_config)
    query_job.result()
    print(f"-> ran, job_id={query_job.job_id}")


if __name__ == "__main__":
    for label, sql, user in QUERIES:
        run_query(label, sql, user)
        time.sleep(1)