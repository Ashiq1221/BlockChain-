"""
ORCHESTRATOR
Wires the agent orchestra together in one async loop:

  Scanner ──> Analyst (rugcheck + Claude) ──> Risk Manager ──> Paper Broker
                                                  │
  Position Monitor <──────────────────────────────┘ (stops / TP / trailing / time exits)

Run:  python orchestrator.py
Stop: Ctrl+C  (state is saved; restart resumes open positions)
"""
import asyncio
import logging
import aiohttp

from config import settings
import scanner
import analyst
import risk
import broker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-9s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orch")

SOL_MINT = "So11111111111111111111111111111111111111112"


async def sol_price_usd(session: aiohttp.ClientSession) -> float:
    """SOL/USD via DexScreener (SOL-USDC pairs)."""
    price = await scanner.get_price(session, SOL_MINT)
    return price or 0.0


async def monitor_positions(session: aiohttp.ClientSession, state: risk.RiskState):
    """Check every open position against exit rules."""
    if not state.positions:
        return
    sol_usd = await sol_price_usd(session)
    if sol_usd <= 0:
        return
    for mint in list(state.positions):
        pos = state.positions[mint]
        price = await scanner.get_price(session, mint)
        if price is None:
            continue
        reason = risk.exit_reason(pos, price)
        if reason:
            broker.paper_sell(state, pos, price, sol_usd, reason)
            broker.save_state(state)


async def hunt_entries(session: aiohttp.ClientSession, state: risk.RiskState, seen: set):
    """Scan -> analyze -> size -> execute."""
    open_value = sum(p.size_sol for p in state.positions.values())
    ok, why = risk.can_open(state, open_value)
    if not ok:
        log.info("entries paused: %s", why)
        return

    candidates = await scanner.get_new_candidates(session, seen)
    if not candidates:
        return

    sol_usd = await sol_price_usd(session)
    if sol_usd <= 0:
        return

    for cand in candidates:
        if cand["mint"] in state.positions:
            continue
        signal = await analyst.analyze(session, cand)
        if not signal:
            continue
        ok, why = risk.can_open(state, open_value)
        if not ok:
            break
        size = risk.position_size_sol(state)
        if broker.paper_buy(state, signal, size, sol_usd):
            open_value += size
            broker.save_state(state)


async def main():
    if not settings.PAPER_MODE:
        raise SystemExit(
            "Live mode is not wired up in this build. "
            "Prove the edge in paper mode first: run for 2-4 weeks, "
            "then analyze trades.csv before even thinking about real funds."
        )
    if settings.ANTHROPIC_API_KEY:
        log.info("analyst: Claude scoring enabled (%s)", settings.CLAUDE_MODEL)
    else:
        log.info("analyst: no ANTHROPIC_API_KEY — free heuristic scoring mode")

    state = broker.load_state()
    seen: set[str] = set(state.positions)
    log.info("=== PAPER TRADING MODE | bankroll %.2f SOL ===", state.balance_sol)

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                await monitor_positions(session, state)
                await hunt_entries(session, state, seen)
                equity = state.balance_sol + sum(p.size_sol for p in state.positions.values())
                log.info("equity ~%.4f SOL | open %d | daily %+.2f%%",
                         equity, len(state.positions),
                         risk.daily_pnl_pct(state, equity - state.balance_sol))
            except Exception as e:
                log.exception("loop error: %s", e)
            await asyncio.sleep(settings.SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped — state saved in state.json, trades in trades.csv")
