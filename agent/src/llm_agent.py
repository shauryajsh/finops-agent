"""LLM-powered diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries, fetches each query's table
schema and partitioning info, and asks the LLM to explain why the query
is expensive with a specific fix.
"""

import os
from dotenv import load_dotenv
from google.cloud import bigquery
from llm_client import ask_llm

load_dotenv()

# Config comes from .env - see .env.example for required variables.
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET = os.environ["BIGQUERY_DATASET"]

# Tables our traffic generator queries against - used to detect which
# table a flagged query references, so we can fetch its schema.
KNOWN_TABLES = [
    "bigquery-public-data.crypto_ethereum.transactions",
    "bigquery-public-data.github_repos.commits",
    "bigquery-public-data.hacker_news.full",
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


def get_partition_info(table_id: str) -> str:
    """Returns a plain-English description of a table's partitioning and clustering."""
    table = client.get_table(table_id)

    if table.time_partitioning:
        partition_text = f"Partitioned by {table.time_partitioning.field} ({table.time_partitioning.type_})"
    else:
        partition_text = "Not partitioned"

    if table.clustering_fields:
        clustering_text = f"Clustered by {', '.join(table.clustering_fields)}"
    else:
        clustering_text = "Not clustered"

    return f"{partition_text}. {clustering_text}."


def build_prompt(query_text: str, schema: list[str], partition_info: str) -> str:
    """Builds the prompt sent to the LLM for one flagged query."""
    schema_text = "\n".join(schema)
    return f"""You are a BigQuery cost optimization expert. A query has been
flagged as unusually expensive. Explain specifically why, using the table
schema and partitioning info below, and suggest one concrete fix.

Query:
{query_text}

Table schema:
{schema_text}

Table partitioning:
{partition_info}

Important: a WHERE filter only reduces cost if it targets the actual
partitioning column on a partitioned table. If the table is not
partitioned, filtering does not reduce bytes scanned - only selecting
fewer columns does. Do not suggest adding a filter as a cost fix unless
the table is genuinely partitioned on the relevant column.

Do not assume a query is merely exploratory just because it selects few
columns or uses LIMIT - it may be intended to retrieve real data for
downstream use. Do not suggest using a free table-preview feature as a
fix unless the query is clearly a one-off inspection. If the query
appears likely to run repeatedly, suggest materializing a smaller derived
table instead of rescanning the full table each time.

Reply in 2-3 sentences. Be specific about which columns or clauses drive
the cost - do not give a generic answer."""


def diagnose(query_text: str) -> str:
    """Returns an LLM-generated explanation for one flagged query."""
    table = find_table(query_text)
    if table is None:
        return "Could not identify table - skipping LLM diagnosis."

    schema = get_schema(table)
    partition_info = get_partition_info(table)
    prompt = build_prompt(query_text, schema, partition_info)
    return ask_llm(prompt)


if __name__ == "__main__":
    flagged = get_flagged_queries()
    print(f"Found {len(flagged)} flagged queries\n")

    for row in flagged:
        print(f"Owner: {row.query_owner}")
        print(f"Cost: ${row.estimated_cost_usd:.6f} (avg: ${row.avg_cost_usd:.6f})")
        print(f"LLM diagnosis: {diagnose(row.query)}")
        print()