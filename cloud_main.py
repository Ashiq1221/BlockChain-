"""
Full cloud autonomous bot — deploy to Railway (railway.app).

Pipeline (every 2nd cycle, 24/7):
  1. Discover Web3/AI projects hiring via X/Twitter + Tavily
  2. Find & join their Telegram group
  3. Read the room context
  4. Identify CEO / Founder (admin scan)
  5. Craft personalized DM using Ashiq's real stats
  6. Send DM via user account (Pyrogram StringSession)

Bot commands (send to your bot on Telegram):
  /execute — run the FULL pipeline now (most powerful)
  /hunt    — trigger one hunt+DM cycle right now
  /status  — show cycle stats and recent actions
  /pause   — pause autonomous mode
  /resume  — resume autonomous mode
  /dm @user message — manually send a DM via your account
  /search query — search for opportunities now
  /cycle N — change hunt frequency (1=every cycle)
  any text — AI chat (powered by Groq)

Required env vars:
  TELEGRAM_SESSION_STRING   ← from generate_session.py
  TELEGRAM_API_ID
  TELEGRAM_API_HASH
  TELEGRAM_BOT_TOKEN        ← reports to your Telegram
  TELEGRAM_OWNER_ID
  GROQ_API_KEY
  TAVILY_API_KEY
  GEMINI_API_KEY
"""
import asyncio, os, sys, subprocess, aiohttp, json
from dotenv import load_dotenv
load_dotenv()

for pkg in ["pyrogram==2.0.106", "TgCrypto", "httpx", "aiohttp",
            "aiosqlite", "python-dotenv", "rich", "aiofiles", "beautifulsoup4"]:
    try:
        __import__(pkg.split("==")[0].replace("-", "_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

from pyrogram import Client
from rich.console import Console
from rich.panel import Panel

from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain
from telegram_agents.tools import ai_tools, web_tools, telegram_tools

console = Console()

BOT_BASE     = f"https://api.telegram.org/bot{Config.BOT_TOKEN}"
OWNER_ID     = str(Config.OWNER_ID) if Config.OWNER_ID else ""
_BOT_TIMEOUT = aiohttp.ClientTimeout(total=15)

# Shared state
_brain: AgentBrain | None = None
_last_update_id = 0


# ─── Bot API helpers ──────────────────────────────────────────────────────────

async def _send(text: str, parse_mode: str = "Markdown"):
    if not Config.BOT_TOKEN or not OWNER_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{BOT_BASE}/sendMessage",
                         json={"chat_id": OWNER_ID, "text": text,
                               "parse_mode": parse_mode},
                         timeout=_BOT_TIMEOUT)
    except Exception:
        pass


async def _get_updates(offset: int) -> list[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(f"{BOT_BASE}/getUpdates",
                            params={"offset": offset, "timeout": 25, "limit": 10},
                            timeout=aiohttp.ClientTimeout(total=30))
            if r.status == 200:
                return (await r.json()).get("result", [])
    except Exception:
        pass
    return []


# ─── Command handlers ─────────────────────────────────────────────────────────

async def _cmd_help():
    await _send(
        "*🤖 Ashiq's Autonomous Bot*\n\n"
        "*Commands:*\n"
        "`/execute` — ⚡ run the FULL pipeline now (hunt + act + DM)\n"
        "`/hunt` — run a search + DM cycle now\n"
        "`/status` — show stats & recent actions\n"
        "`/pause` — pause autonomous hunting\n"
        "`/resume` — resume autonomous hunting\n"
        "`/dm @user message` — send a manual DM\n"
        "`/search query` — search for opportunities\n"
        "`/cycle N` — change hunt frequency (1=every cycle)\n\n"
        "*Or just chat* — I'll answer with AI 🧠\n\n"
        "_Running 24/7 on Railway. No phone needed._"
    )


async def _cmd_status():
    if not _brain:
        await _send("Bot initialising, try again in a moment.")
        return
    obs = await _brain.observe()
    mode = "⏸ PAUSED" if _brain._paused else "▶️ RUNNING"
    await _send(
        f"*Status — Cycle {_brain.cycle}* | {mode}\n"
        f"Hunt every: {_brain._hunt_every} cycles\n\n"
        f"```\n{obs[:600]}\n```"
    )


async def _cmd_hunt():
    if not _brain:
        await _send("Bot not ready yet.")
        return
    if _brain._paused:
        await _send("⚠️ Bot is paused. Send /resume first.")
        return
    await _send("🔍 Hunting now — I'll report back when done...")
    try:
        sent = await _brain.smart_hunt_cycle()
        await _send(f"✅ Hunt complete — *{sent} DMs sent* this cycle.")
    except Exception as e:
        await _send(f"❌ Hunt error: `{e}`")


async def _cmd_pause():
    if _brain:
        _brain._paused = True
    await _send("⏸ Autonomous mode paused. Send /resume to restart.")


async def _cmd_resume():
    if _brain:
        _brain._paused = False
    await _send("▶️ Autonomous mode resumed. Hunting continues.")


async def _cmd_dm(args: str):
    if not _brain:
        await _send("Bot not ready.")
        return
    parts = args.strip().split(" ", 1)
    if len(parts) < 2 or not parts[0].startswith("@"):
        await _send("Usage: `/dm @username Your message here`")
        return
    target = parts[0].lstrip("@")
    message = parts[1].strip()
    r = await telegram_tools.send_dm(_brain.client, f"@{target}", message)
    if r:
        await _send(f"✅ DM sent to @{target}")
    else:
        await _send(f"❌ Could not DM @{target} — they may have DMs closed.")


async def _cmd_search(args: str):
    query = args.strip() or "web3 AI project hiring ambassador 2026"
    await _send(f"🔍 Searching: `{query}`...")
    results = await web_tools.web_search(query, num=6)
    if not results:
        await _send("No results found.")
        return
    lines = [
        f"• *{r.get('title','')[:60]}*\n  {r.get('snippet','')[:100]}\n  {r.get('url','')}"
        for r in results[:5]
    ]
    await _send("*Search Results:*\n\n" + "\n\n".join(lines))


async def _cmd_cycle(args: str):
    if not _brain:
        await _send("Bot not ready.")
        return
    try:
        n = max(1, min(10, int(args.strip())))
        _brain._hunt_every = n
        await _send(f"✅ Hunt frequency set to every *{n}* cycles.")
    except ValueError:
        await _send("Usage: `/cycle 2` (1 = every cycle, 3 = every 3rd, etc.)")


async def _cmd_execute(args: str):
    """Run a full pipeline cycle: observe → hunt → act — the most powerful command."""
    if not _brain:
        await _send("Bot not ready yet.")
        return
    if _brain._paused:
        await _send("⚠️ Bot is paused. Send /resume first.")
        return

    await _send(
        "⚡ *EXECUTE — Full pipeline running*\n"
        "1. 🔍 Discovering projects...\n"
        "2. 📡 Joining groups...\n"
        "3. 🎯 Finding founders...\n"
        "4. ✉️ Sending DMs..."
    )
    try:
        obs     = await _brain.observe()
        thought = _brain.think(obs)
        plan    = _brain.plan(thought, obs)
        results = await _brain.act(plan)
        ok      = sum(1 for r in results if r["result"].get("ok"))

        sent = await _brain.smart_hunt_cycle()

        await _send(
            f"✅ *Execute complete*\n\n"
            f"Actions taken: *{ok}/{len(results)}* succeeded\n"
            f"DMs sent: *{sent}*\n\n"
            f"_Cycle {_brain.cycle} — running 24/7_"
        )
    except Exception as e:
        await _send(f"❌ Execute error: `{e}`")


async def _ai_chat(text: str):
    """AI chat response using Groq."""
    await _send("_thinking..._")
    MY_CONTEXT = (
        "You are an AI assistant for Ashiq (@ashiq80), a Web3/AI community specialist from Kashmir, India. "
        "He has 16K+ Twitter/X followers, 6K+ community members, and runs an autonomous outreach bot. "
        "He's looking for: Community Manager, Ambassador, Content Creator, Social Media Manager roles at Web3/AI projects. "
        "Help him with: crafting DMs, analyzing projects, outreach strategy, writing, or any question. "
        "Be sharp and concise — max 3 paragraphs unless asked for more. No fluff."
    )
    try:
        response = ai_tools.think(
            system_addon=MY_CONTEXT,
            user_prompt=text,
            max_tokens=600,
        )
        if response and not response.startswith("[") and len(response) > 5:
            await _send(response)
        else:
            await _send("AI is rate-limited. Try again in 30 seconds.")
    except Exception as e:
        await _send(f"AI error: `{e}`")


# ─── Command router ───────────────────────────────────────────────────────────

COMMANDS = {
    "/start":   lambda _: _cmd_help(),
    "/help":    lambda _: _cmd_help(),
    "/status":  lambda _: _cmd_status(),
    "/hunt":    lambda _: _cmd_hunt(),
    "/execute": lambda args: _cmd_execute(args),
    "/pause":   lambda _: _cmd_pause(),
    "/resume":  lambda _: _cmd_resume(),
    "/dm":      _cmd_dm,
    "/search":  _cmd_search,
    "/cycle":   _cmd_cycle,
}


async def bot_commander():
    """Long-poll the Bot API and handle owner commands + chat."""
    global _last_update_id
    await asyncio.sleep(5)
    console.print("[cyan]🤖 Bot commander online — listening for commands[/cyan]")
    await _send(
        "🤖 *Bot commander ready*\n"
        "Send /help to see all commands, or just chat with me!"
    )

    while True:
        try:
            updates = await _get_updates(_last_update_id + 1)
            for update in updates:
                _last_update_id = update.get("update_id", _last_update_id)
                msg = update.get("message", {})
                if not msg:
                    continue

                from_id = str(msg.get("from", {}).get("id", ""))
                if from_id != OWNER_ID:
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                console.print(f"[cyan]📩 Owner: {text[:80]}[/cyan]")

                if text.startswith("/"):
                    parts = text.split(" ", 1)
                    cmd  = parts[0].lower().split("@")[0]
                    args = parts[1] if len(parts) > 1 else ""
                    handler = COMMANDS.get(cmd)
                    if handler:
                        await handler(args)
                    else:
                        await _send(f"Unknown command: `{cmd}`\nSend /help to see all commands.")
                else:
                    await _ai_chat(text)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            console.print(f"[red]Commander error: {e}[/red]")
            await asyncio.sleep(5)


# ─── Startup check ────────────────────────────────────────────────────────────

def _check():
    missing = []
    if not Config.API_ID:   missing.append("TELEGRAM_API_ID")
    if not Config.API_HASH: missing.append("TELEGRAM_API_HASH")
    if not os.getenv("TELEGRAM_SESSION_STRING"):
        missing.append("TELEGRAM_SESSION_STRING  ← run generate_session.py on Termux")
    for m in missing:
        console.print(f"[red]❌ Missing: {m}[/red]")
    return not missing


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    global _brain

    if not _check():
        return

    session_str = os.getenv("TELEGRAM_SESSION_STRING")

    db     = Database()
    await db.connect()
    memory = Memory()

    user_client = Client(
        name           = "cloud_session",
        api_id         = Config.API_ID,
        api_hash       = Config.API_HASH,
        session_string = session_str,
    )

    async with user_client:
        me = await user_client.get_me()
        console.print(Panel(
            f"[bold green]✅ Logged in as {me.first_name} (@{me.username})[/bold green]\n\n"
            "[bold magenta]🚀 FULL CLOUD AUTONOMOUS BOT — ONLINE[/bold magenta]\n\n"
            "[white]Every 2nd cycle:\n"
            "  1. 🔍 Discover projects (X/Twitter + Tavily)\n"
            "  2. 📡 Join their Telegram group\n"
            "  3. 👁  Read room context\n"
            "  4. 🎯 Find CEO / Founder\n"
            "  5. ✍️  Craft DM (Ashiq | @ashiq80)\n"
            "  6. ✉️  Send DM via your account\n\n"
            "Bot commander: send /help to your bot[/white]",
            border_style="magenta",
        ))

        await _send(
            f"🚀 *Cloud Bot Online*\n"
            f"Account: {me.first_name} (@{me.username})\n"
            f"Running 24/7 — no phone needed.\n"
            f"Send /help for commands."
        )

        tools  = ToolRegistry(user_client, db)
        _brain = AgentBrain(tools, db, memory, user_client=user_client)

        await asyncio.gather(
            _brain.run_forever(),
            bot_commander(),
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")
