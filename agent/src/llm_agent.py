"""LLM-powered diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries, fetches each query's table
schema, and asks the LLM to explain why the query is expensive with a
specific fix. Compares against the rule-based baseline from Phase 3.
"""

from google.cloud import bigquery
from llm_client import ask_llm

PROJECT_ID = "finops-agent-505810"
DATASET = "dbt_finops"

# Tables our traffic generator queries against - used to detect which
# table a flagged query references, so we can fetch its schema.
KNOWN_TABLES = [
    "bigquery-public-data.austin_311.311_service_requests",
    "bigquery-public-data.samples.shakespeare",
]

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


def find_table(query_text: str) -> str | None:
    """Returns the known table referenced in a query, if any."""
    for table in KNOWN_TABLES:
        if table in query_text:
            return table
    return None


def get_schema(table_id: str) -> list[str]:
    """Returns column name/type pairs for a table."""
    table = client.get_table(table_id)
    return [f"{field.name} ({field.field_type})" for field in table.schema]


def build_prompt(query_text: str, schema: list[str]) -> str:
    """Builds the prompt sent to the LLM for one flagged query."""
    schema_text = "\n".join(schema)
    return f"""You are a BigQuery cost optimization expert. A query has been
flagged as unusually expensive. Explain specifically why, using the table
schema below, and suggest one concrete fix.

Query:
{query_text}

Table schema:
{schema_text}

Reply in 2-3 sentences. Be specific about which columns or clauses drive
the cost - do not give a generic answer."""


def diagnose(query_text: str) -> str:
    """Returns an LLM-generated explanation for one flagged query."""
    table = find_table(query_text)
    if table is None:
        return "Could not identify table - skipping LLM diagnosis."

    schema = get_schema(table)
    prompt = build_prompt(query_text, schema)
    return ask_llm(prompt)


if __name__ == "__main__":
    flagged = get_flagged_queries()
    print(f"Found {len(flagged)} flagged queries\n")

    for row in flagged:
        print(f"Owner: {row.query_owner}")
        print(f"Cost: ${row.estimated_cost_usd:.6f} (avg: ${row.avg_cost_usd:.6f})")
        print(f"LLM diagnosis: {diagnose(row.query)}")
        print()