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
    body = [
        f"**{status} | {title}**",
        "- フェーズ: `paper-only`",
        "- 主レーン: `Polymarket公開シグナル活用 Coincheck BTC/JPY post-only 紙トレード (未実装)`",
        "- 並走レーン: `Polymarket公開シグナル活用 bitbank BTC/JPY maker 紙トレード (収集中)`",
        "- 探索レーン: `アビトラ候補検証 (paper-only)`",
        "- Coincheck BTC/JPY取引所手数料: `maker 0 bps / taker 0 bps`",
        "- 別途評価: `spread / 約定可能性 / 遅延`",
        "- Polymarket: `公開シグナル参照のみ`",
        "**今回の観測**",
    ]
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
            lines.append(f"{label}: `{_ja_value(fields[key])}`")
    return lines[:6]


def _ja_value(value: str) -> str:
    return {
        "NONE": "なし",
        "none": "なし",
        "no_pending": "未発注",
        "both_filled": "両足約定",
        "buy_only": "買いだけ約定",
        "sell_only": "売りだけ約定",
        "neither_limit_crossed": "どちらも未約定",
        "both_limits_crossed": "両方の指値に到達",
        "sell_leg_missed": "売り足未約定",
        "buy_leg_missed": "買い足未約定",
        "net_spread_below_threshold": "純スプレッド不足",
        "allowed": "許可",
    }.get(value, value)
