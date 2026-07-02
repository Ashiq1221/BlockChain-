# Solana Meme-Coin Agent Orchestra (Paper Trading)

An educational multi-agent trading simulator. It scans real live Solana token
launches, runs real rug-safety checks, gets a real Claude verdict — and then
**simulates** the trade with realistic slippage and fees. No wallet, no keys,
no real money. The output is an honest P&L record you can actually learn from.

## Architecture

```
Scanner (DexScreener) ─> Analyst (RugCheck hard filters + Claude conviction score)
        │                                   │
        │                                   v
Position Monitor <── Risk Manager (sizing, stops, daily kill switch)
        │                                   │
        └──────────> Paper Broker (simulated fills -> trades.csv)
```

**Key design principle:** every safety rule (rug filters, position size, stop
loss, daily loss kill switch) is enforced in *code*. The LLM only contributes a
conviction score — it can never bypass a limit. This is how you should design
any agent system that touches money.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python orchestrator.py
```

Stop with Ctrl+C. State persists in `state.json`; open positions resume on restart.

The only dependency is `aiohttp` — the Claude API is called over plain HTTP,
so no Rust/C toolchain is needed to install.

**No API credits? It still runs.** If `ANTHROPIC_API_KEY` is unset (or a call
fails, e.g. out of credits), the analyst scores candidates with a free
built-in heuristic (buy/sell ratio, volume-to-liquidity, holders, rugcheck
risk) instead of Claude. All safety filters and risk limits are unchanged —
Claude only ever contributes the conviction score.

### Termux (Android)

```bash
pkg install python git tmux
AIOHTTP_NO_EXTENSIONS=1 pip install aiohttp   # skip C extensions
export ANTHROPIC_API_KEY=sk-ant-...
termux-wake-lock                              # keep Android from suspending it
tmux new -s trader                            # survive closing the app
python orchestrator.py
```

Detach tmux with `Ctrl+b` then `d`; reattach with `tmux attach -t trader`.
Set Termux's battery usage to Unrestricted in Android settings.

## What it does each cycle (every 30s)

1. **Monitor** open paper positions → exit on stop-loss (-20%), take-profit
   (+60%), trailing stop, or 4h time limit.
2. **Scan** DexScreener for fresh Solana pairs (< 2h old, > $15k liquidity).
3. **Filter** via RugCheck: mint authority revoked, no freeze authority,
   LP ≥90% locked/burned, top-10 holders < 35%.
4. **Score** survivors with Claude (conviction 1–10). Only ≥7 trades.
5. **Size** at 2% of bankroll, max 5 open positions.
6. **Kill switch**: if the day is down 6%, all new entries stop until tomorrow.

## Judging the results honestly

After 2–4 weeks, open `trades.csv` and compute:

- **Win rate** and **average win vs average loss** (a 35% win rate can be
  profitable if winners are 3x losers)
- **Expectancy per trade** = (win% × avg win) − (loss% × avg loss)
- **Max drawdown** — the worst peak-to-trough equity dip
- **Sample size** — under ~200 trades, results are mostly noise

If expectancy is negative (likely at first), that's the education: tune the
filters, conviction threshold, and exits, and re-run. If it's positive over
hundreds of trades, you have evidence — not a guarantee — of an edge.

## Tuning knobs

Everything lives in `config.py`. Good experiments:
- Raise `MIN_CONVICTION` to 8 (fewer, higher-quality trades)
- Tighten `MAX_PAIR_AGE_MIN` to 30 (earlier entries, more rug risk)
- Try asymmetric exits: `STOP_LOSS_PCT=-15`, `TAKE_PROFIT_PCT=100`

## Notes

- API endpoints (DexScreener, RugCheck, Jupiter) change occasionally — verify
  at their docs if requests start failing.
- Paper fills include 1.5% slippage + fees per side. Real meme-coin slippage
  is often *worse*, so treat paper results as optimistic.
- Claude API usage: see https://docs.claude.com/en/api/overview
