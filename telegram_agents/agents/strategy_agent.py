"""
Agent 10 — Strategy Agent
The long-horizon planner. Analyzes the full state of the account,
defines multi-week campaigns, sets agent priorities, and adapts
tactics based on real performance data.
"""
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools


class StrategyAgent(BaseAgent):
    name = "StrategyAgent"
    emoji = "♟️"

    async def run(self, goal: str = "", timeframe: str = "2 weeks", **kwargs):
        self.log(f"Generating strategy for: {goal or 'maximize Telegram impact'} | Timeframe: {timeframe}")

        # Gather current state
        stats = await self.db.get_stats()
        groups = await self.db.get_groups()
        contacts = await self.db.get_contacts()
        jobs = await self.db.get_jobs()
        tasks = await self.db.get_tasks()

        context = f"""
Current account state:
- Groups: {stats.get('groups', 0)} discovered, {sum(1 for g in groups if g.get('joined'))} joined
- Contacts: {stats.get('contacts', 0)} indexed
- Jobs: {stats.get('jobs', 0)} found, {stats.get('jobs_applied', 0)} applied
- Messages sent: {stats.get('messages_sent', 0)}
- Tasks completed: {sum(1 for t in tasks if t['status'] == 'completed')}
- Top group categories: {self._top_categories(groups)}
        """.strip()

        strategy = ai_tools.think(
            system_addon=f"""You are a master strategist for Telegram growth and outreach.
Create a detailed {timeframe} action plan with daily/weekly milestones.
Structure: Phase 1 (Days 1-3), Phase 2 (Days 4-7), Phase 3 (Week 2).
For each phase specify: which agents to run, target metrics, and success criteria.""",
            user_prompt=f"Goal: {goal or 'Maximize opportunities, jobs, and network on Telegram'}\n\n{context}\n\nCreate the strategy:",
            max_tokens=2000,
        )

        task_id = await self.db.create_task(self.name, goal)
        await self.db.update_task(task_id, "completed", strategy)
        await self.db.log_event("strategy_created", {"goal": goal, "timeframe": timeframe})

        self.log(f"\n[bold yellow]STRATEGY:[/bold yellow]\n{strategy}")
        return strategy

    async def daily_brief(self) -> str:
        """Generate a morning briefing with priorities for the day."""
        stats = await self.db.get_stats()
        pending_tasks = await self.db.get_tasks(status="pending")
        jobs = await self.db.get_jobs(applied=False)

        brief = ai_tools.think(
            system_addon="You generate concise daily briefings for an autonomous Telegram agent system. Be specific and directive.",
            user_prompt=f"""
Today's status:
- Groups joined: {stats.get('groups', 0)}
- Contacts: {stats.get('contacts', 0)}
- Unapplied jobs: {len(jobs)}
- Pending tasks: {len(pending_tasks)}

Generate today's top 5 priorities and recommended agent actions:""",
            max_tokens=600,
        )
        self.log(f"\n[bold]Daily Brief:[/bold]\n{brief}")
        return brief

    def _top_categories(self, groups: list) -> str:
        cats: dict[str, int] = {}
        for g in groups:
            c = g.get("category", "other")
            cats[c] = cats.get(c, 0) + 1
        return ", ".join(f"{c}:{n}" for c, n in sorted(cats.items(), key=lambda x: -x[1])[:5])
