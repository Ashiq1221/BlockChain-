"""
BROKER (PAPER MODE)
Simulates order execution with realistic frictions — slippage and fees —
so the P&L you measure is honest, not fantasy fills at mid-price.
Every trade is appended to trades.csv for later analysis.
"""
import csv
import json
import time
import logging
import os
from config import settings
from risk import Position, RiskState

log = logging.getLogger("broker")

CSV_HEADER = ["ts", "action", "symbol", "mint", "price_usd", "size_sol",
              "pnl_sol", "pnl_pct", "reason", "conviction", "thesis"]


def _log_trade(row: dict):
    new = not os.path.exists(settings.TRADE_LOG)
    with open(settings.TRADE_LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new:
            w.writeheader()
        w.writerow(row)


def paper_buy(state: RiskState, signal: dict, size_sol: float, sol_price_usd: float) -> Position | None:
    price = signal["price_usd"]
    if price <= 0 or sol_price_usd <= 0:
        return None

    # simulate slippage: you buy slightly above quote
    fill_price = price * (1 + settings.ASSUMED_SLIPPAGE_PCT / 100)
    cost_sol = size_sol + settings.ASSUMED_FEE_SOL
    if cost_sol > state.balance_sol:
        log.warning("insufficient paper balance")
        return None

    tokens = (size_sol * sol_price_usd) / fill_price
    state.balance_sol -= cost_sol

    pos = Position(
        mint=signal["mint"], symbol=signal["symbol"],
        entry_price=fill_price, size_sol=size_sol, tokens=tokens,
        opened_at=time.time(), peak_price=fill_price,
        conviction=signal["conviction"], thesis=signal["thesis"],
    )
    state.positions[signal["mint"]] = pos
    _log_trade({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "BUY",
        "symbol": pos.symbol, "mint": pos.mint, "price_usd": round(fill_price, 8),
        "size_sol": size_sol, "pnl_sol": "", "pnl_pct": "",
        "reason": "entry", "conviction": pos.conviction, "thesis": pos.thesis,
    })
    log.info("PAPER BUY %s: %.4f SOL @ $%.8f (conviction %d)",
             pos.symbol, size_sol, fill_price, pos.conviction)
    return pos


def paper_sell(state: RiskState, pos: Position, current_price: float,
               sol_price_usd: float, reason: str) -> float:
    # simulate slippage: you sell slightly below quote (memes have thin exits)
    fill_price = current_price * (1 - settings.ASSUMED_SLIPPAGE_PCT / 100)
    proceeds_usd = pos.tokens * fill_price
    proceeds_sol = proceeds_usd / sol_price_usd - settings.ASSUMED_FEE_SOL
    proceeds_sol = max(proceeds_sol, 0)

    pnl_sol = proceeds_sol - pos.size_sol
    pnl_pct = (fill_price / pos.entry_price - 1) * 100

    state.balance_sol += proceeds_sol
    del state.positions[pos.mint]

    _log_trade({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "SELL",
        "symbol": pos.symbol, "mint": pos.mint, "price_usd": round(fill_price, 8),
        "size_sol": round(proceeds_sol, 4), "pnl_sol": round(pnl_sol, 4),
        "pnl_pct": round(pnl_pct, 1), "reason": reason,
        "conviction": pos.conviction, "thesis": "",
    })
    log.info("PAPER SELL %s: %s | P&L %+.4f SOL (%+.1f%%)",
             pos.symbol, reason, pnl_sol, pnl_pct)
    return pnl_sol


def save_state(state: RiskState):
    data = {
        "balance_sol": state.balance_sol,
        "day_start_balance": state.day_start_balance,
        "day_stamp": state.day_stamp,
        "halted": state.halted,
        "positions": {m: vars(p) for m, p in state.positions.items()},
    }
    with open(settings.STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_state() -> RiskState:
    state = RiskState()
    if os.path.exists(settings.STATE_FILE):
        try:
            with open(settings.STATE_FILE) as f:
                data = json.load(f)
            state.balance_sol = data.get("balance_sol", state.balance_sol)
            state.day_start_balance = data.get("day_start_balance", state.day_start_balance)
            state.day_stamp = data.get("day_stamp", "")
            state.halted = data.get("halted", False)
            for m, p in (data.get("positions") or {}).items():
                state.positions[m] = Position(**p)
            log.info("resumed state: %.4f SOL, %d open positions",
                     state.balance_sol, len(state.positions))
        except Exception as e:
            log.warning("could not load state: %s", e)
    return state
