"""Thin async JSON-RPC client for Solana — no heavy SDK dependency."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from . import config

log = logging.getLogger("solbot.rpc")

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30)
    return _client


async def call(method: str, params: list[Any] | None = None, retries: int = 3) -> Any:
    """Single JSON-RPC call with exponential-backoff retries."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    delay = 1.0
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client().post(config.RPC_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"RPC {method}: {data['error']}")
            return data.get("result")
        except (httpx.HTTPError, RuntimeError) as exc:
            last_err = exc
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
    raise RuntimeError(f"RPC {method} failed after {retries} attempts: {last_err}")


async def get_balance_sol(pubkey: str) -> float:
    result = await call("getBalance", [pubkey])
    return result["value"] / config.LAMPORTS_PER_SOL


async def get_mint_info(mint: str) -> dict | None:
    """Return parsed mint account data (supply, authorities) or None."""
    result = await call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    value = result.get("value") if result else None
    if not value:
        return None
    parsed = value.get("data", {}).get("parsed", {})
    if parsed.get("type") != "mint":
        return None
    return parsed.get("info")


async def get_top_holder_pct(mint: str, top_n: int = 10) -> float | None:
    """Percentage of supply held by the top N token accounts.

    The largest account is usually the liquidity pool itself, so it is
    excluded from the concentration figure.
    """
    supply_res = await call("getTokenSupply", [mint])
    supply = float(supply_res["value"]["amount"])
    if supply <= 0:
        return None
    largest = await call("getTokenLargestAccounts", [mint])
    accounts = largest.get("value", [])
    amounts = sorted((float(a["amount"]) for a in accounts), reverse=True)
    without_pool = amounts[1 : top_n + 1]
    return sum(without_pool) / supply * 100


async def get_token_balance(owner: str, mint: str) -> int:
    """Raw (integer) token balance for owner's associated accounts."""
    result = await call(
        "getTokenAccountsByOwner",
        [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
    )
    total = 0
    for acc in result.get("value", []):
        info = acc["account"]["data"]["parsed"]["info"]
        total += int(info["tokenAmount"]["amount"])
    return total


async def send_raw_transaction(raw_b64: str) -> str:
    """Submit a signed transaction (base64) and return its signature."""
    return await call(
        "sendTransaction",
        [raw_b64, {"encoding": "base64", "skipPreflight": False, "maxRetries": 3}],
    )


async def confirm_signature(signature: str, timeout_sec: int = 60) -> bool:
    """Poll until the signature is confirmed/finalized or the timeout passes."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    while asyncio.get_event_loop().time() < deadline:
        result = await call("getSignatureStatuses", [[signature]])
        status = (result.get("value") or [None])[0]
        if status:
            if status.get("err"):
                log.error("tx %s failed: %s", signature, status["err"])
                return False
            if status.get("confirmationStatus") in ("confirmed", "finalized"):
                return True
        await asyncio.sleep(2)
    log.warning("tx %s not confirmed within %ss", signature, timeout_sec)
    return False
