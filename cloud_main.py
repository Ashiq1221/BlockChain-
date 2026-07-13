"""
Full cloud autonomous bot — deploy to Railway (railway.app).

Pipeline (every 2nd cycle, 24/7):
  1. Discover Web3/AI projects hiring via X/Twitter + Tavily
  2. Find & join their Telegram group
  3. Read the room context
  4. Identify CEO / Founder (admin scan)
  5. Craft personalized DM using Ashiq's real stats
  6. Send DM via user account (Pyrogram StringSession)

Bot commands (send to your bot on Telegram):
  /execute — run the FULL pipeline now (most powerful)
  /hunt    — trigger one hunt+DM cycle right now
  /status  — show cycle stats and recent actions
  /pause   — pause autonomous mode
  /resume  — resume autonomous mode
  /dm @user message — manually send a DM via your account
  /search query — search for opportunities now
  /cycle N — change hunt frequency (1=every cycle)
  /debate question — all 5 AIs debate then synthesize the best answer
  any text — AI chat (race mode — fastest provider wins)

Required env vars:
  TELEGRAM_SESSION_STRING   ← from generate_session.py
  TELEGRAM_API_ID
  TELEGRAM_API_HASH
  TELEGRAM_BOT_TOKEN        ← reports to your Telegram
  TELEGRAM_OWNER_ID
  GROQ_API_KEY
  TAVILY_API_KEY
  GEMINI_API_KEY
"""
import asyncio
import json
import os
import sys
import subprocess

import aiohttp
from dotenv import load_dotenv

load_dotenv()

for pkg in ["pyrogram==2.0.106", "TgCrypto", "httpx", "aiohttp",
            "aiosqlite", "python-dotenv", "rich", "aiofiles", "beautifulsoup4"]:
    try:
        __import__(pkg.split("==")[0].replace("-", "_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

from pyrogram import Client
from rich.console import Console
from rich.panel import Panel

from telegram_agents.config import Config
from telegram_agents.database import Database
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.brain import AgentBrain
from telegram_agents.orchestra import Orchestra
from telegram_agents.tools import ai_tools, web_tools, telegram_tools

console = Console()

BOT_BASE     = f"https://api.telegram.org/bot{Config.BOT_TOKEN}"
OWNER_ID     = str(Config.OWNER_ID) if Config.OWNER_ID else ""
_BOT_TIMEOUT = aiohttp.ClientTimeout(total=15)

_brain:     AgentBrain | None = None
_orchestra: Orchestra  | None = None
_last_update_id = 0


# ─── Bot API helpers ──────────────────────────────────────────────────────────

async def _send(text: str, parse_mode: str = "Markdown"):
    if not Config.BOT_TOKEN or not OWNER_ID:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{BOT_BASE}/sendMessage",
                json={"chat_id": OWNER_ID, "text": text, "parse_mode": parse_mode},
                timeout=_BOT_TIMEOUT,
            )
    except Exception:
        pass


async def _get_updates(offset: int) -> list[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            r = await s.get(
                f"{BOT_BASE}/getUpdates",
                params={"offset": offset, "timeout": 25, "limit": 10},
                timeout=aiohttp.ClientTimeout(total=30),
            )
            if r.status == 200:
                return (await r.json()).get("result", [])
    except Exception:
        pass
    return []


# ─── Command handlers ─────────────────────────────────────────────────────────

async def _cmd_help():
    await _send(
        "*🤖 Ashiq's Autonomous Bot*\n\n"
        "*Commands:*\n"
        "`/execute` — ⚡ full pipeline (hunt + act + DM)\n"
        "`/hunt` — search + DM cycle\n"
        "`/agents` — list all running AI agents\n"
        "`/status` — stats & recent actions\n"
        "`/pause` / `/resume` — pause/resume autonomous mode\n"
        "`/dm @user msg` — send a DM\n"
        "`/search query` — search web\n"
        "`/cycle N` — hunt frequency (1=every cycle)\n"
        "`/debate question` — 5-AI debate then synthesize\n\n"
        "*Or just type any task in plain English:*\n"
        "• `post announcement about X in @channel`\n"
        "• `kick @spammer from @group`\n"
        "• `mute @user in @group`\n"
        "• `reply to message 123 in @group saying thanks`\n"
        "• `create content about DeFi trends`\n"
        "• `create an agent that posts daily news in @channel`\n"
        "• Any question → AI answers 🧠\n\n"
        "_Running 24/7 on Railway._"
    )


async def _cmd_status():
    if not _brain:
        await _send("Bot initialising, try again in a moment.")
        return
    obs  = await _brain.observe()
    mode = "⏸ PAUSED" if _brain._paused else "▶️ RUNNING"
    await _send(
        f"*Status — Cycle {_brain.cycle}* | {mode}\n"
        f"Hunt every: {_brain._hunt_every} cycles\n\n"
        f"```\n{obs[:600]}\n```"
    )


async def _cmd_hunt():
    if not _brain:
        await _send("Bot not ready yet.")
        return
    if _brain._paused:
        await _send("⚠️ Bot is paused. Send /resume first.")
        return
    await _send("🔍 Hunting now — I'll report back when done...")
    try:
        sent = await _brain.smart_hunt_cycle()
        await _send(f"✅ Hunt complete — *{sent} DMs sent* this cycle.")
    except Exception as e:
        await _send(f"❌ Hunt error: `{e}`")


async def _cmd_pause():
    if _brain:
        _brain._paused = True
    await _send("⏸ Autonomous mode paused. Send /resume to restart.")


async def _cmd_resume():
    if _brain:
        _brain._paused = False
    await _send("▶️ Autonomous mode resumed. Hunting continues.")


async def _cmd_dm(args: str):
    if not _brain:
        await _send("Bot not ready.")
        return
    parts = args.strip().split(" ", 1)
    if len(parts) < 2 or not parts[0].startswith("@"):
        await _send("Usage: `/dm @username Your message here`")
        return
    target  = parts[0].lstrip("@")
    message = parts[1].strip()
    r = await telegram_tools.send_dm(_brain.client, f"@{target}", message)
    if r:
        await _send(f"✅ DM sent to @{target}")
    else:
        await _send(f"❌ Could not DM @{target} — they may have DMs closed.")


async def _cmd_search(args: str):
    query = args.strip() or "web3 AI project hiring ambassador 2026"
    await _send(f"🔍 Searching: `{query}`...")
    results = await web_tools.web_search(query, num=6)
    if not results:
        await _send("No results found.")
        return
    lines = [
        f"• *{r.get('title', '')[:60]}*\n  {r.get('snippet', '')[:100]}\n  {r.get('url', '')}"
        for r in results[:5]
    ]
    await _send("*Search Results:*\n\n" + "\n\n".join(lines))


async def _cmd_cycle(args: str):
    if not _brain:
        await _send("Bot not ready.")
        return
    try:
        n = max(1, min(10, int(args.strip())))
        _brain._hunt_every = n
        await _send(f"✅ Hunt frequency set to every *{n}* cycles.")
    except ValueError:
        await _send("Usage: `/cycle 2` (1 = every cycle, 3 = every 3rd, etc.)")


async def _cmd_execute(args: str):
    """Run a full pipeline cycle: observe → hunt → act."""
    if not _brain:
        await _send("Bot not ready yet.")
        return
    if _brain._paused:
        await _send("⚠️ Bot is paused. Send /resume first.")
        return

    await _send(
        "⚡ *EXECUTE — Full pipeline running*\n"
        "1. 🔍 Discovering projects...\n"
        "2. 📡 Joining groups...\n"
        "3. 🎯 Finding founders...\n"
        "4. ✉️ Sending DMs..."
    )
    try:
        obs     = await _brain.observe()
        thought = _brain.think(obs)
        plan    = _brain.plan(thought, obs)
        results = await _brain.act(plan)
        ok      = sum(1 for r in results if r["result"].get("ok"))
        sent    = await _brain.smart_hunt_cycle()

        await _send(
            f"✅ *Execute complete*\n\n"
            f"Actions taken: *{ok}/{len(results)}* succeeded\n"
            f"DMs sent: *{sent}*\n\n"
            f"_Cycle {_brain.cycle} — running 24/7_"
        )
    except Exception as e:
        await _send(f"❌ Execute error: `{e}`")


async def _cmd_agents():
    if not _brain:
        await _send("Bot not ready.")
        return
    summary = _brain.factory.list_summary()
    await _send(
        f"*🤖 Running Agents:*\n\n{summary}\n\n"
        '_To create a new agent, just describe it:\n'
        'e.g. "create an agent that posts daily crypto news in @mychannel"_'
    )


async def _cmd_orchestra(args: str):
    global _orchestra
    if not _orchestra:
        await _send("Orchestra not ready yet. Try again in a moment.")
        return
    task = args.strip() or "full autonomous: discover web3 AI opportunities, analyze them, draft outreach, report stats"
    await _send(
        f"🎼 *100-Agent Orchestra launching...*\n\n"
        f"Task: _{task[:100]}_\n\n"
        "Activating 9 departments..."
    )
    updates_sent = [False]

    async def _progress(msg: str):
        if not updates_sent[0]:
            await _send(f"⚡ *Orchestra running...*\n\n{msg}")
            updates_sent[0] = True

    result = await _orchestra.run(task, progress_cb=_progress)
    await _send(result)


async def _cmd_debate(args: str):
    """All 5 AI providers answer in parallel, synthesizer picks the best."""
    from telegram_agents.tools.ai_router import think_debate
    question = args.strip()
    if not question:
        await _send(
            "*🧠 AI Debate Mode*\n\n"
            "All 5 AI providers (Groq, DeepSeek, OpenAI, Claude, Gemini) answer "
            "your question simultaneously, then a synthesizer picks the best answer.\n\n"
            "Usage: `/debate your question here`"
        )
        return
    await _send(
        f"🤝 *5-AI Debate starting...*\n"
        f"Question: _{question[:120]}_\n\n"
        "Firing Groq · DeepSeek · OpenAI · Claude · Gemini in parallel..."
    )
    MY_CONTEXT = (
        "You are an expert AI assistant for Ashiq (@ashiq80), a Web3/AI community specialist. "
        "Be sharp, precise, and concise."
    )
    result = await think_debate(MY_CONTEXT, question, max_tokens=800)
    await _send(f"🏆 *Debate Synthesized:*\n\n{result}")


# ─── Natural language task parser ─────────────────────────────────────────────

_TASK_PARSER = """You are a task parser for a Telegram automation bot.
Parse the user's natural language request and return a JSON action plan.

CAPABILITIES:
- post: Post a message/announcement/content to a group or channel
- reply: Reply to a specific message in a group
- moderate: Kick, ban, mute, or unmute a user from a group
- dm: Send a direct message to a user
- content: Generate content on a topic (without posting)
- create_agent: Create a new autonomous AI agent with a custom goal
- list_agents: Show all running agents
- toggle_agent: Enable or disable a specific agent
- search: Search the web for something
- chat: Just answer a question (no action needed)

Parse and return ONLY valid JSON (no markdown fences):
{
  "action": "post|reply|moderate|dm|content|create_agent|list_agents|toggle_agent|search|chat",
  "target": "@channel_or_group or null",
  "user": "@username to act on or null",
  "mod_action": "kick|ban|mute|unmute or null",
  "msg_id": message_id_integer_or_null,
  "topic": "content topic or agent goal or null",
  "style": "announcement|post|thread|caption or null",
  "agent_name": "name of agent to toggle or null",
  "enable": true_or_false_or_null,
  "query": "search query or null",
  "generate_content": true_if_content_needs_to_be_ai_generated
}"""


async def _ai_task(text: str):
    """Parse natural language → execute real action OR answer as AI."""
    await _send("_processing..._")

    raw = ai_tools.think(
        system_addon=_TASK_PARSER,
        user_prompt=text,
        max_tokens=300,
    )
    try:
        start  = raw.find('{')
        intent = json.loads(raw[start:raw.rfind('}') + 1]) if start >= 0 else {"action": "chat"}
    except Exception:
        intent = {"action": "chat"}

    action = intent.get("action", "chat")

    if action == "post":
        target  = intent.get("target", "")
        topic   = intent.get("topic", text)
        style   = intent.get("style", "announcement")
        if not target:
            await _send("Which group or channel should I post to? Use `/post @channel topic`")
            return
        content = await _brain.tools.create_content(topic=topic, style=style)
        if not content or content.startswith("["):
            await _send("❌ Couldn't generate content. Try again.")
            return
        await _send(f"📝 *Preview:*\n\n{content}\n\nPosting to {target}...")
        ok = await _brain.tools.post_to_channel(channel=target, text=content)
        await _send(f"{'✅ Posted to ' + target if ok else '❌ Failed to post — check bot/channel permissions'}")

    elif action == "reply":
        target = intent.get("target", "")
        msg_id = intent.get("msg_id")
        topic  = intent.get("topic", "")
        if not target or not msg_id:
            await _send("Usage: `reply to message [ID] in @group saying [text]`")
            return
        if intent.get("generate_content"):
            reply_text = ai_tools.think(
                system_addon="Write a short, friendly Telegram reply. Return only the message text.",
                user_prompt=f"Write a reply that says: {topic}",
                max_tokens=200,
            )
        else:
            reply_text = topic
        ok = await _brain.tools.reply_message(chat_id=target, msg_id=int(msg_id), text=reply_text)
        await _send(f"{'✅ Replied to message ' + str(msg_id) if ok else '❌ Failed to reply'}")

    elif action == "moderate":
        target     = intent.get("target", "")
        user       = intent.get("user", "").lstrip("@")
        mod_action = intent.get("mod_action", "kick")
        if not target or not user:
            await _send("Usage: `kick @user from @group` or `mute @user in @group`")
            return
        await _send(f"⚙️ {mod_action.capitalize()}ing @{user} from {target}...")
        ok = await _brain.tools.moderate_user(chat_id=target, user_id=f"@{user}", action=mod_action)
        await _send(f"{'✅ ' + mod_action.capitalize() + 'ed @' + user if ok else '❌ Failed — need admin rights in ' + target}")

    elif action == "dm":
        user  = intent.get("user", "").lstrip("@")
        topic = intent.get("topic", text)
        if not user:
            await _send("Usage: `dm @username your message here`")
            return
        if intent.get("generate_content"):
            msg = ai_tools.think(
                system_addon="Write a short, natural Telegram DM. Return only the message.",
                user_prompt=topic,
                max_tokens=300,
            )
        else:
            msg = topic
        ok = await _brain.tools.send_dm(user_id=f"@{user}", text=msg)
        await _send(f"{'✅ DM sent to @' + user if ok else '❌ Failed to DM @' + user}")

    elif action == "content":
        topic   = intent.get("topic", text)
        style   = intent.get("style", "post")
        content = await _brain.tools.create_content(topic=topic, style=style)
        if content and not content.startswith("["):
            await _send(f"📝 *Generated {style}:*\n\n{content}")
        else:
            await _send("❌ Content generation failed. Try again.")

    elif action == "create_agent":
        goal  = intent.get("topic", text)
        await _send(f"🏭 *Creating new agent...*\nGoal: _{goal}_")
        agent = await _brain.factory.create(goal)
        if agent:
            await _send(
                f"✅ *Agent created!*\n\n"
                f"Name: `{agent.name}`\n"
                f"Goal: {agent.goal}\n"
                f"Tools: {', '.join(agent.tools)}\n"
                f"Schedule: every {agent.schedule_minutes} minutes\n\n"
                "Strategy:\n" +
                "\n".join(f"{i+1}. {s}" for i, s in enumerate(agent.strategy)) +
                "\n\n_Agent is now running autonomously._"
            )
        else:
            await _send("❌ Failed to create agent. Try describing the goal more clearly.")

    elif action == "list_agents":
        summary = _brain.factory.list_summary()
        await _send(f"*🤖 Active Agents:*\n\n{summary}")

    elif action == "toggle_agent":
        name   = intent.get("agent_name", "")
        enable = intent.get("enable", True)
        agent  = _brain.factory.get_agent(name)
        if agent:
            agent._enabled = enable
            await _send(f"{'▶️ Enabled' if enable else '⏸ Disabled'} agent `{name}`")
        else:
            await _send(f"No agent named `{name}` found. Use /agents to list them.")

    elif action == "search":
        query   = intent.get("query", text)
        results = await web_tools.web_search(query, num=5)
        if results:
            lines = [
                f"• *{r.get('title', '')[:60]}*\n  {r.get('snippet', '')[:100]}"
                for r in results[:4]
            ]
            await _send("*Search Results:*\n\n" + "\n\n".join(lines))
        else:
            await _send("No results found.")

    else:
        MY_CONTEXT = (
            "You are an AI assistant for Ashiq (@ashiq80), a Web3/AI community specialist. "
            "He has 16K+ followers, 6K+ community members, and runs an autonomous Telegram bot. "
            "Help him with DM drafts, strategy, Web3 analysis, or any question. "
            "Be sharp and concise. No fluff."
        )
        response = ai_tools.think(
            system_addon=MY_CONTEXT,
            user_prompt=text,
            max_tokens=600,
        )
        if response and not response.startswith("[") and len(response) > 5:
            await _send(response)
        else:
            await _send("AI is busy. Try again in 30 seconds.")


# ─── Command router ───────────────────────────────────────────────────────────

COMMANDS = {
    "/start":     lambda _: _cmd_help(),
    "/help":      lambda _: _cmd_help(),
    "/status":    lambda _: _cmd_status(),
    "/hunt":      lambda _: _cmd_hunt(),
    "/execute":   lambda args: _cmd_execute(args),
    "/orchestra": lambda args: _cmd_orchestra(args),
    "/o100":      lambda args: _cmd_orchestra(args),
    "/debate":    lambda args: _cmd_debate(args),
    "/pause":     lambda _: _cmd_pause(),
    "/resume":    lambda _: _cmd_resume(),
    "/dm":        _cmd_dm,
    "/search":    _cmd_search,
    "/cycle":     _cmd_cycle,
    "/agents":    lambda _: _cmd_agents(),
}


async def bot_commander():
    """Long-poll the Bot API and handle owner commands + chat."""
    global _last_update_id
    await asyncio.sleep(5)
    console.print("[cyan]🤖 Bot commander online — listening for commands[/cyan]")
    await _send(
        "🤖 *Bot commander ready*\n"
        "Send /help to see all commands, or just chat with me!"
    )

    while True:
        try:
            updates = await _get_updates(_last_update_id + 1)
            for update in updates:
                _last_update_id = update.get("update_id", _last_update_id)
                msg = update.get("message", {})
                if not msg:
                    continue

                from_id = str(msg.get("from", {}).get("id", ""))
                if from_id != OWNER_ID:
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                console.print(f"[cyan]📩 Owner: {text[:80]}[/cyan]")

                if text.startswith("/"):
                    parts   = text.split(" ", 1)
                    cmd     = parts[0].lower().split("@")[0]
                    args    = parts[1] if len(parts) > 1 else ""
                    handler = COMMANDS.get(cmd)
                    if handler:
                        await handler(args)
                    else:
                        await _send(f"Unknown command: `{cmd}`\nSend /help to see all commands.")
                else:
                    await _ai_task(text)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            console.print(f"[red]Commander error: {e}[/red]")
            await asyncio.sleep(5)


# ─── Startup check ────────────────────────────────────────────────────────────

def _check():
    missing = []
    if not Config.API_ID:
        missing.append("TELEGRAM_API_ID")
    if not Config.API_HASH:
        missing.append("TELEGRAM_API_HASH")
    if not os.getenv("TELEGRAM_SESSION_STRING"):
        missing.append("TELEGRAM_SESSION_STRING  ← run generate_session.py on Termux")
    for m in missing:
        console.print(f"[red]❌ Missing: {m}[/red]")
    return not missing


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    global _brain, _orchestra

    if not _check():
        return

    session_str = os.getenv("TELEGRAM_SESSION_STRING")

    db     = Database()
    await db.connect()
    memory = Memory()

    user_client = Client(
        name           = "cloud_session",
        api_id         = Config.API_ID,
        api_hash       = Config.API_HASH,
        session_string = session_str,
    )

    async with user_client:
        me = await user_client.get_me()
        console.print(Panel(
            f"[bold green]✅ Logged in as {me.first_name} (@{me.username})[/bold green]\n\n"
            "[bold magenta]🚀 FULL CLOUD AUTONOMOUS BOT — ONLINE[/bold magenta]\n\n"
            "[white]Every 2nd cycle:\n"
            "  1. 🔍 Discover projects (X/Twitter + Tavily)\n"
            "  2. 📡 Join their Telegram group\n"
            "  3. 👁  Read room context\n"
            "  4. 🎯 Find CEO / Founder\n"
            "  5. ✍️  Craft DM (Ashiq | @ashiq80)\n"
            "  6. ✉️  Send DM via your account\n\n"
            "Bot commander: send /help to your bot[/white]",
            border_style="magenta",
        ))

        await _send(
            f"🚀 *Cloud Bot Online*\n"
            f"Account: {me.first_name} (@{me.username})\n"
            f"Running 24/7 — no phone needed.\n"
            f"Send /help for commands."
        )

        tools      = ToolRegistry(user_client, db)
        _brain     = AgentBrain(tools, db, memory, user_client=user_client)
        _orchestra = Orchestra(tools, db)
        console.print(
            f"[bold cyan]🎼 Orchestra ready — {_orchestra.agent_count()} agents across 9 departments[/bold cyan]"
        )

        await asyncio.gather(
            _brain.run_forever(),
            bot_commander(),
        )

    await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")
