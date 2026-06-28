"""
AOS Telegram Bot — 5-Agent Autonomous Orchestra
Cloud-native: all research + planning runs 24/7 via HTTPS.
Telegram actions (join group, DM CEO) queued for Termux execution.
"""
import asyncio, json, sys, subprocess, os, re, time, sqlite3
from datetime import datetime

for pkg in ["aiohttp", "beautifulsoup4", "aiosqlite", "python-dotenv", "rich", "httpx"]:
    try:
        __import__(pkg.replace("-", "_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

import aiohttp
from bs4 import BeautifulSoup
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv
load_dotenv()

from aos.pipeline import AOS
from aos.config import AOSConfig as C

console = Console()
aos     = AOS()

BASE    = f"https://api.telegram.org/bot{C.BOT_TOKEN}"
TIMEOUT = aiohttp.ClientTimeout(total=40)
HUNT_INTERVAL = 3600   # autonomous hunt every 60 min
_hunt_running = False
_last_hunt    = 0.0

# ── Action Queue DB ───────────────────────────────────────────────────────────
QUEUE_DB = "action_queue.db"

def _init_queue_db():
    db = sqlite3.connect(QUEUE_DB)
    db.execute("""
        CREATE TABLE IF NOT EXISTS action_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            status      TEXT DEFAULT 'pending',
            project     TEXT,
            tg_username TEXT,
            ceo_hint    TEXT,
            dm_message  TEXT,
            score       INTEGER DEFAULT 0,
            reason      TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            executed_at TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS hunt_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            summary    TEXT,
            leads      INTEGER,
            ts         TEXT DEFAULT (datetime('now'))
        )
    """)
    db.commit()
    db.close()

_init_queue_db()

def _queue_action(project, tg_username, ceo_hint, dm_message, score, reason):
    db = sqlite3.connect(QUEUE_DB)
    # Don't duplicate
    existing = db.execute(
        "SELECT id FROM action_queue WHERE tg_username=? AND status='pending'",
        (tg_username,)
    ).fetchone()
    if not existing:
        db.execute(
            "INSERT INTO action_queue (project,tg_username,ceo_hint,dm_message,score,reason) VALUES (?,?,?,?,?,?)",
            (project, tg_username, ceo_hint, dm_message, score, reason)
        )
        db.commit()
    db.close()

def _get_queue(status="pending", limit=20):
    db = sqlite3.connect(QUEUE_DB)
    rows = db.execute(
        "SELECT * FROM action_queue WHERE status=? ORDER BY score DESC LIMIT ?",
        (status, limit)
    ).fetchall()
    cols = [d[0] for d in db.execute("PRAGMA table_info(action_queue)").fetchall()]
    db.close()
    return [dict(zip(cols, r)) for r in rows]

def _queue_size(status="pending"):
    db = sqlite3.connect(QUEUE_DB)
    n = db.execute("SELECT COUNT(*) FROM action_queue WHERE status=?", (status,)).fetchone()[0]
    db.close()
    return n


# ── Bot API helpers ───────────────────────────────────────────────────────────

async def api(session, method, **kwargs):
    try:
        async with session.post(f"{BASE}/{method}", json=kwargs, timeout=TIMEOUT) as r:
            return await r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

async def send(session, chat_id, text, reply_markup=None, parse_mode="Markdown"):
    params = {"chat_id": chat_id, "text": text[:4096], "parse_mode": parse_mode}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "sendMessage", **params)

async def edit(session, chat_id, msg_id, text, reply_markup=None):
    params = {"chat_id": chat_id, "message_id": msg_id,
              "text": text[:4096], "parse_mode": "Markdown"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return await api(session, "editMessageText", **params)

async def answer_cb(session, cb_id):
    await api(session, "answerCallbackQuery", callback_query_id=cb_id)


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_kb():
    return {"inline_keyboard": [[
        {"text": "🔍 Hunt Now",    "callback_data": "hunt"},
        {"text": "📋 Queue",       "callback_data": "queue"},
        {"text": "📊 Providers",   "callback_data": "providers"},
    ]]}


# ── AOS pipeline ──────────────────────────────────────────────────────────────

def _bar(pct):
    return "█" * (pct // 10) + "░" * (10 - pct // 10)

def _footer(resp):
    critics = "✅" if resp.critics_passed else "⚠️"
    return (
        f"\n\n─────────────────\n"
        f"🎯 *Confidence: {resp.confidence}%* {_bar(resp.confidence)}\n"
        f"{resp.confidence_reason}\n"
        f"👥 {', '.join(resp.agents_used)}\n"
        f"🔁 Debate: {resp.debate_rounds} round(s)  🛡 Critics: {critics}  ⏱ {resp.elapsed_ms}ms"
    )

async def _run_aos(session, chat_id, text):
    r      = await send(session, chat_id,
                        "🧠 *AOS Processing...*\n\n⏳ Routing → Agents → Critics → Debate → Judge → Writing...")
    msg_id = r.get("result", {}).get("message_id")
    try:
        resp   = await aos.process(text)
        answer = resp.answer + _footer(resp)
        if len(answer) > 4000:
            answer = answer[:3900] + "\n\n_[truncated]_"
        kb = None
        if resp.sources:
            buttons = [[{"text": f"🔗 Source {i+1}", "url": s}]
                       for i, s in enumerate(resp.sources[:3]) if s.startswith("http")]
            buttons.append([{"text": "👍", "callback_data": "fb_y"},
                            {"text": "👎", "callback_data": "fb_n"}])
            kb = {"inline_keyboard": buttons}
        if msg_id:
            await edit(session, chat_id, msg_id, answer, kb)
        else:
            await send(session, chat_id, answer, kb)
    except Exception as e:
        if msg_id:
            await edit(session, chat_id, msg_id, f"❌ AOS Error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  5-AGENT AUTONOMOUS ORCHESTRA
# ══════════════════════════════════════════════════════════════════════════════

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


# ── AGENT 1: SCOUT — Find raw opportunities ───────────────────────────────────

SCOUT_QUERIES = [
    "new web3 AI blockchain project hiring ambassador community manager 2026",
    "DeFi NFT crypto startup hiring developer moderator telegram 2026",
    "blockchain python developer remote job opening 2026",
    "web3 project open roles content creator ambassador apply telegram 2026",
    "AI crypto startup team expansion hiring 2026 telegram",
]

async def _tavily_search(query: str, max_results: int = 8) -> list[dict]:
    """Tavily API — works through cloud proxy, no scraping needed."""
    if not C.TAVILY_KEY:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": C.TAVILY_KEY,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": max_results,
                    "include_answer": True,
                },
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    results = d.get("results", [])
                    answer  = d.get("answer", "")
                    return [{"title": x.get("title",""), "url": x.get("url",""),
                             "snip": x.get("content","")[:300], "answer": answer}
                            for x in results]
    except Exception as e:
        console.print(f"[yellow]  Tavily error: {e}[/yellow]")
    return []


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
                        "max_search_results": 20,
                    },
                },
                timeout=aiohttp.ClientTimeout(total=35),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return d["choices"][0]["message"]["content"]
                console.print(f"[yellow]  Grok status {r.status}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]  Grok error: {e}[/yellow]")
    return ""


async def agent_scout() -> str:
    """PRIMARY: Tavily API | SECONDARY: Grok live search | both via HTTPS."""
    console.print("[cyan]Agent 1 Scout: Searching...[/cyan]")
    chunks = []

    # ── PRIMARY: Tavily (reliable HTTPS API, works in cloud) ─────────────────
    tavily_hits = []
    tasks = [_tavily_search(q, max_results=6) for q in SCOUT_QUERIES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            tavily_hits.extend(r)

    if tavily_hits:
        # Deduplicate by URL
        seen, unique = set(), []
        for h in tavily_hits:
            if h["url"] not in seen:
                seen.add(h["url"])
                unique.append(h)
        lines = [f"- {h['title']}: {h['snip']} | {h['url']}" for h in unique[:30]]
        chunks.append(f"[TAVILY SEARCH — {len(unique)} results]\n" + "\n".join(lines))
        console.print(f"[green]  Tavily: {len(unique)} results[/green]")

    # ── SECONDARY: Grok live X/Twitter (if credits available) ────────────────
    grok_text = await _grok_search(
        "Search X/Twitter and web RIGHT NOW (2026) for Web3, AI, blockchain projects "
        "ACTIVELY hiring or seeking developers, ambassadors, community managers, "
        "moderators, content creators.\n\n"
        "For each: Name | What they do | Role needed | Telegram handle | Source URL\n"
        "Find at least 10 real projects with actual hiring signals."
    )
    if grok_text:
        chunks.append(f"[GROK LIVE X/TWITTER]\n{grok_text}")
        console.print(f"[green]  Grok: {len(grok_text)} chars[/green]")

    if not chunks:
        console.print("[red]  Scout: all sources failed[/red]")

    return "\n\n".join(chunks)[:8000]


# ── AGENT 2: ANALYST — Score and extract structured leads ─────────────────────

async def agent_analyst(raw_data: str) -> list[dict]:
    """AI extracts and scores structured project leads from raw scout data."""
    console.print("[cyan]Agent 2 Analyst: Scoring leads...[/cyan]")
    if not raw_data.strip():
        return []

    prompt = f"""You are a 500 IQ talent agent analyzing raw intelligence data.

RAW DATA:
{raw_data[:6000]}

Extract up to 10 REAL hiring opportunities. For each, return a JSON object:
{{
  "project": "Project Name",
  "what_they_do": "One sentence",
  "role": "Specific role they need",
  "tg_username": "username (without @, or empty string if not found)",
  "website": "URL if found",
  "source": "tweet URL or webpage URL",
  "score": 8,
  "reason": "Why this is worth pursuing"
}}

Score 1-10 based on: recency, specificity of need, quality of project, likelihood of response.
Return ONLY a valid JSON array. No markdown. No explanation. Just the array."""

    result = await _ai_call(prompt, max_tokens=2000)

    # Parse JSON
    match = re.search(r'\[.*\]', result, re.DOTALL)
    if not match:
        console.print("[yellow]  Analyst: no JSON found[/yellow]")
        return []
    try:
        leads = json.loads(match.group())
        leads = [l for l in leads if isinstance(l, dict) and l.get("project")]
        console.print(f"[green]  Analyst: {len(leads)} leads scored[/green]")
        return sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
    except Exception as e:
        console.print(f"[yellow]  Analyst JSON error: {e}[/yellow]")
        return []


# ── AGENT 3: STRATEGIST — Pick top targets and decide approach ────────────────

async def agent_strategist(leads: list[dict]) -> list[dict]:
    """Filters already-contacted leads, selects top 5, decides approach per target."""
    console.print("[cyan]Agent 3 Strategist: Planning approach...[/cyan]")
    existing = {r['tg_username'] for r in _get_queue(status='pending')}
    existing |= {r['tg_username'] for r in _get_queue(status='done')}
    existing |= {r['tg_username'] for r in _get_queue(status='skipped')}

    fresh = [l for l in leads if l.get("tg_username") and
             l["tg_username"] not in existing and len(l["tg_username"]) > 2][:5]

    if not fresh:
        console.print("[yellow]  Strategist: no fresh leads[/yellow]")
        return []

    console.print(f"[green]  Strategist: {len(fresh)} fresh targets selected[/green]")
    return fresh


# ── AGENT 4: WRITER — Craft personalized DMs ─────────────────────────────────

async def agent_writer(lead: dict) -> tuple[str, str]:
    """Crafts a human-sounding personalized DM and CEO identification hint."""
    console.print(f"[cyan]Agent 4 Writer: Crafting DM for {lead['project']}...[/cyan]")

    dm_prompt = f"""You are a brilliant career strategist writing a Telegram DM.

Target: {lead['project']} — {lead.get('what_they_do', '')}
Role they need: {lead.get('role', 'developer/community')}
Telegram: @{lead.get('tg_username', '')}

Write a SHORT (3-4 sentences max), human-sounding, non-robotic DM to the CEO/founder.
- Reference something specific about their project
- Briefly mention relevant skills (Python developer, Web3 experience, blockchain)
- End with a clear question (not just "please hire me")
- Sound like a real person, not a job application template
- NO emojis, NO "Dear Sir/Madam", NO generic phrases

Return ONLY the message text, nothing else."""

    ceo_prompt = f"""For the project "{lead['project']}" with Telegram @{lead.get('tg_username', '')},
what keywords or patterns would identify the CEO/founder in a Telegram group?
(e.g. "founder", "CEO", "creator", pinned messages, admin with no tag, etc.)
Give 3-5 specific signals to look for. Be brief."""

    dm_msg, ceo_hint = await asyncio.gather(
        _ai_call(dm_prompt, max_tokens=300),
        _ai_call(ceo_prompt, max_tokens=150),
    )
    return dm_msg.strip(), ceo_hint.strip()


# ── AGENT 5: QUEUE MANAGER — Store and report ────────────────────────────────

async def agent_queue(session, owner_id: int, targets: list[dict],
                      dm_messages: list[tuple]):
    """Stores action queue in SQLite and sends rich report to owner."""
    console.print("[cyan]Agent 5 Queue: Storing actions and reporting...[/cyan]")

    queued = 0
    report_lines = ["🎯 *5-Agent Hunt Report*\n"]

    for lead, (dm_msg, ceo_hint) in zip(targets, dm_messages):
        project  = lead.get("project", "Unknown")
        tg_user  = lead.get("tg_username", "")
        score    = lead.get("score", 5)
        reason   = lead.get("reason", "")
        role     = lead.get("role", "")

        if tg_user and dm_msg:
            _queue_action(project, tg_user, ceo_hint, dm_msg, score, reason)
            queued += 1

        line = (
            f"\n{'⭐' * min(score, 5)} *{project}* (score: {score}/10)\n"
            f"Role: {role}\n"
            f"TG: @{tg_user}\n"
            f"Why: {reason[:120]}\n"
            f"_DM queued: \"{dm_msg[:80]}...\"_"
        )
        report_lines.append(line)

    queue_size = _queue_size("pending")
    ts = datetime.now().strftime("%H:%M %d/%m")

    summary = "\n".join(report_lines)
    summary += (
        f"\n\n─────────────────\n"
        f"✅ *{queued} new actions queued*\n"
        f"📋 Total queue: {queue_size} pending\n"
        f"🕐 {ts} | Next hunt in 60 min\n\n"
        f"*To execute on your phone:*\n"
        f"`cd ~/BlockChain- && bash run_termux.sh`\n"
        f"Then send `/execute` in the bot."
    )

    await send(session, owner_id, summary[:4096])

    # Log to DB
    db = sqlite3.connect(QUEUE_DB)
    db.execute("INSERT INTO hunt_log (summary, leads) VALUES (?,?)",
               (f"{queued} queued from hunt at {ts}", queued))
    db.commit()
    db.close()

    console.print(f"[bold green]Hunt complete: {queued} actions queued[/bold green]")


# ── AI call helper ────────────────────────────────────────────────────────────

async def _ai_call(prompt: str, max_tokens: int = 800) -> str:
    providers = []
    if C.XAI_KEY:
        providers.append(("Grok",   "https://api.x.ai/v1/chat/completions",
                          C.XAI_KEY,  C.XAI_MODEL, "openai"))
    if C.CLAUDE_KEY:
        providers.append(("Claude", "anthropic",
                          C.CLAUDE_KEY, "claude-3-5-haiku-20241022", "anthropic"))
    if C.GROQ_KEY:
        providers.append(("Groq",   "https://api.groq.com/openai/v1/chat/completions",
                          C.GROQ_KEY,  C.GROQ_MODEL, "openai"))
    if C.GEMINI_KEY:
        providers.append(("Gemini", "gemini",
                          C.GEMINI_KEY, C.GEMINI_MODEL, "gemini"))

    for name, url, key, model, fmt in providers:
        try:
            async with aiohttp.ClientSession() as s:
                if fmt == "anthropic":
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
                elif fmt == "gemini":
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


# ── ORCHESTRA CONDUCTOR ───────────────────────────────────────────────────────

async def run_orchestra(session, owner_id: int):
    """Runs all 5 agents in sequence — the full autonomous pipeline."""
    global _hunt_running, _last_hunt
    if _hunt_running:
        await send(session, owner_id, "⏳ Hunt already running, please wait...")
        return
    _hunt_running = True
    _last_hunt    = time.time()

    try:
        await send(session, owner_id,
                   "🎼 *5-Agent Orchestra Starting*\n\n"
                   "Agent 1 Scout    → Searching X/Twitter + Web...\n"
                   "Agent 2 Analyst  → AI scoring leads\n"
                   "Agent 3 Strategist → Selecting targets\n"
                   "Agent 4 Writer   → Crafting DMs\n"
                   "Agent 5 Queue    → Storing for execution")

        # Agent 1: Scout
        raw = await agent_scout()
        if not raw:
            await send(session, owner_id, "⚠️ Scout found nothing — all sources failed.")
            return

        # Agent 2: Analyst
        leads = await agent_analyst(raw)
        if not leads:
            await send(session, owner_id, "⚠️ Analyst: no structured leads extracted.")
            return

        # Agent 3: Strategist
        targets = await agent_strategist(leads)
        if not targets:
            await send(session, owner_id,
                       f"✅ Hunt done — all {len(leads)} leads already in queue.\n"
                       f"Queue size: {_queue_size('pending')} pending.")
            return

        # Agent 4: Writer (parallel DM crafting)
        dm_results = await asyncio.gather(
            *[agent_writer(t) for t in targets]
        )

        # Agent 5: Queue + Report
        await agent_queue(session, owner_id, targets, dm_results)

    except Exception as e:
        console.print(f"[red]Orchestra error: {e}[/red]")
        await send(session, owner_id, f"❌ Orchestra error: {e}")
    finally:
        _hunt_running = False


async def _auto_loop(session, owner_id: int):
    await asyncio.sleep(20)  # brief startup delay
    while True:
        await run_orchestra(session, owner_id)
        await asyncio.sleep(HUNT_INTERVAL)


# ── Update handlers ───────────────────────────────────────────────────────────

WELCOME = (
    "🎼 *AOS — 5-Agent Autonomous Orchestra*\n\n"
    "*How it works:*\n"
    "🔍 Agent 1: Scout (Grok X/Twitter + Web search)\n"
    "🧠 Agent 2: Analyst (AI scores each lead)\n"
    "🎯 Agent 3: Strategist (picks top targets)\n"
    "✍️ Agent 4: Writer (crafts personalized DM)\n"
    "📋 Agent 5: Queue (stores for Termux execution)\n\n"
    "*Runs every 60 min automatically.*\n\n"
    "*Commands:*\n"
    "/hunt — run orchestra now\n"
    "/queue — show pending actions\n"
    "/status — brain status\n"
    "/providers — active AI\n"
    "Or ask anything — AOS 14-layer brain answers."
)

async def handle_update(session, update, owner_id):
    if cb := update.get("callback_query"):
        await answer_cb(session, cb["id"])
        chat_id = cb["message"]["chat"]["id"]
        uid     = cb.get("from", {}).get("id", 0)
        if C.OWNER_ID and uid != C.OWNER_ID:
            return
        data = cb.get("data", "")
        if data == "hunt":
            asyncio.create_task(run_orchestra(session, chat_id))
        elif data == "queue":
            await _cmd_queue(session, chat_id)
        elif data == "providers":
            p = C.available_providers()
            await send(session, chat_id,
                       "*Active AI Providers:*\n" + "\n".join(f"✅ {x}" for x in p))
        elif data in ("fb_y", "fb_n"):
            await send(session, chat_id,
                       "👍 Thanks!" if data == "fb_y" else "👎 Noted!")
        return

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
        await send(session, chat_id, WELCOME, _main_kb())

    elif text in ("/hunt", "/hunt@AshiqAibot"):
        asyncio.create_task(run_orchestra(session, chat_id))

    elif text in ("/queue", "/queue@AshiqAibot"):
        await _cmd_queue(session, chat_id)

    elif text in ("/status", "/status@AshiqAibot"):
        await _cmd_status(session, chat_id)

    elif text in ("/providers", "/providers@AshiqAibot"):
        p = C.available_providers()
        body = "\n".join(f"✅ {x}" for x in p) if p else "❌ None"
        await send(session, chat_id, f"*Active providers:*\n{body}")

    elif text in ("/help", "/help@AshiqAibot"):
        await send(session, chat_id,
                   "*Commands:*\n"
                   "/hunt — run full 5-agent orchestra now\n"
                   "/queue — view pending DM actions\n"
                   "/status — orchestra status\n"
                   "/providers — active AI providers\n\n"
                   "_Execute queued DMs on Termux:_\n"
                   "`bash run_termux.sh` → `/execute`")

    elif text.startswith("/"):
        pass

    else:
        asyncio.create_task(_run_aos(session, chat_id, text))


async def _cmd_queue(session, chat_id):
    items = _get_queue("pending", limit=10)
    if not items:
        done = _queue_size("done")
        await send(session, chat_id,
                   f"📋 *Queue empty*\n{done} actions already executed.\n\nRun /hunt to find new targets.")
        return
    lines = [f"📋 *Pending Actions ({len(items)})*\n"]
    for i, item in enumerate(items, 1):
        lines.append(
            f"{i}. *{item['project']}* (score: {item['score']}/10)\n"
            f"   TG: @{item['tg_username']}\n"
            f"   _\"{item['dm_message'][:60]}...\"_"
        )
    lines.append("\n_Run on Termux: `bash run_termux.sh` → `/execute`_")
    await send(session, chat_id, "\n".join(lines)[:4096])


async def _cmd_status(session, chat_id):
    pending = _queue_size("pending")
    done    = _queue_size("done")
    since   = "never"
    next_in = 60
    if _last_hunt:
        mins    = int((time.time() - _last_hunt) / 60)
        since   = f"{mins} min ago"
        next_in = max(0, 60 - mins)
    status = (
        f"🎼 *Orchestra Status*\n\n"
        f"{'🔄 Hunting now...' if _hunt_running else '🟢 Ready'}\n"
        f"Last hunt: {since}\n"
        f"Next hunt: in {next_in} min\n\n"
        f"📋 Queue: {pending} pending, {done} executed\n"
        f"🤖 Providers: {', '.join(C.available_providers())}"
    )
    await send(session, chat_id, status, _main_kb())


# ── Long-polling loop ─────────────────────────────────────────────────────────

async def main():
    if not C.BOT_TOKEN:
        console.print("[bold red]❌ TELEGRAM_BOT_TOKEN not set[/bold red]")
        return

    owner_id = C.OWNER_ID or 0
    console.print(Panel(
        "[bold magenta]🎼 AOS — 5-Agent Autonomous Orchestra[/bold magenta]\n\n"
        f"[white]Bot:       @AshiqAibot\n"
        f"Providers: {', '.join(C.available_providers()) or 'none'}\n"
        f"Owner:     {owner_id}\n"
        f"Hunt:      every {HUNT_INTERVAL//60} min\n\n"
        "First hunt fires in 20 seconds...[/white]",
        border_style="magenta",
    ))

    offset = 0
    async with aiohttp.ClientSession() as session:
        await api(session, "deleteWebhook", drop_pending_updates=True)

        if owner_id:
            asyncio.create_task(_auto_loop(session, owner_id))
            console.print("[green]✅ Autonomous orchestra running[/green]")

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
        console.print("\n[yellow]Orchestra offline.[/yellow]")
