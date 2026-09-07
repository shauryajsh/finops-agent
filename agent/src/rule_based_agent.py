"""Rule-based diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries and applies simple rules
to explain likely cost drivers, before any LLM is involved. Serves as a
fast, free first-pass filter ahead of the LLM diagnosis.
"""

import os
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()

# Config comes from .env - see .env.example for required variables.
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET = os.environ["BIGQUERY_DATASET"]

client = bigquery.Client(project=PROJECT_ID)


def get_flagged_queries():
    """Returns flagged rows from fct_flagged_queries, most expensive first."""
    sql = f"""
        SELECT query_owner, query, estimated_cost_usd, avg_cost_usd
        FROM `{PROJECT_ID}.{DATASET}.fct_flagged_queries`
        WHERE is_flagged = true
        ORDER BY estimated_cost_usd DESC
    """
    return list(client.query(sql).result())


def diagnose(query_text: str) -> list[str]:
    """Returns plain-English reasons a query is likely expensive."""
    reasons = []
    normalized = query_text.upper()

    has_select_star = "SELECT *" in normalized
    has_where = "WHERE" in normalized
    has_wildcard_table = "*`" in query_text
    has_count_distinct = "COUNT(DISTINCT" in normalized
    has_order_by = "ORDER BY" in normalized
    has_limit = "LIMIT" in normalized

    if has_select_star:
        reasons.append(
            "Uses SELECT * — BigQuery bills by columns scanned, not rows filtered."
        )
        if not has_where:
            reasons.append(
                "Also missing a WHERE clause - filter on the partition column, if this table has one."
            )

    if has_wildcard_table:
        reasons.append(
            "Uses a wildcard table (table_*) - scans every match unless filtered on _TABLE_SUFFIX."
        )

    if has_count_distinct:
        reasons.append(
            "Uses COUNT(DISTINCT ...) - expensive on large columns. Try APPROX_COUNT_DISTINCT instead."
        )

    if has_order_by and not has_limit:
        reasons.append(
            "ORDER BY with no LIMIT - sorts the full result set for no reason."
        )

    if not reasons:
        reasons.append("No issue matched by current rules.")

    return reasons


if __name__ == "__main__":
    flagged = get_flagged_queries()
    print(f"Found {len(flagged)} flagged queries\n")

    for row in flagged:
        print(f"Owner: {row.query_owner}")
        print(f"Cost: ${row.estimated_cost_usd:.6f} (avg: ${row.avg_cost_usd:.6f})")
        for reason in diagnose(row.query):
            print(f"  - {reason}")
        print()