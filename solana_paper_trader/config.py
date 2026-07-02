"""
Central configuration for the meme-coin agent orchestra.
Everything tunable lives here. PAPER_MODE=True means no real transactions ever fire.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # ---- MODE ----
    PAPER_MODE: bool = True          # True = simulate fills, never touch a wallet
    STARTING_BALANCE_SOL: float = 10.0   # virtual bankroll for paper trading

    # ---- API KEYS (env vars, never hardcode) ----
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # ---- ENDPOINTS ----
    DEXSCREENER_BASE: str = "https://api.dexscreener.com"
    RUGCHECK_BASE: str = "https://api.rugcheck.xyz/v1"
    JUPITER_PRICE: str = "https://lite-api.jup.ag/price/v2"   # verify at dev.jup.ag

    # ---- SCANNER ----
    CHAIN: str = "solana"
    SCAN_INTERVAL_SEC: int = 30          # how often to poll for new pairs
    MIN_LIQUIDITY_USD: float = 15_000    # ignore pairs thinner than this
    MAX_PAIR_AGE_MIN: int = 120          # only look at tokens < 2h old

    # ---- ANALYST (hard filters before Claude even sees it) ----
    MAX_TOP10_HOLDER_PCT: float = 35.0   # reject if top 10 wallets own more
    REQUIRE_MINT_REVOKED: bool = True
    REQUIRE_LP_LOCKED_OR_BURNED: bool = True
    MAX_RUGCHECK_SCORE: int = 400        # rugcheck risk score ceiling (lower = safer)

    # ---- CLAUDE ----
    CLAUDE_MODEL: str = "claude-sonnet-4-6"
    CLAUDE_MAX_TOKENS: int = 600
    MIN_CONVICTION: int = 7              # 1-10; only trade >= this

    # ---- RISK MANAGER (hard limits, enforced in code) ----
    POSITION_SIZE_PCT: float = 2.0       # % of bankroll per trade
    MAX_OPEN_POSITIONS: int = 5
    STOP_LOSS_PCT: float = -20.0         # close if down 20%
    TAKE_PROFIT_PCT: float = 60.0        # close if up 60%
    TRAILING_STOP_PCT: float = 25.0      # after TP1, trail by 25% from peak
    MAX_DAILY_LOSS_PCT: float = -6.0     # kill switch: stop all trading for the day
    MAX_HOLD_MINUTES: int = 240          # time-based exit: memes decay fast

    # ---- SIMULATION REALISM ----
    ASSUMED_SLIPPAGE_PCT: float = 1.5    # paper fills are penalized like real ones
    ASSUMED_FEE_SOL: float = 0.002       # priority fee + tx fee estimate

    # ---- LOGGING ----
    TRADE_LOG: str = "trades.csv"
    STATE_FILE: str = "state.json"


settings = Settings()
