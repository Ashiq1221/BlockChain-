#!/usr/bin/env python3
"""Fill + submit a single application URL directly (no debate gate).

For JS-rendered / multi-step forms where a plain fetch can't feed the debate.
The profile supplies name/email/location/handles; SUBMIT_CONTEXT adds the
tailored free-text answer. Set DO_SUBMIT=false for a dry-run (fills + shots,
no submit). Reports to Telegram if TELEGRAM_* are set.

Env:  SUBMIT_URL (required)  SUBMIT_CONTEXT  DO_SUBMIT=true|false
"""
import asyncio
import os

import aiohttp
from dotenv import load_dotenv
load_dotenv()

from apply_agent.form_filler import fill_application
from apply_agent import memory


async def _tg(text: str) -> None:
    tok, owner = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_OWNER_ID", "")
    if not tok or not owner:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                         json={"chat_id": owner, "text": text[:4096],
                               "disable_web_page_preview": True},
                         timeout=aiohttp.ClientTimeout(total=20))
    except Exception:
        pass


async def main() -> None:
    url = os.environ["SUBMIT_URL"].strip()
    context = os.getenv("SUBMIT_CONTEXT", "")
    submit = os.getenv("DO_SUBMIT", "true").lower() == "true"

    rep = await fill_application(url, plan_context=context, submit=submit)
    print(rep.summary())

    status = ("submitted" if rep.submitted else
              "captcha" if rep.captcha_detected else
              "filled_dryrun" if rep.filled else "failed")
    memory.record(url, "", "", "DIRECT", 0.0, notes=f"submit_one: {status}")
    memory.set_status(url, status)
    await _tg(f"🖊️ Apply Pilot direct submit\n{url}\n\n{rep.summary()[:1500]}")


if __name__ == "__main__":
    asyncio.run(main())
