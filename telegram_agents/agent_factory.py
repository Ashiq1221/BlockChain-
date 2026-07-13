"""
Dynamic Agent Factory — creates new 1000 IQ agents from a natural language goal.

Each agent has:
  - A NAME and GOAL
  - A list of TOOLS it's allowed to use
  - A SCHEDULE (how often to run, in minutes)
  - A run() method that uses the brain to execute its goal autonomously

Usage:
  factory = AgentFactory(brain)
  agent = await factory.create("Monitor crypto prices every hour and alert on big moves")
  brain.register_agent(agent)
"""
import asyncio
import json
import re
from datetime import datetime
from rich.console import Console
from telegram_agents.tools import ai_tools

console = Console()

AVAILABLE_TOOLS = [
    "search_web", "search_groups", "join_group",
    "post_in_group", "post_to_channel", "send_dm",
    "reply_message", "moderate_user", "pin_message",
    "get_group_members", "get_dialogs", "get_chat_history",
    "get_recent_messages", "create_content", "get_stats",
    "get_contacts", "harvest_members", "get_inbox",
]

AGENT_DESIGNER_PROMPT = """You are designing a 1000 IQ autonomous AI agent.

Given the user's goal, design an agent with:
1. A concise snake_case NAME (e.g. price_monitor, spam_detector)
2. A clear one-sentence GOAL
3. The minimal set of TOOLS needed from the available list
4. A SCHEDULE in minutes (how often to run: 60=hourly, 1440=daily, 10=every 10 min)
5. A STRATEGY: step-by-step instructions the agent follows each run (max 5 steps)

Available tools: """ + ", ".join(AVAILABLE_TOOLS) + """

Return ONLY valid JSON (no markdown):
{
  "name": "agent_name",
  "goal": "One sentence goal",
  "tools": ["tool1", "tool2"],
  "schedule_minutes": 60,
  "strategy": [
    "Step 1: ...",
    "Step 2: ...",
    "Step 3: ..."
  ]
}"""


class DynamicAgent:
    """A self-contained autonomous agent created from a natural language goal."""

    def __init__(self, name: str, goal: str, tools: list[str],
                 schedule_minutes: int, strategy: list[str]):
        self.name             = name
        self.goal             = goal
        self.tools            = [t for t in tools if t in AVAILABLE_TOOLS]
        self.schedule_minutes = max(5, schedule_minutes)
        self.strategy         = strategy
        self._last_run        = 0.0
        self._run_count       = 0
        self._enabled         = True

    def is_due(self) -> bool:
        if not self._enabled:
            return False
        elapsed = (asyncio.get_event_loop().time() - self._last_run) / 60
        return elapsed >= self.schedule_minutes

    async def run(self, brain) -> str:
        """Execute one cycle of this agent using the brain's tools."""
        self._last_run  = asyncio.get_event_loop().time()
        self._run_count += 1
        console.print(f"[cyan]🤖 [{self.name}] Running (#{self._run_count})[/cyan]")

        strategy_text = "\
".join(f"{i+1}. {s}" for i, s in enumerate(self.strategy))
        obs = (
            f"Agent: {self.name}\
"
            f"Goal: {self.goal}\
"
            f"Strategy:\
{strategy_text}\
"
            f"Allowed tools: {self.tools}\
"
            f"Run #{self._run_count} at {datetime.now().strftime('%H:%M %d/%m')}"
        )

        thought = ai_tools.think(
            system_addon=(
                "You are a 1000 IQ autonomous agent. Execute your goal using ONLY "
                f"these tools: {self.tools}. "
                "Think, then output: CONCLUSION: [what to do this run]"
            ),
            user_prompt=obs,
            max_tokens=200,
        )

        plan = brain.plan(thought, obs)
        # Restrict plan to this agent's allowed tools
        plan = [s for s in plan if s.get("tool") in self.tools][:3]

        if not plan:
            return f"{self.name}: no actions this cycle"

        results = await brain.act(plan)
        ok = sum(1 for r in results if r["result"].get("ok"))
        report = f"{self.name}: {ok}/{len(results)} actions OK"
        console.print(f"[green]  ✅ {report}[/green]")
        return report

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "goal": self.goal,
            "tools": self.tools,
            "schedule_minutes": self.schedule_minutes,
            "strategy": self.strategy,
            "run_count": self._run_count,
            "enabled": self._enabled,
        }

    def __repr__(self):
        return (f"DynamicAgent({self.name!r}, every {self.schedule_minutes}m, "
                f"runs={self._run_count})")


class AgentFactory:
    """Creates, stores, and runs dynamic agents."""

    def __init__(self):
        self._agents: list[DynamicAgent] = []
        self._preload_defaults()

    def _preload_defaults(self):
        """Built-in agents that start with every session."""
        self._agents = [
            DynamicAgent(
                name="spam_watcher",
                goal="Monitor group chats for spam or scam messages and alert owner",
                tools=["get_recent_messages", "get_dialogs"],
                schedule_minutes=30,
                strategy=[
                    "Get list of joined groups from dialogs",
                    "Read recent messages from the top 3 most active groups",
                    "Flag any messages that look like spam/scam (price pumping, phishing links, 'send ETH' etc)",
                    "Report flagged messages with group name and message ID",
                ],
            ),
            DynamicAgent(
                name="opportunity_alerter",
                goal="Find new Web3/AI job postings and alert when hot leads appear",
                tools=["search_web", "create_content"],
                schedule_minutes=120,
                strategy=[
                    "Search web for 'web3 AI project hiring ambassador 2026'",
                    "Filter for opportunities not seen before",
                    "Summarize top 3 new opportunities found",
                ],
            ),
        ]

    async def create(self, goal_description: str) -> DynamicAgent | None:
        """Design and return a new agent from a natural language goal."""
        console.print(f"[cyan]🏭 Designing agent: {goal_description[:60]}[/cyan]")

        raw = ai_tools.think(
            system_addon=AGENT_DESIGNER_PROMPT,
            user_prompt=f"Design an agent for this goal: {goal_description}",
            max_tokens=500,
        )

        try:
            m = re.search(r'\\{.*?\\}', raw, re.DOTALL)
            spec = json.loads(m.group()) if m else None
            if not spec:
                return None

            agent = DynamicAgent(
                name             = spec.get("name", "custom_agent"),
                goal             = spec.get("goal", goal_description),
                tools            = spec.get("tools", ["search_web"]),
                schedule_minutes = int(spec.get("schedule_minutes", 60)),
                strategy         = spec.get("strategy", ["Execute the goal"]),
            )
            self._agents.append(agent)
            console.print(f"[green]✅ Created: {agent}[/green]")
            return agent

        except Exception as e:
            console.print(f"[red]AgentFactory error: {e}[/red]")
            return None

    def get_agents(self) -> list[DynamicAgent]:
        return self._agents

    def get_agent(self, name: str) -> DynamicAgent | None:
        return next((a for a in self._agents if a.name == name), None)

    def list_summary(self) -> str:
        if not self._agents:
            return "No agents registered."
        lines = [
            f"• *{a.name}* — {a.goal[:60]}\
"
            f"  Every {a.schedule_minutes}m | Runs: {a._run_count} | "
            f"{'▶️' if a._enabled else '⏸'}"
            for a in self._agents
        ]
        return "\
\
".join(lines)

    async def tick(self, brain) -> list[str]:
        """Called each brain cycle — runs any due agents."""
        reports = []
        for agent in self._agents:
            if agent.is_due():
                try:
                    report = await agent.run(brain)
                    reports.append(report)
                except Exception as e:
                    reports.append(f"{agent.name}: error — {e}")
                await asyncio.sleep(2)
        return reports
