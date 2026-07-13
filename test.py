"""Run this to diagnose what's broken: python test.py"""
import sys, os

print("\n=== TELEGRAM AI AGENT — DIAGNOSTIC ===\n")

# 1. Check packages
packages = {
    "pyrogram": "pyrogram",
    "httpx": "httpx",
    "aiosqlite": "aiosqlite",
    "python-dotenv": "dotenv",
    "rich": "rich",
    "aiohttp": "aiohttp",
    "beautifulsoup4": "bs4",
}

print("📦 Packages:")
all_ok = True
for name, imp in packages.items():
    try:
        __import__(imp)
        print(f"   ✅ {name}")
    except ImportError:
        print(f"   ❌ {name}  ← MISSING")
        all_ok = False

if not all_ok:
    print("\n⚠️  Run this to fix:\n")
    print("pip install httpx pyrogram==2.0.106 TgCrypto aiohttp aiosqlite python-dotenv rich aiofiles beautifulsoup4\n")
    sys.exit(1)

# 2. Check .env
print("\n📋 Config:")
from dotenv import load_dotenv
load_dotenv()

checks = {
    "TELEGRAM_API_ID": os.getenv("TELEGRAM_API_ID"),
    "TELEGRAM_API_HASH": os.getenv("TELEGRAM_API_HASH"),
    "TELEGRAM_PHONE": os.getenv("TELEGRAM_PHONE"),
    "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
}
for k, v in checks.items():
    if v and v not in ("your_api_id", ""):
        print(f"   ✅ {k} = {v[:6]}...")
    else:
        print(f"   ❌ {k} is MISSING")

# 3. Check session
session = os.getenv("TELEGRAM_SESSION_NAME", "my_session") + ".session"
if os.path.exists(session):
    print(f"\n🔐 Session: ✅ Found ({session})")
else:
    print(f"\n🔐 Session: ❌ NOT FOUND — you need to login first")

# 4. Test Claude AI
print("\n🤖 Testing Claude AI...")
try:
    import httpx
    key = os.getenv("ANTHROPIC_API_KEY", "")
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-3-5-sonnet-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "say hi"}]},
        timeout=15,
    )
    if resp.status_code == 200:
        print("   ✅ Claude AI working!")
    else:
        print(f"   ❌ Claude API error: {resp.status_code} — {resp.text[:100]}")
except Exception as e:
    print(f"   ❌ Claude AI failed: {e}")

# 5. Test Telegram connection
print("\n📱 Testing Telegram...")
import asyncio
async def test_tg():
    try:
        from pyrogram import Client
        api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
        api_hash = os.getenv("TELEGRAM_API_HASH", "")
        phone = os.getenv("TELEGRAM_PHONE", "")
        session_name = os.getenv("TELEGRAM_SESSION_NAME", "my_session")
        app = Client(session_name, api_id=api_id, api_hash=api_hash, phone_number=phone)
        await app.connect()
        print("   ✅ Telegram connected!")
        me = await app.get_me()
        print(f"   ✅ Logged in as: {me.first_name} (@{me.username})")
        await app.disconnect()
    except Exception as e:
        print(f"   ❌ Telegram error: {e}")

asyncio.run(test_tg())

print("\n=== Done. Share this output so the error can be fixed. ===\n")
