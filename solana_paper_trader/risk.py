"""
RISK MANAGER
Hard, code-enforced limits. The LLM never touches these:
  - position sizing as a fixed % of bankroll
  - max concurrent positions
  - stop loss / take profit / trailing stop / time-based exits
  - daily loss kill switch (halts new entries until the next day)
"""
import time
import logging
from dataclasses import dataclass, field
from config import settings

log = logging.getLogger("risk")


@dataclass
class Position:
    mint: str
    symbol: str
    entry_price: float
    size_sol: float
    tokens: float
    opened_at: float
    peak_price: float
    conviction: int
    thesis: str


@dataclass
class RiskState:
    balance_sol: float = settings.STARTING_BALANCE_SOL
    day_start_balance: float = settings.STARTING_BALANCE_SOL
    day_stamp: str = ""
    halted: bool = False
    positions: dict[str, Position] = field(default_factory=dict)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _roll_day(state: RiskState, equity_sol: float):
    """New calendar day: reset the daily P&L baseline and lift any halt."""
    today = _today()
    if state.day_stamp != today:
        state.day_stamp = today
        state.day_start_balance = equity_sol
        if state.halted:
            log.info("new day — kill switch reset")
        state.halted = False


def daily_pnl_pct(state: RiskState, open_value_sol: float) -> float:
    """Day P&L as % of the day's starting equity."""
    equity = state.balance_sol + open_value_sol
    if state.day_start_balance <= 0:
        return 0.0
    return (equity / state.day_start_balance - 1) * 100


def position_size_sol(state: RiskState) -> float:
    """Fixed fraction of current bankroll (cash + capital in open positions)."""
    bankroll = state.balance_sol + sum(p.size_sol for p in state.positions.values())
    return round(bankroll * settings.POSITION_SIZE_PCT / 100, 4)


def can_open(state: RiskState, open_value_sol: float) -> tuple[bool, str]:
    """Gate for new entries. Returns (allowed, reason_if_blocked)."""
    _roll_day(state, state.balance_sol + open_value_sol)

    if state.halted:
        return False, "daily kill switch active"

    pnl = daily_pnl_pct(state, open_value_sol)
    if pnl <= settings.MAX_DAILY_LOSS_PCT:
        state.halted = True
        log.warning("KILL SWITCH: day %+.2f%% <= %.2f%% — no new entries today",
                    pnl, settings.MAX_DAILY_LOSS_PCT)
        return False, f"daily loss limit hit ({pnl:+.2f}%)"

    if len(state.positions) >= settings.MAX_OPEN_POSITIONS:
        return False, f"max open positions ({settings.MAX_OPEN_POSITIONS})"

    size = position_size_sol(state)
    if state.balance_sol < size + settings.ASSUMED_FEE_SOL:
        return False, "insufficient balance for next position"

    return True, ""


def exit_reason(pos: Position, price: float) -> str | None:
    """
    Check one open position against every exit rule.
    Also updates pos.peak_price. Returns a reason string or None to hold.
    """
    if price > pos.peak_price:
        pos.peak_price = price

    pnl_pct = (price / pos.entry_price - 1) * 100

    if pnl_pct <= settings.STOP_LOSS_PCT:
        return f"stop_loss ({pnl_pct:+.1f}%)"

    if pnl_pct >= settings.TAKE_PROFIT_PCT:
        return f"take_profit ({pnl_pct:+.1f}%)"

    # trailing stop: only armed once the position has been in profit,
    # so it locks gains rather than duplicating the fixed stop loss
    if pos.peak_price > pos.entry_price:
        drop_from_peak = (price / pos.peak_price - 1) * 100
        if drop_from_peak <= -settings.TRAILING_STOP_PCT:
            return f"trailing_stop ({drop_from_peak:+.1f}% from peak)"

    held_min = (time.time() - pos.opened_at) / 60
    if held_min >= settings.MAX_HOLD_MINUTES:
        return f"time_exit ({held_min:.0f}min)"

    return None
