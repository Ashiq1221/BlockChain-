"""solbot — Solana meme-coin trading bot.

Discovers fresh meme coins via DexScreener, runs rug-safety checks over
Solana RPC, buys through the Jupiter aggregator, and manages exits with
take-profit / stop-loss / trailing-stop rules.

Paper-trading is the default; live trading requires SOLBOT_LIVE=true and
a funded wallet key. See README.md → "Solana Meme-Coin Trading Bot".
"""

__version__ = "0.1.0"
