from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VenueInventory:
    venue: str
    base_qty: float
    quote_qty: float


@dataclass(frozen=True)
class InventoryCheck:
    allowed: bool
    reason: str


def check_limit_arbitrage_inventory(
    inventories: list[VenueInventory],
    buy_venue: str,
    sell_venue: str,
    qty: float,
    notional_usd: float,
    min_base_qty: float,
    min_quote_qty: float,
) -> InventoryCheck:
    by_venue = {inventory.venue: inventory for inventory in inventories}
    buy_inventory = by_venue.get(buy_venue)
    sell_inventory = by_venue.get(sell_venue)
    if buy_inventory is None or sell_inventory is None:
        return InventoryCheck(False, "missing_venue_inventory")
    if buy_inventory.quote_qty - notional_usd < min_quote_qty:
        return InventoryCheck(False, "buy_venue_quote_too_low")
    if sell_inventory.base_qty - qty < min_base_qty:
        return InventoryCheck(False, "sell_venue_base_too_low")
    return InventoryCheck(True, "allowed")
