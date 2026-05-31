from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


RTDS_URL = "wss://ws-live-data.polymarket.com"


@dataclass(frozen=True)
class CryptoPriceEvent:
    source: str
    symbol: str
    price: float
    source_timestamp_ms: int
    received_at: str
    message_timestamp_ms: int | None = None


def build_crypto_price_subscription() -> dict[str, Any]:
    return {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "crypto_prices",
                "type": "update",
            },
            {
                "topic": "crypto_prices_chainlink",
                "type": "*",
                "filters": "",
            },
        ],
    }


def parse_crypto_price_message(raw_message: str, received_at: str | None = None) -> CryptoPriceEvent | None:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if not isinstance(message, dict) or message.get("type") != "update":
        return None

    topic = str(message.get("topic") or "")
    source = {
        "crypto_prices": "binance",
        "crypto_prices_chainlink": "chainlink",
    }.get(topic)
    if source is None:
        return None

    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return CryptoPriceEvent(
            source=source,
            symbol=str(payload["symbol"]),
            price=float(payload["value"]),
            source_timestamp_ms=int(payload["timestamp"]),
            received_at=received_at or utc_now(),
            message_timestamp_ms=int(message["timestamp"]) if message.get("timestamp") is not None else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


def append_crypto_price_event(path: Path, event: CryptoPriceEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")


def collect_crypto_prices(
    output_path: Path,
    url: str = RTDS_URL,
    ping_seconds: float = 5.0,
    reconnect_seconds: float = 3.0,
    stop_after_events: int | None = None,
    connect: Callable[..., Any] | None = None,
) -> None:
    if connect is None:
        from websocket import create_connection

        connect = create_connection

    written = 0
    while stop_after_events is None or written < stop_after_events:
        socket = None
        try:
            socket = connect(url, timeout=ping_seconds)
            socket.send(json.dumps(build_crypto_price_subscription(), separators=(",", ":")))
            last_ping = time.monotonic()
            while stop_after_events is None or written < stop_after_events:
                if time.monotonic() - last_ping >= ping_seconds:
                    socket.send("PING")
                    last_ping = time.monotonic()
                try:
                    message = socket.recv()
                except Exception as exc:
                    if _is_timeout(exc):
                        continue
                    raise
                if not isinstance(message, str):
                    continue
                event = parse_crypto_price_message(message)
                if event is None:
                    continue
                append_crypto_price_event(output_path, event)
                written += 1
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Polymarket RTDS reconnecting after error: {exc}", flush=True)
            if stop_after_events is None or written < stop_after_events:
                time.sleep(reconnect_seconds)
        finally:
            if socket is not None:
                socket.close()


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _is_timeout(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or exc.__class__.__name__ == "WebSocketTimeoutException"
