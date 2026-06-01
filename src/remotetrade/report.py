from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class CsvSummary:
    rows: int
    recent_rows: int
    latest: dict[str, str]


def build_daily_report(data_dir: Path, now: datetime | None = None, hours: int = 24) -> str:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    limit_ticks = _summarize_many(data_dir.glob("limit_paper*_ticks.csv"), since)
    limit_trades = _summarize_many(data_dir.glob("limit_paper*_trades.csv"), since)
    spread_ticks = _summarize_csv(data_dir / "spread_ticks.csv", since)
    wick_ticks = _summarize_csv(data_dir / "wick_ticks.csv", since)
    snapshots = _count_lines(data_dir / "orderbook_snapshots.jsonl")
    states = _state_pnls(data_dir)

    latest_limit = limit_ticks.latest
    realized = latest_limit.get("realized_pnl") or _format_float(states.get("limit_paper", 0.0))
    both = latest_limit.get("both_filled", "0")
    buy_only = latest_limit.get("buy_only", "0")
    sell_only = latest_limit.get("sell_only", "0")
    expired = latest_limit.get("expired", "0")
    one_leg = _safe_int(buy_only) + _safe_int(sell_only)

    lines = [
        "**RemoteTrade 日次レポート**",
        "- Polymarket実弾判定レビュー: `2026-06-15 JST` / 到達しても自動発注は有効化しない",
        f"- 対象期間: 直近{hours}時間",
        f"- 指値裁定: tick `{limit_ticks.recent_rows}` / 約定 `{limit_trades.recent_rows}` / 実現損益 `{realized}`",
        f"- 約定内訳: 両足 `{both}` / 片足 `{one_leg}` / 期限切れ `{expired}`",
        f"- 板スナップショット: `{snapshots}` 行",
        f"- スプレッドtick: `{spread_ticks.recent_rows}` / ひげ取りtick: `{wick_ticks.recent_rows}`",
    ]
    if states:
        state_line = " / ".join(f"{name} `{_format_float(value)}`" for name, value in sorted(states.items()))
        lines.append(f"- state損益: {state_line}")
    latest_time = latest_limit.get("time")
    if latest_time:
        lines.append(f"- 最終tick: `{latest_time}`")
    return "\n".join(lines)


def _summarize_csv(path: Path, since: datetime) -> CsvSummary:
    if not path.exists():
        return CsvSummary(0, 0, {})
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(row)
    recent = [row for row in rows if _is_recent(row.get("time", ""), since)]
    latest = rows[-1] if rows else {}
    return CsvSummary(len(rows), len(recent), latest)


def _summarize_many(paths, since: datetime) -> CsvSummary:
    total = 0
    recent_total = 0
    latest: dict[str, str] = {}
    latest_time: datetime | None = None
    for path in sorted(paths):
        summary = _summarize_csv(path, since)
        total += summary.rows
        recent_total += summary.recent_rows
        raw_time = summary.latest.get("time", "")
        try:
            value = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            value = None
        if value and (latest_time is None or value > latest_time):
            latest_time = value
            latest = summary.latest
    return CsvSummary(total, recent_total, latest)


def _is_recent(raw_time: str, since: datetime) -> bool:
    if not raw_time:
        return False
    try:
        value = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value >= since


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def _state_pnls(data_dir: Path) -> dict[str, float]:
    pnls: dict[str, float] = {}
    for path in data_dir.glob("*_state.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pnl = payload.get("realized_pnl")
        if pnl is None:
            continue
        name = path.name.removesuffix("_state.json")
        pnls[name] = float(pnl)
    return pnls


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def _format_float(value: float) -> str:
    return f"{value:.4f}"
