from __future__ import annotations

import argparse
import json
import os
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from eth_account import Account
from eth_utils import to_checksum_address

from remotetrade.boba_zencha_probe import CALCULATE_SWAP, USDC, USDT, ZENCHA_SWAP_FLASH_LOAN, _calculate_swap, _encode
from remotetrade.dex_route_probe import EthereumRpcClient


BALANCE_OF = "0x70a08231"
ALLOWANCE = "0xdd62ed3e"
APPROVE = "0x095ea7b3"
MAX_CANARY_USDC = 10.0
SWAP_GAS_LIMIT = 250_000
APPROVE_GAS_LIMIT = 80_000
LIVE_CONFIRMATION = "EXECUTE_ZENCHA_CANARY"


@dataclass(frozen=True)
class ZenchaLivePreflight:
    wallet: str
    chain_id: int
    block_number: int
    amount_usdc: float
    quoted_usdt: float
    min_usdt: float
    slippage_bps: float
    eth_balance: float
    usdc_balance: float
    usdt_balance: float
    allowance_usdc: float
    estimated_max_gas_eth: float
    executable: bool
    issues: tuple[str, ...]


def create_wallet(path: Path) -> str:
    if path.exists():
        raise RuntimeError(f"Refusing to replace existing wallet file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.parent.chmod(0o700)
    account = Account.create()
    with path.open("x", encoding="ascii") as handle:
        handle.write(account.key.hex() + "\n")
    if os.name != "nt":
        path.chmod(0o600)
    return account.address


def build_preflight(rpc: EthereumRpcClient, wallet: str, amount_usdc: float, slippage_bps: float) -> ZenchaLivePreflight:
    _validate_canary(amount_usdc, slippage_bps)
    chain_id = rpc.chain_id()
    if chain_id != 288:
        raise RuntimeError(f"Zencha live canary requires Boba mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    amount_units = int(amount_usdc * 10**6)
    quoted_units = _calculate_swap(rpc, 1, 2, amount_units, block_number)
    min_units = quoted_units * int(10_000 - slippage_bps) // 10_000
    eth_balance = _eth_balance(rpc, wallet)
    usdc_balance = _erc20_balance(rpc, USDC, wallet) / 10**6
    usdt_balance = _erc20_balance(rpc, USDT, wallet) / 10**6
    allowance_usdc = _allowance(rpc, USDC, wallet, ZENCHA_SWAP_FLASH_LOAN) / 10**6
    estimated_max_gas_eth = (SWAP_GAS_LIMIT + (APPROVE_GAS_LIMIT if allowance_usdc < amount_usdc else 0)) * rpc.gas_price() / 10**18
    issues = []
    if usdc_balance < amount_usdc:
        issues.append(f"USDC balance is short: need {amount_usdc:.6f}, have {usdc_balance:.6f}")
    if eth_balance < estimated_max_gas_eth:
        issues.append(f"ETH gas balance is short: need {estimated_max_gas_eth:.8f}, have {eth_balance:.8f}")
    return ZenchaLivePreflight(
        wallet=wallet,
        chain_id=chain_id,
        block_number=block_number,
        amount_usdc=amount_usdc,
        quoted_usdt=quoted_units / 10**6,
        min_usdt=min_units / 10**6,
        slippage_bps=slippage_bps,
        eth_balance=eth_balance,
        usdc_balance=usdc_balance,
        usdt_balance=usdt_balance,
        allowance_usdc=allowance_usdc,
        estimated_max_gas_eth=estimated_max_gas_eth,
        executable=not issues,
        issues=tuple(issues),
    )


def execute_canary(rpc: EthereumRpcClient, key_file: Path, amount_usdc: float, slippage_bps: float, confirmation: str) -> dict[str, object]:
    if confirmation != LIVE_CONFIRMATION:
        raise RuntimeError(f"Live execution requires --confirm {LIVE_CONFIRMATION}")
    account = _load_account(key_file)
    preflight = build_preflight(rpc, account.address, amount_usdc, slippage_bps)
    if not preflight.executable:
        raise RuntimeError("Preflight failed: " + "; ".join(preflight.issues))
    amount_units = int(amount_usdc * 10**6)
    min_units = int(preflight.min_usdt * 10**6)
    receipts = []
    if preflight.allowance_usdc < amount_usdc:
        receipts.append(_send_transaction(rpc, account, USDC, _encode(APPROVE, int(ZENCHA_SWAP_FLASH_LOAN, 16), amount_units), APPROVE_GAS_LIMIT))
    deadline = int(time.time()) + 300
    swap_selector = _selector(rpc, "swap(uint8,uint8,uint256,uint256,uint256)")
    receipts.append(
        _send_transaction(
            rpc,
            account,
            ZENCHA_SWAP_FLASH_LOAN,
            _encode(swap_selector, 1, 2, amount_units, min_units, deadline),
            SWAP_GAS_LIMIT,
        )
    )
    return {
        "preflight": asdict(preflight),
        "receipts": receipts,
        "post_usdc_balance": _erc20_balance(rpc, USDC, account.address) / 10**6,
        "post_usdt_balance": _erc20_balance(rpc, USDT, account.address) / 10**6,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or execute a capped Boba Zencha USDC -> USDT canary swap.")
    parser.add_argument("--wallet-file", type=Path, default=Path("secrets/zencha_wallet.key"))
    parser.add_argument("--rpc-url", default=os.getenv("BOBA_RPC_URL", "https://mainnet.boba.network"))
    parser.add_argument("--amount-usdc", type=float, default=10.0)
    parser.add_argument("--slippage-bps", type=float, default=50.0)
    parser.add_argument("--create-wallet", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if sum((args.create_wallet, args.preflight, args.execute)) != 1:
        parser.error("Choose exactly one of --create-wallet, --preflight, or --execute.")
    if args.create_wallet:
        print(json.dumps({"wallet": create_wallet(args.wallet_file), "wallet_file": str(args.wallet_file)}))
        return
    account = _load_account(args.wallet_file)
    rpc = EthereumRpcClient(args.rpc_url, timeout=30)
    if args.preflight:
        print(json.dumps(asdict(build_preflight(rpc, account.address, args.amount_usdc, args.slippage_bps)), indent=2))
        return
    print(json.dumps(execute_canary(rpc, args.wallet_file, args.amount_usdc, args.slippage_bps, args.confirm or ""), indent=2))


def _validate_canary(amount_usdc: float, slippage_bps: float) -> None:
    if not 0 < amount_usdc <= MAX_CANARY_USDC:
        raise RuntimeError(f"Canary amount must be greater than 0 and at most {MAX_CANARY_USDC:.2f} USDC.")
    if not 0 <= slippage_bps <= 100:
        raise RuntimeError("Slippage must be between 0 and 100 bps.")


def _load_account(path: Path):
    if not path.exists():
        raise RuntimeError(f"Wallet file does not exist: {path}. Run --create-wallet first.")
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError(f"Wallet file permissions must be 600: {path}")
    return Account.from_key(path.read_text(encoding="ascii").strip())


def _eth_balance(rpc: EthereumRpcClient, wallet: str) -> float:
    return int(rpc.call("eth_getBalance", [wallet, "latest"]), 16) / 10**18


def _erc20_balance(rpc: EthereumRpcClient, token: str, wallet: str) -> int:
    return int(rpc.call("eth_call", [{"to": token, "data": _encode(BALANCE_OF, int(wallet, 16))}, "latest"]), 16)


def _allowance(rpc: EthereumRpcClient, token: str, owner: str, spender: str) -> int:
    return int(rpc.call("eth_call", [{"to": token, "data": _encode(ALLOWANCE, int(owner, 16), int(spender, 16))}, "latest"]), 16)


def _selector(rpc: EthereumRpcClient, signature: str) -> str:
    return rpc.call("web3_sha3", ["0x" + signature.encode().hex()])[:10]


def _send_transaction(rpc: EthereumRpcClient, account, to: str, data: str, gas: int) -> dict[str, object]:
    nonce = int(rpc.call("eth_getTransactionCount", [account.address, "pending"]), 16)
    transaction = {
        "chainId": 288,
        "nonce": nonce,
        "to": to_checksum_address(to),
        "value": 0,
        "gas": gas,
        "gasPrice": rpc.gas_price(),
        "data": data,
    }
    signed = account.sign_transaction(transaction)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    raw_hex = raw.hex()
    tx_hash = rpc.call("eth_sendRawTransaction", [raw_hex if raw_hex.startswith("0x") else "0x" + raw_hex])
    receipt = _wait_for_receipt(rpc, tx_hash)
    if int(receipt["status"], 16) != 1:
        raise RuntimeError(f"Transaction reverted: {tx_hash}")
    return {"transaction_hash": tx_hash, "block_number": int(receipt["blockNumber"], 16), "gas_used": int(receipt["gasUsed"], 16)}


def _wait_for_receipt(rpc: EthereumRpcClient, tx_hash: str, timeout_seconds: int = 120) -> dict[str, str]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        receipt = rpc.call("eth_getTransactionReceipt", [tx_hash])
        if receipt is not None:
            return receipt
        time.sleep(2)
    raise RuntimeError(f"Timed out waiting for transaction receipt: {tx_hash}")


if __name__ == "__main__":
    main()
