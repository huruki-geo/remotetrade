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
        body.append(f"- **{tick.title}** `{_ja_status(tick.status)}`")
        body.extend(f"  - {line}" for line in tick.lines)
    return "\n".join(body)


def format_discord_error(title: str, error: Exception | str) -> str:
    return f"**エラー {title}**\n- `{error}`"


def _overall_status(ticks: list[DiscordTick]) -> str:
    statuses = {tick.status for tick in ticks}
    if statuses & {"opened", "closed", "opportunity", "placed", "both_filled", "buy_only", "sell_only"}:
        return "売買あり"
    if statuses & {"error"}:
        return "エラー"
    return "待機"


def _ja_status(status: str) -> str:
    return {
        "opened": "新規建て",
        "closed": "決済",
        "opportunity": "機会あり",
        "placed": "指値配置",
        "both_filled": "両足約定",
        "buy_only": "買いだけ約定",
        "sell_only": "売りだけ約定",
        "no_candidate": "候補なし",
        "none": "なし",
        "wait": "待機",
        "hold": "保有中",
        "pending": "指値待ち",
        "expired": "期限切れ",
        "no_pending": "未発注",
    }.get(status, status)


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
        ("position", "ポジション"),
        ("pending", "待機中の指値"),
        ("realized_pnl", "実現損益"),
        ("unrealized_pnl", "含み損益"),
        ("pnl", "今回損益"),
        ("net_profit", "純利益"),
        ("est_profit", "想定利益"),
        ("net_spread", "純スプレッド"),
        ("spread", "スプレッド"),
        ("z", "z"),
        ("fill", "約定判定"),
        ("reason", "理由"),
        ("buy", "買い"),
        ("sell", "売り"),
        ("long", "ロング"),
        ("short", "ショート"),
        ("signal", "シグナル"),
    ]
    lines = []
    for key, label in labels:
        if key in fields:
            lines.append(f"{label}: `{fields[key]}`")
    return lines[:6]
