"""
1000 IQ Agent Brain — True Agentic Loop
Reason → Plan → Act → Observe → Reflect → Learn → Adapt → Repeat
"""
import asyncio
import json
import re
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from telegram_agents.tools import ai_tools
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database

console = Console()


MASTER_GOAL = """
You are managing a Telegram account for a professional seeking to:
1. Find and join the most relevant groups (blockchain, Python, remote jobs, tech)
2. Find remote job opportunities and send compelling applications
3. Build a strong professional network by connecting with the right people
4. Post valuable content to build reputation and attract opportunities
5. Respond to all incoming messages intelligently to build relationships
6. Never stop — always find new opportunities and act on them
Be aggressive, smart, and strategic. Maximize every opportunity.
"""


class AgentBrain:
    def __init__(self, tools: ToolRegistry, db: Database, memory: Memory):
        self.tools = tools
        self.db = db
        self.memory = memory
        self.cycle = 0
        self.action_history: list[str] = []

    # ── STEP 1: OBSERVE ──────────────────────────────────────────────────────

    async def observe(self) -> str:
        """Collect current world state."""
        stats = await self.db.get_stats()
        groups = await self.db.get_groups(joined=True)
        jobs = await self.db.get_jobs(applied=False)
        contacts = await self.db.get_contacts()
        inbox = await self.tools.get_inbox()
        best_strategies = await self.memory.best_strategies()

        return f"""
CURRENT STATE (Cycle {self.cycle}):
- Groups joined: {len(groups)} | Total discovered: {stats.get('groups', 0)}
- Contacts indexed: {len(contacts)}
- Jobs found: {stats.get('jobs', 0)} | Applied: {stats.get('jobs_applied', 0)} | Pending: {len(jobs)}
- Messages sent: {stats.get('messages_sent', 0)}
- Unread conversations: {len(inbox)}
- Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}

WHAT HAS WORKED BEFORE:
{best_strategies}

RECENT ACTIONS:
{chr(10).join(self.action_history[-5:]) or 'None yet'}
""".strip()

    # ── STEP 2: THINK ────────────────────────────────────────────────────────

    def think(self, observation: str) -> str:
        """Deep chain-of-thought reasoning about what to do."""
        return ai_tools.think(
            system_addon="""You are a 1000 IQ autonomous agent managing a Telegram account.
Think deeply about the current situation. Reason step by step.
Consider: What is the biggest opportunity right now? What's been neglected?
What sequence of actions will have the most impact?
Be strategic, not random. Think like a chess grandmaster.
Write your reasoning as a paragraph, then end with: CONCLUSION: [your decision]""",
            user_prompt=f"""MASTER GOAL:
{MASTER_GOAL}

OBSERVATION:
{observation}

AVAILABLE TOOLS:
{self.tools.descriptions}

Think carefully and reason about the best course of action right now:""",
            max_tokens=800,
        )

    # ── STEP 3: PLAN ─────────────────────────────────────────────────────────

    def plan(self, thought: str, observation: str) -> list[dict]:
        """Convert thought into a concrete action plan with tool calls."""
        raw = ai_tools.think(
            system_addon="""You are a planning agent. Convert reasoning into a JSON action plan.
Return ONLY a JSON array. Each item must have:
{
  "step": 1,
  "reason": "why this step",
  "tool": "tool_name",
  "args": {"param": "value"}
}
Use ONLY tools from the available list. Be specific with args.
Max 5 steps. Think about dependencies between steps.""",
            user_prompt=f"""REASONING:
{thought}

OBSERVATION:
{observation}

AVAILABLE TOOLS:
{self.tools.descriptions}

Return JSON action plan:""",
            max_tokens=1200,
        )

        # Parse JSON plan
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            try:
                steps = json.loads(match.group())
                return [s for s in steps if isinstance(s, dict) and "tool" in s]
            except Exception:
                pass

        # Fallback plan if JSON parsing fails
        return [
            {"step": 1, "reason": "Discover new opportunities", "tool": "get_stats", "args": {}},
            {"step": 2, "reason": "Find relevant groups", "tool": "find_tg_groups_web", "args": {"topic": "blockchain developer jobs remote"}},
        ]

    # ── STEP 4: ACT ──────────────────────────────────────────────────────────

    async def act(self, plan: list[dict]) -> list[dict]:
        """Execute the plan step by step, observing results."""
        results = []
        for step in plan:
            tool = step.get("tool", "")
            args = step.get("args", {})
            reason = step.get("reason", "")

            console.print(f"  [cyan]▶ Step {step.get('step','')}[/cyan] [{tool}] — {reason}")

            result = await self.tools.call(tool, **args)
            results.append({"step": step, "result": result})

            # Log action
            self.action_history.append(
                f"[{datetime.now().strftime('%H:%M')}] {tool}({args}) → {'✅' if result.get('ok') else '❌'}"
            )

            # Brief summary
            if result.get("ok"):
                r = result.get("result")
                if isinstance(r, list):
                    console.print(f"    [green]✅ Got {len(r)} results[/green]")
                elif isinstance(r, dict):
                    console.print(f"    [green]✅ {json.dumps(r)[:80]}[/green]")
                else:
                    console.print(f"    [green]✅ {str(r)[:80]}[/green]")
            else:
                console.print(f"    [red]❌ {result.get('error','unknown error')}[/red]")

            # Small delay between actions
            await asyncio.sleep(2)

        return results

    # ── STEP 5: REFLECT ──────────────────────────────────────────────────────

    async def reflect(self, observation: str, plan: list[dict], results: list[dict]) -> str:
        """Critically analyze what happened and extract learnings."""
        results_summary = json.dumps([
            {
                "tool": r["step"]["tool"],
                "args": r["step"]["args"],
                "success": r["result"].get("ok", False),
                "result_size": len(r["result"].get("result", [])) if isinstance(r["result"].get("result"), list) else 1,
            }
            for r in results
        ], indent=2)

        reflection = ai_tools.think(
            system_addon="""You are a self-reflective AI agent. Analyze what just happened critically.
Answer:
1. What worked well? (be specific)
2. What failed or underperformed?
3. What should be done differently next cycle?
4. What is the single most important next action?
5. Score this cycle 1-10 and explain why.
Be brutally honest. The goal is continuous improvement.""",
            user_prompt=f"""MASTER GOAL: {MASTER_GOAL}

STATE BEFORE: {observation[:500]}

PLAN EXECUTED:
{json.dumps([s['step'] for s in results], indent=2)[:500]}

RESULTS:
{results_summary}

Reflect and learn:""",
            max_tokens=600,
        )
        return reflection

    # ── STEP 6: LEARN ────────────────────────────────────────────────────────

    async def learn(self, reflection: str, results: list[dict]):
        """Update memory with what worked and what didn't."""
        # Score successful tools positively
        for r in results:
            tool = r["step"]["tool"]
            success = r["result"].get("ok", False)
            result_value = r["result"].get("result")
            has_data = bool(result_value) and (
                not isinstance(result_value, list) or len(result_value) > 0
            )
            score = 1.0 if (success and has_data) else -0.5

            await self.memory.remember(
                key=f"tool_{tool}_cycle{self.cycle}",
                value=f"Tool {tool} in cycle {self.cycle}: {'success' if success else 'failed'}",
                memory_type="tool_performance",
                score=score,
            )

        # Extract and store strategic insights from reflection
        insight = ai_tools.think(
            system_addon="Extract ONE key strategic insight as a single sentence. Start with an action verb.",
            user_prompt=f"Reflection:\n{reflection}\n\nKey insight:",
            max_tokens=80,
        )
        await self.memory.remember(
            key=f"strategy_cycle{self.cycle}",
            value=insight,
            memory_type="strategy",
            score=0,
        )

    # ── STEP 7: HANDLE INBOX ─────────────────────────────────────────────────

    async def handle_inbox(self):
        """Autonomously respond to any pending conversations."""
        try:
            inbox = await self.tools.get_inbox()
            if not inbox:
                return

            console.print(f"  [yellow]📬 {len(inbox)} unread conversation(s)[/yellow]")
            for chat in inbox[:5]:
                chat_id = chat.get("chat_id")
                top_msg = chat.get("top_message", "")
                if not top_msg or not chat_id:
                    continue

                # Compose intelligent reply
                reply = ai_tools.smart_reply(
                    incoming=top_msg,
                    conversation_history="",
                    goal=MASTER_GOAL,
                )
                await self.tools.reply_to_dm(user_id=chat_id, text=reply)
                console.print(f"  [green]💬 Replied to chat {chat_id}[/green]")
                await asyncio.sleep(3)
        except Exception as e:
            console.print(f"  [red]Inbox error: {e}[/red]")

    # ── MAIN AGENTIC LOOP ────────────────────────────────────────────────────

    async def run_forever(self):
        console.print(Panel(
            "[bold magenta]1000 IQ AUTONOMOUS AGENT — ONLINE[/bold magenta]\n"
            "[white]Reason → Plan → Act → Observe → Reflect → Learn → Adapt[/white]\n"
            "[dim]True agentic intelligence. Runs forever. Zero human input.[/dim]",
            border_style="magenta",
        ))

        while True:
            self.cycle += 1
            console.print(Rule(f"[bold]CYCLE {self.cycle} — {datetime.now().strftime('%H:%M:%S')}[/bold]"))

            try:
                # 1. OBSERVE — what's the current state?
                console.print("[dim]👁  Observing...[/dim]")
                observation = await self.observe()

                # 2. THINK — reason deeply about what to do
                console.print("[dim]🧠 Thinking...[/dim]")
                thought = self.think(observation)
                console.print(f"[dim italic]{thought[:300]}...[/dim italic]")

                # 3. PLAN — turn thought into concrete tool calls
                console.print("[dim]📋 Planning...[/dim]")
                plan = self.plan(thought, observation)
                console.print(f"[dim]Plan: {len(plan)} steps[/dim]")

                # 4. ACT — execute the plan
                console.print("[cyan]⚡ Acting...[/cyan]")
                results = await self.act(plan)

                # 5. HANDLE INBOX — reply to people
                console.print("[dim]📬 Checking inbox...[/dim]")
                await self.handle_inbox()

                # 6. REFLECT — critically analyze what happened
                console.print("[dim]🪞 Reflecting...[/dim]")
                reflection = await self.reflect(observation, plan, results)
                console.print(f"[dim italic]{reflection[:200]}...[/dim italic]")

                # 7. LEARN — store insights in memory
                console.print("[dim]💾 Learning...[/dim]")
                await self.learn(reflection, results)

                # 8. ADAPT — decide how long to sleep before next cycle
                sleep_minutes = await self._decide_sleep(reflection, results)
                console.print(f"[dim]😴 Next cycle in {sleep_minutes} min[/dim]")
                await asyncio.sleep(sleep_minutes * 60)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                console.print(f"[red]Cycle error: {e} — retrying in 5 min[/red]")
                await asyncio.sleep(300)

    async def _decide_sleep(self, reflection: str, results: list[dict]) -> int:
        """AI decides how long to wait before next cycle."""
        successes = sum(1 for r in results if r["result"].get("ok"))
        total = len(results)
        raw = ai_tools.think(
            system_addon="Decide sleep time in minutes (5-45). Reply with ONLY the number.",
            user_prompt=f"Cycle had {successes}/{total} successes. Reflection: {reflection[:100]}\nSleep minutes:",
            max_tokens=5,
        )
        try:
            return max(5, min(45, int("".join(filter(str.isdigit, raw)) or "20")))
        except Exception:
            return 20
