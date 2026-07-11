"""Jupiter aggregator client: quotes + signed swap execution.

Uses the free lite-api endpoints; no Jupiter API key required.
"""

from __future__ import annotations

import base64
import logging

import httpx

from . import config, rpc

log = logging.getLogger("solbot.jupiter")

QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
SWAP_URL = "https://lite-api.jup.ag/swap/v1/swap"
# Fallback (legacy public endpoint) if lite-api is unavailable.
QUOTE_URL_FALLBACK = "https://quote-api.jup.ag/v6/quote"
SWAP_URL_FALLBACK = "https://quote-api.jup.ag/v6/swap"

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30)
    return _client


def load_keypair():
    """Load the trading wallet from SOLBOT_PRIVATE_KEY (base58, Phantom export)."""
    if not config.PRIVATE_KEY:
        raise RuntimeError("SOLBOT_PRIVATE_KEY is not set — required for live trading")
    from .signing import Wallet  # pure Python — no compiled dependencies

    return Wallet(config.PRIVATE_KEY)


async def get_quote(input_mint: str, output_mint: str, amount_raw: int) -> dict:
    """Best route quote for swapping `amount_raw` (integer base units)."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount_raw),
        "slippageBps": str(config.SLIPPAGE_BPS),
    }
    for url in (QUOTE_URL, QUOTE_URL_FALLBACK):
        try:
            resp = await client().get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("error"):
                raise RuntimeError(f"quote error: {data['error']}")
            return data
        except httpx.HTTPError as exc:
            log.warning("quote via %s failed: %s", url, exc)
    raise RuntimeError(f"no Jupiter quote for {input_mint} -> {output_mint}")


async def execute_swap(quote: dict, keypair) -> str | None:
    """Build, sign, and submit the swap. Returns the tx signature or None."""
    from .signing import sign_versioned_transaction

    body = {
        "quoteResponse": quote,
        "userPublicKey": str(keypair.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": config.PRIORITY_FEE_LAMPORTS,
    }
    swap_b64 = None
    for url in (SWAP_URL, SWAP_URL_FALLBACK):
        try:
            resp = await client().post(url, json=body)
            resp.raise_for_status()
            swap_b64 = resp.json().get("swapTransaction")
            if swap_b64:
                break
        except httpx.HTTPError as exc:
            log.warning("swap build via %s failed: %s", url, exc)
    if not swap_b64:
        log.error("could not build swap transaction")
        return None

    signed = sign_versioned_transaction(base64.b64decode(swap_b64), keypair)
    raw_b64 = base64.b64encode(signed).decode()

    signature = await rpc.send_raw_transaction(raw_b64)
    log.info("swap submitted: %s", signature)
    if await rpc.confirm_signature(signature):
        return signature
    return None


async def buy_token(mint: str, sol_amount: float, keypair) -> tuple[str, int] | None:
    """Swap SOL -> token. Returns (signature, tokens_received_raw) or None."""
    lamports = int(sol_amount * config.LAMPORTS_PER_SOL)
    quote = await get_quote(config.SOL_MINT, mint, lamports)
    out_amount = int(quote.get("outAmount", 0))
    signature = await execute_swap(quote, keypair)
    return (signature, out_amount) if signature else None


async def sell_token(mint: str, amount_raw: int, keypair) -> tuple[str, float] | None:
    """Swap token -> SOL. Returns (signature, sol_received) or None."""
    quote = await get_quote(mint, config.SOL_MINT, amount_raw)
    sol_out = int(quote.get("outAmount", 0)) / config.LAMPORTS_PER_SOL
    signature = await execute_swap(quote, keypair)
    return (signature, sol_out) if signature else None
