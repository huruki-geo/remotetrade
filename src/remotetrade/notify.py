from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class DiscordTick:
    title: str
    status: str
    lines: list[str]


def send_discord_message(content: str, webhook_url: str | None = None) -> bool:
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print("discord notification skipped: DISCORD_WEBHOOK_URL is not set", flush=True)
        return False

    response = requests.post(url, json={"content": content[:1900]}, timeout=10)
    response.raise_for_status()
    return True


def format_discord_tick(title: str, lines: list[str]) -> str:
    ticks = [_summarize_line(line) for line in lines]
    status = _overall_status(ticks)
    body = [f"**{status} {title}**"]
    for tick in ticks:
        body.append(f"- **{tick.title}** `{tick.status}`")
        body.extend(f"  - {line}" for line in tick.lines)
    return "\n".join(body)


def format_discord_error(title: str, error: Exception | str) -> str:
    return f"**ERROR {title}**\n- `{error}`"


def _overall_status(ticks: list[DiscordTick]) -> str:
    statuses = {tick.status for tick in ticks}
    if statuses & {"opened", "closed", "opportunity", "placed", "both_filled", "buy_only", "sell_only"}:
        return "TRADE"
    if statuses & {"error"}:
        return "ERROR"
    return "WAIT"


def _summarize_line(line: str) -> DiscordTick:
    title_match = re.match(r"\[([^\]]+)\]\s+([^:]+):\s*(.*)", line)
    if not title_match:
        return DiscordTick("Bot", "info", [line])

    title, status, rest = title_match.groups()
    fields = _parse_fields(rest)
    interesting = _interesting_fields(fields)
    if not interesting:
        interesting = [rest]
    return DiscordTick(title, status.strip(), interesting)


def _parse_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in re.finditer(r"([a-zA-Z_]+)=([^ ]+)", text):
        fields[match.group(1)] = match.group(2)
    return fields


def _interesting_fields(fields: dict[str, str]) -> list[str]:
    labels = [
        ("position", "position"),
        ("pending", "pending"),
        ("realized_pnl", "realized"),
        ("unrealized_pnl", "unrealized"),
        ("pnl", "pnl"),
        ("net_profit", "net profit"),
        ("est_profit", "est profit"),
        ("net_spread", "net spread"),
        ("spread", "spread"),
        ("z", "z"),
        ("fill", "fill"),
        ("reason", "reason"),
        ("buy", "buy"),
        ("sell", "sell"),
        ("long", "long"),
        ("short", "short"),
        ("signal", "signal"),
    ]
    lines = []
    for key, label in labels:
        if key in fields:
            lines.append(f"{label}: `{fields[key]}`")
    return lines[:6]
