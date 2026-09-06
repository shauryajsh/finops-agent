"""Checks partitioning/clustering and real SELECT * size for candidate datasets.

Verifies real BigQuery metadata and dry-run size estimates rather than
assuming from documentation or memory - public dataset sizes change and
aren't always accurately documented.
"""

from google.cloud import bigquery

PROJECT_ID = "finops-agent-505810"

CANDIDATES = [
    "bigquery-public-data.stackoverflow.posts_questions",
    "bigquery-public-data.hacker_news.full",
    "bigquery-public-data.samples.natality",
    "bigquery-public-data.noaa_gsod.gsod2020",
    "bigquery-public-data.google_analytics_sample.ga_sessions_20170801",
]

client = bigquery.Client(project=PROJECT_ID)


def check_table(table_id: str):
    table = client.get_table(table_id)
    print(f"\n{table_id}")

    if table.time_partitioning:
        print(f"  Partitioned by: {table.time_partitioning.field} ({table.time_partitioning.type_})")
    else:
        print("  Not partitioned")

    if table.clustering_fields:
        print(f"  Clustered by: {table.clustering_fields}")
    else:
        print("  Not clustered")

    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(f"SELECT * FROM `{table_id}`", job_config=job_config)
    size_gb = query_job.total_bytes_processed / 1024**3
    print(f"  SELECT * size: {size_gb:.3f} GB")


if __name__ == "__main__":
    for table_id in CANDIDATES:
        check_table(table_id)