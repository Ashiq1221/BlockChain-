"""
Run this ONCE on Termux to generate your TELEGRAM_SESSION_STRING.
It saves the string directly into .env so the bot can start immediately.
Also prints it so you can copy it into Railway env vars.

Usage:
  python3 generate_session.py
"""
import asyncio, os, sys, subprocess, re

for pkg in ["pyrogram==2.0.106", "TgCrypto"]:
    try:
        __import__(pkg.split("==")[0])
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"])

from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded


def _save_to_env(key: str, value: str):
    """Write or update a key in .env file."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        content = open(env_path).read()
        if re.search(rf"^{key}=", content, re.MULTILINE):
            content = re.sub(rf"^{key}=.*$", f"{key}={value}", content, flags=re.MULTILINE)
        else:
            content += f"\n{key}={value}\n"
        open(env_path, "w").write(content)
    else:
        open(env_path, "w").write(f"{key}={value}\n")


async def main():
    print("\n=== Telegram Session Generator ===")
    print("Enter your details (only needed once).\n")

    from dotenv import load_dotenv
    load_dotenv()

    api_id_env   = os.getenv("TELEGRAM_API_ID", "")
    api_hash_env = os.getenv("TELEGRAM_API_HASH", "")
    phone_env    = os.getenv("TELEGRAM_PHONE", "")

    api_id   = input(f"TELEGRAM_API_ID  [{api_id_env}]: ").strip() or api_id_env
    api_hash = input(f"TELEGRAM_API_HASH [{api_hash_env[:6]}...]: ").strip() or api_hash_env
    phone    = input(f"TELEGRAM_PHONE   [{phone_env}]: ").strip() or phone_env

    if not api_id or not api_hash or not phone:
        print("❌ API ID, API Hash, and Phone are required.")
        return

    app = Client("_session_gen", api_id=int(api_id), api_hash=api_hash,
                 phone_number=phone)

    await app.connect()
    try:
        sent = await app.send_code(phone)
    except Exception as e:
        print(f"❌ Could not send OTP: {e}")
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

    try:
        os.remove("_session_gen.session")
    except FileNotFoundError:
        pass

    _save_to_env("TELEGRAM_SESSION_STRING", s)

    print(f"\n✅ Authenticated as {me.first_name} (@{me.username})")
    print("✅ Session string saved to .env — bot will start automatically.\n")
    print("=" * 70)
    print("TELEGRAM_SESSION_STRING (copy this for Railway):")
    print("-" * 70)
    print(s)
    print("-" * 70)
    print("\nPaste the above into Railway → Variables → TELEGRAM_SESSION_STRING")


asyncio.run(main())
