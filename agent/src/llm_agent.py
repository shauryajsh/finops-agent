"""LLM-powered diagnosis of flagged BigQuery queries.

Reads flagged rows from fct_flagged_queries, discovers the table each
query references directly from BigQuery, and asks the LLM to explain
why it's expensive and propose a dry-run-validated fix.
"""

import os
import json
import re
from dotenv import load_dotenv
from google.cloud import bigquery
from llm_client import ask_llm

load_dotenv()

# Config comes from .env - see .env.example for required variables.
PROJECT_ID = os.environ["GCP_PROJECT_ID"]
DATASET = os.environ["BIGQUERY_DATASET"]

# A real deployment only needs its own GCP_PROJECT_ID for table discovery -
# below. These external datasets exist only because this demo borrows
# public datasets in place of a real company's own tables, and
# bigquery-public-data itself is too large to enumerate in full.
EXTERNAL_DATASETS = [
    "bigquery-public-data.hacker_news",
    "bigquery-public-data.github_repos",
    "bigquery-public-data.crypto_ethereum",
    "bigquery-public-data.stackoverflow",
    "bigquery-public-data.samples",
    "bigquery-public-data.covid19_open_data",
    "bigquery-public-data.austin_311",
    "bigquery-public-data.new_york_citibike",
    "bigquery-public-data.noaa_gsod",
    "bigquery-public-data.google_analytics_sample",
]

_discovered_tables = None

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


def discover_tables() -> list[str]:
    """Finds every real table in the project, plus the configured external datasets."""
    tables = []

    for dataset in client.list_datasets(project=PROJECT_ID):
        for table in client.list_tables(dataset.reference):
            tables.append(f"{PROJECT_ID}.{dataset.dataset_id}.{table.table_id}")

    for dataset_ref in EXTERNAL_DATASETS:
        for table in client.list_tables(dataset_ref):
            tables.append(f"{dataset_ref}.{table.table_id}")

    return tables


def find_table(query_text: str) -> str | None:
    """Returns the real table referenced in a query, if any.

    Tables are discovered from BigQuery directly, once per run, rather
    than hardcoded - any table actually in scope is found automatically.
    Wildcard references are matched by prefix against the same discovered
    list, since a wildcard pattern never matches a literal table name.
    """
    global _discovered_tables
    if _discovered_tables is None:
        _discovered_tables = discover_tables()

    wildcard_match = re.search(r"`([\w.-]+\.[\w-]+\.[\w]+)\*`", query_text)
    if wildcard_match:
        prefix = wildcard_match.group(1)
        for table in _discovered_tables:
            if table.startswith(prefix):
                return table

    for table in _discovered_tables:
        if table in query_text:
            return table

    return None


def get_schema(table_id: str, max_columns: int = 25) -> list[str]:
    """Returns column name/type pairs for a table, pre-quoted with backticks
    so reserved-word column names (like `hash` or `by`) can't break generated
    SQL, and capped to control prompt size on wide tables.
    """
    table = client.get_table(table_id)
    columns = [f"`{field.name}` ({field.field_type})" for field in table.schema]
    return columns[:max_columns]


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

Before answering, decide: is there any further change to THIS query that
would reduce cost, given the table's actual structure? If it already
selects the minimum needed columns on an unpartitioned table, already
filters on the correct partition column, or already uses an approximate
function instead of an exact one - there is nothing left to fix, even if
it still scans real data due to the table's own size. Set has_issue to
false in that case, and explain why in one sentence. Do not describe
cost mechanics as a problem when the query has already applied the best
available fix for that table.

Column names in the schema above are shown with backticks. Keep them
backtick-quoted in the fixed query exactly as shown.

If the original query uses SELECT *, still propose narrowing to the
columns most likely needed, explicitly excluding large, rarely-needed
fields like free-text blobs - state in the explanation that this
assumes those fields aren't required downstream, rather than claiming
guaranteed equivalence. Only respond with "fixed_query": null when the
query already selects a narrow, deliberate set of columns and no
further column or partition-based reduction is reasonably available.

Reply with valid JSON only, no other text, in exactly this format:
{{"explanation": "2-3 sentences on what drives the cost", "fixed_query": "the corrected SQL as a single string", "has_issue": true or false}}"""


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
    print(f"Found {len(flagged)} flagged queries\n")

    for row in flagged:
        result = diagnose_and_fix(row.query)
        validation = validate_fix(row.query, result["fixed_query"])

        print(f"Owner: {row.query_owner}")
        print(f"Cost: ${row.estimated_cost_usd:.6f} (avg: ${row.avg_cost_usd:.6f})")
        print(f"Explanation: {result['explanation']}")
        print(f"Fixed query: {result['fixed_query']}")

        if result["fixed_query"] is None:
            print("No query-level fix available - this query may need materialization instead.")
        elif validation["valid"]:
            original_gb = validation["original_bytes"] / 1024**3
            fixed_gb = validation["fixed_bytes"] / 1024**3
            reduction_pct = (1 - validation["fixed_bytes"] / validation["original_bytes"]) * 100
            print(f"Validated: {original_gb:.3f} GB -> {fixed_gb:.3f} GB ({reduction_pct:.1f}% reduction)")
        else:
            print(f"Fix could not be validated: {validation.get('error', 'unknown error')}")

        print()