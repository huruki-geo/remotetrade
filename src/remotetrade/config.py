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
    arbitrage_notional_usd: float = 100.0
    arbitrage_fee_bps: float = 20.0
    arbitrage_min_net_spread_pct: float = 0.001
    limit_maker_fee_bps: float = 10.0
    limit_price_improvement_bps: float = 1.0
    wick_granularity_seconds: int = 60
    wick_min_ratio: float = 0.55
    wick_min_range_pct: float = 0.001
    spread_window: int = 30
    spread_entry_zscore: float = 2.0
    spread_exit_zscore: float = 0.5
    spread_stop_zscore: float = 4.0
    spread_notional_usd: float = 100.0
    state_path: Path = Path("data/paper_state.json")
    trades_path: Path = Path("data/trades.csv")
    ticks_path: Path = Path("data/ticks.csv")
    arbitrage_ticks_path: Path = Path("data/arbitrage_ticks.csv")

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
            arbitrage_notional_usd=env_float("ARBITRAGE_NOTIONAL_USD", cls.arbitrage_notional_usd),
            arbitrage_fee_bps=env_float("ARBITRAGE_FEE_BPS", cls.arbitrage_fee_bps),
            arbitrage_min_net_spread_pct=env_float(
                "ARBITRAGE_MIN_NET_SPREAD_PCT",
                cls.arbitrage_min_net_spread_pct,
            ),
            limit_maker_fee_bps=env_float("LIMIT_MAKER_FEE_BPS", cls.limit_maker_fee_bps),
            limit_price_improvement_bps=env_float("LIMIT_PRICE_IMPROVEMENT_BPS", cls.limit_price_improvement_bps),
            wick_granularity_seconds=env_int("WICK_GRANULARITY_SECONDS", cls.wick_granularity_seconds),
            wick_min_ratio=env_float("WICK_MIN_RATIO", cls.wick_min_ratio),
            wick_min_range_pct=env_float("WICK_MIN_RANGE_PCT", cls.wick_min_range_pct),
            spread_window=env_int("SPREAD_WINDOW", cls.spread_window),
            spread_entry_zscore=env_float("SPREAD_ENTRY_ZSCORE", cls.spread_entry_zscore),
            spread_exit_zscore=env_float("SPREAD_EXIT_ZSCORE", cls.spread_exit_zscore),
            spread_stop_zscore=env_float("SPREAD_STOP_ZSCORE", cls.spread_stop_zscore),
            spread_notional_usd=env_float("SPREAD_NOTIONAL_USD", cls.spread_notional_usd),
            state_path=Path(os.getenv("STATE_PATH", str(cls.state_path))),
            trades_path=Path(os.getenv("TRADES_PATH", str(cls.trades_path))),
            ticks_path=Path(os.getenv("TICKS_PATH", str(cls.ticks_path))),
            arbitrage_ticks_path=Path(os.getenv("ARBITRAGE_TICKS_PATH", str(cls.arbitrage_ticks_path))),
        )
