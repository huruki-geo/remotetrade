from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from remotetrade.clients import PolymarketClient, PredictionMarket


CLOB_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


@dataclass(frozen=True)
class ClobMarketEvent:
    market_slug: str
    received_at: str
    event: dict[str, Any]


def market_asset_ids(market: PredictionMarket) -> list[str]:
    raw_ids = market.raw.get("clobTokenIds") or market.raw.get("clob_token_ids") or []
    if isinstance(raw_ids, str):
        try:
            raw_ids = json.loads(raw_ids)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_ids, list):
        return []
    return [str(asset_id) for asset_id in raw_ids if str(asset_id)]


def build_market_subscription(asset_ids: list[str]) -> dict[str, Any]:
    if not asset_ids:
        raise ValueError("At least one Polymarket asset ID is required.")
    return {
        "assets_ids": asset_ids,
        "type": "market",
        "custom_feature_enabled": True,
    }


def parse_market_messages(raw_message: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw_message)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        return [payload] if payload.get("event_type") else []
    if isinstance(payload, list):
        return [event for event in payload if isinstance(event, dict) and event.get("event_type")]
    return []


def append_market_event(path: Path, event: ClobMarketEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")


def collect_btc_5m_market_events(
    output_path: Path,
    gamma_url: str,
    market_query: str = "BTC Up or Down 5m",
    url: str = CLOB_MARKET_URL,
    ping_seconds: float = 10.0,
    refresh_seconds: float = 60.0,
    reconnect_seconds: float = 3.0,
    stop_after_events: int | None = None,
    connect: Callable[..., Any] | None = None,
) -> None:
    if connect is None:
        from websocket import create_connection

        connect = create_connection

    client = PolymarketClient(gamma_url)
    written = 0
    while stop_after_events is None or written < stop_after_events:
        socket = None
        try:
            market = client.find_market(None, market_query)
            asset_ids = market_asset_ids(market)
            if not asset_ids:
                raise RuntimeError(f"No CLOB token IDs found for {market.slug}.")
            socket = connect(url, timeout=min(ping_seconds, refresh_seconds))
            socket.send(json.dumps(build_market_subscription(asset_ids), separators=(",", ":")))
            connected_at = time.monotonic()
            last_ping = connected_at
            while stop_after_events is None or written < stop_after_events:
                now = time.monotonic()
                if now - connected_at >= refresh_seconds:
                    break
                if now - last_ping >= ping_seconds:
                    socket.send("PING")
                    last_ping = now
                try:
                    message = socket.recv()
                except Exception as exc:
                    if _is_timeout(exc):
                        continue
                    raise
                if not isinstance(message, str):
                    continue
                for payload in parse_market_messages(message):
                    append_market_event(output_path, ClobMarketEvent(market.slug, utc_now(), payload))
                    written += 1
                    if stop_after_events is not None and written >= stop_after_events:
                        break
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Polymarket CLOB reconnecting after error: {exc}", flush=True)
            if stop_after_events is None or written < stop_after_events:
                time.sleep(reconnect_seconds)
        finally:
            if socket is not None:
                socket.close()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or exc.__class__.__name__ == "WebSocketTimeoutException"
