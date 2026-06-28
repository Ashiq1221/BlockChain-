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
            "search_groups":      self.search_groups,
            "join_group":         self.join_group,
            "post_in_group":      self.post_in_group,
            "send_dm":            self.send_dm,
            "get_group_members":  self.get_group_members,
            "get_dialogs":        self.get_dialogs,
            "get_chat_history":   self.get_chat_history,
            "search_web":         self.search_web,
            "find_tg_groups_web": self.find_tg_groups_web,
            "get_stats":          self.get_stats,
            "get_unapplied_jobs": self.get_unapplied_jobs,
            "save_job":           self.save_job,
            "apply_to_job":       self.apply_to_job,
            "get_contacts":       self.get_contacts,
            "harvest_members":    self.harvest_members,
            "reply_to_dm":        self.reply_to_dm,
            "get_inbox":          self.get_inbox,
        }

    @property
    def descriptions(self) -> str:
        return """
search_groups(query)             — search for Telegram groups by keyword
join_group(username)             — join a public Telegram group by @username
post_in_group(group_id, text)    — post a message in a group
send_dm(user_id, text)           — send a direct message to a user
get_group_members(group_id)      — list members of a group
get_dialogs()                    — list all current chats/groups
get_chat_history(group_id)       — read recent messages in a group
search_web(query)                — search the web for information
find_tg_groups_web(topic)        — find public Telegram groups via web search
get_stats()                      — get account performance stats
get_unapplied_jobs()             — get list of found jobs not yet applied to
save_job(title,company,desc,src) — save a job posting to database
apply_to_job(job_id, message)    — send job application to source group
get_contacts(tags)               — get contacts filtered by tags
harvest_members(group_id)        — collect members from a group into contacts
reply_to_dm(user_id, text)       — reply to a user who messaged you
get_inbox()                      — get recent incoming direct messages
"""

    async def call(self, tool: str, **kwargs) -> dict:
        fn = self._tools.get(tool)
        if not fn:
            return {"error": f"Unknown tool: {tool}"}
        try:
            result = await fn(**kwargs)
            return {"ok": True, "result": result}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def search_groups(self, query: str) -> list:
        return await telegram_tools.search_public_groups(self.client, query, limit=10)

    async def join_group(self, username: str) -> bool:
        success = await telegram_tools.join_chat(self.client, username)
        if success:
            await self.db.upsert_group(tg_id=hash(username), username=username, title=username, joined=1)
        return success

    async def post_in_group(self, group_id: int, text: str) -> bool:
        raise PermissionError("Autonomous group posting is disabled. Manual sending only.")

    async def send_dm(self, user_id: int, text: str) -> bool:
        raise PermissionError("Autonomous DM sending is disabled. Manual sending only.")

    async def reply_to_dm(self, user_id: int, text: str) -> bool:
        raise PermissionError("Autonomous DM sending is disabled. Manual sending only.")

    async def get_group_members(self, group_id: int) -> list:
        return await telegram_tools.get_group_members(self.client, group_id, limit=50)

    async def get_dialogs(self) -> list:
        return await telegram_tools.get_dialogs(self.client, limit=30)

    async def get_chat_history(self, group_id: int) -> list:
        return await telegram_tools.get_chat_history(self.client, group_id, limit=30)

    async def search_web(self, query: str) -> list:
        return await web_tools.web_search(query, num=5)

    async def find_tg_groups_web(self, topic: str) -> list:
        return await web_tools.find_telegram_groups_online(topic)

    async def get_stats(self) -> dict:
        return await self.db.get_stats()

    async def get_unapplied_jobs(self) -> list:
        return await self.db.get_jobs(applied=False)

    async def save_job(self, title: str, company: str = "", description: str = "", source: str = "") -> bool:
        await self.db.save_job(title=title, company=company, description=description, source=source, url="")
        return True

    async def apply_to_job(self, job_id: int, message: str) -> bool:
        # Saves application draft without sending any message
        await self.db.mark_job_applied(job_id, message)
        return True

    async def get_contacts(self, tags: str = None) -> list:
        return await self.db.get_contacts(tags=tags)

    async def harvest_members(self, group_id: int) -> int:
        members = await telegram_tools.get_group_members(self.client, group_id, limit=100)
        for m in members:
            await self.db.upsert_contact(
                tg_id=m["tg_id"],
                username=m.get("username",""),
                first_name=m.get("first_name",""),
                last_name=m.get("last_name",""),
            )
        return len(members)

    async def get_inbox(self) -> list:
        messages = await self.db.get_tasks()
        dialogs = await telegram_tools.get_dialogs(self.client, limit=20)
        return [d for d in dialogs if d.get("unread", 0) > 0]
