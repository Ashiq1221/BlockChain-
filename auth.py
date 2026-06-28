"""One-time Telegram authentication — run this first."""
import asyncio
from pyrogram import Client
from dotenv import load_dotenv
import os

load_dotenv()

async def main():
    app = Client(
        os.getenv("TELEGRAM_SESSION_NAME", "my_session"),
        api_id=int(os.getenv("TELEGRAM_API_ID")),
        api_hash=os.getenv("TELEGRAM_API_HASH"),
        phone_number=os.getenv("TELEGRAM_PHONE"),
    )
    async with app:
        me = await app.get_me()
        print(f"\n✅ Authenticated as: {me.first_name} (@{me.username}) — ID: {me.id}")
        print("Session saved. You can now run the agents.")

asyncio.run(main())
