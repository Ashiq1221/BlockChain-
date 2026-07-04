#!/usr/bin/env python3
"""Autopilot — the unattended hire-me orchestra.

Every run: harvest job links from Telegram job channels → debate each new
matched lead → on APPLY with fit >= APPLY_MIN_FIT, autofill the application
(and submit when APPLY_AUTO_SUBMIT=true) → report the whole run to the owner
via the Telegram bot → persist state so the next run never repeats work.

Designed to run on a GitHub Actions cron (see .github/workflows/autopilot.yml)
so it needs no machine. Env knobs:
  AUTOPILOT_MAX=5        max leads processed per run
  APPLY_MIN_FIT=7        min debate fit score to attempt an application
  APPLY_AUTO_SUBMIT      true = actually submit; false = dry-run + screenshots
  AUTOPILOT_FILL=true    false = debate only, skip the browser
  TELEGRAM_BOT_TOKEN / TELEGRAM_OWNER_ID   where to send the run report
"""
import asyncio
import json
import os
import time
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
load_dotenv()

from apply_agent import harvester, memory
from apply_agent.orchestrator import evaluate_job

STATE_PATH = Path("autopilot_state.json")

MAX_PER_RUN = int(os.getenv("AUTOPILOT_MAX", "5"))
MIN_FIT     = float(os.getenv("APPLY_MIN_FIT", "7"))
AUTO_SUBMIT = os.getenv("APPLY_AUTO_SUBMIT", "false").lower() == "true"
DO_FILL     = os.getenv("AUTOPILOT_FILL", "true").lower() == "true"
BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID    = os.getenv("TELEGRAM_OWNER_ID", "")


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"seen": [], "submitted": [], "runs": 0}


def _save_state(state: dict) -> None:
    state["seen"] = state["seen"][-2000:]          # cap growth
    STATE_PATH.write_text(json.dumps(state, indent=1))


async def _tg_report(text: str) -> None:
    if not BOT_TOKEN or not OWNER_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                         json={"chat_id": OWNER_ID, "text": text[:4096],
                               "disable_web_page_preview": True},
                         timeout=aiohttp.ClientTimeout(total=20))
    except Exception:
        pass


async def submit_approved(urls: list[str]) -> str:
    """Submit specific user-approved URLs (the per-job approval path).

    Each URL here was explicitly named by the owner (SUBMIT_URLS input on the
    workflow dispatch, or /apply_submit in the bot) after reviewing the
    autopilot's dry-run report for it.
    """
    from apply_agent.form_filler import fill_application
    state = _load_state()
    lines = [f"🚀 Submitting {len(urls)} approved application(s):", ""]
    for url in [u.strip() for u in urls if u.strip()]:
        try:
            plan = await evaluate_job(url)
            context = plan.cover_letter + "\n" + "\n".join(
                f"{k}: {v}" for k, v in plan.screener_answers.items())
            rep = await fill_application(url, plan_context=context, submit=True)
            if rep.submitted:
                lines.append(f"✅ SUBMITTED — {plan.title} @ {plan.company}\n   {url}")
                memory.set_status(url, "submitted")
                await _done(lead, "submitted")
                state["submitted"].append({"url": url, "title": plan.title, "ts": time.time()})
            elif rep.captcha_detected:
                lines.append(f"🧩 CAPTCHA blocked — finish manually: {url}")
            else:
                lines.append(f"⚠️ could not submit ({rep.error or 'no submit button found'}): {url}")
        except Exception as e:
            lines.append(f"💥 {url}: {e}")
    _save_state(state)
    report = "\n".join(lines)
    await _tg_report(report)
    return report


async def run_once() -> str:
    from aos.config import AOSConfig as C
    if not C.available_providers():
        msg = ("❌ Autopilot aborted: no AI provider configured. Add CF_ACCOUNT_ID + "
               "CF_EMAIL + CF_GLOBAL_API_KEY (or ANTHROPIC_API_KEY) as repo secrets. "
               "No leads were consumed.")
        await _tg_report(msg)
        return msg

    approved = os.getenv("SUBMIT_URLS", "").strip()
    if approved:
        return await submit_approved(approved.split(","))

    state = _load_state()
    seen = set(state["seen"])
    t0 = time.time()

    # Leads from @AshiqAibot (mirrored to CF KV) take priority over the harvest.
    from apply_agent import lead_source
    bot_jobs = await lead_source.pull_bot_jobs(limit=MAX_PER_RUN)
    bot_leads = [{"url": j["apply_url"], "title": j.get("title", ""),
                  "matched": True, "_key": j["_key"], "_bot": True}
                 for j in bot_jobs if j["apply_url"] not in seen]

    res = await harvester.harvest()
    harvest_leads = [l for l in harvester.pending(60, matched_only=True)
                     if l["url"] not in seen]
    leads = (bot_leads + harvest_leads)[:MAX_PER_RUN]

    lines = [f"🎼 Autopilot run #{state['runs'] + 1}",
             f"From @AshiqAibot (CF KV): {len(bot_leads)} lead(s).",
             f"Harvested {res['total']} links, {len(res['new'])} new; "
             f"processing {len(leads)} matched lead(s).",
             ("Mode: SUBMIT" if AUTO_SUBMIT else
              "Mode: dry-run — approve picks via the Autopilot workflow submit_urls box")
             + f" | min fit {MIN_FIT}", ""]

    async def _done(lead, status):
        """Mark a lead processed in its source (harvester DB or bot's CF KV)."""
        harvester.mark(lead["url"], status)
        if lead.get("_bot"):
            from apply_agent import lead_source
            await lead_source.mark_processed(lead["_key"], status)

    for lead in leads:
        url = lead["url"]
        seen.add(url)
        src = "🤖bot " if lead.get("_bot") else ""
        try:
            plan = await evaluate_job(url)
        except Exception as e:
            lines.append(f"💥 {src}{url} — evaluation error: {e}")
            await _done(lead, "error")
            continue

        tag = f"{plan.title or lead['title'][:40]} @ {plan.company or '?'}"
        if plan.decision != "APPLY":
            lines.append(f"⏭️ SKIP ({plan.fit_score}/10) {tag}")
            await _done(lead, "skipped")
            continue
        if plan.fit_score < MIN_FIT:
            lines.append(f"🤏 APPLY but fit {plan.fit_score} < {MIN_FIT}: {tag}\n   {url}")
            await _done(lead, "low_fit")
            continue
        if not DO_FILL:
            lines.append(f"✅ APPLY ({plan.fit_score}/10) {tag} — fill skipped\n   {url}")
            await _done(lead, "evaluated")
            continue

        from apply_agent.form_filler import fill_application
        context = plan.cover_letter + "\n" + "\n".join(
            f"{k}: {v}" for k, v in plan.screener_answers.items())
        try:
            rep = await fill_application(url, plan_context=context, submit=AUTO_SUBMIT)
        except Exception as e:
            lines.append(f"💥 fill error for {tag}: {e}\n   {url}")
            await _done(lead, "error")
            continue

        if rep.submitted:
            lines.append(f"🚀 SUBMITTED ({plan.fit_score}/10) {tag}\n   {url}")
            memory.set_status(url, "submitted")
            await _done(lead, "submitted")
            state["submitted"].append({"url": url, "title": tag, "ts": time.time()})
        elif rep.captcha_detected:
            lines.append(f"🧩 CAPTCHA — needs you ({plan.fit_score}/10) {tag}\n   {url}")
            await _done(lead, "manual_needed")
        else:
            lines.append(f"📝 filled {len(rep.filled)} fields, not submitted "
                         f"({plan.fit_score}/10) {tag}\n   {url}"
                         + (f"\n   ⚠️ {rep.error}" if rep.error else ""))
            await _done(lead, "filled_dryrun")

    state["runs"] += 1
    state["seen"] = sorted(seen)
    _save_state(state)

    lines.append("")
    lines.append(f"⏱ {int(time.time() - t0)}s | lifetime submitted: {len(state['submitted'])}")
    report = "\n".join(lines)
    await _tg_report(report)
    return report


if __name__ == "__main__":
    print(asyncio.run(run_once()))
