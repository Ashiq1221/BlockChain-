"""Main trading loop: discover -> vet -> buy -> monitor -> exit."""

from __future__ import annotations

import asyncio
import logging
import time

from . import ai, birdeye, config, jupiter, notify, rpc
from .discovery import Discovery, PairInfo
from .portfolio import Portfolio, Position
from .safety import evaluate

log = logging.getLogger("solbot.trader")


class Trader:
    def __init__(self) -> None:
        self.discovery = Discovery()
        self.portfolio = Portfolio.load(config.STATE_FILE)
        self.keypair = jupiter.load_keypair() if config.LIVE else None
        self._rejected: dict[str, float] = {}  # mint -> last rejection ts

    # ── Entries ──────────────────────────────────────────────────────────────

    async def scan_and_buy(self) -> None:
        if len(self.portfolio.open_positions) >= config.MAX_POSITIONS:
            return
        if self.portfolio.buys_today() >= config.MAX_DAILY_BUYS:
            log.info("daily buy cap (%d) reached", config.MAX_DAILY_BUYS)
            return

        mints = await self.discovery.candidate_mints()
        if birdeye.enabled():
            for mint in await birdeye.trending_mints():
                mints.setdefault(mint, "birdeye-trending")
            for mint in await birdeye.new_listing_mints():
                mints.setdefault(mint, "birdeye-new")
        now = time.time()
        for mint, source in mints.items():
            if len(self.portfolio.open_positions) >= config.MAX_POSITIONS:
                break
            if self.portfolio.has_traded(mint):
                continue
            if now - self._rejected.get(mint, 0) < 1800:  # re-vet at most every 30m
                continue

            pair = await self.discovery.best_sol_pair(mint, source)
            if pair is None:
                self._rejected[mint] = now
                continue

            report = await evaluate(pair)
            if not report.ok:
                log.debug("skip %s (%s): %s", pair.symbol, mint[:8], report)
                self._rejected[mint] = now
                continue

            log.info(
                "filters passed for %s (%s) — liq $%s, h1 vol $%s, h1 %+.1f%%, age %.0fm [%s]",
                pair.symbol, mint[:8],
                f"{pair.liquidity_usd:,.0f}", f"{pair.volume_h1:,.0f}",
                pair.price_change_h1, pair.age_minutes, source,
            )

            decision = None
            if ai.AI_ENABLED:
                extra = await self._birdeye_context(mint)
                decision = await ai.analyze(pair, report.top10_pct, extra)
                if decision is None or not decision.approved:
                    self._rejected[mint] = now
                    continue

            await self.buy(pair, decision)

    @staticmethod
    async def _birdeye_context(mint: str) -> str:
        """Extra market context for the AI brief when Birdeye is configured."""
        if not birdeye.enabled():
            return ""
        lines = []
        sec = await birdeye.security(mint)
        if sec:
            lines.append(f"Birdeye security: {birdeye.security_summary(sec)}")
        candles = await birdeye.recent_candles(mint)
        if candles:
            lines.append(f"Recent 15m candles (change/volume): {candles}")
        return ("\n".join(lines) + "\n") if lines else ""

    async def buy(self, pair: PairInfo, decision: ai.AIDecision | None = None) -> None:
        sol_amount = config.BUY_AMOUNT_SOL
        if decision is not None:
            sol_amount = round(sol_amount * decision.size_multiplier, 6)
        signature = ""
        tokens_raw = int(sol_amount / pair.price_native * 1e6) if pair.price_native else 0

        if config.LIVE:
            balance = await rpc.get_balance_sol(str(self.keypair.pubkey()))
            if balance - sol_amount < config.MIN_WALLET_SOL:
                log.warning("wallet %.4f SOL too low to buy (reserve %.4f)",
                            balance, config.MIN_WALLET_SOL)
                return
            result = await jupiter.buy_token(pair.mint, sol_amount, self.keypair)
            if result is None:
                log.error("live buy of %s failed", pair.symbol)
                return
            signature, tokens_raw = result

        position = Position(
            mint=pair.mint,
            symbol=pair.symbol,
            pair_address=pair.pair_address,
            entry_price_native=pair.price_native,
            entry_price_usd=pair.price_usd,
            sol_spent=sol_amount,
            tokens_raw=tokens_raw,
            opened_at=time.time(),
            peak_price_native=pair.price_native,
            live=config.LIVE,
            buy_signature=signature,
            ai_conviction=decision.conviction if decision else -1,
            ai_reasoning=decision.reasoning if decision else "",
        )
        self.portfolio.open(position)
        mode = "LIVE" if config.LIVE else "PAPER"
        ai_note = (
            f"\n🤖 AI conviction {decision.conviction}/100: {decision.reasoning}"
            if decision else ""
        )
        msg = (
            f"🟢 [{mode}] BUY {pair.symbol} — {sol_amount} SOL @ "
            f"{pair.price_native:.10f} SOL (${pair.price_usd:.8f}){ai_note}\n{pair.url}"
        )
        log.info(msg)
        await notify.send(msg)

    # ── Exits ────────────────────────────────────────────────────────────────

    def exit_reason(self, position: Position, price_native: float) -> str | None:
        pnl = position.pnl_pct_at(price_native)
        if pnl <= -config.STOP_LOSS_PCT:
            return f"stop-loss {pnl:+.1f}%"
        if pnl >= config.TAKE_PROFIT_PCT:
            return f"take-profit {pnl:+.1f}%"
        # Trailing stop arms once the position is up half the take-profit target.
        peak_pnl = position.pnl_pct_at(position.peak_price_native)
        if peak_pnl >= config.TAKE_PROFIT_PCT / 2 and position.peak_price_native > 0:
            drawdown = (1 - price_native / position.peak_price_native) * 100
            if drawdown >= config.TRAILING_STOP_PCT:
                return f"trailing-stop {pnl:+.1f}% (peak {peak_pnl:+.1f}%)"
        if position.hold_minutes >= config.MAX_HOLD_MINUTES:
            return f"max-hold timeout {pnl:+.1f}%"
        return None

    async def monitor_positions(self) -> None:
        for position in self.portfolio.open_positions:
            pair = await self.discovery.refresh_pair(position.pair_address)
            if pair is None or pair.price_native <= 0:
                # Pair vanished from DexScreener — likely rugged/delisted.
                if position.hold_minutes > 10:
                    await self.sell(position, position.entry_price_native * 0.0,
                                    "pair delisted (possible rug)")
                continue
            if pair.price_native > position.peak_price_native:
                position.peak_price_native = pair.price_native
                self.portfolio.save()
            reason = self.exit_reason(position, pair.price_native)
            if reason:
                await self.sell(position, pair.price_native, reason)

    async def sell(self, position: Position, price_native: float, reason: str) -> None:
        signature = ""
        if position.live and config.LIVE:
            balance = await rpc.get_token_balance(str(self.keypair.pubkey()), position.mint)
            amount = min(balance, position.tokens_raw) or balance
            if amount <= 0:
                log.error("no %s balance to sell; marking closed", position.symbol)
                self.portfolio.close(position, price_native, 0.0, reason + " (no balance)")
                return
            result = await jupiter.sell_token(position.mint, amount, self.keypair)
            if result is None:
                log.error("live sell of %s failed; will retry next tick", position.symbol)
                return
            signature, sol_received = result
        else:
            # Paper fill at current price with slippage haircut.
            gross = position.sol_spent * (price_native / position.entry_price_native
                                          if position.entry_price_native else 0)
            sol_received = gross * (1 - config.SLIPPAGE_BPS / 10_000)

        self.portfolio.close(position, price_native, sol_received, reason, signature)
        mode = "LIVE" if position.live else "PAPER"
        msg = (
            f"🔴 [{mode}] SELL {position.symbol} — {reason}\n"
            f"received {sol_received:.4f} SOL vs spent {position.sol_spent:.4f} "
            f"(PnL {position.pnl_sol:+.4f} SOL) after {position.hold_minutes:.0f}m"
        )
        log.info(msg)
        await notify.send(msg)

    # ── Loop ─────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        mode = "LIVE 💸" if config.LIVE else "PAPER 📝"
        brain = f"AI analyst ON ({ai.AI_MODEL}, min conviction {ai.MIN_CONVICTION})" \
            if ai.AI_ENABLED else "AI analyst OFF (set ANTHROPIC_API_KEY to enable)"
        log.info(
            "solbot starting [%s] — buy %.3f SOL, max %d positions, "
            "TP %.0f%% / SL %.0f%% / trail %.0f%% — %s",
            mode, config.BUY_AMOUNT_SOL, config.MAX_POSITIONS,
            config.TAKE_PROFIT_PCT, config.STOP_LOSS_PCT, config.TRAILING_STOP_PCT,
            brain,
        )
        if config.LIVE:
            balance = await rpc.get_balance_sol(str(self.keypair.pubkey()))
            log.info("wallet %s — %.4f SOL", self.keypair.pubkey(), balance)
            await notify.send(f"solbot LIVE started — wallet {balance:.4f} SOL")

        last_scan = 0.0
        while True:
            try:
                await self.monitor_positions()
                if time.time() - last_scan >= config.SCAN_INTERVAL_SEC:
                    await self.scan_and_buy()
                    last_scan = time.time()
            except Exception:
                log.exception("trading loop error — continuing")
            await asyncio.sleep(config.MONITOR_INTERVAL_SEC)
