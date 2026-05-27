from __future__ import annotations

import os

import requests


def send_discord_message(content: str, webhook_url: str | None = None) -> bool:
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print("discord notification skipped: DISCORD_WEBHOOK_URL is not set", flush=True)
        return False

    response = requests.post(url, json={"content": content[:1900]}, timeout=10)
    response.raise_for_status()
    return True
