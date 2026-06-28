"""
TELEGRAM AI AGENTS — START HERE
Just run: python start.py
"""
import subprocess, sys, os

# ── Auto-install missing packages ────────────────────────────────────────────
PACKAGES = [
    "pyrogram==2.0.106",
    "TgCrypto",
    "httpx",          # replaces anthropic SDK — pure Python, no Rust needed
    "aiohttp",
    "aiosqlite",
    "python-dotenv",
    "rich",
    "aiofiles",
    "beautifulsoup4",
]

def install(pkg):
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", pkg, "-q",
         "--no-build-isolation"],
        stderr=subprocess.DEVNULL,
    )

print("\n🔧 Checking packages...")
for pkg in PACKAGES:
    name = pkg.split("==")[0].lower()
    try:
        __import__(name.replace("-","_"))
    except ImportError:
        print(f"   Installing {pkg}...")
        try:
            install(pkg)
        except Exception as e:
            print(f"   ⚠️  {name} skipped (non-critical): {e}")

# ── Now import everything ─────────────────────────────────────────────────────
import asyncio
from dotenv import load_dotenv, set_key

load_dotenv()

API_ID   = os.getenv("TELEGRAM_API_ID", "")
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
PHONE    = os.getenv("TELEGRAM_PHONE", "")
ANT_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
SESSION  = os.getenv("TELEGRAM_SESSION_NAME", "my_session")

ENV_FILE = ".env"

# ── Create .env if missing ────────────────────────────────────────────────────
def ask(prompt, current=""):
    if current:
        val = input(f"{prompt} [{current}]: ").strip()
        return val if val else current
    while True:
        val = input(f"{prompt}: ").strip()
        if val:
            return val

if not os.path.exists(ENV_FILE) or not API_ID or not API_HASH:
    print("\n📋 First time setup — enter your details:\n")
    API_ID   = ask("Telegram API ID",   API_ID)
    API_HASH = ask("Telegram API Hash", API_HASH)
    PHONE    = ask("Your phone number (e.g. +919622940810)", PHONE)
    ANT_KEY  = ask("Anthropic API Key", ANT_KEY)

    with open(ENV_FILE, "w") as f:
        f.write(f"""TELEGRAM_API_ID={API_ID}
TELEGRAM_API_HASH={API_HASH}
TELEGRAM_PHONE={PHONE}
TELEGRAM_SESSION_NAME=my_session
ANTHROPIC_API_KEY={ANT_KEY}
AGENT_LANGUAGE=en
MAX_DM_PER_HOUR=10
MAX_GROUP_POSTS_PER_HOUR=5
RATE_LIMIT_SLEEP=3
AUTO_RESPOND=true
JOB_KEYWORDS=python developer,blockchain engineer,backend engineer,remote developer
""")
    print("\n✅ Saved!\n")
    load_dotenv(override=True)
    API_ID   = os.getenv("TELEGRAM_API_ID")
    API_HASH = os.getenv("TELEGRAM_API_HASH")
    PHONE    = os.getenv("TELEGRAM_PHONE")
    ANT_KEY  = os.getenv("ANTHROPIC_API_KEY")


# ── Telegram login ────────────────────────────────────────────────────────────
async def login():
    from pyrogram import Client
    from pyrogram.errors import SessionPasswordNeeded

    print("\n📱 Connecting to Telegram...")
    print(f"   Sending OTP to {PHONE} ...\n")

    app = Client(
        SESSION,
        api_id=int(API_ID),
        api_hash=API_HASH,
        phone_number=PHONE,
    )

    await app.connect()

    try:
        sent = await app.send_code(PHONE)
    except Exception as e:
        print(f"❌ Could not send code: {e}")
        await app.disconnect()
        return False

    print("✅ OTP sent to your Telegram app (or SMS).")
    code = input("\n👉 Enter the OTP code here: ").strip()

    try:
        await app.sign_in(PHONE, sent.phone_code_hash, code)
        print("\n✅ Logged in!")
    except SessionPasswordNeeded:
        pwd = input("🔒 2FA password required. Enter it: ").strip()
        await app.check_password(pwd)
        print("\n✅ Logged in with 2FA!")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        await app.disconnect()
        return False

    me = await app.get_me()
    print(f"\n👤 Welcome, {me.first_name}! (@{me.username})")
    print("💾 Session saved — you won't need to log in again.\n")
    await app.disconnect()
    return True


# ── Menu ─────────────────────────────────────────────────────────────────────
def show_menu():
    print("""
╔══════════════════════════════════════╗
║    TELEGRAM AI AGENT SYSTEM 🤖       ║
╚══════════════════════════════════════╝

  1.  🔍 Find & join relevant groups
  2.  💼 Hunt jobs & apply automatically
  3.  ✉️  Send DMs to people
  4.  📝 Post content in groups
  5.  🕸️  Collect contacts from groups
  6.  👁️  Watch groups for keywords
  7.  💬 Auto-reply to messages (1 hour)
  8.  📊 Show analytics & stats
  9.  ♟️  Create a strategy plan
  10. 🧠 Tell AI your goal (it handles everything)
  0.  ❌ Exit
""")

async def run_choice(choice):
    from pyrogram import Client
    sys.path.insert(0, os.path.dirname(__file__))

    from telegram_agents.database import Database
    from telegram_agents.agents.group_discovery import GroupDiscoveryAgent
    from telegram_agents.agents.job_hunter     import JobHunterAgent
    from telegram_agents.agents.dm_agent       import DMAgent
    from telegram_agents.agents.content_agent  import ContentAgent
    from telegram_agents.agents.network_agent  import NetworkAgent
    from telegram_agents.agents.monitor_agent  import MonitorAgent
    from telegram_agents.agents.responder_agent import ResponderAgent
    from telegram_agents.agents.analytics_agent import AnalyticsAgent
    from telegram_agents.agents.strategy_agent  import StrategyAgent
    from telegram_agents.agents.commander       import CommanderAgent

    db = Database()
    await db.connect()

    async with Client(SESSION, api_id=int(API_ID), api_hash=API_HASH, phone_number=PHONE) as client:
        A = {
            "group_discovery": GroupDiscoveryAgent(client, db),
            "job_hunter":      JobHunterAgent(client, db),
            "dm":              DMAgent(client, db),
            "content":         ContentAgent(client, db),
            "network":         NetworkAgent(client, db),
            "monitor":         MonitorAgent(client, db),
            "responder":       ResponderAgent(client, db),
            "analytics":       AnalyticsAgent(client, db),
            "strategy":        StrategyAgent(client, db),
            "commander":       CommanderAgent(client, db),
        }

        if choice == "1":
            t = input("Topics (e.g. blockchain, python, jobs): ").strip()
            topics = [x.strip() for x in t.split(",")] if t else None
            await A["group_discovery"].run(topics=topics)

        elif choice == "2":
            print("Scanning for jobs and applying... this may take a few minutes.")
            await A["job_hunter"].run(apply=True)

        elif choice == "3":
            goal = input("What should the message say / goal?: ").strip()
            n    = input("How many DMs? (default 10): ").strip()
            await A["dm"].run(goal=goal, max_send=int(n) if n.isdigit() else 10)

        elif choice == "4":
            topic = input("What do you want to post about?: ").strip()
            await A["content"].run(topic=topic)

        elif choice == "5":
            print("Collecting contacts from all joined groups...")
            await A["network"].run()

        elif choice == "6":
            kw  = input("Keywords to watch (comma separated): ").strip()
            dur = input("How many minutes? (default 10): ").strip()
            await A["monitor"].run(
                keywords=[k.strip() for k in kw.split(",") if k.strip()],
                duration_seconds=int(dur)*60 if dur.isdigit() else 600,
            )

        elif choice == "7":
            print("Auto-reply ON for 1 hour. Keep this open...")
            await A["responder"].run(duration_seconds=3600)

        elif choice == "8":
            await A["analytics"].run()

        elif choice == "9":
            goal = input("Your goal (e.g. find a remote job in 2 weeks): ").strip()
            await A["strategy"].run(goal=goal)

        elif choice == "10":
            goal = input("What do you want? (type anything): ").strip()
            others = {k: v for k, v in A.items() if k != "commander"}
            await A["commander"].run(goal=goal, agent_registry=others)

    await db.close()


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    # Login if no session file exists
    session_file = f"{SESSION}.session"
    if not os.path.exists(session_file):
        ok = await login()
        if not ok:
            print("Login failed. Try again.")
            return

    # Main loop
    while True:
        show_menu()
        choice = input("Enter number: ").strip()
        if choice == "0":
            print("Goodbye! 👋")
            break
        if choice not in [str(i) for i in range(1, 11)]:
            print("Invalid. Try again.")
            continue
        print()
        try:
            await run_choice(choice)
        except KeyboardInterrupt:
            print("\nStopped.")
        except Exception as e:
            print(f"\n❌ Error: {e}")
        input("\n✅ Done! Press Enter to go back to menu...")


if __name__ == "__main__":
    asyncio.run(main())
