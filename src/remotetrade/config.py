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
    crypto_product_ids: tuple[str, ...] = ("BTC-USD",)
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
    arbitrage_safety_bps: float = 5.0
    limit_maker_fee_bps: float = 10.0
    limit_taker_fee_bps: float = 20.0
    limit_price_improvement_bps: float = 1.0
    limit_order_ttl_ticks: int = 3
    limit_max_hedge_slippage_bps: float = 25.0
    limit_paper_variants: str = "normal:0.001:1.0,loose:0.0005:1.0,strict:0.002:1.0"
    wick_granularity_seconds: int = 60
    wick_min_ratio: float = 0.55
    wick_min_range_pct: float = 0.001
    spread_window: int = 30
    spread_entry_zscore: float = 2.0
    spread_exit_zscore: float = 0.5
    spread_stop_zscore: float = 4.0
    spread_notional_usd: float = 100.0
    health_max_tick_age_seconds: int = 300
    health_min_free_disk_mb: int = 512
    replay_required_win_rate: float = 0.70
    replay_min_trades: int = 30
    replay_imbalance_threshold: float = 0.20
    replay_fee_per_share: float = 0.0
    discovery_max_order_notional_jpy: float = 2_000.0
    discovery_max_order_notional_usdt: float = 20.0
    discovery_min_depth_jpy: float = 10_000.0
    discovery_min_depth_usdt: float = 100.0
    discovery_max_spread_bps: float = 500.0
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
            crypto_product_ids=_env_csv("CRYPTO_PRODUCT_IDS", cls.crypto_product_ids),
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
            arbitrage_safety_bps=env_float("ARBITRAGE_SAFETY_BPS", cls.arbitrage_safety_bps),
            limit_maker_fee_bps=env_float("LIMIT_MAKER_FEE_BPS", cls.limit_maker_fee_bps),
            limit_taker_fee_bps=env_float("LIMIT_TAKER_FEE_BPS", cls.limit_taker_fee_bps),
            limit_price_improvement_bps=env_float("LIMIT_PRICE_IMPROVEMENT_BPS", cls.limit_price_improvement_bps),
            limit_order_ttl_ticks=env_int("LIMIT_ORDER_TTL_TICKS", cls.limit_order_ttl_ticks),
            limit_max_hedge_slippage_bps=env_float(
                "LIMIT_MAX_HEDGE_SLIPPAGE_BPS",
                cls.limit_max_hedge_slippage_bps,
            ),
            limit_paper_variants=os.getenv("LIMIT_PAPER_VARIANTS", cls.limit_paper_variants),
            wick_granularity_seconds=env_int("WICK_GRANULARITY_SECONDS", cls.wick_granularity_seconds),
            wick_min_ratio=env_float("WICK_MIN_RATIO", cls.wick_min_ratio),
            wick_min_range_pct=env_float("WICK_MIN_RANGE_PCT", cls.wick_min_range_pct),
            spread_window=env_int("SPREAD_WINDOW", cls.spread_window),
            spread_entry_zscore=env_float("SPREAD_ENTRY_ZSCORE", cls.spread_entry_zscore),
            spread_exit_zscore=env_float("SPREAD_EXIT_ZSCORE", cls.spread_exit_zscore),
            spread_stop_zscore=env_float("SPREAD_STOP_ZSCORE", cls.spread_stop_zscore),
            spread_notional_usd=env_float("SPREAD_NOTIONAL_USD", cls.spread_notional_usd),
            health_max_tick_age_seconds=env_int("HEALTH_MAX_TICK_AGE_SECONDS", cls.health_max_tick_age_seconds),
            health_min_free_disk_mb=env_int("HEALTH_MIN_FREE_DISK_MB", cls.health_min_free_disk_mb),
            replay_required_win_rate=env_float("REPLAY_REQUIRED_WIN_RATE", cls.replay_required_win_rate),
            replay_min_trades=env_int("REPLAY_MIN_TRADES", cls.replay_min_trades),
            replay_imbalance_threshold=env_float("REPLAY_IMBALANCE_THRESHOLD", cls.replay_imbalance_threshold),
            replay_fee_per_share=env_float("REPLAY_FEE_PER_SHARE", cls.replay_fee_per_share),
            discovery_max_order_notional_jpy=env_float(
                "DISCOVERY_MAX_ORDER_NOTIONAL_JPY",
                cls.discovery_max_order_notional_jpy,
            ),
            discovery_max_order_notional_usdt=env_float(
                "DISCOVERY_MAX_ORDER_NOTIONAL_USDT",
                cls.discovery_max_order_notional_usdt,
            ),
            discovery_min_depth_jpy=env_float("DISCOVERY_MIN_DEPTH_JPY", cls.discovery_min_depth_jpy),
            discovery_min_depth_usdt=env_float("DISCOVERY_MIN_DEPTH_USDT", cls.discovery_min_depth_usdt),
            discovery_max_spread_bps=env_float("DISCOVERY_MAX_SPREAD_BPS", cls.discovery_max_spread_bps),
            state_path=Path(os.getenv("STATE_PATH", str(cls.state_path))),
            trades_path=Path(os.getenv("TRADES_PATH", str(cls.trades_path))),
            ticks_path=Path(os.getenv("TICKS_PATH", str(cls.ticks_path))),
            arbitrage_ticks_path=Path(os.getenv("ARBITRAGE_TICKS_PATH", str(cls.arbitrage_ticks_path))),
        )


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())
