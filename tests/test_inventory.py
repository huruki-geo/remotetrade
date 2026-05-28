from __future__ import annotations

import unittest

from remotetrade.inventory import VenueInventory, check_limit_arbitrage_inventory


class InventoryTest(unittest.TestCase):
    def test_rejects_when_sell_venue_lacks_base_inventory(self) -> None:
        result = check_limit_arbitrage_inventory(
            [
                VenueInventory("coinbase", base_qty=0.0, quote_qty=1000.0),
                VenueInventory("kraken", base_qty=0.01, quote_qty=0.0),
            ],
            buy_venue="coinbase",
            sell_venue="kraken",
            qty=0.02,
            notional_usd=100.0,
            min_base_qty=0.0,
            min_quote_qty=0.0,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "sell_venue_base_too_low")


if __name__ == "__main__":
    unittest.main()
