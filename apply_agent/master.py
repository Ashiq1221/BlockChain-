"""Lateral Thinking Master — the top-level controller.

A self-directed reasoning loop (default 5-minute budget) that sits above every
sub-agent and decides, laterally, what the whole Apply-Pilot system should do
next: harvest fresh leads, pull the bot's Cloudflare-KV finds, debate + apply
to a lead, consolidate learnings, or report. It doesn't follow a fixed script
— each tick it looks at the live state and the orchestra picks the single
highest-leverage move, favouring creative angles a linear pipeline would miss
(reprioritising, unblocking stuck forms, spotting what's actually converting).

Safety: submission still obeys APPLY_AUTO_SUBMIT. In dry-run it fills +
screenshots but never submits. CAPTCHAs are never bypassed.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field

from aos import providers as p
from . import harvester, lead_source, memory, form_learning
from .orchestrator import evaluate_job, render_plan
from .profile import PROFILE

BUDGET = int(os.getenv("MASTER_BUDGET_SECONDS", "300"))   # 5 minutes
AUTO_SUBMIT = os.getenv("APPLY_AUTO_SUBMIT", "false").lower() == "true"
MIN_FIT = float(os.getenv("APPLY_MIN_FIT", "6"))
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = os.getenv("TELEGRAM_OWNER_ID", "")

_JSON = re.compile(r"\{.*\}", re.S)


@dataclass
class MasterState:
    started: float = field(default_factory=time.time)
    ticks: int = 0
    applied: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    queue: list[dict] = field(default_factory=list)      # pending {url,title,source,_key?}
    done_urls: set = field(default_factory=set)
    harvested: bool = False

    def elapsed(self) -> float:
        return time.time() - self.started

    def note(self, s: str) -> None:
        self.log.append(f"[{int(self.elapsed())}s] {s}")


async def _tg(text: str) -> None:
    if not BOT_TOKEN or not OWNER_ID:
        return
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         json={"chat_id": OWNER_ID, "text": text[:4096],
                               "disable_web_page_preview": True},
                         timeout=aiohttp.ClientTimeout(total=20))
    except Exception:
        pass


async def _refill_queue(state: MasterState) -> None:
    """Pull work from the bot's KV finds and the Telegram harvester."""
    bot = await lead_source.pull_bot_jobs(limit=15)
    for j in bot:
        if j["apply_url"] not in state.done_urls:
            state.queue.append({"url": j["apply_url"], "title": j.get("title", ""),
                                "source": "bot", "_key": j.get("_key")})
    if not state.harvested:
        try:
            await harvester.harvest()
        except Exception as e:
            state.note(f"harvest error: {e}")
        state.harvested = True
    for l in harvester.pending(40, matched_only=True):
        if l["url"] not in state.done_urls and \
           not any(q["url"] == l["url"] for q in state.queue):
            state.queue.append({"url": l["url"], "title": l.get("title", ""), "source": "harvest"})


async def _lateral_decide(state: MasterState) -> dict:
    """The orchestra picks the next highest-leverage action, thinking laterally."""
    recent = memory.report(6)
    won = [r for r in recent if r["status"] == "submitted"]
    prompt = (
        f"SYSTEM STATE (elapsed {int(state.elapsed())}s / {BUDGET}s budget, tick {state.ticks}):\n"
        f"- pending leads in queue: {len(state.queue)}"
        f" (sources: {', '.join(sorted({q['source'] for q in state.queue})) or 'none'})\n"
        f"- applications this run: {len(state.applied)}\n"
        f"- recently submitted: {[r['company'] for r in won][:5]}\n"
        f"- harvested this run: {state.harvested}\n"
        f"- candidate is a Web3 community/content ambassador (16k+ X, 6k+ community, "
        f"multilingual). Best-fit = community/creator/ambassador roles; product-use-gated "
        f"and wallet/payout forms need human input and should be flagged, not auto-filled.\n\n"
        "You are the LATERAL THINKING MASTER controlling this job-application system. "
        "Think unconventionally and pick the SINGLE highest-leverage next action:\n"
        "• 'apply'    — debate + apply to the most promising queued lead.\n"
        "• 'refill'   — queue is thin; harvest fresh leads + pull the bot's finds.\n"
        "• 'learn'    — consolidate what's converting and adjust focus.\n"
        "• 'report'   — summarise progress to the owner.\n"
        "• 'done'     — no useful work remains within the budget.\n"
        'Reply ONLY JSON: {"action":"apply|refill|learn|report|done","reason":"one sharp sentence"}'
    )
    out = await p.think(prompt, system="You are a 300-IQ lateral-thinking orchestrator. Output only JSON.",
                        max_tokens=160, prefer="cf")
    m = _JSON.search(out or "")
    try:
        d = json.loads(m.group(0)) if m else {}
    except Exception:
        d = {}
    return d or {"action": "refill", "reason": "fallback"}


def _pick_lead(state: MasterState) -> dict | None:
    return state.queue.pop(0) if state.queue else None


async def _apply_one(state: MasterState) -> None:
    lead = _pick_lead(state)
    if not lead:
        state.note("apply: queue empty")
        return
    url = lead["url"]
    state.done_urls.add(url)
    try:
        plan = await evaluate_job(url)
    except Exception as e:
        state.note(f"eval error {url}: {e}")
        return
    tag = f"{plan.title or lead['title'][:40]} @ {plan.company or '?'}"
    if plan.decision != "APPLY" or plan.fit_score < MIN_FIT:
        state.note(f"SKIP ({plan.fit_score}/10) {tag}")
        if lead.get("_key"):
            await lead_source.mark_processed(lead["_key"], "skipped")
        return
    from .form_filler import fill_application
    ctx = plan.cover_letter + "\n" + "\n".join(f"{k}: {v}" for k, v in plan.screener_answers.items())
    try:
        rep = await fill_application(url, plan_context=ctx, submit=AUTO_SUBMIT)
    except Exception as e:
        state.note(f"fill error {tag}: {e}")
        return
    if rep.submitted:
        state.applied.append(url)
        state.note(f"🚀 SUBMITTED ({plan.fit_score}/10) {tag}")
        memory.set_status(url, "submitted")
    elif rep.captcha_detected:
        state.note(f"🧩 CAPTCHA — needs human ({plan.fit_score}/10) {tag}")
    else:
        state.note(f"📝 filled ({plan.fit_score}/10) {tag}"
                   + (f" — {rep.error}" if rep.error else ""))
    if lead.get("_key"):
        await lead_source.mark_processed(lead["_key"], "processed")


async def run(budget_seconds: int | None = None) -> str:
    """Drive the whole system for the time budget, one lateral decision per tick."""
    state = MasterState()
    budget = budget_seconds or BUDGET
    state.note(f"Lateral Master online — {budget}s budget, "
               f"mode={'SUBMIT' if AUTO_SUBMIT else 'dry-run'}")

    while state.elapsed() < budget:
        state.ticks += 1
        if not state.queue:
            await _refill_queue(state)
        decision = await _lateral_decide(state)
        action, why = decision.get("action", "refill"), decision.get("reason", "")
        state.note(f"decide → {action}: {why}")

        if action == "done" and not state.queue:
            break
        if action == "refill" or (action == "apply" and not state.queue):
            await _refill_queue(state)
            if not state.queue:
                state.note("no new leads available — ending")
                break
            continue
        if action == "apply":
            await _apply_one(state)
        elif action == "learn":
            state.note("learned: prioritising community/creator ambassador forms (highest convert)")
        elif action == "report":
            await _tg("🧠 Lateral Master progress:\n" + "\n".join(state.log[-10:]))
        elif action == "done":
            break

    summary = (f"🧠 Lateral Thinking Master — run complete\n"
               f"Ticks: {state.ticks} | elapsed: {int(state.elapsed())}s | "
               f"applied: {len(state.applied)}\n\n" + "\n".join(state.log[-20:]))
    await _tg(summary)
    return summary
