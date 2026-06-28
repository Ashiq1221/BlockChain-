"""
AOS Telegram Bot — Autonomous AI Operating System
Pure aiohttp long-polling + autonomous background brain.
No Pyrogram needed — 100% HTTPS, works everywhere.
"""
import asyncio
import json
import sys
import subprocess
import os
import re
import time
from datetime import datetime

for pkg in ["aiohttp", "beautifulsoup4", "aiosqlite", "python-dotenv", "rich", "httpx"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

import aiohttp
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv
load_dotenv()

from aos.pipeline import AOS
from aos.config import AOSConfig as C

console = Console()
aos     = AOS()

BASE    = f"https://api.telegram.org/bot{C.BOT_TOKEN}"
TIMEOUT = aiohttp.ClientTimeout(total=35)

# ── State ─────────────────────────────────────────────────────────────────────
_last_hunt:     float = 0.0          # timestamp of last hunt
_hunt_results:  list  = []           # latest discovered opportunities
_hunt_running:  bool  = False
_contacted:     set   = set()        # avoid duplicate outreach

HUNT_INTERVAL = 3600   # run hunt every 60 minutes

WELCOME = (
    "🧠 *AOS — AI Operating System + Autonomous Brain ONLINE*\n\n"
    "*14-layer AI pipeline:*\n"
    "1️⃣ Task decomposition\n"
    "2️⃣ Specialist agents\n"
    "3️⃣ Critics & Debate\n"
    "4️⃣ Judge (10 metrics)\n"
    "5️⃣ Final Writer\n"
    "6️⃣ Confidence score\n\n"
    "*Autonomous brain (runs every hour):*\n"
    "🔍 Grok/Web search → Web3/AI opportunities\n"
    "🧠 AI ranks & filters best leads\n"
    "📨 Reports delivered here\n\n"
    "*Commands:* /hunt /jobs /status /providers\n"
    "*Or just ask anything.*"
)


# ── Bot API helpers ───────────────────────────────────────────────────────────

async def api(session: aiohttp.ClientSession, method: str, **kwargs) -> dict:
    try:
        async with session.post(f"{BASE}/{method}", json=kwargs, timeout=TIMEOUT) as r:
            return await r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


async def send(session, chat_id: int, text: str, reply_markup=None,
               parse_mode="Markdown") -> dict:
    params = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "sendMessage", **params)


async def edit(session, chat_id: int, msg_id: int, text: str,
               reply_markup=None) -> dict:
    params = {"chat_id": chat_id, "message_id": msg_id,
              "text": text[:4096], "parse_mode": "Markdown"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "editMessageText", **params)


async def answer_cb(session, cb_id: str) -> None:
    await api(session, "answerCallbackQuery", callback_query_id=cb_id)


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _start_kb():
    return {"inline_keyboard": [[
        {"text": "📊 Providers",  "callback_data": "providers"},
        {"text": "🔬 Test AOS",   "callback_data": "test"},
        {"text": "🔍 Hunt Now",   "callback_data": "hunt"},
    ]]}


def _feedback_kb(sources: list):
    buttons = []
    for i, s in enumerate(sources[:3]):
        if s.startswith("http"):
            buttons.append([{"text": f"🔗 Source {i+1}", "url": s}])
    buttons.append([
        {"text": "👍 Useful",     "callback_data": "fb_y"},
        {"text": "👎 Not useful", "callback_data": "fb_n"},
    ])
    return {"inline_keyboard": buttons}


# ── AOS pipeline ──────────────────────────────────────────────────────────────

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
    r      = await send(session, chat_id,
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


# ── Autonomous Brain ──────────────────────────────────────────────────────────

async def _grok_search(prompt: str) -> str:
    """Grok live X/Twitter + web search."""
    if not C.XAI_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {C.XAI_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": C.XAI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "search_parameters": {
                        "mode": "on",
                        "sources": [{"type": "x"}, {"type": "web"}],
                        "max_search_results": 15,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status != 200:
                    return ""
                data = await r.json()
                return data["choices"][0]["message"]["content"]
    except Exception:
        return ""


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

async def _web_search(query: str, num: int = 6) -> list[dict]:
    """Bing → DDG fallback search."""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get("https://www.bing.com/search",
                             params={"q": query, "count": num},
                             timeout=aiohttp.ClientTimeout(total=15)) as resp:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(await resp.text(), "html.parser")
                results = []
                for r in soup.select(".b_algo")[:num]:
                    a = r.select_one("h2 a")
                    p = r.select_one(".b_caption p, .b_algoSlug")
                    if a:
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a.get("href", ""),
                            "snippet": p.get_text(strip=True) if p else "",
                        })
                if results:
                    return results
    except Exception:
        pass
    # DDG fallback
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.post("https://html.duckduckgo.com/html/",
                              data={"q": query},
                              timeout=aiohttp.ClientTimeout(total=15)) as resp:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(await resp.text(), "html.parser")
                results = []
                for r in soup.select(".result")[:num]:
                    ta = r.select_one(".result__title")
                    sn = r.select_one(".result__snippet")
                    aa = r.select_one("a[href]")
                    if ta and aa:
                        results.append({
                            "title":   ta.get_text(strip=True),
                            "url":     aa.get("href", ""),
                            "snippet": sn.get_text(strip=True) if sn else "",
                        })
                return results
    except Exception:
        return []


async def _ai_think(prompt: str, max_tokens: int = 800) -> str:
    """Call best available AI provider."""
    providers = []
    if C.XAI_KEY:
        providers.append(("Grok",   "https://api.x.ai/v1/chat/completions",
                          C.XAI_KEY, C.XAI_MODEL))
    if C.CLAUDE_KEY:
        providers.append(("Claude", "anthropic", C.CLAUDE_KEY, "claude-3-5-haiku-20241022"))
    if C.GROQ_KEY:
        providers.append(("Groq",   "https://api.groq.com/openai/v1/chat/completions",
                          C.GROQ_KEY, C.GROQ_MODEL))
    if C.GEMINI_KEY:
        providers.append(("Gemini", "gemini", C.GEMINI_KEY, C.GEMINI_MODEL))

    for name, url, key, model in providers:
        try:
            async with aiohttp.ClientSession() as s:
                if url == "anthropic":
                    async with s.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                 "content-type": "application/json"},
                        json={"model": model, "max_tokens": max_tokens,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            return d["content"][0]["text"].strip()
                elif url == "gemini":
                    async with s.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
                        json={"contents": [{"parts": [{"text": prompt}]}],
                              "generationConfig": {"maxOutputTokens": max_tokens}},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            return d["candidates"][0]["content"]["parts"][0]["text"].strip()
                else:
                    async with s.post(
                        url,
                        headers={"Authorization": f"Bearer {key}",
                                 "Content-Type": "application/json"},
                        json={"model": model, "max_tokens": max_tokens,
                              "messages": [{"role": "user", "content": prompt}]},
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as r:
                        if r.status == 200:
                            d = await r.json()
                            return d["choices"][0]["message"]["content"].strip()
        except Exception:
            continue
    return ""


HUNT_QUERIES = [
    "new web3 AI blockchain project hiring ambassador community manager 2026",
    "DeFi NFT gaming crypto startup team open roles telegram 2026",
    "blockchain python developer remote job posting 2026",
    "web3 project looking for moderator content creator 2026",
    "AI crypto startup expanding team 2026 telegram apply",
]


async def _run_hunt(session, owner_id: int):
    """Full autonomous opportunity hunt: search → AI rank → report to owner."""
    global _hunt_results, _last_hunt, _hunt_running

    if _hunt_running:
        return
    _hunt_running = True
    _last_hunt    = time.time()

    try:
        await send(session, owner_id,
                   "🔍 *Autonomous Hunt Started*\n\nSearching Grok + Web for Web3/AI opportunities...")

        raw_chunks = []

        # PRIMARY: Grok live X/Twitter search
        grok_text = await _grok_search(
            "Search X/Twitter and the web RIGHT NOW and find 10 brand-new Web3, AI, or blockchain "
            "projects from 2026 that are actively hiring or seeking developers, ambassadors, "
            "community managers, moderators, or content creators.\n\n"
            "For each project include:\n"
            "- Project name\n- What they do (1 sentence)\n- Role(s) needed\n"
            "- Telegram username (t.me/...) if findable\n- Source URL or tweet\n\n"
            "Focus on REAL recent announcements. Include DeFi, NFT, AI x Web3, L1/L2."
        )
        if grok_text:
            raw_chunks.append(f"[GROK LIVE SEARCH]\n{grok_text}")

        # FALLBACK: Web scraping
        web_results = []
        for q in HUNT_QUERIES:
            results = await _web_search(q, num=4)
            web_results.extend(results)
            await asyncio.sleep(0.5)

        if web_results:
            web_text = "\n".join(
                f"- {r['title']}: {r['snippet']} ({r['url']})"
                for r in web_results[:20]
            )
            raw_chunks.append(f"[WEB SEARCH RESULTS]\n{web_text}")

        if not raw_chunks:
            await send(session, owner_id,
                       "⚠️ Hunt found no results — all search sources unavailable.")
            return

        combined = "\n\n".join(raw_chunks)[:6000]

        # AI analysis and ranking
        await send(session, owner_id, "🧠 *AI Analyzing opportunities...*")

        ai_prompt = f"""You are a 500 IQ career strategist analyzing raw search data.

RAW DATA:
{combined}

Extract and rank the TOP 5 most promising opportunities for a Web3/AI developer.
For each, provide:
1. **Project Name** — what they do
2. **Role** — what position is available
3. **Action** — exactly how to apply (Telegram link, email, URL)
4. **Why** — 1-sentence reason this is worth pursuing
5. **Score** — urgency/quality 1-10

Format each as a numbered list. Be specific and actionable. Skip vague results."""

        analysis = await _ai_think(ai_prompt, max_tokens=1200)

        if not analysis:
            analysis = "AI analysis unavailable — showing raw results.\n\n" + combined[:1500]

        # Extract TG usernames from raw data
        tg_handles = list(set(re.findall(r't\.me/([\w]+)', combined)))
        tg_handles = [h for h in tg_handles
                      if len(h) > 3 and h not in ("joinchat", "s", "share")][:5]

        _hunt_results = tg_handles

        ts  = datetime.now().strftime("%H:%M %d/%m")
        msg = (
            f"🎯 *Autonomous Hunt Report* — {ts}\n\n"
            f"{analysis[:3000]}"
        )
        if tg_handles:
            msg += f"\n\n📡 *Telegram groups found:*\n" + "\n".join(f"• t.me/{h}" for h in tg_handles)

        msg += "\n\n_Next hunt in 60 min. Type /hunt to run again._"

        await send(session, owner_id, msg[:4096])
        console.print(f"[green]Hunt complete — {len(tg_handles)} TG groups found[/green]")

    except Exception as e:
        console.print(f"[red]Hunt error: {e}[/red]")
        await send(session, owner_id, f"❌ Hunt error: {e}")
    finally:
        _hunt_running = False


async def _autonomous_loop(session, owner_id: int):
    """Background brain — runs hunt every HUNT_INTERVAL seconds."""
    await asyncio.sleep(30)   # wait 30s after bot starts before first hunt
    while True:
        try:
            await _run_hunt(session, owner_id)
        except Exception as e:
            console.print(f"[red]Autonomous loop error: {e}[/red]")
        await asyncio.sleep(HUNT_INTERVAL)


# ── Update handlers ───────────────────────────────────────────────────────────

async def handle_update(session: aiohttp.ClientSession, update: dict, owner_id: int):
    # ── Callback query ─────────────────────────────────────────────────────
    if cb := update.get("callback_query"):
        await answer_cb(session, cb["id"])
        chat_id = cb["message"]["chat"]["id"]
        uid     = cb.get("from", {}).get("id", 0)
        if C.OWNER_ID and uid != C.OWNER_ID:
            return
        data = cb.get("data", "")

        if data == "providers":
            p = C.available_providers()
            await send(session, chat_id, "*Active AI Providers:*\n" + "\n".join(f"✅ {x}" for x in p))

        elif data == "test":
            await send(session, chat_id, "🧪 Running test through all 14 layers...")
            asyncio.create_task(_run_aos(session, chat_id, "What is 2 + 2 and why?"))

        elif data == "hunt":
            asyncio.create_task(_run_hunt(session, chat_id))

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
                   "*Commands:*\n"
                   "/start — welcome\n"
                   "/hunt — force opportunity hunt now\n"
                   "/jobs — show latest found opportunities\n"
                   "/status — brain status\n"
                   "/providers — active AI providers\n\n"
                   "Or type any question — AOS 14-layer pipeline answers it.")

    elif text == "/providers":
        p    = C.available_providers()
        body = "\n".join(f"✅ {x}" for x in p) if p else "❌ None configured"
        await send(session, chat_id, f"*Active providers:*\n{body}")

    elif text in ("/hunt", "/hunt@AshiqAibot"):
        asyncio.create_task(_run_hunt(session, chat_id))

    elif text in ("/jobs", "/jobs@AshiqAibot"):
        if _hunt_results:
            body = "\n".join(f"• t.me/{h}" for h in _hunt_results)
            await send(session, chat_id,
                       f"*Latest TG Groups Found:*\n{body}\n\n_Run /hunt for a fresh search._")
        else:
            secs = max(0, int(HUNT_INTERVAL - (time.time() - _last_hunt))) if _last_hunt else 0
            if secs > 0:
                await send(session, chat_id, f"⏳ Hunt running — results in ~{secs}s.")
            else:
                asyncio.create_task(_run_hunt(session, chat_id))

    elif text in ("/status", "/status@AshiqAibot"):
        since = "never"
        if _last_hunt:
            mins = int((time.time() - _last_hunt) / 60)
            since = f"{mins} min ago"
        next_in = max(0, int((HUNT_INTERVAL - (time.time() - _last_hunt)) / 60)) if _last_hunt else 0
        status = (
            f"🧠 *Autonomous Brain Status*\n\n"
            f"{'🟢 Running' if not _hunt_running else '🔄 Hunting now...'}\n"
            f"Last hunt: {since}\n"
            f"Next hunt: in {next_in} min\n"
            f"TG groups found: {len(_hunt_results)}\n"
            f"Providers: {', '.join(C.available_providers())}"
        )
        await send(session, chat_id, status)

    elif text.startswith("/"):
        pass  # ignore unknown commands

    else:
        asyncio.create_task(_run_aos(session, chat_id, text))


# ── Long-polling loop ─────────────────────────────────────────────────────────

async def main():
    if not C.BOT_TOKEN:
        console.print("[bold red]❌ TELEGRAM_BOT_TOKEN not set in .env[/bold red]")
        return

    owner_id = C.OWNER_ID or 0

    console.print(Panel(
        "[bold magenta]🧠 AOS — AI Operating System + Autonomous Brain[/bold magenta]\n\n"
        f"[white]Bot:           @AshiqAibot\n"
        f"Providers:     {', '.join(C.available_providers()) or 'none'}\n"
        f"Owner ID:      {owner_id}\n"
        f"Hunt interval: every {HUNT_INTERVAL//60} min\n\n"
        "Open Telegram → @AshiqAibot → /start[/white]",
        border_style="magenta",
    ))

    offset = 0
    async with aiohttp.ClientSession() as session:
        await api(session, "deleteWebhook", drop_pending_updates=True)

        # Start autonomous brain in background
        if owner_id:
            asyncio.create_task(_autonomous_loop(session, owner_id))
            console.print("[green]✅ Autonomous brain started — first hunt in 30s[/green]")
        else:
            console.print("[yellow]⚠ TELEGRAM_OWNER_ID not set — autonomous brain disabled[/yellow]")

        while True:
            try:
                data = await api(session, "getUpdates",
                                 offset=offset, timeout=25, limit=10)
                if not data.get("ok"):
                    await asyncio.sleep(3)
                    continue

                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    asyncio.create_task(handle_update(session, upd, owner_id))

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
