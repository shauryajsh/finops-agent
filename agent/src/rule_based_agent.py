"""Rule-based diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries and applies simple heuristics
to explain likely cost drivers, before any LLM is involved. Serves as a
baseline to compare against the LLM agent.
"""

from google.cloud import bigquery

PROJECT_ID = "finops-agent-505810"
DATASET = "dbt_finops"

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

    if has_select_star:
        reasons.append(
            "Uses SELECT * — BigQuery bills by columns scanned, so this "
            "reads every column even if only a few are needed."
        )
        if not has_where:
            reasons.append(
                "Also has no WHERE clause. If this table is partitioned, "
                "a filter on the partition column would reduce scan size further."
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