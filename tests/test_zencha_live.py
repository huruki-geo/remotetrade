from __future__ import annotations

import unittest

from eth_account import Account

from remotetrade.boba_zencha_probe import USDC, USDT
from remotetrade.zencha_live import ALLOWANCE, BALANCE_OF, LIVE_CONFIRMATION, _send_transaction, build_preflight, execute_canary


WALLET = "0x1111111111111111111111111111111111111111"


class StubRpc:
    def chain_id(self):
        return 288

    def block_number(self):
        return 123

    def gas_price(self):
        return 1_000_000

    def eth_call_at(self, address, data, block_number):
        return hex(10_200_000)

    def call(self, method, params):
        if method == "eth_getBalance":
            return hex(10**15)
        if method == "eth_call":
            call = params[0]
            if call["data"].startswith(BALANCE_OF):
                if call["to"] == USDC:
                    return hex(10 * 10**6)
                if call["to"] == USDT:
                    return hex(2 * 10**6)
            if call["data"].startswith(ALLOWANCE):
                return hex(0)
        raise AssertionError((method, params))


class ZenchaLiveTest(unittest.TestCase):
    def test_preflight_reports_funded_capped_canary(self) -> None:
        report = build_preflight(StubRpc(), WALLET, amount_usdc=10.0, slippage_bps=50.0)

        self.assertTrue(report.executable)
        self.assertEqual(report.quoted_usdt, 10.2)
        self.assertEqual(report.min_usdt, 10.149)
        self.assertEqual(report.allowance_usdc, 0.0)

    def test_preflight_rejects_amount_above_canary_cap(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "at most 10.00 USDC"):
            build_preflight(StubRpc(), WALLET, amount_usdc=10.01, slippage_bps=50.0)

    def test_execution_requires_exact_confirmation_before_reading_key(self) -> None:
        with self.assertRaisesRegex(RuntimeError, LIVE_CONFIRMATION):
            execute_canary(StubRpc(), None, 10.0, 50.0, confirmation="")

    def test_signs_and_normalizes_raw_transaction(self) -> None:
        account = Account.create()

        class SendRpc:
            def gas_price(self):
                return 1_000_000

            def call(self, method, params):
                if method == "eth_getTransactionCount":
                    return "0x0"
                if method == "eth_sendRawTransaction":
                    self.raw = params[0]
                    return "0x1234"
                if method == "eth_getTransactionReceipt":
                    return {"status": "0x1", "blockNumber": "0x7b", "gasUsed": "0x5208"}
                raise AssertionError((method, params))

        rpc = SendRpc()
        receipt = _send_transaction(rpc, account, USDC, "0x", 80_000)

        self.assertTrue(rpc.raw.startswith("0x"))
        self.assertFalse(rpc.raw.startswith("0x0x"))
        self.assertEqual(receipt["transaction_hash"], "0x1234")


if __name__ == "__main__":
    unittest.main()
