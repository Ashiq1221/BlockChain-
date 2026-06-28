"""
Agent 1 — Commander
Master orchestrator. Understands natural-language goals, breaks them into
sub-tasks, and delegates to the right specialist agents.
"""
import asyncio
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools


class CommanderAgent(BaseAgent):
    name = "Commander"
    emoji = "🧠"

    TOOLS = [
        "GroupDiscoveryAgent  — find & join relevant Telegram groups",
        "JobHunterAgent       — search job posts, craft and send applications",
        "DMAgent              — send targeted direct messages",
        "ContentAgent         — create and publish posts in groups",
        "NetworkAgent         — build contact lists from groups",
        "MonitorAgent         — watch for keywords / mentions in real-time",
        "ResponderAgent       — auto-reply to incoming DMs",
        "AnalyticsAgent       — report stats and performance",
        "StrategyAgent        — design long-term engagement strategy",
    ]

    async def run(self, goal: str, agent_registry: dict):
        self.log(f"Received goal: [bold]{goal}[/bold]")

        plan = ai_tools.plan_action(
            goal=goal,
            available_tools=self.TOOLS,
            context="User's Telegram account needs autonomous management.",
        )
        self.log(f"Action plan:\n{plan}")

        task_id = await self.db.create_task(self.name, goal)

        # Parse which agents are mentioned in the plan and dispatch them
        dispatched = []
        for agent_name, agent_obj in agent_registry.items():
            if agent_name.lower() in plan.lower():
                self.log(f"Dispatching → {agent_obj.emoji} {agent_name}")
                dispatched.append(asyncio.create_task(
                    agent_obj.run(goal=goal)
                ))

        if dispatched:
            await asyncio.gather(*dispatched, return_exceptions=True)

        await self.db.update_task(task_id, "completed", plan)
        self.log_success("All sub-tasks dispatched and completed.")
        return plan

    async def interpret_command(self, raw_input: str) -> str:
        """Turn free-form user text into a structured goal."""
        return ai_tools.think(
            system_addon="You interpret vague user commands into precise, actionable goals for a Telegram automation system.",
            user_prompt=f"User said: \"{raw_input}\"\n\nRestate this as a clear, specific goal:",
        )
