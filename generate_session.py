"""
Run this ONCE on Termux to generate your TELEGRAM_SESSION_STRING.
Copy the printed string and set it as an env var on Railway.

Usage:
  python3 generate_session.py
"""
import asyncio, sys, subprocess

for pkg in ["pyrogram==2.0.106", "TgCrypto"]:
    try:
        __import__(pkg.split("==")[0])
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"])

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded


async def main():
    print("\n=== Telegram Session Generator ===")
    print("Run this ONCE. Paste the output string into Railway env vars.\n")

    api_id   = int(input("TELEGRAM_API_ID  : ").strip())
    api_hash = input("TELEGRAM_API_HASH : ").strip()
    phone    = input("TELEGRAM_PHONE (e.g. +91XXXXXXXXXX): ").strip()

    app = Client("_session_gen", api_id=api_id, api_hash=api_hash, phone_number=phone)

    await app.connect()
    try:
        sent = await app.send_code(phone)
    except Exception as e:
        print(f"Could not send OTP: {e}")
        return

    code = input("\nOTP from Telegram: ").strip()
    try:
        await app.sign_in(phone, sent.phone_code_hash, code)
    except SessionPasswordNeeded:
        pwd = input("2FA password: ").strip()
        await app.check_password(pwd)

    me  = await app.get_me()
    s   = await app.export_session_string()
    await app.disconnect()

    import os
    try:
        os.remove("_session_gen.session")
    except FileNotFoundError:
        pass

    print(f"\n✅ Authenticated as {me.first_name} (@{me.username})")
    print("\n" + "=" * 70)
    print("TELEGRAM_SESSION_STRING (copy everything between the lines):")
    print("-" * 70)
    print(s)
    print("-" * 70)
    print("\nSet these env vars in Railway:")
    print("  TELEGRAM_SESSION_STRING = <string above>")
    print("  TELEGRAM_API_ID         = your api id")
    print("  TELEGRAM_API_HASH       = your api hash")
    print("  TELEGRAM_OWNER_ID       = your telegram id")
    print("  TELEGRAM_BOT_TOKEN      = bot token from @BotFather")
    print("  GROQ_API_KEY            = from console.groq.com")
    print("  GEMINI_API_KEY          = from aistudio.google.com")
    print("  TAVILY_API_KEY          = from tavily.com")
    print("  XAI_API_KEY             = (optional)")
    print("  ANTHROPIC_API_KEY       = (optional)")


asyncio.run(main())
