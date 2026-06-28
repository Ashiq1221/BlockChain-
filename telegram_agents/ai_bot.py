"""
AI Telegram Bot
───────────────
Chat with the bot — it understands anything and executes it.

Commands:
  /start   — welcome
  /help    — full capability list
  /status  — account stats
  /hunt    — find ambassador/CM/mod roles now
  /news    — post latest Web3/AI news
  /jobs    — search and apply for jobs
  /groups  — list joined groups
  Or just send any message in plain text.
"""
import asyncio
import json
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from pyrogram.enums import ChatAction
from rich.console import Console
from telegram_agents.config import Config
from telegram_agents.tools import ai_tools, web_tools
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database

console = Console()

WELCOME = """🤖 **AI Telegram Agent — Online**

I'm your personal AI agent. Just tell me what to do:

• `join 10 web3 groups`
• `post AI news in my groups`
• `hunt ambassador / CM / moderator roles and apply`
• `search blockchain developer jobs and apply`
• `send DM to @username saying: hi there`
• `post in all my groups: [your message]`
• `generate a post about DeFi 2026`
• `what groups am I in?`
• `find new Web3 projects on X/Twitter`

Or use the buttons below for quick actions.
"""

HELP = """📋 **All Capabilities**

**Telegram Actions**
• Join groups by keyword or count
• Post in specific groups or all groups at once
• Send DMs to any @username or user_id
• Read group messages and chat history
• Harvest members from groups
• Leave groups

**Opportunity Hunting**
• Hunt ambassador programs (web + X/Twitter, 2026)
• Apply for CM / moderator / content creator roles
• Find new Web3/AI project roles and send applications

**Web & AI**
• Search web for anything
• Fetch any URL and summarize it
• Generate high-quality content about any topic
• Post latest AI/Web3 news to groups

**Job Search**
• Search for blockchain/remote developer jobs
• Save and apply to job listings

**Account Info**
• Stats: messages sent, groups joined, applications
• List all joined groups
• View inbox / unread messages

Just type anything naturally — the AI figures out what to do!
"""

AI_SYSTEM = """You are a 1000 IQ autonomous Telegram AI agent.
The user sends you tasks. Plan and execute them using available tools.

AVAILABLE TOOLS:
search_groups(query)                 — search Telegram groups by keyword
join_group(username)                 — join a group by @username or t.me link
post_in_group(group_id, text)        — post a message in a group (group_id is integer)
send_dm(user_id, text)               — send a direct message to a user by user_id
send_to_username(username, text)     — send a DM to @username
get_group_members(group_id)          — list group members
get_dialogs()                        — list all my chats
get_chat_history(group_id)           — read recent messages
search_web(query)                    — search the web
find_tg_groups_web(topic)            — find Telegram groups via web search
get_stats()                          — account stats
get_unapplied_jobs()                 — pending job applications
save_job(title,company,desc,src)     — save a job
apply_to_job(job_id, message)        — apply to a saved job
get_contacts()                       — saved contacts
harvest_members(group_id)            — collect members from a group
reply_to_dm(user_id, text)           — reply to someone
get_inbox()                          — unread messages
post_news(topic)                     — fetch and post latest news on a topic in groups
bulk_join_groups(topic, count)       — join multiple groups (default 5)
post_to_all_groups(text)             — post a message in ALL joined groups
generate_content(topic)              — generate a high-quality post
fetch_url(url)                       — fetch and read any URL
hunt_opportunities(role)             — hunt ambassador/CM/mod/creator roles and apply
leave_group(username)                — leave a group

Return ONLY a JSON array:
[{"step": 1, "tool": "tool_name", "args": {"key": "value"}, "reason": "why"}]

Max 6 steps. Be specific. No extra text.
"""


def _quick_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Hunt Roles", callback_data="hunt"),
            InlineKeyboardButton("📰 Post News", callback_data="news"),
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("👥 Join Groups", callback_data="join"),
        ],
        [
            InlineKeyboardButton("💼 Find Jobs", callback_data="jobs"),
            InlineKeyboardButton("📋 My Groups", callback_data="groups"),
        ],
    ])


class AIBot:
    def __init__(self, bot: Client, user_client: Client, tools: ToolRegistry, db: Database):
        self.bot         = bot
        self.user_client = user_client
        self.tools       = tools
        self.db          = db
        self._history: dict[int, list[dict]] = {}  # per-user conversation history

    async def start(self):
        """Register all handlers."""
        # Commands
        self.bot.add_handler(MessageHandler(self._cmd_start,  filters.command("start")  & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_help,   filters.command("help")   & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_status, filters.command("status") & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_hunt,   filters.command("hunt")   & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_news,   filters.command("news")   & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_jobs,   filters.command("jobs")   & filters.private))
        self.bot.add_handler(MessageHandler(self._cmd_groups, filters.command("groups") & filters.private))
        # Any text
        self.bot.add_handler(MessageHandler(self._on_message, filters.text & filters.private))
        # Button clicks
        self.bot.add_handler(CallbackQueryHandler(self._on_button))
        console.print("[bold green]🤖 Telegram Bot ONLINE[/bold green] — users can now chat with the bot")

    def _owner_only(self, uid: int) -> bool:
        """Allow owner always; if OWNER_ID not set, allow anyone (first-use mode)."""
        if Config.OWNER_ID and uid != Config.OWNER_ID:
            return False
        return True

    # ── Commands ────────────────────────────────────────────────────────────────

    async def _cmd_start(self, bot: Client, msg: Message):
        await msg.reply(WELCOME, reply_markup=_quick_buttons())

    async def _cmd_help(self, bot: Client, msg: Message):
        await msg.reply(HELP)

    async def _cmd_status(self, bot: Client, msg: Message):
        await self._execute_and_reply(msg, "get current account stats and show a summary")

    async def _cmd_hunt(self, bot: Client, msg: Message):
        await self._execute_and_reply(msg, "hunt ambassador CM moderator content creator roles in web3 AI 2026 projects")

    async def _cmd_news(self, bot: Client, msg: Message):
        await self._execute_and_reply(msg, "search and post latest AI and Web3 crypto news in my groups")

    async def _cmd_jobs(self, bot: Client, msg: Message):
        await self._execute_and_reply(msg, "search for blockchain remote developer jobs and save them")

    async def _cmd_groups(self, bot: Client, msg: Message):
        await self._execute_and_reply(msg, "get dialogs and list all groups I am currently in")

    # ── Button callbacks ─────────────────────────────────────────────────────────

    async def _on_button(self, bot: Client, cb: CallbackQuery):
        await cb.answer()
        mapping = {
            "hunt":   "hunt ambassador CM moderator content creator roles in web3 AI 2026 and apply",
            "news":   "search and post latest AI Web3 crypto news in my groups",
            "stats":  "get stats and show account performance summary",
            "join":   "find and join 5 top web3 AI crypto telegram groups",
            "jobs":   "search blockchain remote developer jobs and apply to the best ones",
            "groups": "list all groups I am currently in",
        }
        task = mapping.get(cb.data, cb.data)
        # Create a fake message object to reuse _execute_and_reply
        await bot.send_message(cb.from_user.id, f"⏳ Starting: *{task}*...")
        await self._run_task(cb.from_user.id, task)

    # ── Any text message ─────────────────────────────────────────────────────────

    async def _on_message(self, bot: Client, msg: Message):
        uid  = msg.from_user.id
        text = (msg.text or "").strip()
        if not text or text.startswith("/"):
            return
        if not self._owner_only(uid):
            await msg.reply("⛔ Access denied.")
            return
        await self._execute_and_reply(msg, text)

    # ── Core execution ───────────────────────────────────────────────────────────

    async def _execute_and_reply(self, msg: Message, task: str):
        uid = msg.from_user.id
        ack = await msg.reply(f"⏳ Working on: *{task[:80]}*\n\nPlanning...")
        await self.bot.send_chat_action(uid, ChatAction.TYPING)
        result = await self._run_task(uid, task, ack)
        # Final reply with quick buttons
        try:
            await ack.edit(result, reply_markup=_quick_buttons())
        except Exception:
            await self.bot.send_message(uid, result, reply_markup=_quick_buttons())

    async def _run_task(self, uid: int, task: str, ack: Message | None = None) -> str:
        started = datetime.now()
        # Conversation history per user
        history = self._history.setdefault(uid, [])
        history.append({"role": "user", "content": task})
        if len(history) > 12:
            history[:] = history[-12:]

        history_str = "\n".join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in history[-6:]
        )
        try:
            plan_raw = ai_tools.think(
                system_addon=AI_SYSTEM,
                user_prompt=f"HISTORY:\n{history_str}\n\nTASK: {task}\n\nJSON plan:",
                max_tokens=900,
            )
            steps = []
            m = re.search(r'\[.*?\]', plan_raw, re.DOTALL)
            if m:
                try:
                    steps = json.loads(m.group())
                except Exception:
                    pass
            if not steps:
                steps = [{"step": 1, "tool": "get_stats", "args": {}, "reason": "Check state"}]

            # Show plan in ack message
            if ack:
                plan_preview = "\n".join(
                    f"  {i+1}. `{s.get('tool','?')}` — {s.get('reason','')[:50]}"
                    for i, s in enumerate(steps)
                )
                try:
                    await ack.edit(f"⏳ *{task[:60]}*\n\n**Plan:**\n{plan_preview}")
                except Exception:
                    pass

            results_log = []
            for step in steps:
                tool   = step.get("tool", "")
                args   = step.get("args", {})
                reason = step.get("reason", "")
                console.print(f"  [cyan]▶[/cyan] [{tool}] {reason}")
                result = await self._call_tool(tool, **args)
                ok  = result.get("ok", False)
                out = str(result.get("result", result.get("error", "")))
                results_log.append({"tool": tool, "success": ok, "output": out[:400]})
                console.print(f"    {'[green]✅' if ok else '[red]❌'} {out[:80]}[/]")
                await asyncio.sleep(1)

            summary = ai_tools.think(
                system_addon=(
                    "You are a Telegram bot assistant. Summarise what was done and the results "
                    "in a clear, concise reply (max 200 words). Use bullet points. Be specific "
                    "— include numbers, names, outcomes. No jargon."
                ),
                user_prompt=(
                    f"Task: {task}\n\n"
                    f"Steps:\n{json.dumps(results_log, indent=2)}\n\n"
                    "Reply:"
                ),
                max_tokens=350,
            )
            elapsed = (datetime.now() - started).seconds
            reply = f"✅ **Done** ({elapsed}s)\n\n{summary}"
            history.append({"role": "assistant", "content": summary})

        except Exception as e:
            reply = f"❌ Error: {e}"
            console.print(f"[red]Bot error: {e}[/red]")

        return reply

    # ── Tool dispatcher ──────────────────────────────────────────────────────────

    async def _call_tool(self, tool: str, **kwargs) -> dict:
        # Extended tools
        if tool == "post_news":
            return await self._post_news(kwargs.get("topic", "AI web3 crypto"))
        if tool == "bulk_join_groups":
            return await self._bulk_join_groups(kwargs.get("topic", "web3"), int(kwargs.get("count", 5)))
        if tool == "post_to_all_groups":
            return await self._post_to_all_groups(kwargs.get("text", ""))
        if tool == "generate_content":
            return {"ok": True, "result": ai_tools.think(
                system_addon="Write an engaging Telegram post (150-200 words). No hashtags. Sound human.",
                user_prompt=f"Topic: {kwargs.get('topic', '')}",
                max_tokens=400,
            )}
        if tool == "fetch_url":
            content = await web_tools.fetch_page(kwargs.get("url", ""))
            return {"ok": bool(content), "result": content[:600]}
        if tool == "hunt_opportunities":
            return await self._hunt_opps(kwargs.get("role", ""))
        if tool == "send_to_username":
            return await self._send_to_username(kwargs.get("username", ""), kwargs.get("text", ""))
        if tool == "leave_group":
            username = kwargs.get("username", "").lstrip("@")
            try:
                await self.user_client.leave_chat(username)
                return {"ok": True, "result": f"Left @{username}"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        # Standard tools via user_client ToolRegistry
        return await self.tools.call(tool, **kwargs)

    async def _post_news(self, topic: str) -> dict:
        results = await web_tools.web_search(f"latest {topic} news 2026", num=5)
        if not results:
            return {"ok": False, "error": "No news found"}
        headlines = "\n".join(f"• {r['title']}" for r in results[:5] if r.get("title"))
        post = ai_tools.think(
            system_addon="Write a short engaging Telegram post (3-5 bullet points) about these news headlines. No hashtags. Sound human.",
            user_prompt=f"Topic: {topic}\nHeadlines:\n{headlines}\n\nPost:",
            max_tokens=300,
        )
        groups = await self.db.get_groups(joined=True)
        posted = 0
        for g in groups[:5]:
            try:
                from telegram_agents.tools import telegram_tools
                msg = await telegram_tools.send_message(self.user_client, g["tg_id"], post)
                if msg:
                    posted += 1
                await asyncio.sleep(3)
            except Exception:
                pass
        return {"ok": True, "result": f"Posted '{topic}' news in {posted} groups.\n\nPost:\n{post[:200]}"}

    async def _bulk_join_groups(self, topic: str, count: int = 5) -> dict:
        groups = await web_tools.find_telegram_groups_online(topic)
        joined = 0
        from telegram_agents.tools import telegram_tools
        for g in groups[:count]:
            username = g.get("username", "")
            if not username:
                continue
            try:
                ok = await telegram_tools.join_chat(self.user_client, username)
                if ok:
                    await self.db.upsert_group(tg_id=hash(username), username=username, title=g.get("title", username), joined=1)
                    joined += 1
                await asyncio.sleep(4)
            except Exception:
                pass
        return {"ok": True, "result": f"Joined {joined}/{min(count, len(groups))} groups about '{topic}'"}

    async def _post_to_all_groups(self, text: str) -> dict:
        if not text:
            return {"ok": False, "error": "No text provided"}
        groups = await self.db.get_groups(joined=True)
        posted = 0
        from telegram_agents.tools import telegram_tools
        for g in groups:
            try:
                msg = await telegram_tools.send_message(self.user_client, g["tg_id"], text)
                if msg:
                    posted += 1
                await asyncio.sleep(3)
            except Exception:
                pass
        return {"ok": True, "result": f"Posted in {posted}/{len(groups)} groups"}

    async def _hunt_opps(self, role: str = "") -> dict:
        from telegram_agents.agents.opportunity_hunter import OpportunityHunterAgent
        hunter = OpportunityHunterAgent(self.user_client, self.db)
        r = await hunter.run(max_apply=10)
        return {"ok": True, "result": f"Found {r['found']} opportunities, applied to {r['applied']}"}

    async def _send_to_username(self, username: str, text: str) -> dict:
        if not username or not text:
            return {"ok": False, "error": "Missing username or text"}
        username = username.lstrip("@").strip()
        try:
            from telegram_agents.tools import telegram_tools
            msg = await telegram_tools.send_dm(self.user_client, f"@{username}", text)
            return {"ok": bool(msg), "result": f"Sent DM to @{username}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
