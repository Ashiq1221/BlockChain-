"""
Agent 8 — Responder Agent
Listens for incoming DMs and group mentions; generates and sends
intelligent, contextual replies — fully autonomous.
"""
import asyncio
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, telegram_tools
from telegram_agents.config import Config


class ResponderAgent(BaseAgent):
    name = "ResponderAgent"
    emoji = "💬"

    def __init__(self, client, db):
        super().__init__(client, db)
        self._goal = ""
        self._conversation_history: dict[int, list[str]] = {}

    async def run(
        self,
        goal: str = "Engage helpfully, build relationships, advance opportunities.",
        duration_seconds: int = 600,
        respond_to_groups: bool = False,
        **kwargs,
    ):
        if not Config.AUTO_RESPOND:
            self.log_warn("AUTO_RESPOND is off. Skipping.")
            return

        self._goal = goal
        self._running = True
        self.log(f"Listening for incoming messages ({duration_seconds}s)")

        me = await telegram_tools.get_me(self.client)
        my_id = me["id"]

        async def dm_handler(client, message: Message):
            if not self._running:
                return
            if message.from_user and message.from_user.id == my_id:
                return  # Skip own messages

            text = message.text or ""
            if not text:
                return

            peer_id = message.from_user.id if message.from_user else message.chat.id
            await self.db.log_message("in", peer_id, "user", text, message.id)

            # Build conversation history
            history = self._conversation_history.get(peer_id, [])
            history.append(f"Them: {text}")
            history_str = "\n".join(history[-10:])  # Last 10 turns

            reply = ai_tools.smart_reply(
                incoming=text,
                conversation_history=history_str,
                goal=self._goal,
            )

            sent = await telegram_tools.send_dm(self.client, peer_id, reply)
            if sent:
                history.append(f"Me: {reply}")
                self._conversation_history[peer_id] = history
                await self.db.log_message("out", peer_id, "user", reply, sent.id)
                self.log_success(f"Replied to {peer_id}: {reply[:60]}...")

        async def mention_handler(client, message: Message):
            if not self._running or not respond_to_groups:
                return
            text = message.text or ""
            me_username = me.get("username", "")
            if me_username and f"@{me_username}" not in text:
                return

            chat_id = message.chat.id
            reply = ai_tools.smart_reply(
                incoming=text,
                conversation_history="",
                goal=self._goal,
            )
            sent = await telegram_tools.send_message(self.client, chat_id, reply)
            if sent:
                await self.db.log_message("out", chat_id, "group", reply, sent.id)
                self.log_success(f"Replied to group mention in {message.chat.title}: {reply[:60]}")

        h1 = self.client.add_handler(MessageHandler(dm_handler, filters.private & filters.text & filters.incoming))
        h2 = self.client.add_handler(MessageHandler(mention_handler, filters.group & filters.text & filters.incoming))

        try:
            await asyncio.sleep(duration_seconds)
        finally:
            self._running = False
            self.client.remove_handler(*h1)
            self.client.remove_handler(*h2)

        self.log(f"Responder done. Handled {sum(len(v) for v in self._conversation_history.values())} message turns.")
