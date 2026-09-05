"""Runs the full FinOps agent workflow: diagnoses flagged queries, opens a
GitHub issue per query, then posts a Slack digest linking to each issue.
"""

from llm_agent import get_flagged_queries, diagnose
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


def build_slack_digest(flagged_queries, issue_urls) -> str:
    """Builds one summary message listing each flagged query with a link to its issue."""
    lines = [f"FinOps weekly digest: {len(flagged_queries)} expensive queries flagged"]
    lines.append("")

    for row, issue_url in zip(flagged_queries, issue_urls):
        lines.append(f"- {row.query_owner}: ${row.estimated_cost_usd:.6f} (avg ${row.avg_cost_usd:.6f}) - {issue_url}")

    return "\n".join(lines)


def run():
    flagged_queries = get_flagged_queries()

    if len(flagged_queries) == 0:
        print("No flagged queries this run.")
        return

    issue_urls = []

    for row in flagged_queries:
        diagnosis_text = diagnose(row.query)

        issue_title = f"Expensive query flagged: {row.query_owner} (${row.estimated_cost_usd:.6f})"
        issue_body = build_issue_body(row, diagnosis_text)
        issue_url = create_github_issue(issue_title, issue_body)
        issue_urls.append(issue_url)

        print(f"Opened issue for {row.query_owner}: {issue_url}")

    digest = build_slack_digest(flagged_queries, issue_urls)
    send_slack_message(digest)
    print("Posted Slack digest.")


if __name__ == "__main__":
    run()