"""
Full cloud autonomous bot — deploy to Railway (railway.app).

Pipeline (every 3rd cycle, 24/7):
  1. Discover Web3/AI projects hiring via X/Twitter + Tavily
  2. Find & join their Telegram group
  3. Read the room context
  4. Identify CEO / Founder (admin scan)
  5. Craft personalized DM using Ashiq's real stats
  6. Send DM via user account (Pyrogram StringSession)

Setup (one time):
  1. Run on Termux:  python3 generate_session.py  → copy SESSION_STRING
  2. Go to railway.app → New Project → Deploy from GitHub
  3. Set env vars in Railway dashboard (list below)
  4. Deploy → runs forever, no phone needed

Required env vars:
  TELEGRAM_SESSION_STRING   ← from generate_session.py
  TELEGRAM_API_ID
  TELEGRAM_API_HASH
  TELEGRAM_BOT_TOKEN        ← reports to your Telegram
  TELEGRAM_OWNER_ID
  GROQ_API_KEY              ← free at console.groq.com
  TAVILY_API_KEY            ← free at tavily.com
  GEMINI_API_KEY            ← free at aistudio.google.com
"""
import asyncio, os, sys, subprocess, aiohttp, time
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

console = Console()

BOT_BASE   = f"https://api.telegram.org/bot{Config.BOT_TOKEN}"
OWNER_ID   = Config.OWNER_ID
_BOT_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _notify(text: str):
    """Send status message to owner via Bot API (no Pyrogram needed)."""
    if not Config.BOT_TOKEN or not OWNER_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"{BOT_BASE}/sendMessage",
                         json={"chat_id": OWNER_ID, "text": text,
                               "parse_mode": "Markdown"},
                         timeout=_BOT_TIMEOUT)
    except Exception:
        pass


def _check():
    missing = []
    if not Config.API_ID:   missing.append("TELEGRAM_API_ID")
    if not Config.API_HASH: missing.append("TELEGRAM_API_HASH")
    if not os.getenv("TELEGRAM_SESSION_STRING"):
        missing.append("TELEGRAM_SESSION_STRING  ← run generate_session.py on Termux")
    if missing:
        for m in missing:
            console.print(f"[red]❌ Missing: {m}[/red]")
        return False
    return True


async def main():
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
            "[white]Every 3rd cycle:\n"
            "  1. 🔍 Discover projects (X/Twitter + Tavily)\n"
            "  2. 📡 Join their Telegram group\n"
            "  3. 👁  Read room context\n"
            "  4. 🎯 Find CEO / Founder\n"
            "  5. ✍️  Craft DM (Ashiq | @ashiq80)\n"
            "  6. ✉️  Send DM via your account[/white]",
            border_style="magenta",
        ))

        await _notify(
            f"🚀 *Cloud Bot Online*\n"
            f"Account: {me.first_name} (@{me.username})\n"
            f"Pipeline: X/Twitter + Tavily → join group → DM CEO\n"
            f"Running 24/7 — no phone needed."
        )

        tools = ToolRegistry(user_client, db)
        brain = AgentBrain(tools, db, memory, user_client=user_client)

        await brain.run_forever()

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")
