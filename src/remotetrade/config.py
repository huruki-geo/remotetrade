from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value in (None, "") else float(value)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value in (None, "") else int(value)


@dataclass(frozen=True)
class Settings:
    gamma_url: str = "https://gamma-api.polymarket.com"
    coinbase_url: str = "https://api.exchange.coinbase.com"
    market_slug: str | None = None
    market_query: str = "BTC Up or Down 5m"
    crypto_product_id: str = "BTC-USD"
    poll_seconds: int = 15
    hold_seconds: int = 300
    entry_threshold: float = 0.06
    strong_threshold: float = 0.10
    take_profit_pct: float = 0.004
    stop_loss_pct: float = -0.0025
    risk_fraction: float = 0.10
    max_trade_size_usd: float = 30.0
    min_trade_size_usd: float = 10.0
    start_cash_usd: float = 300.0
    state_path: Path = Path("data/paper_state.json")
    trades_path: Path = Path("data/trades.csv")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        market_slug = os.getenv("MARKET_SLUG") or None
        return cls(
            gamma_url=os.getenv("POLYMARKET_GAMMA_URL", cls.gamma_url),
            coinbase_url=os.getenv("COINBASE_URL", cls.coinbase_url),
            market_slug=market_slug,
            market_query=os.getenv("MARKET_QUERY", cls.market_query),
            crypto_product_id=os.getenv("CRYPTO_PRODUCT_ID", cls.crypto_product_id),
            poll_seconds=env_int("POLL_SECONDS", cls.poll_seconds),
            hold_seconds=env_int("HOLD_SECONDS", cls.hold_seconds),
            entry_threshold=env_float("ENTRY_THRESHOLD", cls.entry_threshold),
            strong_threshold=env_float("STRONG_THRESHOLD", cls.strong_threshold),
            take_profit_pct=env_float("TAKE_PROFIT_PCT", cls.take_profit_pct),
            stop_loss_pct=env_float("STOP_LOSS_PCT", cls.stop_loss_pct),
            risk_fraction=env_float("RISK_FRACTION", cls.risk_fraction),
            max_trade_size_usd=env_float("MAX_TRADE_SIZE_USD", cls.max_trade_size_usd),
            min_trade_size_usd=env_float("MIN_TRADE_SIZE_USD", cls.min_trade_size_usd),
            start_cash_usd=env_float("START_CASH_USD", cls.start_cash_usd),
            state_path=Path(os.getenv("STATE_PATH", str(cls.state_path))),
            trades_path=Path(os.getenv("TRADES_PATH", str(cls.trades_path))),
        )
