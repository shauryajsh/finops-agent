"""Generates labeled eval cases for the LLM/rule-based comparison.

Each case is built from a real table, so the LLM path can fetch real
schema. Expected concepts are known by construction, since we choose
which anti-pattern each case injects. Cases are never executed for
real - only their text is analyzed, and any dry-run checks are free.

Column names come from real table schema, not hardcoded lists.
"""

from google.cloud import bigquery

PROJECT_ID = "finops-agent-505810"

HACKERNEWS = "bigquery-public-data.hacker_news.full"
GITHUB = "bigquery-public-data.github_repos.commits"
CRYPTO = "bigquery-public-data.crypto_ethereum.transactions"
STACKOVERFLOW = "bigquery-public-data.stackoverflow.posts_questions"
NATALITY = "bigquery-public-data.samples.natality"

SELECT_STAR_TABLES = [
    HACKERNEWS,
    GITHUB,
    STACKOVERFLOW,
    NATALITY,
    "bigquery-public-data.covid19_open_data.covid19_open_data",
    "bigquery-public-data.austin_311.311_service_requests",
    "bigquery-public-data.new_york_citibike.citibike_trips",
    "bigquery-public-data.samples.shakespeare",
]

client = bigquery.Client(project=PROJECT_ID)


def get_column_names(table_id: str) -> list[str]:
    """Returns real column names for a table, fetched from BigQuery."""
    table = client.get_table(table_id)
    return [field.name for field in table.schema]


def generate_select_star_cases() -> list[dict]:
    """SELECT * cases across real, unpartitioned tables."""
    cases = []

    for table in SELECT_STAR_TABLES:
        cases.append({
            "query": f"SELECT * FROM `{table}`",
            "expected_concepts": ["select *"],
            "description": f"SELECT * on {table.split('.')[-1]}",
        })

    return cases


def generate_missing_partition_cases() -> list[dict]:
    """Queries filtering on a non-partition column of a genuinely partitioned table."""
    columns = get_column_names(CRYPTO)
    skip = {"block_timestamp", "block_number", "block_hash"}
    filter_columns = [c for c in columns if c not in skip][:10]

    cases = []
    for column in filter_columns:
        cases.append({
            "query": f"SELECT `hash`, value FROM `{CRYPTO}` WHERE `{column}` IS NOT NULL",
            "expected_concepts": ["partition"],
            "description": f"Filters on non-partition column ({column})",
        })

    return cases


def generate_wildcard_table_cases() -> list[dict]:
    """Queries against wildcard table patterns, scanning every matching table."""
    return [
        {
            "query": "SELECT * FROM `bigquery-public-data.noaa_gsod.gsod*`",
            "expected_concepts": ["wildcard"],
            "description": "Wildcard table scan across every year",
        },
        {
            "query": "SELECT station_number, temp FROM `bigquery-public-data.noaa_gsod.gsod20*`",
            "expected_concepts": ["wildcard"],
            "description": "Narrower wildcard prefix, still no _TABLE_SUFFIX filter",
        },
        {
            "query": "SELECT * FROM `bigquery-public-data.google_analytics_sample.ga_sessions_*`",
            "expected_concepts": ["wildcard"],
            "description": "Wildcard scan across a full year of daily analytics tables",
        },
        {
            "query": "SELECT totals.visits FROM `bigquery-public-data.google_analytics_sample.ga_sessions_2017*`",
            "expected_concepts": ["wildcard"],
            "description": "Wildcard scoped to a year, still no explicit suffix filter",
        },
    ]


def generate_count_distinct_cases() -> list[dict]:
    """Queries using exact COUNT(DISTINCT ...) on a large column, across tables."""
    tables_and_limits = [
        (HACKERNEWS, 6),
        (GITHUB, 4),
        (STACKOVERFLOW, 4),
    ]

    cases = []
    for table, limit in tables_and_limits:
        columns = get_column_names(table)[:limit]
        for column in columns:
            cases.append({
                "query": f"SELECT COUNT(DISTINCT `{column}`) FROM `{table}`",
                "expected_concepts": ["distinct"],
                "description": f"Exact COUNT DISTINCT on {table.split('.')[-1]}.{column}",
            })

    return cases


def generate_udf_cases() -> list[dict]:
    """Queries using a JavaScript UDF where native SQL would work and cost less."""
    return [
        {
            "query": f"""CREATE TEMP FUNCTION extractDomain(url STRING) RETURNS STRING LANGUAGE js AS \"\"\"return url.split('/')[2];\"\"\";
SELECT extractDomain(url) FROM `{HACKERNEWS}` WHERE url IS NOT NULL""",
            "expected_concepts": ["udf"],
            "description": "JS UDF doing simple string parsing REGEXP_EXTRACT could do natively",
        },
        {
            "query": f"""CREATE TEMP FUNCTION wordCount(text STRING) RETURNS INT64 LANGUAGE js AS \"\"\"return text.split(' ').length;\"\"\";
SELECT wordCount(title) FROM `{HACKERNEWS}` WHERE title IS NOT NULL""",
            "expected_concepts": ["udf"],
            "description": "JS UDF counting words, native SQL alternative exists",
        },
        {
            "query": f"""CREATE TEMP FUNCTION toUpper(s STRING) RETURNS STRING LANGUAGE js AS \"\"\"return s.toUpperCase();\"\"\";
SELECT toUpper(title) FROM `{HACKERNEWS}` WHERE title IS NOT NULL""",
            "expected_concepts": ["udf"],
            "description": "JS UDF uppercasing text, UPPER() does this natively",
        },
        {
            "query": f"""CREATE TEMP FUNCTION isLong(title STRING) RETURNS BOOL LANGUAGE js AS \"\"\"return title.length > 50;\"\"\";
SELECT title FROM `{HACKERNEWS}` WHERE isLong(title)""",
            "expected_concepts": ["udf"],
            "description": "JS UDF checking string length, LENGTH() does this natively",
        },
    ]


def generate_fan_out_join_cases() -> list[dict]:
    """Self-joins that multiply rows via a one-to-many relationship."""
    return [
        {
            "query": f"""SELECT s.title, c.text
FROM `{HACKERNEWS}` s
JOIN `{HACKERNEWS}` c ON c.parent = s.id
WHERE s.type = 'story'""",
            "expected_concepts": ["join"],
            "description": "Self-join on parent, one story fans out to many comments",
        },
        {
            "query": f"""SELECT s.title, c.by, c.text
FROM `{HACKERNEWS}` s
JOIN `{HACKERNEWS}` c ON c.parent = s.id
JOIN `{HACKERNEWS}` r ON r.parent = c.id
WHERE s.type = 'story'""",
            "expected_concepts": ["join"],
            "description": "Two-level self-join, comments fan out to replies too",
        },
        {
            "query": f"""SELECT s.by, COUNT(c.id)
FROM `{HACKERNEWS}` s
JOIN `{HACKERNEWS}` c ON c.parent = s.id
GROUP BY s.by""",
            "expected_concepts": ["join"],
            "description": "Self-join with no type filter at all, widest possible fan-out",
        },
    ]


def generate_known_fine_cases() -> list[dict]:
    """Queries that are already efficient - should not be flagged by anything."""
    cases = []

    # One good counterpart per select-star table: same table, few real columns.
    for table in SELECT_STAR_TABLES:
        columns = get_column_names(table)[:2]
        column_list = ", ".join(columns)
        cases.append({
            "query": f"SELECT {column_list} FROM `{table}` LIMIT 100",
            "expected_concepts": [],
            "description": f"Few real columns on {table.split('.')[-1]}, not SELECT *",
        })

    # Correctly filtered on the partition column, a few different real ranges.
    date_ranges = [
        ("2024-01-01", "2024-01-02"),
        ("2023-06-01", "2023-06-02"),
        ("2024-12-01", "2024-12-31"),
    ]
    for start, end in date_ranges:
        cases.append({
            "query": f"SELECT `hash`, value FROM `{CRYPTO}` WHERE block_timestamp BETWEEN TIMESTAMP('{start}') AND TIMESTAMP('{end}')",
            "expected_concepts": [],
            "description": f"Properly filtered on partition column ({start} to {end})",
        })

    # Approximate distinct instead of exact, on a couple more tables.
    for table in [GITHUB, STACKOVERFLOW]:
        first_column = get_column_names(table)[0]
        cases.append({
            "query": f"SELECT APPROX_COUNT_DISTINCT(`{first_column}`) FROM `{table}`",
            "expected_concepts": [],
            "description": f"Approximate distinct count on {table.split('.')[-1]}, not exact",
        })

    # A single real table, not a wildcard pattern.
    cases.append({
        "query": "SELECT station_number, temp FROM `bigquery-public-data.noaa_gsod.gsod2020`",
        "expected_concepts": [],
        "description": "A single real table, not a wildcard pattern",
    })

    # Native SQL doing the same job a UDF would.
    cases.append({
        "query": f"SELECT REGEXP_EXTRACT(url, r'https?://([^/]+)') FROM `{HACKERNEWS}` WHERE url IS NOT NULL",
        "expected_concepts": [],
        "description": "Native SQL doing the same job the UDF cases do, no UDF used",
    })
    cases.append({
        "query": f"SELECT UPPER(title) FROM `{HACKERNEWS}` WHERE title IS NOT NULL LIMIT 100",
        "expected_concepts": [],
        "description": "Native UPPER() instead of a JS UDF",
    })

    # No join at all, where a join isn't actually needed.
    cases.append({
        "query": f"SELECT title FROM `{HACKERNEWS}` WHERE type = 'story' LIMIT 100",
        "expected_concepts": [],
        "description": "No join at all, simple filtered query",
    })

    return cases


if __name__ == "__main__":
    cases = (
        generate_select_star_cases()
        + generate_missing_partition_cases()
        + generate_wildcard_table_cases()
        + generate_count_distinct_cases()
        + generate_udf_cases()
        + generate_fan_out_join_cases()
        + generate_known_fine_cases()
    )
    print(f"Generated {len(cases)} cases")

    by_category = {}
    for case in cases:
        if case["expected_concepts"]:
            category = case["expected_concepts"][0]
        else:
            category = "known_fine"

        if category in by_category:
            by_category[category] = by_category[category] + 1
        else:
            by_category[category] = 1

    for category, count in by_category.items():
        print(f"  {category}: {count}")