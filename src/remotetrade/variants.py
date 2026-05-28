from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LimitPaperVariant:
    id: str
    min_net_spread_pct: float
    price_improvement_bps: float


def load_limit_paper_variants(raw: str) -> list[LimitPaperVariant]:
    variants: list[LimitPaperVariant] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = item.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid LIMIT_PAPER_VARIANTS item: {item!r}")
        variant_id = _safe_id(parts[0])
        variants.append(
            LimitPaperVariant(
                id=variant_id,
                min_net_spread_pct=float(parts[1]),
                price_improvement_bps=float(parts[2]),
            )
        )
    if not variants:
        raise ValueError("LIMIT_PAPER_VARIANTS must define at least one variant.")
    return variants


def file_suffix(product_id: str, variant_id: str) -> str:
    return _safe_id(f"{product_id.lower()}_{variant_id}")


def _safe_id(value: str) -> str:
    normalized = value.strip().replace("-", "_").replace("/", "_").replace(".", "_")
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", normalized)
    normalized = normalized.strip("_")
    if not normalized:
        raise ValueError(f"Invalid empty id from {value!r}")
    return normalized
