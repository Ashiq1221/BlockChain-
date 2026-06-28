"""
1000 IQ AUTONOMOUS TELEGRAM AI + REMOTE COMMAND CHANNEL
Run once: python run.py

Two ways to send commands:
  1. Type here in Claude chat → I write it → agent executes on your phone
  2. Message yourself in Telegram Saved Messages → agent executes instantly
"""
import asyncio, os, sys, subprocess
from dotenv import load_dotenv

load_dotenv()

# ── Auto-install ──────────────────────────────────────────────────────────────
PKGS = ["pyrogram==2.0.106","TgCrypto","httpx","aiohttp",
        "aiosqlite","python-dotenv","rich","aiofiles","beautifulsoup4"]
for pkg in PKGS:
    name = pkg.split("==")[0].replace("-","_")
    try: __import__(name)
    except ImportError:
        subprocess.call([sys.executable,"-m","pip","install",pkg,"-q"],
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
from telegram_agents.commander_channel import CommanderChannel

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

        tools   = ToolRegistry(client, db)
        brain   = AgentBrain(tools, db, memory)
        channel = CommanderChannel(client, tools, db)

        console.print(Panel(
            "[bold magenta]1000 IQ AUTONOMOUS AGENT — ONLINE[/bold magenta]\n\n"
            "[white]• Autonomous brain runs in background forever\n"
            "• Send commands via your [bold]Telegram Saved Messages[/bold]\n"
            "• Or give a prompt in Claude chat — I relay it instantly[/white]\n\n"
            "[dim]Saved Messages = message yourself in Telegram app[/dim]",
            border_style="magenta",
        ))

        # Start command channels (GitHub + Saved Messages)
        await channel.start()

        # Run autonomous brain + command channel in parallel
        await asyncio.gather(
            brain.run_forever(),       # 1000 IQ autonomous loop
            channel.poll_github(),     # GitHub command polling
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")
