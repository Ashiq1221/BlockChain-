"""
Simple menu for non-coders.
Just run: python menu.py
"""
import asyncio
import os
import sys

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("""
╔══════════════════════════════════════╗
║    TELEGRAM AI AGENT SYSTEM          ║
║    All 10 Agents — Just Pick One     ║
╚══════════════════════════════════════╝
""")

def menu():
    print("What do you want to do?\n")
    print("  1.  Find & join relevant groups")
    print("  2.  Hunt jobs & apply automatically")
    print("  3.  Send DMs to people")
    print("  4.  Post content in groups")
    print("  5.  Collect contacts from groups")
    print("  6.  Watch groups for keywords")
    print("  7.  Auto-reply to incoming messages (1 hour)")
    print("  8.  Show analytics & stats")
    print("  9.  Create a strategy plan")
    print("  10. Let AI decide everything (type your goal)")
    print("  0.  Exit")
    print()

async def run_agent(choice, goal=""):
    from pyrogram import Client
    from dotenv import load_dotenv
    load_dotenv()

    from telegram_agents.database import Database
    from telegram_agents.config import Config
    from telegram_agents.agents.group_discovery import GroupDiscoveryAgent
    from telegram_agents.agents.job_hunter import JobHunterAgent
    from telegram_agents.agents.dm_agent import DMAgent
    from telegram_agents.agents.content_agent import ContentAgent
    from telegram_agents.agents.network_agent import NetworkAgent
    from telegram_agents.agents.monitor_agent import MonitorAgent
    from telegram_agents.agents.responder_agent import ResponderAgent
    from telegram_agents.agents.analytics_agent import AnalyticsAgent
    from telegram_agents.agents.strategy_agent import StrategyAgent
    from telegram_agents.agents.commander import CommanderAgent

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
            "monitor":         MonitorAgent(client, db),
            "responder":       ResponderAgent(client, db),
            "analytics":       AnalyticsAgent(client, db),
            "strategy":        StrategyAgent(client, db),
            "commander":       CommanderAgent(client, db),
        }

        if choice == "1":
            topics = input("What topics? (e.g. blockchain, python, jobs) : ").strip()
            topics_list = [t.strip() for t in topics.split(",")] if topics else None
            await agents["group_discovery"].run(topics=topics_list)

        elif choice == "2":
            print("Scanning groups and web for jobs, then applying...")
            await agents["job_hunter"].run(apply=True)

        elif choice == "3":
            goal_text = input("What should the DM say / goal? : ").strip()
            max_s = input("How many DMs max? (press Enter for 10) : ").strip()
            max_s = int(max_s) if max_s.isdigit() else 10
            await agents["dm"].run(goal=goal_text, max_send=max_s)

        elif choice == "4":
            topic = input("What do you want to post about? : ").strip()
            await agents["content"].run(topic=topic)

        elif choice == "5":
            print("Harvesting contacts from all joined groups...")
            await agents["network"].run()

        elif choice == "6":
            kw = input("Keywords to watch (comma separated): ").strip()
            dur = input("How long in minutes? (press Enter for 10) : ").strip()
            dur_sec = int(dur) * 60 if dur.isdigit() else 600
            keywords = [k.strip() for k in kw.split(",") if k.strip()]
            await agents["monitor"].run(keywords=keywords, duration_seconds=dur_sec)

        elif choice == "7":
            print("Auto-reply active for 1 hour. Keep this window open...")
            await agents["responder"].run(duration_seconds=3600)

        elif choice == "8":
            await agents["analytics"].run()

        elif choice == "9":
            goal_text = input("What is your goal? (e.g. find a job in 2 weeks): ").strip()
            await agents["strategy"].run(goal=goal_text)

        elif choice == "10":
            goal_text = input("Tell me what you want (in plain English): ").strip()
            all_agents = {k: v for k, v in agents.items() if k != "commander"}
            await agents["commander"].run(goal=goal_text, agent_registry=all_agents)

    await db.close()


def main():
    clear()
    banner()

    # Check .env exists
    if not os.path.exists(".env"):
        print("⚠️  .env file not found!")
        print("Create a .env file with your credentials first.")
        print("See README.md for instructions.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    while True:
        menu()
        choice = input("Enter number: ").strip()

        if choice == "0":
            print("\nGoodbye!")
            break

        if choice not in [str(i) for i in range(1, 11)]:
            print("Invalid choice. Try again.\n")
            continue

        print("\nStarting... (Telegram may ask for a code the first time)\n")
        try:
            asyncio.run(run_agent(choice))
        except KeyboardInterrupt:
            print("\nStopped.")
        except Exception as e:
            print(f"\nError: {e}")

        input("\nPress Enter to go back to menu...")
        clear()
        banner()


if __name__ == "__main__":
    main()
