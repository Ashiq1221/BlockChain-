"""solbot configuration — all values overridable via environment variables."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _f(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _i(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _b(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ── Mode ─────────────────────────────────────────────────────────────────────
# Paper trading (simulated fills, no wallet needed) unless SOLBOT_LIVE=true.
LIVE = _b("SOLBOT_LIVE", False)

# ── Wallet / RPC ─────────────────────────────────────────────────────────────
RPC_URL = os.getenv("SOLBOT_RPC_URL", "https://api.mainnet-beta.solana.com")
# Base58-encoded private key (Phantom export format). Only needed when LIVE.
PRIVATE_KEY = os.getenv("SOLBOT_PRIVATE_KEY", "")

# ── Position sizing ──────────────────────────────────────────────────────────
BUY_AMOUNT_SOL = _f("SOLBOT_BUY_AMOUNT_SOL", 0.05)   # SOL spent per entry
MAX_POSITIONS = _i("SOLBOT_MAX_POSITIONS", 5)         # concurrent open positions
MAX_DAILY_BUYS = _i("SOLBOT_MAX_DAILY_BUYS", 20)      # hard cap on entries per UTC day
MIN_WALLET_SOL = _f("SOLBOT_MIN_WALLET_SOL", 0.02)    # never spend below this reserve

# ── Exit rules (percentages are relative to entry price in SOL) ──────────────
TAKE_PROFIT_PCT = _f("SOLBOT_TAKE_PROFIT_PCT", 60.0)
STOP_LOSS_PCT = _f("SOLBOT_STOP_LOSS_PCT", 25.0)
TRAILING_STOP_PCT = _f("SOLBOT_TRAILING_STOP_PCT", 20.0)  # from peak, armed after TP/2
MAX_HOLD_MINUTES = _i("SOLBOT_MAX_HOLD_MINUTES", 240)     # timeout exit

# ── Entry filters (DexScreener pair metrics) ─────────────────────────────────
MIN_LIQUIDITY_USD = _f("SOLBOT_MIN_LIQUIDITY_USD", 20_000)
MAX_LIQUIDITY_USD = _f("SOLBOT_MAX_LIQUIDITY_USD", 2_000_000)  # too big = not a fresh meme
MIN_VOLUME_H1_USD = _f("SOLBOT_MIN_VOLUME_H1_USD", 10_000)
MIN_TXNS_H1 = _i("SOLBOT_MIN_TXNS_H1", 50)
MIN_BUY_SELL_RATIO = _f("SOLBOT_MIN_BUY_SELL_RATIO", 1.1)  # h1 buys / sells
MIN_PAIR_AGE_MINUTES = _f("SOLBOT_MIN_PAIR_AGE_MINUTES", 30)   # skip brand-new rugs
MAX_PAIR_AGE_HOURS = _f("SOLBOT_MAX_PAIR_AGE_HOURS", 48)       # skip stale pairs
MIN_PRICE_CHANGE_H1_PCT = _f("SOLBOT_MIN_PRICE_CHANGE_H1_PCT", 0.0)  # require momentum
MAX_PRICE_CHANGE_H1_PCT = _f("SOLBOT_MAX_PRICE_CHANGE_H1_PCT", 300.0)  # skip vertical pumps

# ── Safety checks (on-chain) ─────────────────────────────────────────────────
REQUIRE_MINT_RENOUNCED = _b("SOLBOT_REQUIRE_MINT_RENOUNCED", True)
REQUIRE_FREEZE_RENOUNCED = _b("SOLBOT_REQUIRE_FREEZE_RENOUNCED", True)
MAX_TOP10_HOLDER_PCT = _f("SOLBOT_MAX_TOP10_HOLDER_PCT", 40.0)

# ── Swap execution ───────────────────────────────────────────────────────────
SLIPPAGE_BPS = _i("SOLBOT_SLIPPAGE_BPS", 300)  # 3%
PRIORITY_FEE_LAMPORTS = _i("SOLBOT_PRIORITY_FEE_LAMPORTS", 200_000)

# ── Loop timing ──────────────────────────────────────────────────────────────
SCAN_INTERVAL_SEC = _i("SOLBOT_SCAN_INTERVAL_SEC", 30)      # discovery sweep
MONITOR_INTERVAL_SEC = _i("SOLBOT_MONITOR_INTERVAL_SEC", 10)  # open-position checks

# ── State / notifications ────────────────────────────────────────────────────
STATE_FILE = os.getenv("SOLBOT_STATE_FILE", "solbot_state.json")
TELEGRAM_BOT_TOKEN = os.getenv("SOLBOT_TG_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("SOLBOT_TG_CHAT_ID", "")

# ── Constants ────────────────────────────────────────────────────────────────
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
LAMPORTS_PER_SOL = 1_000_000_000
