"""Creates GitHub issues for flagged BigQuery queries."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = "shauryajsh/finops-agent"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/issues"


def create_github_issue(title: str, body: str) -> str:
    """Opens a new issue on the configured repo, returns its URL."""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    payload = {"title": title, "body": body}

    response = requests.post(GITHUB_API_URL, headers=headers, json=payload)

    if response.status_code != 201:
        raise Exception(f"GitHub issue creation failed: {response.status_code} {response.text}")

    return response.json()["html_url"]


if __name__ == "__main__":
    url = create_github_issue(
        "FinOps agent test issue",
        "Test issue created by the FinOps agent to confirm the GitHub client works.",
    )
    print(f"Issue created: {url}")