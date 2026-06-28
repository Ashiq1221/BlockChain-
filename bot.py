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
"""
import asyncio, os, sys, subprocess
from dotenv import load_dotenv

load_dotenv()

# ── Auto-install ──────────────────────────────────────────────────────────────
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
from pyrogram.errors import SessionPasswordNeeded
from rich.console import Console
from rich.panel import Panel
from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain
from telegram_agents.ai_bot import AIBot
from telegram_agents.agents.opportunity_hunter import OpportunityHunterAgent

console = Console()


def _check_config():
    """Validate required config before starting."""
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
        console.print("\n[yellow]Edit your .env file and add the missing values.[/yellow]")
        return False
    if not Config.OWNER_ID:
        console.print("[yellow]⚠  TELEGRAM_OWNER_ID not set — bot will respond to everyone.[/yellow]")
        console.print("[dim]  Get your ID: message @userinfobot on Telegram[/dim]")
    return True


async def _login_user():
    """First-time OTP login for the user account (Pyrogram)."""
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


async def main():
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

    # User account client (does actual Telegram actions)
    user_client = Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    )

    # Bot client (chat interface)
    bot_client = Client(
        "bot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
    )

    async with user_client, bot_client:
        tools      = ToolRegistry(user_client, db)
        brain      = AgentBrain(tools, db, memory)
        ai_bot     = AIBot(bot_client, user_client, tools, db)
        opp_hunter = OpportunityHunterAgent(user_client, db)

        # Start bot handlers
        await ai_bot.start()

        console.print(Panel(
            "[bold magenta]🤖 TELEGRAM AI BOT — ONLINE[/bold magenta]\n\n"
            "[white]Open Telegram → find your bot → send any message\n\n"
            "Quick commands:\n"
            "  /start  — welcome screen\n"
            "  /hunt   — find ambassador/CM/mod roles\n"
            "  /news   — post latest AI/Web3 news\n"
            "  /jobs   — search blockchain jobs\n"
            "  /status — account stats\n"
            "  /groups — list joined groups\n\n"
            "Or just type anything in plain English![/white]\n\n"
            f"[dim]Bot token: {Config.BOT_TOKEN[:20]}...[/dim]",
            border_style="magenta",
        ))

        async def opportunity_loop():
            """Hunt and apply to roles every 3 hours autonomously."""
            while True:
                try:
                    await opp_hunter.run(max_apply=10)
                except Exception as e:
                    console.print(f"[red]OpportunityHunter error: {e}[/red]")
                await asyncio.sleep(3 * 60 * 60)

        async def keep_alive():
            while True:
                await asyncio.sleep(60)

        await asyncio.gather(
            keep_alive(),
            opportunity_loop(),  # autonomous: finds + applies every 3 hrs
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped.[/yellow]")
