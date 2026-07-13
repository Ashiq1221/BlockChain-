"""
All agent capabilities as callable tools with structured input/output.
The AI brain picks tools, calls them, reads results, and decides next action.
"""
import asyncio
from pyrogram import Client
from telegram_agents.database import Database
from telegram_agents.tools import telegram_tools, web_tools, ai_tools
from telegram_agents.config import Config


class ToolRegistry:
    def __init__(self, client: Client, db: Database):
        self.client = client
        self.db = db
        self._tools = {
            # ── Telegram ──────────────────────────────────────────────
            "search_groups":      self.search_groups,
            "join_group":         self.join_group,
            "post_in_group":      self.post_in_group,
            "post_to_channel":    self.post_to_channel,
            "send_dm":            self.send_dm,
            "reply_to_dm":        self.reply_to_dm,
            "reply_message":      self.reply_message,
            "moderate_user":      self.moderate_user,
            "pin_message":        self.pin_message,
            "get_admins":         self.get_admins,
            "get_group_members":  self.get_group_members,
            "get_dialogs":        self.get_dialogs,
            "get_chat_history":   self.get_chat_history,
            "get_recent_messages":self.get_recent_messages,
            "get_inbox":          self.get_inbox,
            # ── Content ───────────────────────────────────────────────
            "create_content":     self.create_content,
            # ── Web ───────────────────────────────────────────────────
            "search_web":         self.search_web,
            "find_tg_groups_web": self.find_tg_groups_web,
            # ── Jobs ──────────────────────────────────────────────────
            "get_stats":          self.get_stats,
            "get_unapplied_jobs": self.get_unapplied_jobs,
            "save_job":           self.save_job,
            "apply_to_job":       self.apply_to_job,
            "get_contacts":       self.get_contacts,
            "harvest_members":    self.harvest_members,
        }

    @property
    def descriptions(self) -> str:
        return """
TELEGRAM:
  search_groups(query)                       — find groups by keyword
  join_group(username)                       — join a public group by @username
  post_in_group(group_id, text)              — post message in a group
  post_to_channel(channel, text)             — post to a channel (@username or id)
  send_dm(user_id, text)                     — DM a user
  reply_to_dm(user_id, text)                 — reply to a user's DM
  reply_message(chat_id, msg_id, text)       — reply to a specific message
  moderate_user(chat_id, user_id, action)    — kick|ban|mute|unmute a user
  pin_message(chat_id, msg_id)               — pin a message in a group/channel
  get_admins(chat_id)                        — list admins of a group
  get_group_members(group_id)                — list members of a group
  get_dialogs()                              — list all chats/groups
  get_chat_history(group_id)                 — read recent messages
  get_recent_messages(chat_id, limit)        — read messages with IDs for replies
  get_inbox()                                — unread DMs
CONTENT:
  create_content(topic, style, length)       — AI-generate post/announcement/thread
WEB:
  search_web(query)                          — web search
  find_tg_groups_web(topic)                  — find groups via web
JOBS/DATA:
  get_stats()                                — account stats
  get_unapplied_jobs()                       — pending job applications
  save_job(title, company, desc, src)        — save a job
  apply_to_job(job_id, message)              — apply to a saved job
  get_contacts(tags)                         — fetch contacts
  harvest_members(group_id)                  — collect members into contacts
"""

    async def call(self, tool: str, **kwargs) -> dict:
        fn = self._tools.get(tool)
        if not fn:
            return {"ok": False, "error": f"Unknown tool: {tool}"}
        try:
            result = await fn(**kwargs)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def search_groups(self, query: str) -> list:
        return await telegram_tools.search_public_groups(self.client, query, limit=10)

    async def join_group(self, username: str) -> bool:
        success = await telegram_tools.join_chat(self.client, username)
        if success:
            await self.db.upsert_group(tg_id=hash(username), username=username,
                                       title=username, joined=1)
        return success

    async def post_in_group(self, group_id: int | str, text: str) -> bool:
        msg = await telegram_tools.send_message(self.client, group_id, text)
        if msg:
            await self.db.log_message("out", group_id, "group", text, msg.id)
        return bool(msg)

    async def post_to_channel(self, channel: int | str, text: str) -> bool:
        msg = await telegram_tools.send_message(self.client, channel, text)
        if msg:
            await self.db.log_message("out", channel, "channel", text, msg.id)
        return bool(msg)

    async def send_dm(self, user_id: int | str, text: str) -> bool:
        msg = await telegram_tools.send_dm(self.client, user_id, text)
        if msg:
            await self.db.log_message("out", user_id, "user", text, msg.id)
        return bool(msg)

    async def reply_to_dm(self, user_id: int | str, text: str) -> bool:
        return await self.send_dm(user_id=user_id, text=text)

    async def reply_message(self, chat_id: int | str,
                            msg_id: int, text: str) -> bool:
        msg = await telegram_tools.reply_to_message(self.client, chat_id, msg_id, text)
        return bool(msg)

    async def moderate_user(self, chat_id: int | str,
                            user_id: int | str, action: str) -> bool:
        return await telegram_tools.moderate_user(self.client, chat_id, user_id, action)

    async def pin_message(self, chat_id: int | str, msg_id: int) -> bool:
        return await telegram_tools.pin_message(self.client, chat_id, msg_id)

    async def get_admins(self, chat_id: int | str) -> list:
        return await telegram_tools.get_admins(self.client, chat_id)

    async def get_group_members(self, group_id: int | str) -> list:
        return await telegram_tools.get_group_members(self.client, group_id, limit=50)

    async def get_dialogs(self) -> list:
        return await telegram_tools.get_dialogs(self.client, limit=30)

    async def get_chat_history(self, group_id: int | str) -> list:
        return await telegram_tools.get_chat_history(self.client, group_id, limit=30)

    async def get_recent_messages(self, chat_id: int | str,
                                  limit: int = 20) -> list:
        return await telegram_tools.get_recent_messages(self.client, chat_id, limit)

    async def get_inbox(self) -> list:
        dialogs = await telegram_tools.get_dialogs(self.client, limit=20)
        return [d for d in dialogs if d.get("unread", 0) > 0]

    # ── Content ───────────────────────────────────────────────────────────────

    async def create_content(self, topic: str, style: str = "post",
                             length: str = "medium") -> str:
        """Generate content using AI. style: post|announcement|thread|caption"""
        length_guide = {"short": "2-3 sentences", "medium": "1-2 paragraphs",
                        "long": "3-5 paragraphs"}.get(length, "1-2 paragraphs")
        return ai_tools.think(
            system_addon=(
                f"Write a Telegram {style} about the given topic. "
                f"Length: {length_guide}. "
                "Sound human, engaging, and on-brand for a Web3/AI community. "
                "No hashtags unless it's a social post. Return only the message text."
            ),
            user_prompt=f"Topic: {topic}",
            max_tokens=600,
        )

    # ── Web ───────────────────────────────────────────────────────────────────

    async def search_web(self, query: str) -> list:
        return await web_tools.web_search(query, num=5)

    async def find_tg_groups_web(self, topic: str) -> list:
        return await web_tools.find_telegram_groups_online(topic)

    # ── Jobs / Data ───────────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        return await self.db.get_stats()

    async def get_unapplied_jobs(self) -> list:
        return await self.db.get_jobs(applied=False)

    async def save_job(self, title: str, company: str = "",
                       description: str = "", source: str = "") -> bool:
        await self.db.save_job(title=title, company=company,
                               description=description, source=source, url="")
        return True

    async def apply_to_job(self, job_id: int, message: str) -> bool:
        jobs = await self.db.get_jobs()
        for j in jobs:
            if j["id"] == job_id and j.get("group_id"):
                msg = await telegram_tools.send_message(
                    self.client, j["group_id"], message)
                if msg:
                    await self.db.mark_job_applied(job_id, message)
                    await self.db.log_message("out", j["group_id"],
                                              "group", message, msg.id)
                    return True
        await self.db.mark_job_applied(job_id, message)
        return True

    async def get_contacts(self, tags: str = None) -> list:
        return await self.db.get_contacts(tags=tags)

    async def harvest_members(self, group_id: int | str) -> int:
        members = await telegram_tools.get_group_members(
            self.client, group_id, limit=100)
        for m in members:
            await self.db.upsert_contact(
                tg_id=m["tg_id"],
                username=m.get("username", ""),
                first_name=m.get("first_name", ""),
                last_name=m.get("last_name", ""),
            )
        return len(members)
