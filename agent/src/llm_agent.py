"""LLM-powered diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries, fetches each query's table
schema and partitioning info, and asks the LLM to explain why the query
is expensive with a specific fix.
"""

import os
import json
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

def get_recurring_queries():
    """Returns recurring query patterns flagged as worth attention, costliest first."""
    sql = f"""
        SELECT sample_query, most_recent_owner, run_count, total_cost_usd, avg_cost_per_run_usd
        FROM `{PROJECT_ID}.{DATASET}.fct_recurring_queries`
        WHERE is_recurring_flagged = true
        ORDER BY total_cost_usd DESC
    """
    return list(client.query(sql).result())

def find_table(query_text: str) -> str | None:
    """Returns the known table referenced in a query, if any."""
    for table in KNOWN_TABLES:
        if table in query_text:
            return table
    return None


def get_schema(table_id: str) -> list[str]:
    """Returns column name/type pairs for a table, pre-quoted with backticks
    so reserved-word column names (like `hash` or `by`) can't break generated SQL.
    """
    table = client.get_table(table_id)
    return [f"`{field.name}` ({field.field_type})" for field in table.schema]


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

def parse_llm_json(raw_text: str) -> dict:
    """Parses the LLM's JSON reply, stripping markdown code fences if present."""
    text = raw_text.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)

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

def build_fix_prompt(query_text: str, schema: list[str], partition_info: str) -> str:
    """Builds a prompt asking the LLM to diagnose a query and rewrite it."""
    schema_text = "\n".join(schema)
    return f"""You are a BigQuery cost optimization expert. A query has been
flagged as unusually expensive. Diagnose why, and rewrite it as a
corrected, lower-cost query returning equivalent results.

Query:
{query_text}

Table schema:
{schema_text}

Table partitioning:
{partition_info}

Important: a WHERE filter only reduces cost if it targets the actual
partitioning column on a partitioned table. If the table is not
partitioned, filtering does not reduce bytes scanned - only selecting
fewer columns does.

Do not add filters that were not in the original query unless they
target the actual partitioning column on a partitioned table. Any other
added filter changes which rows are returned, not just cost, and is
not an acceptable fix.

Column names in the schema above are shown with backticks. Keep them
backtick-quoted in the fixed query exactly as shown.

Reply with valid JSON only, no other text, in exactly this format:
{{"explanation": "2-3 sentences on what drives the cost", "fixed_query": "the corrected SQL as a single string"}}"""

def diagnose_and_fix(query_text: str) -> dict:
    """Returns an explanation and a corrected query for one flagged query."""
    table = find_table(query_text)
    if table is None:
        return {"explanation": "Could not identify table - skipping.", "fixed_query": None}

    schema = get_schema(table)
    partition_info = get_partition_info(table)
    prompt = build_fix_prompt(query_text, schema, partition_info)
    raw_response = ask_llm(prompt)

    try:
        return parse_llm_json(raw_response)
    except (json.JSONDecodeError, IndexError):
        return {"explanation": raw_response, "fixed_query": None}

def estimate_bytes_for(sql: str) -> int:
    """Returns bytes a query would process, without running it."""
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    query_job = client.query(sql, job_config=job_config)
    return query_job.total_bytes_processed


def validate_fix(original_query: str, fixed_query: str) -> dict:
    """Dry-runs the fixed query to check it's valid and measure real byte savings."""
    if fixed_query is None:
        return {"valid": False, "original_bytes": None, "fixed_bytes": None}

    try:
        original_bytes = estimate_bytes_for(original_query)
        fixed_bytes = estimate_bytes_for(fixed_query)
        return {"valid": True, "original_bytes": original_bytes, "fixed_bytes": fixed_bytes}
    except Exception as e:
        return {"valid": False, "error": str(e), "original_bytes": None, "fixed_bytes": None}

if __name__ == "__main__":
    flagged = get_flagged_queries()
    row = flagged[0]
    result = diagnose_and_fix(row.query)
    print("Fixed query:", result["fixed_query"])
    print()
    print("Validation:", validate_fix(row.query, result["fixed_query"]))