from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from remotetrade.config import Settings


@dataclass(frozen=True)
class StockCategory:
    id: str
    label: str
    query: str
    market_slugs: list[str]
    up_long: list[str]
    up_short: list[str]
    down_long: list[str]
    down_short: list[str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StockCategory":
        category_id = _safe_id(payload["id"], "category")
        return cls(
            id=category_id,
            label=str(payload.get("label") or category_id),
            query=str(payload["query"]),
            market_slugs=[str(item) for item in payload.get("market_slugs", [])],
            up_long=_symbols(payload.get("up_long")),
            up_short=_symbols(payload.get("up_short")),
            down_long=_symbols(payload.get("down_long")),
            down_short=_symbols(payload.get("down_short")),
        )


@dataclass(frozen=True)
class StockPattern:
    id: str
    label: str
    entry_threshold: float
    strong_threshold: float
    take_profit_pct: float
    stop_loss_pct: float
    hold_seconds: int
    risk_fraction: float
    max_trade_size_usd: float
    prefer_short: bool
    categories: list[StockCategory]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StockPattern":
        pattern_id = _safe_id(payload["id"], "pattern")
        categories = [StockCategory.from_dict(item) for item in payload.get("categories", [])]
        if not categories:
            raise ValueError(f"Stock pattern {pattern_id!r} must define at least one category.")
        return cls(
            id=pattern_id,
            label=str(payload.get("label") or pattern_id),
            entry_threshold=float(payload["entry_threshold"]),
            strong_threshold=float(payload["strong_threshold"]),
            take_profit_pct=float(payload["take_profit_pct"]),
            stop_loss_pct=float(payload["stop_loss_pct"]),
            hold_seconds=int(payload["hold_seconds"]),
            risk_fraction=float(payload["risk_fraction"]),
            max_trade_size_usd=float(payload["max_trade_size_usd"]),
            prefer_short=bool(payload.get("prefer_short", False)),
            categories=categories,
        )

    def apply(self, settings: Settings) -> Settings:
        data_dir = settings.state_path.parent
        return replace(
            settings,
            entry_threshold=self.entry_threshold,
            strong_threshold=self.strong_threshold,
            take_profit_pct=self.take_profit_pct,
            stop_loss_pct=self.stop_loss_pct,
            hold_seconds=self.hold_seconds,
            risk_fraction=self.risk_fraction,
            max_trade_size_usd=self.max_trade_size_usd,
            state_path=data_dir / f"stock_{self.id}_state.json",
            trades_path=data_dir / f"stock_{self.id}_trades.csv",
            ticks_path=data_dir / f"stock_{self.id}_ticks.csv",
        )


def load_stock_patterns(path: Path) -> list[StockPattern]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("stock_patterns.json must contain a list of pattern objects.")
    return [StockPattern.from_dict(item) for item in payload]


def _safe_id(value: Any, label: str) -> str:
    item_id = str(value)
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", item_id):
        raise ValueError(f"{label} id must be filesystem-safe: {item_id!r}")
    return item_id


def _symbols(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("symbol lists must be arrays.")
    return [str(item).upper() for item in value]
