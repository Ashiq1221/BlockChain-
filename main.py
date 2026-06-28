"""
Telegram Autonomous Agent System
10 AI agents, all powered by Claude, managing your Telegram account.

Usage:
  python main.py                          # Interactive mode
  python main.py --goal "find blockchain jobs and apply"
  python main.py --agent group_discovery --topics "python developer,remote"
  python main.py --agent job_hunter
  python main.py --agent dm --goal "introduce myself to developers"
  python main.py --agent content --topic "I am available for freelance work"
  python main.py --agent network
  python main.py --agent monitor --keywords "hiring,job,developer" --duration 600
  python main.py --agent responder --duration 3600
  python main.py --agent analytics
  python main.py --agent strategy --goal "land a remote job in 2 weeks"
  python main.py --agent brief
"""
import asyncio
import argparse
import sys
from pyrogram import Client
from rich.console import Console
from rich.panel import Panel
from telegram_agents.config import Config
from telegram_agents.database import Database

from telegram_agents.agents.commander import CommanderAgent
from telegram_agents.agents.group_discovery import GroupDiscoveryAgent
from telegram_agents.agents.job_hunter import JobHunterAgent
from telegram_agents.agents.dm_agent import DMAgent
from telegram_agents.agents.content_agent import ContentAgent
from telegram_agents.agents.network_agent import NetworkAgent
from telegram_agents.agents.monitor_agent import MonitorAgent
from telegram_agents.agents.responder_agent import ResponderAgent
from telegram_agents.agents.analytics_agent import AnalyticsAgent
from telegram_agents.agents.strategy_agent import StrategyAgent

console = Console()

BANNER = """
[bold cyan]
╔══════════════════════════════════════════════════════════╗
║        TELEGRAM AUTONOMOUS AI AGENT SYSTEM v1.0          ║
║              10 Agents · Powered by Claude               ║
╚══════════════════════════════════════════════════════════╝
[/bold cyan]
"""

AGENTS_INFO = [
    ("🧠", "Commander",      "Orchestrates all agents via natural language"),
    ("🔍", "GroupDiscovery", "Finds & joins relevant Telegram groups"),
    ("💼", "JobHunter",      "Scans for jobs and sends applications"),
    ("✉️",  "DMAgent",        "Targeted personalized DM campaigns"),
    ("📝", "ContentAgent",   "Creates & posts content in groups"),
    ("🕸️",  "NetworkAgent",   "Harvests and tags contacts from groups"),
    ("👁️",  "MonitorAgent",   "Watches groups for keywords in real-time"),
    ("💬", "ResponderAgent", "Auto-replies to DMs and mentions"),
    ("📊", "AnalyticsAgent", "Reports metrics and AI-generated insights"),
    ("♟️",  "StrategyAgent",  "Plans long-term campaigns and daily briefs"),
]


def validate_config():
    errors = []
    if not Config.API_ID or Config.API_ID == 0:
        errors.append("TELEGRAM_API_ID is not set")
    if not Config.API_HASH:
        errors.append("TELEGRAM_API_HASH is not set")
    if not Config.PHONE:
        errors.append("TELEGRAM_PHONE is not set")
    if not Config.ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is not set")
    if errors:
        console.print("[red]Configuration errors:[/red]")
        for e in errors:
            console.print(f"  [red]✗[/red] {e}")
        console.print("\n[yellow]Copy .env.example to .env and fill in your credentials.[/yellow]")
        sys.exit(1)


async def run(args):
    validate_config()
    console.print(BANNER)

    # Print agent roster
    table_rows = "\n".join(f"  {e}  {name:<16} — {desc}" for e, name, desc in AGENTS_INFO)
    console.print(Panel(table_rows, title="[bold]Agent Roster[/bold]", border_style="cyan"))

    db = Database()
    await db.connect()

    async with Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    ) as client:

        # Instantiate all 10 agents
        agents = {
            "commander":      CommanderAgent(client, db),
            "group_discovery": GroupDiscoveryAgent(client, db),
            "job_hunter":     JobHunterAgent(client, db),
            "dm":             DMAgent(client, db),
            "content":        ContentAgent(client, db),
            "network":        NetworkAgent(client, db),
            "monitor":        MonitorAgent(client, db),
            "responder":      ResponderAgent(client, db),
            "analytics":      AnalyticsAgent(client, db),
            "strategy":       StrategyAgent(client, db),
        }

        agent_name = args.agent.lower() if args.agent else None

        if agent_name == "commander" or (args.goal and not agent_name):
            await agents["commander"].run(
                goal=args.goal or await agents["commander"].interpret_command(
                    input("[bold cyan]What do you want? [/bold cyan]> ")
                ),
                agent_registry={k: v for k, v in agents.items() if k != "commander"},
            )

        elif agent_name == "group_discovery":
            topics = args.topics.split(",") if args.topics else None
            await agents["group_discovery"].run(goal=args.goal or "", topics=topics)

        elif agent_name == "job_hunter":
            await agents["job_hunter"].run(goal=args.goal or "", apply=not args.dry_run)

        elif agent_name == "dm":
            ids = [int(x) for x in args.user_ids.split(",")] if args.user_ids else None
            await agents["dm"].run(
                goal=args.goal or "",
                target_user_ids=ids,
                tags_filter=args.tags,
                max_send=args.max_send,
            )

        elif agent_name == "content":
            await agents["content"].run(
                goal=args.goal or "",
                topic=args.topic,
                post_to_all=args.all_groups,
            )

        elif agent_name == "network":
            tags = args.tags.split(",") if args.tags else None
            await agents["network"].run(goal=args.goal or "", tags=tags)

        elif agent_name == "monitor":
            keywords = args.keywords.split(",") if args.keywords else None
            await agents["monitor"].run(
                goal=args.goal or "",
                keywords=keywords,
                duration_seconds=args.duration,
            )

        elif agent_name == "responder":
            await agents["responder"].run(
                goal=args.goal or "",
                duration_seconds=args.duration,
                respond_to_groups=args.groups,
            )

        elif agent_name == "analytics":
            await agents["analytics"].run(goal=args.goal or "")

        elif agent_name == "strategy":
            await agents["strategy"].run(
                goal=args.goal or "",
                timeframe=args.timeframe or "2 weeks",
            )

        elif agent_name == "brief":
            await agents["strategy"].daily_brief()

        elif agent_name == "full":
            # Run the full pipeline sequentially
            console.print("[bold green]Running full pipeline...[/bold green]")
            await agents["group_discovery"].run(goal=args.goal or "")
            await agents["network"].run(goal=args.goal or "")
            await agents["job_hunter"].run(goal=args.goal or "", apply=not args.dry_run)
            await agents["analytics"].run()

        else:
            # Interactive mode
            console.print("[yellow]No agent specified. Entering interactive mode.[/yellow]")
            while True:
                try:
                    user_input = input("\n[You] > ").strip()
                    if user_input.lower() in ("exit", "quit", "q"):
                        break
                    if not user_input:
                        continue
                    await agents["commander"].run(
                        goal=user_input,
                        agent_registry={k: v for k, v in agents.items() if k != "commander"},
                    )
                except (KeyboardInterrupt, EOFError):
                    break

    await db.close()
    console.print("\n[bold green]All agents finished. Session closed.[/bold green]")


def main():
    parser = argparse.ArgumentParser(
        description="Telegram Autonomous AI Agent System — 10 agents powered by Claude"
    )
    parser.add_argument("--agent", help="Agent to run: commander|group_discovery|job_hunter|dm|content|network|monitor|responder|analytics|strategy|brief|full")
    parser.add_argument("--goal", help="Natural language goal")
    parser.add_argument("--topic", help="Content topic")
    parser.add_argument("--topics", help="Comma-separated topics for group discovery")
    parser.add_argument("--keywords", help="Comma-separated keywords to monitor")
    parser.add_argument("--tags", help="Contact tags filter")
    parser.add_argument("--user-ids", help="Comma-separated Telegram user IDs for DM")
    parser.add_argument("--timeframe", default="2 weeks", help="Strategy timeframe")
    parser.add_argument("--duration", type=int, default=300, help="Monitor/responder duration in seconds")
    parser.add_argument("--max-send", type=int, help="Max DMs to send")
    parser.add_argument("--all-groups", action="store_true", help="Post to all joined groups")
    parser.add_argument("--groups", action="store_true", help="Also respond to group mentions")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without sending messages")

    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
