from __future__ import annotations

import csv
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
