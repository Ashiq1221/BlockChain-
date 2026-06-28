"""Low-level Telegram helpers wrapping Pyrogram."""
import asyncio
from typing import AsyncGenerator
from pyrogram import Client
from pyrogram.types import Message, Chat, User, Dialog
from pyrogram.errors import FloodWait, UserAlreadyParticipant, InviteHashExpired
from telegram_agents.config import Config


async def safe_call(coro, retries: int = 5):
    """Execute a Pyrogram coroutine, automatically handling FloodWait."""
    for attempt in range(retries):
        try:
            return await coro
        except FloodWait as e:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(e.value + 1)
    return None


async def search_groups(client: Client, query: str, limit: int = 20) -> list[dict]:
    results = []
    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if chat.type in ("group", "supergroup", "channel"):
            title = chat.title or ""
            if query.lower() in title.lower():
                results.append({
                    "tg_id": chat.id,
                    "username": chat.username or "",
                    "title": title,
                    "members": getattr(chat, "members_count", 0) or 0,
                })
        if len(results) >= limit:
            break
    return results


async def search_public_groups(client: Client, query: str, limit: int = 10) -> list[dict]:
    """Search public groups/channels by username patterns."""
    results = []
    try:
        result = await safe_call(client.search_global(query, limit=limit))
        async for msg in result:
            chat = msg.chat
            if chat and chat.type in ("group", "supergroup", "channel"):
                info = {
                    "tg_id": chat.id,
                    "username": chat.username or "",
                    "title": chat.title or "",
                    "members": getattr(chat, "members_count", 0) or 0,
                }
                if info not in results:
                    results.append(info)
    except Exception:
        pass
    return results


async def join_chat(client: Client, username: str) -> bool:
    try:
        await safe_call(client.join_chat(username))
        return True
    except UserAlreadyParticipant:
        return True
    except (InviteHashExpired, Exception):
        return False


async def send_message(client: Client, peer: str | int, text: str) -> Message | None:
    await asyncio.sleep(Config.RATE_LIMIT_SLEEP)
    return await safe_call(client.send_message(peer, text))


async def send_dm(client: Client, user_id: int | str, text: str) -> Message | None:
    await asyncio.sleep(Config.RATE_LIMIT_SLEEP)
    return await safe_call(client.send_message(user_id, text))


async def get_group_members(client: Client, chat_id: int | str, limit: int = 100) -> list[dict]:
    members = []
    try:
        async for member in client.get_chat_members(chat_id, limit=limit):
            u = member.user
            if u and not u.is_bot:
                members.append({
                    "tg_id": u.id,
                    "username": u.username or "",
                    "first_name": u.first_name or "",
                    "last_name": u.last_name or "",
                    "bio": "",
                })
    except Exception:
        pass
    return members


async def get_chat_history(client: Client, chat_id: int | str, limit: int = 50) -> list[dict]:
    msgs = []
    async for msg in client.get_chat_history(chat_id, limit=limit):
        if msg.text:
            msgs.append({
                "id": msg.id,
                "from_id": msg.from_user.id if msg.from_user else None,
                "text": msg.text,
                "date": str(msg.date),
            })
    return msgs


async def get_dialogs(client: Client, limit: int = 50) -> list[dict]:
    dialogs = []
    async for d in client.get_dialogs(limit=limit):
        dialogs.append({
            "chat_id": d.chat.id,
            "title": d.chat.title or d.chat.first_name or "",
            "type": str(d.chat.type),
            "unread": d.unread_messages_count,
            "top_message": d.top_message.text[:100] if d.top_message and d.top_message.text else "",
        })
    return dialogs


async def get_me(client: Client) -> dict:
    me = await client.get_me()
    return {
        "id": me.id,
        "username": me.username or "",
        "first_name": me.first_name or "",
        "last_name": me.last_name or "",
        "phone": me.phone_number or "",
    }
