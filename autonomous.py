"""
FULLY AUTONOMOUS TELEGRAM AI — 500 IQ MODE
Just run: python autonomous.py
It never stops. It thinks, plans, and acts on its own — forever.
"""
import asyncio, os, sys, time, json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Auto-install ──────────────────────────────────────────────────────────────
import subprocess
PKGS = ["pyrogram==2.0.106","TgCrypto","httpx","aiohttp","aiosqlite",
        "python-dotenv","rich","aiofiles","beautifulsoup4"]
for pkg in PKGS:
    try: __import__(pkg.split("==")[0].replace("-","_"))
    except ImportError:
        subprocess.call([sys.executable,"-m","pip","install",pkg,"-q"],
                        stderr=subprocess.DEVNULL)

from rich.console import Console
from rich.panel import Panel
from pyrogram import Client
from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools import ai_tools
from telegram_agents.agents.group_discovery  import GroupDiscoveryAgent
from telegram_agents.agents.job_hunter       import JobHunterAgent
from telegram_agents.agents.dm_agent         import DMAgent
from telegram_agents.agents.content_agent    import ContentAgent
from telegram_agents.agents.network_agent    import NetworkAgent
from telegram_agents.agents.monitor_agent    import MonitorAgent
from telegram_agents.agents.responder_agent  import ResponderAgent
from telegram_agents.agents.analytics_agent  import AnalyticsAgent
from telegram_agents.agents.strategy_agent   import StrategyAgent

console = Console()

# ── Master goal — edit this to change what the AI works toward ────────────────
MASTER_GOAL = """
I am a professional looking to:
1. Find remote blockchain/Python developer jobs and apply to them
2. Build a strong professional network on Telegram
3. Join the most relevant tech/crypto/jobs groups
4. Post valuable content to establish credibility
5. Respond to all incoming messages intelligently
Maximize all opportunities. Be proactive. Never stop working.
"""

# ── How often each agent runs (in minutes) ────────────────────────────────────
SCHEDULE = {
    "group_discovery": 120,   # every 2 hours — find new groups
    "network":         90,    # every 1.5 hours — harvest contacts
    "job_hunter":      60,    # every hour — hunt & apply to jobs
    "content":         180,   # every 3 hours — post content
    "dm":              120,   # every 2 hours — outreach DMs
    "analytics":       240,   # every 4 hours — report stats
    "strategy":        480,   # every 8 hours — re-plan
}

last_run: dict[str, float] = {}


def should_run(name: str) -> bool:
    interval = SCHEDULE.get(name, 60) * 60
    last = last_run.get(name, 0)
    return (time.time() - last) >= interval


def mark_ran(name: str):
    last_run[name] = time.time()


def log(msg: str, style: str = "cyan"):
    ts = datetime.now().strftime("%H:%M:%S")
    console.print(f"[dim]{ts}[/dim] [{style}]{msg}[/{style}]")


async def brain_decide(db: Database, agents: dict) -> list[str]:
    """AI decides which agents to run RIGHT NOW based on current state."""
    stats = await db.get_stats()
    pending_jobs = await db.get_jobs(applied=False)
    groups_joined = len(await db.get_groups(joined=True))
    contacts = len(await db.get_contacts())

    context = (
        f"Groups joined: {groups_joined} | "
        f"Contacts: {contacts} | "
        f"Jobs found: {stats.get('jobs',0)} | "
        f"Applied: {stats.get('jobs_applied',0)} | "
        f"Messages sent: {stats.get('messages_sent',0)} | "
        f"Unapplied jobs: {len(pending_jobs)}"
    )

    decision = ai_tools.think(
        system_addon="""You are the master brain of a Telegram automation system.
Decide which agents to run right now. Reply with ONLY a comma-separated list of agent names.
Available agents: group_discovery, network, job_hunter, content, dm, analytics, strategy
Rules:
- If groups_joined < 10: always include group_discovery
- If contacts < 50: always include network
- If unapplied jobs > 0: always include job_hunter
- If messages_sent < 5: always include dm
- Pick 2-4 agents max per cycle to avoid spam
Reply format: agent1, agent2, agent3""",
        user_prompt=f"Master goal: {MASTER_GOAL}\n\nCurrent state: {context}\n\nWhich agents should run now?",
        max_tokens=100,
    )

    chosen = [a.strip() for a in decision.split(",") if a.strip() in agents]
    if not chosen:
        chosen = ["group_discovery", "job_hunter"]
    return chosen


async def run_autonomous():
    console.print(Panel(
        "[bold cyan]AUTONOMOUS TELEGRAM AI — 500 IQ MODE[/bold cyan]\n"
        "[white]Running forever. Making its own decisions. Never stopping.[/white]\n"
        "[dim]Press Ctrl+C to stop.[/dim]",
        border_style="cyan"
    ))

    db = Database()
    await db.connect()

    async with Client(
        Config.SESSION_NAME,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        phone_number=Config.PHONE,
    ) as client:

        agents = {
            "group_discovery": GroupDiscoveryAgent(client, db),
            "job_hunter":      JobHunterAgent(client, db),
            "dm":              DMAgent(client, db),
            "content":         ContentAgent(client, db),
            "network":         NetworkAgent(client, db),
            "analytics":       AnalyticsAgent(client, db),
            "strategy":        StrategyAgent(client, db),
        }

        # Responder runs in background — always listening
        responder = ResponderAgent(client, db)

        log("🧠 AI Brain is online. Thinking...", "bold green")

        # Initial strategy
        strategy = agents["strategy"]
        log("♟️  Generating master strategy...", "yellow")
        await strategy.run(goal=MASTER_GOAL, timeframe="ongoing")
        mark_ran("strategy")

        # Run responder as background task (always-on auto-reply)
        async def keep_responding():
            while True:
                try:
                    await responder.run(
                        goal="Respond helpfully, build relationships, advance career and business goals.",
                        duration_seconds=3600,
                    )
                except Exception as e:
                    log(f"Responder restarting: {e}", "yellow")
                await asyncio.sleep(5)

        asyncio.create_task(keep_responding())
        log("💬 Auto-responder is ON (replying to all incoming DMs)", "green")

        cycle = 0
        while True:
            cycle += 1
            log(f"\n━━━ CYCLE {cycle} ━━━ {datetime.now().strftime('%Y-%m-%d %H:%M')}", "bold white")

            # Brain decides what to do
            chosen = await brain_decide(db, agents)
            log(f"🧠 Brain chose: {', '.join(chosen)}", "magenta")

            # Run chosen agents
            for name in chosen:
                if name not in agents:
                    continue

                # Also respect schedule to avoid running too often
                if not should_run(name):
                    next_in = int((SCHEDULE[name]*60 - (time.time()-last_run.get(name,0))) / 60)
                    log(f"⏳ {name} — next run in {next_in} min", "dim")
                    continue

                log(f"▶️  Running {name}...", "cyan")
                try:
                    agent = agents[name]
                    if name == "group_discovery":
                        await agent.run(goal=MASTER_GOAL, join=True)
                    elif name == "job_hunter":
                        await agent.run(goal=MASTER_GOAL, apply=True)
                    elif name == "dm":
                        await agent.run(goal=MASTER_GOAL, max_send=Config.MAX_DM_PER_HOUR)
                    elif name == "content":
                        topic = ai_tools.think(
                            "Pick ONE content topic that fits the master goal. 5 words max.",
                            f"Goal: {MASTER_GOAL}\nPick a topic:",
                            max_tokens=20,
                        )
                        await agent.run(goal=MASTER_GOAL, topic=topic)
                    elif name == "network":
                        await agent.run(goal=MASTER_GOAL)
                    elif name == "analytics":
                        await agent.run(goal=MASTER_GOAL)
                    elif name == "strategy":
                        await agent.run(goal=MASTER_GOAL, timeframe="ongoing")
                    mark_ran(name)
                    log(f"✅ {name} done", "green")
                except Exception as e:
                    log(f"❌ {name} error: {e}", "red")

            # AI decides how long to sleep before next cycle
            sleep_decision = ai_tools.think(
                "You decide sleep duration in minutes between automation cycles. Reply with ONLY a number between 15 and 60.",
                f"State: cycle {cycle}, agents ran: {chosen}. How many minutes to sleep?",
                max_tokens=5,
            )
            try:
                sleep_min = max(15, min(60, int("".join(filter(str.isdigit, sleep_decision)) or "30")))
            except Exception:
                sleep_min = 30

            log(f"😴 Sleeping {sleep_min} min before next cycle...", "dim")
            await asyncio.sleep(sleep_min * 60)

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(run_autonomous())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped by user.[/yellow]")
