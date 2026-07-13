"""
Agent 7 — Monitor Agent
Watches groups in real-time for keywords, opportunities, and mentions.
Fires callbacks when triggers match so other agents can respond instantly.
"""
import asyncio
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools
from telegram_agents.config import Config


class MonitorAgent(BaseAgent):
    name = "MonitorAgent"
    emoji = "👁️"

    def __init__(self, client, db):
        super().__init__(client, db)
        self._keywords: list[str] = []
        self._callbacks: list = []
        self._handler = None

    def add_keyword(self, keyword: str):
        self._keywords.append(keyword.lower())

    def on_match(self, callback):
        """Register a callback(chat_id, user_id, text) for keyword matches."""
        self._callbacks.append(callback)

    async def run(
        self,
        goal: str = "",
        keywords: list[str] | None = None,
        duration_seconds: int = 300,
        **kwargs,
    ):
        if keywords:
            self._keywords = [k.lower() for k in keywords]
        elif not self._keywords:
            # Extract keywords from goal
            raw = ai_tools.think(
                system_addon="Extract monitoring keywords from a goal. Comma-separated only.",
                user_prompt=f"Goal: {goal}\n\nKeywords to monitor:",
            )
            self._keywords = [k.strip().lower() for k in raw.split(",") if k.strip()]

        self.log(f"Monitoring keywords: {self._keywords} for {duration_seconds}s")
        self._running = True

        matched_events: list[dict] = []

        async def handler(client, message: Message):
            if not self._running:
                return
            text = (message.text or "").lower()
            for kw in self._keywords:
                if kw in text:
                    event = {
                        "keyword": kw,
                        "chat_id": message.chat.id,
                        "chat_title": message.chat.title or "",
                        "user_id": message.from_user.id if message.from_user else None,
                        "text": message.text,
                        "msg_id": message.id,
                    }
                    matched_events.append(event)
                    await self.db.log_message("in", message.chat.id, "group", message.text or "", message.id)
                    await self.db.log_event("keyword_match", event)
                    self.log_success(f"Match [{kw}] in {event['chat_title']}: {message.text[:80]}")

                    for cb in self._callbacks:
                        try:
                            await cb(event)
                        except Exception as e:
                            self.log_error(f"Callback error: {e}")
                    break

        self._handler = self.client.add_handler(MessageHandler(handler, filters.text & filters.group))

        try:
            await asyncio.sleep(duration_seconds)
        finally:
            self._running = False
            if self._handler:
                self.client.remove_handler(*self._handler)

        self.log(f"Monitor finished. {len(matched_events)} matches.")
        return matched_events
