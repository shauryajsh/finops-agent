"""Sends messages to Slack via an incoming webhook."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]


def send_slack_message(text: str):
    """Posts a message to the configured Slack channel."""
    response = requests.post(SLACK_WEBHOOK_URL, json={"text": text})

    if response.status_code != 200:
        raise Exception(f"Slack post failed: {response.status_code} {response.text}")


if __name__ == "__main__":
    send_slack_message("FinOps agent test message - webhook is working.")