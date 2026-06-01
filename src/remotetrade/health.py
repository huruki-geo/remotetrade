from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class HealthReport:
    ok: bool
    message: str


def build_health_report(data_dir: Path, max_tick_age_seconds: int, min_free_disk_mb: int) -> HealthReport:
    issues: list[str] = []
    lines = ["**RemoteTrade ヘルスチェック**"]

    tick_files = _limit_paper_tick_files(data_dir)
    if not tick_files:
        issues.append("limit_paper tickファイルがありません")
    for path in tick_files:
        latest = _latest_tick_time(path)
        if latest is None:
            issues.append(f"{path.name}: tick時刻を読めません")
            continue
        age = (datetime.now(UTC) - latest).total_seconds()
        lines.append(f"- {path.name}: 最終tick `{latest.isoformat(timespec='seconds')}` / {age:.0f}秒前")
        if age > max_tick_age_seconds:
            issues.append(f"{path.name}: 最終tickが古いです ({age:.0f}秒前)")

    stream_paths = [
        data_dir / "polymarket_crypto_prices.jsonl",
        data_dir / "polymarket_btc_5m_clob.jsonl",
    ]
    if any(path.exists() for path in stream_paths):
        for path in stream_paths:
            latest = _latest_jsonl_time(path)
            if latest is None:
                issues.append(f"{path.name}: no readable stream event")
                continue
            age = (datetime.now(UTC) - latest).total_seconds()
            lines.append(f"- {path.name}: latest event `{latest.isoformat(timespec='seconds')}` / {age:.0f}s ago")
            if age > max_tick_age_seconds:
                issues.append(f"{path.name}: stream event is stale ({age:.0f}s ago)")

    discovery_path = data_dir / "venue_market_discoveries.jsonl"
    if discovery_path.exists():
        latest = _latest_jsonl_time(discovery_path)
        if latest is None:
            issues.append(f"{discovery_path.name}: no readable discovery event")
        else:
            age = (datetime.now(UTC) - latest).total_seconds()
            lines.append(f"- {discovery_path.name}: latest discovery `{latest.isoformat(timespec='seconds')}` / {age:.0f}s ago")
            if age > max_tick_age_seconds * 2:
                issues.append(f"{discovery_path.name}: discovery is stale ({age:.0f}s ago)")

    for maker_probe_path in (
        data_dir / "maker_probe_ticks.csv",
        data_dir / "bitbank_poly_maker_events.csv",
        data_dir / "coincheck_poly_maker_events.csv",
    ):
        if not maker_probe_path.exists():
            continue
        latest = _latest_tick_time(maker_probe_path)
        if latest is None:
            issues.append(f"{maker_probe_path.name}: no readable probe tick")
        else:
            age = (datetime.now(UTC) - latest).total_seconds()
            lines.append(f"- {maker_probe_path.name}: latest probe `{latest.isoformat(timespec='seconds')}` / {age:.0f}s ago")
            if age > max_tick_age_seconds:
                issues.append(f"{maker_probe_path.name}: probe is stale ({age:.0f}s ago)")

    for route_probe_path in (
        data_dir / "bitbank_route_probes.jsonl",
        data_dir / "dex_route_probes.jsonl",
        data_dir / "bsc_qash_route_probes.jsonl",
        data_dir / "boba_cex_dex_probes.jsonl",
        data_dir / "boba_zencha_probes.jsonl",
        data_dir / "boba_synapse_probes.jsonl",
        data_dir / "boba_atomic_route_probes.jsonl",
    ):
        if not route_probe_path.exists():
            continue
        latest = _latest_jsonl_time(route_probe_path)
        if latest is None:
            issues.append(f"{route_probe_path.name}: no readable route probe")
            continue
        age = (datetime.now(UTC) - latest).total_seconds()
        lines.append(f"- {route_probe_path.name}: latest route probe `{latest.isoformat(timespec='seconds')}` / {age:.0f}s ago")
        if age > max_tick_age_seconds * 2:
            issues.append(f"{route_probe_path.name}: route probe is stale ({age:.0f}s ago)")

    usage = shutil.disk_usage(data_dir if data_dir.exists() else Path("."))
    free_mb = usage.free / 1024 / 1024
    lines.append(f"- 空きディスク: `{free_mb:.0f} MB`")
    if free_mb < min_free_disk_mb:
        issues.append(f"空きディスク不足 ({free_mb:.0f} MB)")

    if issues:
        lines.insert(1, "- 状態: `要確認`")
        lines.extend(f"- 問題: {issue}" for issue in issues)
        return HealthReport(False, "\n".join(lines))

    lines.insert(1, "- 状態: `正常`")
    return HealthReport(True, "\n".join(lines))


def _limit_paper_tick_files(data_dir: Path) -> list[Path]:
    tick_files = sorted(data_dir.glob("limit_paper*_ticks.csv"))
    portfolio_files = [path for path in tick_files if path.name != "limit_paper_ticks.csv"]
    return portfolio_files or tick_files


def _latest_tick_time(path: Path) -> datetime | None:
    latest: datetime | None = None
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("time") or ""
            try:
                value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            latest = value
    return latest


def _latest_jsonl_time(path: Path) -> datetime | None:
    if not path.exists():
        return None
    latest: datetime | None = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
                raw = payload.get("received_at") or payload.get("observed_at") or ""
                value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except (json.JSONDecodeError, AttributeError, ValueError):
                continue
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            latest = value
    return latest
