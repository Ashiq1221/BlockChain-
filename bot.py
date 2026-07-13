"""
Telegram AI Bot — run with: python bot.py

Setup (one time):
  1. Message @BotFather on Telegram → /newbot → copy the token
  2. Add to .env:  TELEGRAM_BOT_TOKEN=your_token_here
  3. Find your Telegram ID: message @userinfobot → copy the id number
  4. Add to .env:  TELEGRAM_OWNER_ID=your_id_here
  5. Run: python bot.py → enter OTP if first time
  6. Open Telegram → find your bot → /start

The bot controls your actual Telegram account via the user session.
Bot commands are handled via HTTP polling (no second Pyrogram session needed).
"""
import asyncio
import os
import sys
import subprocess

from dotenv import load_dotenv

load_dotenv()

# Clean only Pyrogram session WAL/journal lock files (NOT the DB)
import glob as _glob
for _f in _glob.glob("*.session-shm") + _glob.glob("*.session-wal") + _glob.glob("*.session-journal"):
    try:
        os.remove(_f)
    except FileNotFoundError:
        pass

# Auto-install
PKGS = ["pyrogram==2.0.106", "TgCrypto", "httpx", "aiohttp",
        "aiosqlite", "python-dotenv", "rich", "aiofiles", "beautifulsoup4"]
for pkg in PKGS:
    name = pkg.split("==")[0].replace("-", "_")
    try:
        __import__(name)
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

import aiohttp
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from rich.console import Console
from rich.panel import Panel

from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain

console = Console()

# Bot API polling state
BOT_BASE        = f"https://api.telegram.org/bot{Config.BOT_TOKEN}"
OWNER_ID        = str(Config.OWNER_ID) if Config.OWNER_ID else ""
_BOT_TIMEOUT    = aiohttp.ClientTimeout(total=15)
_last_update_id = 0
_brain: AgentBrain | None = None


# ── Bot API helpers ────────────────────────────────────────────────────────────

async def _send(text: str, parse_mode: str = "Markdown"):
    if not Config.BOT_TOKEN or not OWNER_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{BOT_BASE}/sendMessage",
                json={"chat_id": OWNER_ID, "text": text, "parse_mode": parse_mode},
                timeout=_BOT_TIMEOUT,
            )
    except Exception:
        pass


async def _get_updates(offset: int) -> list[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{BOT_BASE}/getUpdates",
                params={"offset": offset, "timeout": 25, "limit": 10},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            if r.status == 200:
                return (await r.json()).get("result", [])
    except Exception:
        pass
    return []


# ── Command handlers ───────────────────────────────────────────────────────────

async def _cmd_help():
    await _send(
        "*🤖 Ashiq's Autonomous Bot*\n\n"
        "*Commands:*\n"
        "`/hunt` — trigger smart hunt + DM cycle now\n"
        "`/execute` — full pipeline (observe + hunt + act)\n"
        "`/status` — cycle stats & recent actions\n"
        "`/pause` / `/resume` — pause/resume autonomous mode\n"
        "`/dm @user msg` — send a DM via your account\n"
        "`/search query` — web search\n"
        "`/cycle N` — hunt frequency (1=every cycle)\n"
        "`/debate question` — 5-AI debate then synthesize\n\n"
        "*Or type any task:*\n"
        "• `post about DeFi in @channel`\n"
        "• `kick @spammer from @group`\n"
        "• `create an agent that monitors @group`\n"
        "• Any question → AI answers 🧠\n\n"
        "_Running autonomously — brain active._"
    )


async def _cmd_status():
    if not _brain:
        await _send("Brain initialising, try again in a moment.")
        return
    obs  = await _brain.observe()
    mode = "⏸ PAUSED" if _brain._paused else "▶️ RUNNING"
    await _send(
        f"*Status — Cycle {_brain.cycle}* | {mode}\n"
        f"Hunt every: {_brain._hunt_every} cycles\n\n"
        f"```\n{obs[:600]}\n```"
    )


async def _cmd_hunt():
    if not _brain:
        await _send("Brain not ready yet.")
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


async def _cmd_execute(args: str):
    if not _brain:
        await _send("Brain not ready yet.")
        return
    if _brain._paused:
        await _send("⚠️ Paused. Send /resume first.")
        return
    await _send(
        "⚡ *EXECUTE — Full pipeline*\n"
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
        sent    = await _brain.smart_hunt_cycle()
        await _send(
            f"✅ *Execute complete*\n\n"
            f"Actions: *{ok}/{len(results)}* succeeded\n"
            f"DMs sent: *{sent}*\n\n"
            f"_Cycle {_brain.cycle}_"
        )
    except Exception as e:
        await _send(f"❌ Execute error: `{e}`")


async def _cmd_pause():
    if _brain:
        _brain._paused = True
    await _send("⏸ Autonomous mode paused. Send /resume to restart.")


async def _cmd_resume():
    if _brain:
        _brain._paused = False
    await _send("▶️ Autonomous mode resumed.")


async def _cmd_dm(args: str):
    if not _brain:
        await _send("Brain not ready.")
        return
    parts = args.strip().split(" ", 1)
    if len(parts) < 2 or not parts[0].startswith("@"):
        await _send("Usage: `/dm @username Your message here`")
        return
    target  = parts[0].lstrip("@")
    message = parts[1].strip()
    from telegram_agents.tools import telegram_tools
    r = await telegram_tools.send_dm(_brain.client, f"@{target}", message)
    await _send(f"{'✅ DM sent to @' + target if r else '❌ Could not DM @' + target}")


async def _cmd_search(args: str):
    from telegram_agents.tools import web_tools
    query = args.strip() or "web3 AI project hiring ambassador 2026"
    await _send(f"🔍 Searching: `{query}`...")
    results = await web_tools.web_search(query, num=5)
    if not results:
        await _send("No results found.")
        return
    lines = [
        f"• *{r.get('title', '')[:60]}*\n  {r.get('snippet', '')[:100]}"
        for r in results[:4]
    ]
    await _send("*Search Results:*\n\n" + "\n\n".join(lines))


async def _cmd_cycle(args: str):
    if not _brain:
        await _send("Brain not ready.")
        return
    try:
        n = max(1, min(10, int(args.strip())))
        _brain._hunt_every = n
        await _send(f"✅ Hunt frequency set to every *{n}* cycles.")
    except ValueError:
        await _send("Usage: `/cycle 2` (1 = every cycle, etc.)")


async def _cmd_debate(args: str):
    from telegram_agents.tools.ai_router import think_debate
    question = args.strip()
    if not question:
        await _send(
            "*🤝 AI Debate Mode*\n\n"
            "All 5 AIs answer, then a synthesizer picks the best.\n"
            "Usage: `/debate your question here`"
        )
        return
    await _send(
        f"🤝 *5-AI Debate...*\n_{question[:120]}_\n\n"
        "Firing Groq · DeepSeek · OpenAI · Claude · Gemini..."
    )
    result = await think_debate(
        "You are an expert AI assistant for Ashiq (@ashiq80), a Web3/AI specialist. Be sharp and concise.",
        question,
        max_tokens=800,
    )
    await _send(f"🏆 *Debate Result:*\n\n{result}")


async def _ai_chat(text: str):
    """Natural language → AI answer."""
    from telegram_agents.tools import ai_tools
    await _send("_thinking..._")
    response = ai_tools.think(
        system_addon=(
            "You are an AI assistant for Ashiq (@ashiq80), a Web3/AI community specialist. "
            "Be sharp and concise. Help with DM drafts, strategy, Web3 analysis, or any question."
        ),
        user_prompt=text,
        max_tokens=600,
    )
    if response and not response.startswith("[") and len(response) > 5:
        await _send(response)
    else:
        await _send("AI is busy. Try again in 30 seconds.")


COMMANDS = {
    "/start":   lambda _: _cmd_help(),
    "/help":    lambda _: _cmd_help(),
    "/status":  lambda _: _cmd_status(),
    "/hunt":    lambda _: _cmd_hunt(),
    "/execute": _cmd_execute,
    "/pause":   lambda _: _cmd_pause(),
    "/resume":  lambda _: _cmd_resume(),
    "/dm":      _cmd_dm,
    "/search":  _cmd_search,
    "/cycle":   _cmd_cycle,
    "/debate":  _cmd_debate,
}


# ── Bot polling loop ───────────────────────────────────────────────────────────

async def bot_commander():
    global _last_update_id
    await asyncio.sleep(5)
    console.print("[cyan]🤖 Bot commander online — polling for commands[/cyan]")
    await _send(
        "🤖 *Bot Online*\n"
        "Autonomous brain is running.\n"
        "Send /help for all commands."
    )

    while True:
        try:
            updates = await _get_updates(_last_update_id + 1)
            for update in updates:
                _last_update_id = update.get("update_id", _last_update_id)
                msg     = update.get("message", {})
                from_id = str(msg.get("from", {}).get("id", ""))
                if not msg or from_id != OWNER_ID:
                    continue
                text = msg.get("text", "").strip()
                if not text:
                    continue

                console.print(f"[cyan]📩 Owner: {text[:80]}[/cyan]")

                if text.startswith("/"):
                    parts   = text.split(" ", 1)
                    cmd     = parts[0].lower().split("@")[0]
                    args    = parts[1] if len(parts) > 1 else ""
                    handler = COMMANDS.get(cmd)
                    if handler:
                        await handler(args)
                    else:
                        await _send(f"Unknown command: `{cmd}`\nSend /help for all commands.")
                else:
                    await _ai_chat(text)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            console.print(f"[red]Commander error: {e}[/red]")
            await asyncio.sleep(5)


# ── Config check ───────────────────────────────────────────────────────────────

def _check_config():
    missing = []
    if not Config.API_ID:
        missing.append("TELEGRAM_API_ID")
    if not Config.API_HASH:
        missing.append("TELEGRAM_API_HASH")
    if not Config.BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN  ← get from @BotFather")
    if missing:
        console.print("[bold red]❌ Missing .env values:[/bold red]")
        for m in missing:
            console.print(f"  [red]• {m}[/red]")
        return False
    if not Config.OWNER_ID:
        console.print("[yellow]⚠  TELEGRAM_OWNER_ID not set — bot will not respond to anyone[/yellow]")
    return True


# ── First-time OTP login ───────────────────────────────────────────────────────

async def _login_user():
    console.print("\n[yellow]First time — logging into Telegram user account...[/yellow]")
    app = Client(Config.SESSION_NAME, api_id=Config.API_ID,
                 api_hash=Config.API_HASH, phone_number=Config.PHONE)
    await app.connect()
    try:
        sent = await app.send_code(Config.PHONE)
    except Exception as e:
        console.print(f"[red]Could not send OTP: {e}[/red]")
        await app.disconnect()
        return False
    console.print(f"[green]✅ OTP sent to {Config.PHONE}[/green]")
    code = input("Enter OTP code: ").strip()
    try:
        await app.sign_in(Config.PHONE, sent.phone_code_hash, code)
    except SessionPasswordNeeded:
        pwd = input("2FA password: ").strip()
        await app.check_password(pwd)
    me = await app.get_me()
    console.print(f"[green]✅ Logged in as {me.first_name} (@{me.username})[/green]")
    await app.disconnect()
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

async def main():
    global _brain

    if not _check_config():
        return

    # First-time user login if no session
    if not os.path.exists(f"{Config.SESSION_NAME}.session"):
        ok = await _login_user()
        if not ok:
            return

    db     = Database()
    await db.connect()
    memory = Memory()

    # Single Pyrogram client — the user account
    # (bot commands arrive via HTTP polling — no second Pyrogram session needed)
    user_client = Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    )

    async with user_client:
        me     = await user_client.get_me()
        tools  = ToolRegistry(user_client, db)
        _brain = AgentBrain(tools, db, memory, user_client=user_client)

        console.print(Panel(
            f"[bold green]✅ Logged in as {me.first_name} (@{me.username})[/bold green]\n\n"
            "[bold magenta]🤖 AUTONOMOUS BOT — ONLINE[/bold magenta]\n\n"
            "[white]Every cycle  : Observe → Think → Plan → Act → Learn\n"
            "Every 2nd    : 🔍 Hunt project → 📡 Join TG → 🎯 Find CEO → ✉️  DM\n\n"
            "Bot commands via Telegram:\n"
            "  /hunt   — trigger now\n"
            "  /status — stats\n"
            "  /dm @u msg — send DM\n"
            "  /debate question — 5-AI debate\n"
            "  Or just type anything![/white]",
            border_style="magenta",
        ))

        await asyncio.gather(
            _brain.run_forever(),
            bot_commander(),
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped.[/yellow]")
