"""
AOS Telegram Bot — pure aiohttp long-polling, zero extra dependencies.
Works in any cloud/proxy environment. Run: python aos_bot.py
"""
import asyncio
import json
import sys
import subprocess

for pkg in ["aiohttp", "beautifulsoup4", "aiosqlite", "python-dotenv", "rich", "httpx"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

import aiohttp
from rich.console import Console
from rich.panel import Panel
import os
from dotenv import load_dotenv
load_dotenv()

from aos.pipeline import AOS
from aos.config import AOSConfig as C

console = Console()
aos     = AOS()

BASE    = f"https://api.telegram.org/bot{C.BOT_TOKEN}"
TIMEOUT = aiohttp.ClientTimeout(total=35)

WELCOME = (
    "🧠 *AOS — AI Operating System Online*\n\n"
    "Every question goes through:\n"
    "1️⃣ Task decomposition\n"
    "2️⃣ Specialist agents (Research, Reasoning, Coding, Search…)\n"
    "3️⃣ Critics (Devil's Advocate, Skeptic, Security…)\n"
    "4️⃣ Debate engine (up to 5 rounds)\n"
    "5️⃣ Judge (10 metrics)\n"
    "6️⃣ Final Writer (polished answer)\n"
    "7️⃣ Confidence score (0–100%)\n\n"
    "*Just ask anything.*"
)


# ── Bot API helpers ───────────────────────────────────────────────────────────

async def api(session: aiohttp.ClientSession, method: str, **kwargs) -> dict:
    try:
        async with session.post(f"{BASE}/{method}", json=kwargs, timeout=TIMEOUT) as r:
            return await r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


async def send(session, chat_id: int, text: str, reply_markup=None, parse_mode="Markdown") -> dict:
    params = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "sendMessage", **params)


async def edit(session, chat_id: int, msg_id: int, text: str, reply_markup=None) -> dict:
    params = {"chat_id": chat_id, "message_id": msg_id,
              "text": text[:4096], "parse_mode": "Markdown"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "editMessageText", **params)


async def answer_cb(session, cb_id: str) -> None:
    await api(session, "answerCallbackQuery", callback_query_id=cb_id)


# ── Keyboard builders ─────────────────────────────────────────────────────────

def _start_kb():
    return {"inline_keyboard": [[
        {"text": "📊 Providers", "callback_data": "providers"},
        {"text": "🔬 Test AOS",  "callback_data": "test"},
    ]]}


def _feedback_kb(sources: list[str]):
    buttons = []
    for i, s in enumerate(sources[:3]):
        if s.startswith("http"):
            buttons.append([{"text": f"🔗 Source {i+1}", "url": s}])
    buttons.append([
        {"text": "👍 Useful",     "callback_data": "fb_y"},
        {"text": "👎 Not useful", "callback_data": "fb_n"},
    ])
    return {"inline_keyboard": buttons}


# ── AOS helpers ───────────────────────────────────────────────────────────────

def _bar(pct: int) -> str:
    return "█" * (pct // 10) + "░" * (10 - pct // 10)


def _footer(resp) -> str:
    critics = "✅" if resp.critics_passed else "⚠️"
    return (
        f"\n\n─────────────────\n"
        f"🎯 *Confidence: {resp.confidence}%* {_bar(resp.confidence)}\n"
        f"{resp.confidence_reason}\n"
        f"👥 {', '.join(resp.agents_used)}\n"
        f"🔁 Debate: {resp.debate_rounds} round(s)  🛡 Critics: {critics}  ⏱ {resp.elapsed_ms}ms"
    )


async def _run_aos(session, chat_id: int, text: str):
    """Process one message through AOS — non-blocking task."""
    r = await send(session, chat_id,
                   "🧠 *AOS Processing...*\n\n⏳ Routing → Agents → Critics → Debate → Judge → Writing...")
    msg_id = r.get("result", {}).get("message_id")
    try:
        resp   = await aos.process(text)
        answer = resp.answer + _footer(resp)
        if len(answer) > 4000:
            answer = answer[:3900] + "\n\n_[truncated]_"
        kb = _feedback_kb(resp.sources) if resp.sources else None
        if msg_id:
            await edit(session, chat_id, msg_id, answer, kb)
        else:
            await send(session, chat_id, answer, kb)
    except Exception as e:
        console.print(f"[red]AOS error: {e}[/red]")
        if msg_id:
            await edit(session, chat_id, msg_id, f"❌ AOS Error: {e}")


# ── Update handlers ───────────────────────────────────────────────────────────

async def handle_update(session: aiohttp.ClientSession, update: dict):
    # ── Callback query (button press) ──────────────────────────────────────
    if cb := update.get("callback_query"):
        await answer_cb(session, cb["id"])
        chat_id = cb["message"]["chat"]["id"]
        uid     = cb.get("from", {}).get("id", 0)
        if C.OWNER_ID and uid != C.OWNER_ID:
            return
        data = cb.get("data", "")

        if data == "providers":
            p    = C.available_providers()
            text = "*Active AI Providers:*\n" + "\n".join(f"✅ {x}" for x in p)
            await send(session, chat_id, text)

        elif data == "test":
            await send(session, chat_id, "🧪 Running test through all 14 layers...")
            asyncio.create_task(_run_aos(session, chat_id, "What is 2 + 2 and why?"))

        elif data in ("fb_y", "fb_n"):
            emoji = "👍" if data == "fb_y" else "👎"
            await send(session, chat_id, f"{emoji} Thanks! AOS learns from your feedback.")
        return

    # ── Regular message ────────────────────────────────────────────────────
    msg = update.get("message", {})
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    uid     = msg.get("from", {}).get("id", 0)
    text    = (msg.get("text") or "").strip()

    if C.OWNER_ID and uid != C.OWNER_ID:
        await send(session, chat_id, "⛔ Access denied.")
        return

    if not text:
        return

    if text == "/start":
        await send(session, chat_id, WELCOME, _start_kb())
    elif text == "/help":
        await send(session, chat_id,
                   "*Commands:*\n/start — welcome\n/help — this\n\nOr just type any question!")
    elif text == "/providers":
        p    = C.available_providers()
        body = "\n".join(f"✅ {x}" for x in p) if p else "❌ None configured"
        await send(session, chat_id, f"*Active providers:*\n{body}")
    elif text.startswith("/"):
        pass  # ignore other commands
    else:
        # Non-blocking — queue each message as its own task
        asyncio.create_task(_run_aos(session, chat_id, text))


# ── Long-polling loop ─────────────────────────────────────────────────────────

async def main():
    if not C.BOT_TOKEN:
        console.print("[bold red]❌ TELEGRAM_BOT_TOKEN not set in .env[/bold red]")
        return

    console.print(Panel(
        "[bold magenta]🧠 AOS Telegram Bot — ONLINE[/bold magenta]\n\n"
        f"[white]Bot:       @AshiqAibot\n"
        f"Providers: {', '.join(C.available_providers()) or 'none'}\n"
        f"Owner ID:  {C.OWNER_ID}\n\n"
        "Open Telegram → @AshiqAibot → ask anything![/white]",
        border_style="magenta",
    ))

    offset = 0
    async with aiohttp.ClientSession() as session:
        # Delete any stale webhook
        await api(session, "deleteWebhook", drop_pending_updates=True)

        while True:
            try:
                data = await api(session, "getUpdates",
                                 offset=offset, timeout=25, limit=10)
                if not data.get("ok"):
                    await asyncio.sleep(3)
                    continue

                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    asyncio.create_task(handle_update(session, upd))

            except asyncio.CancelledError:
                raise
            except Exception as e:
                console.print(f"[red]Poll error: {e}[/red]")
                await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]AOS offline.[/yellow]")
