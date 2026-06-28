"""
Agent 6 — Network Agent
Harvests contacts from joined groups, tags them by relevance,
and builds a strategic contact database for outreach.
"""
import asyncio
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools, telegram_tools


class NetworkAgent(BaseAgent):
    name = "NetworkAgent"
    emoji = "🕸️"

    async def run(
        self,
        goal: str = "",
        tags: list[str] | None = None,
        max_contacts_per_group: int = 50,
        **kwargs,
    ):
        groups = await self.db.get_groups(joined=True)
        if not groups:
            self.log_warn("No joined groups to harvest contacts from.")
            return {"new_contacts": 0}

        new_contacts = 0
        self.log(f"Harvesting contacts from {len(groups)} groups")

        for group in groups:
            try:
                members = await telegram_tools.get_group_members(
                    self.client, group["tg_id"], limit=max_contacts_per_group
                )
                self.log(f"  {group['title']}: {len(members)} members found")

                for member in members:
                    # Tag members by group category + goal relevance
                    member_str = f"{member.get('first_name','')} {member.get('last_name','')} @{member.get('username','')}"
                    relevance = ai_tools.score_relevance(member_str, goal or group.get("category", "networking"))

                    auto_tags = group.get("category", "other")
                    if tags:
                        auto_tags = ", ".join(tags)

                    await self.db.upsert_contact(
                        tg_id=member["tg_id"],
                        username=member.get("username", ""),
                        first_name=member.get("first_name", ""),
                        last_name=member.get("last_name", ""),
                        tags=auto_tags,
                    )
                    new_contacts += 1

                await asyncio.sleep(1)

            except Exception as e:
                self.log_warn(f"Error harvesting {group.get('title')}: {e}")

        self.log_success(f"Network harvest complete. {new_contacts} contacts indexed.")
        await self.db.log_event("network_harvest", {"contacts": new_contacts, "groups": len(groups)})
        return {"new_contacts": new_contacts}

    async def find_influencers(self, topic: str) -> list[dict]:
        """Identify high-value contacts to prioritise."""
        contacts = await self.db.get_contacts()
        scored = []
        for c in contacts:
            bio = c.get("bio", "") or ""
            name = f"{c.get('first_name','')} {c.get('last_name','')} {c.get('username','')}"
            score = ai_tools.score_relevance(f"{name} {bio}", topic)
            scored.append({**c, "influence_score": score})
        scored.sort(key=lambda x: x["influence_score"], reverse=True)
        return scored[:20]
