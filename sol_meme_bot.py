#!/usr/bin/env python3
"""Solana meme-coin trading bot — CLI entry point.

Usage:
    python sol_meme_bot.py run              # start the trading loop (paper by default)
    python sol_meme_bot.py status           # portfolio summary
    python sol_meme_bot.py scan             # one discovery sweep, show what passes filters
    python sol_meme_bot.py sell MINT        # force-close one position at market
    python sol_meme_bot.py close-all        # force-close every open position

Set SOLBOT_LIVE=true plus SOLBOT_PRIVATE_KEY to trade with real funds.
See README.md → "Solana Meme-Coin Trading Bot" for all settings.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from rich.console import Console
from rich.table import Table

from solbot import config
from solbot.portfolio import Portfolio
from solbot.safety import evaluate
from solbot.trader import Trader

console = Console()


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_status() -> None:
    portfolio = Portfolio.load(config.STATE_FILE)
    mode = "LIVE" if config.LIVE else "PAPER"
    console.print(f"[bold]solbot portfolio[/bold] [{mode}] — state: {config.STATE_FILE}")

    open_pos = portfolio.open_positions
    table = Table(title=f"Open positions ({len(open_pos)})")
    for col in ("Symbol", "Mint", "SOL in", "Entry (SOL)", "Peak PnL", "Held"):
        table.add_column(col)
    for p in open_pos:
        table.add_row(
            p.symbol, p.mint[:10] + "…", f"{p.sol_spent:.4f}",
            f"{p.entry_price_native:.10f}", f"{p.pnl_pct:+.1f}%",
            f"{p.hold_minutes:.0f}m",
        )
    console.print(table)

    closed = portfolio.closed_positions
    if closed:
        table = Table(title=f"Closed positions ({len(closed)})")
        for col in ("Symbol", "Reason", "SOL in", "SOL out", "PnL SOL", "Held"):
            table.add_column(col)
        for p in closed[-15:]:
            table.add_row(
                p.symbol, p.exit_reason, f"{p.sol_spent:.4f}",
                f"{p.sol_received:.4f}", f"{p.pnl_sol:+.4f}", f"{p.hold_minutes:.0f}m",
            )
        console.print(table)
        wins = sum(1 for p in closed if p.pnl_sol > 0)
        console.print(
            f"Realized PnL: [bold]{portfolio.realized_pnl_sol():+.4f} SOL[/bold] "
            f"({wins}/{len(closed)} wins)"
        )


async def cmd_scan() -> None:
    trader = Trader()
    console.print("Scanning DexScreener for candidates…")
    mints = await trader.discovery.candidate_mints()
    console.print(f"{len(mints)} Solana candidates found; vetting…")
    passed = 0
    for mint, source in mints.items():
        pair = await trader.discovery.best_sol_pair(mint, source)
        if pair is None:
            continue
        report = await evaluate(pair)
        if report.ok:
            passed += 1
            console.print(
                f"[green]PASS[/green] {pair.symbol:<10} liq ${pair.liquidity_usd:>10,.0f} "
                f"h1 vol ${pair.volume_h1:>10,.0f} h1 {pair.price_change_h1:+6.1f}% "
                f"age {pair.age_minutes:5.0f}m  {pair.url}"
            )
        else:
            console.print(f"[dim]skip {pair.symbol:<10} {report}[/dim]")
    console.print(f"\n{passed} candidate(s) passed all filters.")
    await trader.discovery.close()


async def cmd_sell(mint_prefix: str, close_all: bool = False) -> None:
    trader = Trader()
    targets = [
        p for p in trader.portfolio.open_positions
        if close_all or p.mint.startswith(mint_prefix)
    ]
    if not targets:
        console.print("[yellow]No matching open positions.[/yellow]")
        return
    for position in targets:
        pair = await trader.discovery.refresh_pair(position.pair_address)
        price = pair.price_native if pair else position.entry_price_native
        await trader.sell(position, price, "manual close")
    await trader.discovery.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Solana meme-coin trading bot")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="start the trading loop")
    sub.add_parser("status", help="show portfolio")
    sub.add_parser("scan", help="one discovery sweep")
    sell = sub.add_parser("sell", help="force-close a position")
    sell.add_argument("mint", help="mint address (or unique prefix)")
    sub.add_parser("close-all", help="force-close all open positions")
    args = parser.parse_args()

    setup_logging(args.verbose)

    if config.LIVE and not config.PRIVATE_KEY:
        console.print("[red]SOLBOT_LIVE=true but SOLBOT_PRIVATE_KEY is empty.[/red]")
        sys.exit(1)
    if not config.LIVE and args.command == "run":
        console.print(
            "[yellow]Paper-trading mode[/yellow] — simulated fills only. "
            "Set SOLBOT_LIVE=true to trade real funds."
        )

    if args.command == "run":
        asyncio.run(Trader().run())
    elif args.command == "status":
        cmd_status()
    elif args.command == "scan":
        asyncio.run(cmd_scan())
    elif args.command == "sell":
        asyncio.run(cmd_sell(args.mint))
    elif args.command == "close-all":
        asyncio.run(cmd_sell("", close_all=True))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]solbot stopped.[/dim]")
