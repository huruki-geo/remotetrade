from __future__ import annotations

import os

import requests


def send_discord_message(content: str, webhook_url: str | None = None) -> None:
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return

    response = requests.post(url, json={"content": content[:1900]}, timeout=10)
    response.raise_for_status()
