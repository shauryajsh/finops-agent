"""Runs the full FinOps agent workflow: diagnoses flagged queries and
recurring patterns, opens a GitHub issue for each, then posts a Slack
digest linking to all of them.
"""

from llm_agent import get_flagged_queries, get_recurring_queries, diagnose
from slack_client import send_slack_message
from github_client import create_github_issue


def build_issue_body(row, diagnosis_text: str) -> str:
    """Builds the full GitHub issue body for one flagged query."""
    return f"""**Owner:** {row.query_owner}
**Cost:** ${row.estimated_cost_usd:.6f} (project average: ${row.avg_cost_usd:.6f})

**Query:**
```sql
{row.query}
```

**Diagnosis:**
{diagnosis_text}
"""


def build_recurring_issue_body(row) -> str:
    """Builds the GitHub issue body for one recurring query pattern."""
    return f"""**Most recent owner:** {row.most_recent_owner}
**Run count:** {row.run_count}
**Total cost across all runs:** ${row.total_cost_usd:.6f} (avg ${row.avg_cost_per_run_usd:.6f} per run)

**Query:**
```sql
{row.sample_query}
```

**Diagnosis:**
This exact query ran {row.run_count} times, adding up to ${row.total_cost_usd:.6f} even though no single run looked expensive alone. Materialize the result into a smaller table and read from that instead of rescanning the source table every time.
"""


def build_slack_digest(flagged_queries, flagged_urls, recurring_queries, recurring_urls) -> str:
    """Builds one summary message linking to every issue opened this run."""
    lines = [f"FinOps weekly digest: {len(flagged_queries)} expensive queries, {len(recurring_queries)} recurring patterns flagged"]
    lines.append("")

    if flagged_queries:
        lines.append("Expensive queries:")
        for row, issue_url in zip(flagged_queries, flagged_urls):
            lines.append(f"- {row.query_owner}: ${row.estimated_cost_usd:.6f} (avg ${row.avg_cost_usd:.6f}) - {issue_url}")
        lines.append("")

    if recurring_queries:
        lines.append("Recurring patterns:")
        for row, issue_url in zip(recurring_queries, recurring_urls):
            lines.append(f"- {row.most_recent_owner}: {row.run_count} runs, ${row.total_cost_usd:.6f} total - {issue_url}")

    return "\n".join(lines)


def run():
    flagged_queries = get_flagged_queries()
    recurring_queries = get_recurring_queries()

    if len(flagged_queries) == 0 and len(recurring_queries) == 0:
        print("Nothing flagged this run.")
        return

    flagged_urls = []
    for row in flagged_queries:
        diagnosis_text = diagnose(row.query)

        issue_title = f"Expensive query flagged: {row.query_owner} (${row.estimated_cost_usd:.6f})"
        issue_body = build_issue_body(row, diagnosis_text)
        issue_url = create_github_issue(issue_title, issue_body)
        flagged_urls.append(issue_url)

        print(f"Opened issue for {row.query_owner}: {issue_url}")

    recurring_urls = []
    for row in recurring_queries:
        issue_title = f"Recurring query pattern: {row.most_recent_owner} ({row.run_count} runs, ${row.total_cost_usd:.6f} total)"
        issue_body = build_recurring_issue_body(row)
        issue_url = create_github_issue(issue_title, issue_body)
        recurring_urls.append(issue_url)

        print(f"Opened issue for recurring pattern ({row.most_recent_owner}): {issue_url}")

    digest = build_slack_digest(flagged_queries, flagged_urls, recurring_queries, recurring_urls)
    send_slack_message(digest)
    print("Posted Slack digest.")


if __name__ == "__main__":
    run()