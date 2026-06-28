"""
Full cloud autonomous bot — deploy to Railway (railway.app).

What it does 24/7:
  Every 3rd cycle → discover Web3/AI projects via Tavily + Grok
                  → join their Telegram group
                  → read room context
                  → identify CEO / founder
                  → craft personalized DM (Ashiq | @ashiq80)
                  → send DM autonomously

Setup (one time):
  1. Run generate_session.py on Termux → copy TELEGRAM_SESSION_STRING
  2. Create Railway project → connect this repo
  3. Set env vars in Railway dashboard (see generate_session.py output)
  4. Deploy — runs forever, no phone needed
"""
import asyncio, os, sys, subprocess
from dotenv import load_dotenv
load_dotenv()

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

from pyrogram import Client
from rich.console import Console
from rich.panel import Panel

from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain

console = Console()


def _check():
    missing = []
    if not Config.API_ID:   missing.append("TELEGRAM_API_ID")
    if not Config.API_HASH: missing.append("TELEGRAM_API_HASH")
    if not os.getenv("TELEGRAM_SESSION_STRING"):
        missing.append("TELEGRAM_SESSION_STRING  ← run generate_session.py")
    if missing:
        console.print("[bold red]❌ Missing env vars:[/bold red]")
        for m in missing:
            console.print(f"  [red]• {m}[/red]")
        return False
    return True


async def main():
    if not _check():
        return

    session_str = os.getenv("TELEGRAM_SESSION_STRING")

    db     = Database()
    await db.connect()
    memory = Memory()

    # User client from session string — no file, no OTP on server
    user_client = Client(
        name         = "cloud_session",
        api_id       = Config.API_ID,
        api_hash     = Config.API_HASH,
        session_string = session_str,
    )

    async with user_client:
        me = await user_client.get_me()
        console.print(Panel(
            f"[bold green]✅ User account: {me.first_name} (@{me.username})[/bold green]\n\n"
            "[bold magenta]🚀 FULL CLOUD AUTONOMOUS BOT — ONLINE[/bold magenta]\n\n"
            "[white]Pipeline fires every 3rd cycle:\n"
            "  1. 🔍 Discover Web3/AI projects (Tavily search)\n"
            "  2. 📡 Find & join their Telegram group\n"
            "  3. 👁  Read room context\n"
            "  4. 🎯 Identify CEO / Founder (admin scan)\n"
            "  5. ✍️  Craft personalized DM with Ashiq's real stats\n"
            "  6. ✉️  Send DM via user account\n\n"
            "[dim]No auto-replies to strangers. Only strategic outreach.[/dim]",
            border_style="magenta",
        ))

        tools = ToolRegistry(user_client, db)
        brain = AgentBrain(tools, db, memory, user_client=user_client)

        # Run the full autonomous brain — discovers, infiltrates, DMs
        await brain.run_forever()

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped.[/yellow]")
