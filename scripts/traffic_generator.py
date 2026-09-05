"""Generates synthetic BigQuery query activity for the FinOps agent to analyze.

Runs a mix of cheap and expensive queries across two public datasets,
simulating multiple teams, to populate INFORMATION_SCHEMA.JOBS_BY_PROJECT
with realistic billing history. Each query is dry-run first; anything over
MAX_BYTES_PER_QUERY is skipped.
"""

from google.cloud import bigquery
import time

# Hardcoded, not read from .env - this script only generates demo data for
# this specific project and is never run by someone using the real tool.
# ---- CONFIG ----
PROJECT_ID = "finops-agent-505810"
MAX_BYTES_PER_QUERY = 5 * 1024**3  # 5 GB safety cap per query

AUSTIN = "bigquery-public-data.austin_311.311_service_requests"
SHAKESPEARE = "bigquery-public-data.samples.shakespeare"

client = bigquery.Client(project=PROJECT_ID)

# BigQuery bills by columns scanned, not rows filtered — cost scales with
# column count, not WHERE/LIMIT. Two datasets simulate two teams.
QUERIES = [
    # ops team - austin_311
    ("ops_single_column", f"SELECT status FROM `{AUSTIN}` LIMIT 500", "analyst_1"),
    (
        "ops_two_columns_filtered",
        f"SELECT complaint_description, status FROM `{AUSTIN}` WHERE status = 'Closed' LIMIT 100",
        "analyst_2",
    ),
    ("ops_select_star", f"SELECT * FROM `{AUSTIN}`", "analyst_3"),
    ("ops_select_star_scheduled", f"SELECT * FROM `{AUSTIN}`", "scheduled_dashboard"),

    # research team - shakespeare
    ("research_single_column", f"SELECT word FROM `{SHAKESPEARE}` LIMIT 500", "analyst_4"),
    (
        "research_two_columns_filtered",
        f"SELECT word, word_count FROM `{SHAKESPEARE}` WHERE corpus = 'hamlet'",
        "analyst_4",
    ),
    ("research_select_star", f"SELECT * FROM `{SHAKESPEARE}`", "analyst_5"),
    ("research_select_star_scheduled", f"SELECT * FROM `{SHAKESPEARE}`", "scheduled_report"),
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