"""
AOS Telegram Bot — run with: python aos_bot.py

Every message goes through all 14 AOS layers:
  Orchestrator → Agents → Critics → Debate → Judge → Writer
Then replies with the final answer + confidence score.
"""
import asyncio, sys, subprocess

PKGS = ["pyrogram==2.0.106", "TgCrypto", "aiohttp", "beautifulsoup4",
        "aiosqlite", "python-dotenv", "rich"]
for pkg in PKGS:
    try: __import__(pkg.split("==")[0].replace("-","_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (Message, CallbackQuery,
                            InlineKeyboardMarkup, InlineKeyboardButton)
from pyrogram.enums import ChatAction
from pyrogram.errors import SessionPasswordNeeded
from rich.console import Console
from rich.panel import Panel
import os
from dotenv import load_dotenv
load_dotenv()

from telegram_agents.config import Config
from aos.pipeline import AOS
from aos.config import AOSConfig as C

console = Console()
aos = AOS()

WELCOME = """🧠 **AOS — AI Operating System Online**

Every question goes through:
1️⃣ Task decomposition
2️⃣ Specialist agents (Research, Reasoning, Coding, Search…)
3️⃣ Critical thinking team (Critic, Devil's Advocate, Skeptic…)
4️⃣ Debate engine (up to 5 rounds)
5️⃣ Judge (scores on 10 metrics)
6️⃣ Final Writer (Claude polishes the winner)
7️⃣ Confidence score (0–100%)

**Just ask anything.**"""


def _confidence_bar(pct: int) -> str:
    filled = pct // 10
    return "█" * filled + "░" * (10 - filled)


def _footer(resp) -> str:
    bar = _confidence_bar(resp.confidence)
    critics = "✅" if resp.critics_passed else "⚠️"
    return (
        f"\n\n─────────────────\n"
        f"🎯 **Confidence: {resp.confidence}%** {bar}\n"
        f"{resp.confidence_reason}\n"
        f"👥 Agents: {', '.join(resp.agents_used)}\n"
        f"🔁 Debate: {resp.debate_rounds} round(s)\n"
        f"🛡 Critics: {critics}\n"
        f"⏱ {resp.elapsed_ms}ms"
    )


def _source_buttons(sources: list[str]) -> InlineKeyboardMarkup | None:
    if not sources:
        return None
    buttons = [
        [InlineKeyboardButton(f"🔗 Source {i+1}", url=s)]
        for i, s in enumerate(sources[:3])
        if s.startswith("http")
    ]
    feedback_row = [
        InlineKeyboardButton("👍 Useful", callback_data=f"fb_y"),
        InlineKeyboardButton("👎 Not useful", callback_data=f"fb_n"),
    ]
    buttons.append(feedback_row)
    return InlineKeyboardMarkup(buttons) if buttons else None


async def _process_message(bot: Client, msg: Message, uid: int, text: str):
    """Background task so new messages are never blocked by in-flight processing."""
    try:
        await bot.send_chat_action(uid, ChatAction.TYPING)
    except Exception:
        pass

    thinking_msg = await msg.reply(
        "🧠 **AOS Processing...**\n\n"
        "⏳ Routing → Agents → Critics → Debate → Judge → Writing final answer..."
    )

    try:
        resp = await aos.process(text)
        answer_text = resp.answer + _footer(resp)

        if len(answer_text) > 4000:
            answer_text = answer_text[:3900] + "\n\n_[truncated — answer too long]_"

        kb = _source_buttons(resp.sources)
        await thinking_msg.edit(answer_text, reply_markup=kb)

    except Exception as e:
        await thinking_msg.edit(f"❌ AOS Error: {e}")
        console.print(f"[red]AOS error: {e}[/red]")


async def handle_message(bot: Client, msg: Message):
    uid  = msg.from_user.id if msg.from_user else 0
    text = (msg.text or msg.caption or "").strip()

    # Security: only respond to owner if OWNER_ID is set
    if C.OWNER_ID and uid != C.OWNER_ID:
        await msg.reply("⛔ Access denied.")
        return

    if not text or text.startswith("/"):
        return

    # Fire-and-forget so the next message can be picked up immediately
    asyncio.create_task(_process_message(bot, msg, uid, text))


async def handle_feedback(bot: Client, cb: CallbackQuery):
    await cb.answer()
    useful = cb.data == "fb_y"
    # We don't have response_id easily here, so just log
    emoji = "👍" if useful else "👎"
    console.print(f"[dim]Feedback: {emoji} from {cb.from_user.id}[/dim]")
    await cb.message.reply(
        f"{emoji} Thanks for the feedback! AOS will learn from this."
    )


async def handle_start(bot: Client, msg: Message):
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Providers", callback_data="providers"),
        InlineKeyboardButton("🔬 Test AOS", callback_data="test"),
    ]])
    await msg.reply(WELCOME, reply_markup=kb)


async def handle_providers(bot: Client, cb: CallbackQuery):
    await cb.answer()
    p = C.available_providers()
    text = "**Available AI Providers:**\n" + "\n".join(f"✅ {x}" for x in p)
    if not p:
        text = "❌ No API keys configured. Add them to .env"
    await cb.message.reply(text)


async def handle_test(bot: Client, cb: CallbackQuery):
    await cb.answer()
    await cb.message.reply("🧪 Sending test question through all 14 layers...")
    resp = await aos.process("What is 2 + 2 and why?")
    await cb.message.reply(resp.answer + _footer(resp))


async def main():
    if not Config.BOT_TOKEN:
        console.print("[bold red]❌ TELEGRAM_BOT_TOKEN not set in .env[/bold red]")
        return

    # First-time user session login if needed
    if not os.path.exists(f"{Config.SESSION_NAME}.session") and Config.PHONE:
        console.print("[yellow]Setting up user session for first time...[/yellow]")
        app = Client(Config.SESSION_NAME, api_id=Config.API_ID,
                     api_hash=Config.API_HASH, phone_number=Config.PHONE)
        await app.connect()
        try:
            sent = await app.send_code(Config.PHONE)
            code = input("Enter OTP: ").strip()
            try:
                await app.sign_in(Config.PHONE, sent.phone_code_hash, code)
            except SessionPasswordNeeded:
                pwd = input("2FA password: ").strip()
                await app.check_password(pwd)
        except Exception as e:
            console.print(f"[red]Login error: {e}[/red]")
        await app.disconnect()

    bot = Client(
        "aos_bot_session",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
    )

    bot.add_handler(MessageHandler(handle_start,    filters.command("start") & filters.private))
    bot.add_handler(MessageHandler(handle_message,  filters.text & filters.private))
    bot.add_handler(CallbackQueryHandler(handle_feedback,  filters.regex("^fb_")))
    bot.add_handler(CallbackQueryHandler(handle_providers, filters.regex("^providers$")))
    bot.add_handler(CallbackQueryHandler(handle_test,      filters.regex("^test$")))

    async with bot:
        console.print(Panel(
            "[bold magenta]🧠 AOS Telegram Bot — ONLINE[/bold magenta]\n\n"
            f"[white]Providers ready: {', '.join(C.available_providers())}\n"
            "Find your bot on Telegram → /start → ask anything[/white]",
            border_style="magenta",
        ))
        await asyncio.Event().wait()  # run forever

    aos.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]AOS offline.[/yellow]")
