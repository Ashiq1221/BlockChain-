"""
Agent 4 — DM Agent
Sends targeted, personalised direct messages to users based on goals.
Respects hourly limits to avoid Telegram anti-spam measures.
"""
import asyncio
from datetime import datetime, timezone
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, telegram_tools
from telegram_agents.config import Config


class DMAgent(BaseAgent):
    name = "DMAgent"
    emoji = "✉️"

    async def run(
        self,
        goal: str = "",
        target_user_ids: list[int] | None = None,
        tags_filter: str | None = None,
        message_template: str | None = None,
        max_send: int | None = None,
        **kwargs,
    ):
        limit = max_send or Config.MAX_DM_PER_HOUR

        # Resolve targets
        if not target_user_ids:
            contacts = await self.db.get_contacts(tags=tags_filter)
            target_user_ids = [c["tg_id"] for c in contacts if not c.get("dm_sent")]

        if not target_user_ids:
            self.log_warn("No targets found.")
            return {"sent": 0}

        self.log(f"Preparing to DM {min(len(target_user_ids), limit)} users | goal: {goal}")

        sent_count = 0
        for user_id in target_user_ids[:limit]:
            try:
                # Personalise message per user
                contact_info = ""
                contacts = await self.db.get_contacts()
                for c in contacts:
                    if c["tg_id"] == user_id:
                        contact_info = f"Name: {c.get('first_name','')} {c.get('last_name','')}, Tags: {c.get('tags','')}"
                        break

                if message_template:
                    text = message_template
                else:
                    text = ai_tools.compose_message(
                        context=f"Contact info: {contact_info}",
                        goal=goal or "Introduce myself and explore collaboration opportunities.",
                        tone="friendly and professional",
                    )

                msg = await telegram_tools.send_dm(self.client, user_id, text)
                if msg:
                    sent_count += 1
                    await self.db.log_message("out", user_id, "user", text, msg.id)
                    await self.db.upsert_contact(user_id, dm_sent=1, last_dm=str(datetime.now(timezone.utc)))
                    self.log_success(f"DM sent to {user_id}")
                else:
                    self.log_warn(f"Failed to DM {user_id}")

                await asyncio.sleep(Config.RATE_LIMIT_SLEEP * 2)

            except Exception as e:
                self.log_error(f"DM error for {user_id}: {e}")

        self.log_success(f"DM campaign done. Sent {sent_count}/{len(target_user_ids[:limit])}")
        await self.db.log_event("dm_campaign", {"sent": sent_count, "goal": goal})
        return {"sent": sent_count}

    async def dm_from_message(self, from_user_id: int, incoming_text: str, goal: str = "") -> bool:
        """Compose and send a DM in response to a specific incoming message."""
        reply = ai_tools.compose_message(
            context=f"Incoming message: {incoming_text}",
            goal=goal or "Engage naturally and move the conversation forward.",
            tone="conversational",
        )
        msg = await telegram_tools.send_dm(self.client, from_user_id, reply)
        if msg:
            await self.db.log_message("out", from_user_id, "user", reply, msg.id)
            return True
        return False
