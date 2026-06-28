"""
1000 IQ AUTONOMOUS TELEGRAM AI
Run once: python run.py

Send ANY command to your Saved Messages in Telegram — the AI executes it.
Examples:
  "join 10 web3 groups"
  "post AI news in my groups"
  "find ambassador programs and apply"
  "hunt CM/moderator roles"
  "search blockchain developer jobs"
  "post in all my groups: [your message]"
  "send DM to @username saying hello"
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
from telegram_agents.tg_agent import TelegramAIAgent
from telegram_agents.agents.opportunity_hunter import OpportunityHunterAgent

console = Console()


async def first_time_login():
    console.print("\n[yellow]First time — logging into Telegram...[/yellow]")
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
    if not os.path.exists(f"{Config.SESSION_NAME}.session"):
        ok = await first_time_login()
        if not ok:
            return

    db     = Database()
    await db.connect()
    memory = Memory()

    async with Client(Config.SESSION_NAME, api_id=Config.API_ID,
                      api_hash=Config.API_HASH, phone_number=Config.PHONE) as client:

        tools       = ToolRegistry(client, db)
        brain       = AgentBrain(tools, db, memory)
        tg_agent    = TelegramAIAgent(client, tools, db)
        opp_hunter  = OpportunityHunterAgent(client, db)

        # Start interactive Telegram AI agent (Saved Messages listener)
        await tg_agent.start()

        console.print(Panel(
            "[bold magenta]🤖 1000 IQ AUTONOMOUS TELEGRAM AI — ONLINE[/bold magenta]\n\n"
            "[white]💬 [bold]Send any command to your Saved Messages in Telegram[/bold]\n\n"
            "Examples:\n"
            '  • "join 10 web3 groups"\n'
            '  • "post AI news in my groups"\n'
            '  • "find ambassador programs and apply"\n'
            '  • "hunt CM/moderator roles in 2026 projects"\n'
            '  • "search blockchain developer jobs"\n'
            '  • "send DM to @username saying: hi"\n'
            '  • "post in all my groups: [message]"\n'
            '  • "what groups am I in?"\n\n'
            "[dim]🎯 Opportunity Hunter: runs every 3 hours automatically\n"
            "🧠 Autonomous brain: always finding new opportunities[/dim][/white]",
            border_style="magenta",
        ))

        async def opportunity_loop():
            """Auto-hunt ambassador/CM/moderator/content creator roles every 3 hours."""
            while True:
                try:
                    await opp_hunter.run(max_apply=15)
                except Exception as e:
                    console.print(f"[red]OpportunityHunter error: {e}[/red]")
                await asyncio.sleep(3 * 60 * 60)

        # Run all loops in parallel
        await asyncio.gather(
            brain.run_forever(),    # autonomous 1000 IQ loop
            opportunity_loop(),     # ambassador/CM/mod/creator hunter
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")
