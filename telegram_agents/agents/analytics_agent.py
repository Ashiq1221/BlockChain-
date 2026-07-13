"""
Agent 9 — Analytics Agent
Tracks all activity metrics, generates performance reports,
and surfaces actionable insights using Claude.
"""
from datetime import datetime
from rich.table import Table
from rich.console import Console
from telegram_agents.base_agent import BaseAgent
from telegram_agents.tools import ai_tools

console = Console()


class AnalyticsAgent(BaseAgent):
    name = "AnalyticsAgent"
    emoji = "📊"

    async def run(self, goal: str = "", report: bool = True, **kwargs):
        stats = await self.db.get_stats()
        tasks = await self.db.get_tasks()
        groups = await self.db.get_groups()
        jobs = await self.db.get_jobs()
        contacts = await self.db.get_contacts()

        if report:
            self._print_dashboard(stats, tasks, groups, jobs, contacts)

        # AI-generated insights
        summary = self._build_summary(stats, tasks)
        insights = ai_tools.think(
            system_addon="You are a data analyst. Generate 3-5 concise, actionable insights from Telegram automation performance data.",
            user_prompt=f"Performance data:\n{summary}\n\nGoal: {goal or 'Maximize Telegram outreach and opportunities'}\n\nInsights:",
            max_tokens=600,
        )
        self.log(f"[bold]AI Insights:[/bold]\n{insights}")
        await self.db.log_event("analytics_report", {"stats": stats, "insights": insights})
        return {"stats": stats, "insights": insights}

    def _build_summary(self, stats: dict, tasks: list) -> str:
        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")
        return (
            f"Groups discovered: {stats.get('groups', 0)}\n"
            f"Contacts indexed: {stats.get('contacts', 0)}\n"
            f"Jobs found: {stats.get('jobs', 0)}\n"
            f"Jobs applied: {stats.get('jobs_applied', 0)}\n"
            f"Messages sent: {stats.get('messages_sent', 0)}\n"
            f"Tasks completed: {completed} | Pending: {pending}"
        )

    def _print_dashboard(self, stats, tasks, groups, jobs, contacts):
        table = Table(title=f"[bold cyan]Telegram Agent Dashboard[/bold cyan]  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white", justify="right")

        table.add_row("Groups discovered", str(stats.get("groups", 0)))
        table.add_row("Groups joined", str(sum(1 for g in groups if g.get("joined"))))
        table.add_row("Contacts indexed", str(stats.get("contacts", 0)))
        table.add_row("Jobs found", str(stats.get("jobs", 0)))
        table.add_row("Jobs applied", str(stats.get("jobs_applied", 0)))
        table.add_row("Messages sent (out)", str(stats.get("messages_sent", 0)))
        table.add_row("Total messages", str(stats.get("messages", 0)))
        table.add_row("Tasks completed", str(sum(1 for t in tasks if t["status"] == "completed")))

        console.print(table)

        # Top groups
        if groups:
            g_table = Table(title="Top Groups")
            g_table.add_column("Title"); g_table.add_column("Category"); g_table.add_column("Members", justify="right"); g_table.add_column("Joined")
            for g in sorted(groups, key=lambda x: x.get("members", 0), reverse=True)[:10]:
                g_table.add_row(g["title"][:40], g.get("category","?"), str(g.get("members",0)), "✅" if g.get("joined") else "—")
            console.print(g_table)

        # Recent jobs
        if jobs:
            j_table = Table(title="Jobs")
            j_table.add_column("Title"); j_table.add_column("Company"); j_table.add_column("Applied")
            for j in jobs[:10]:
                j_table.add_row(j["title"][:40], j.get("company","?")[:25], "✅" if j.get("applied") else "—")
            console.print(j_table)
