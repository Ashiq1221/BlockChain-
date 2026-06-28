"""
1000 IQ AUTONOMOUS TELEGRAM AI
The only command you ever need: python run.py
"""
import asyncio, os, sys, subprocess
from dotenv import load_dotenv

load_dotenv()

# ── Auto-install ──────────────────────────────────────────────────────────────
PKGS = ["pyrogram==2.0.106","TgCrypto","httpx","aiohttp",
        "aiosqlite","python-dotenv","rich","aiofiles","beautifulsoup4"]
for pkg in PKGS:
    name = pkg.split("==")[0].replace("-","_")
    try:
        __import__(name)
    except ImportError:
        print(f"Installing {pkg}...")
        subprocess.call([sys.executable,"-m","pip","install",pkg,"-q"],
                        stderr=subprocess.DEVNULL)

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded
from rich.console import Console
from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain

console = Console()


async def first_time_login():
    """Handle Telegram OTP login if no session exists."""
    console.print("\n[yellow]First time — logging into Telegram...[/yellow]")

    app = Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    )
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
    # Login check
    if not os.path.exists(f"{Config.SESSION_NAME}.session"):
        ok = await first_time_login()
        if not ok:
            return

    # Boot up
    db = Database()
    await db.connect()
    memory = Memory()

    async with Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    ) as client:

        tools = ToolRegistry(client, db)
        brain = AgentBrain(tools, db, memory)

        # Run the 1000 IQ agentic loop forever
        await brain.run_forever()

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent stopped.[/yellow]")
