"""
Interactive Telegram AI Agent
─────────────────────────────
Send any message to your Saved Messages in Telegram → the AI executes it.

Examples:
  "join 10 web3 groups"
  "post AI news in my channel"
  "find ambassador programs and apply"
  "search for blockchain developer jobs"
  "send DM to @username saying hi"
  "hunt CM/moderator roles in 2026 projects"
  "what groups am I in?"
  "post in all my groups: [message]"
"""
import asyncio
import json
import re
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from rich.console import Console
from telegram_agents.tools import ai_tools, web_tools
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database

console = Console()

SYSTEM_PROMPT = """You are a 1000 IQ autonomous Telegram AI agent.
The user sends you a task and you plan and execute it using available tools.

AVAILABLE TOOLS:
search_groups(query)                    — search Telegram groups by keyword
join_group(username)                    — join a group by @username or invite link
post_in_group(group_id, text)           — post a message in a group
send_dm(user_id, text)                  — DM a user by ID
send_to_username(username, text)        — DM a user by @username
get_group_members(group_id)             — list group members
get_dialogs()                           — list all my chats/groups
get_chat_history(group_id)              — read recent messages in a group
search_web(query)                       — search the web
find_tg_groups_web(topic)               — find Telegram groups via web search
get_stats()                             — get account stats
get_unapplied_jobs()                    — get jobs not yet applied to
save_job(title,company,desc,src)        — save a job to database
apply_to_job(job_id, message)           — apply to a saved job
get_contacts()                          — list saved contacts
harvest_members(group_id)               — collect members from a group
reply_to_dm(user_id, text)              — reply to someone who messaged you
get_inbox()                             — get unread messages
post_news(topic)                        — search and post latest news on a topic
bulk_join_groups(topic, count)          — join multiple groups on a topic (default 5)
post_to_all_groups(text)                — post a message in ALL joined groups
generate_content(topic)                 — generate high-quality post about a topic
fetch_url(url)                          — fetch content from any URL
hunt_opportunities(role)                — hunt ambassador/CM/mod/creator roles (role optional)
leave_group(username)                   — leave a group

Return a JSON array of steps:
[{"step": 1, "tool": "tool_name", "args": {"key": "value"}, "reason": "why"}]

Be specific. Use real usernames/queries. Max 8 steps. If the task is unclear, use get_stats first.
"""


class TelegramAIAgent:
    """Interactive AI agent — responds to anything you send to your Saved Messages."""

    def __init__(self, client: Client, tools: ToolRegistry, db: Database):
        self.client = client
        self.tools  = tools
        self.db     = db
        self._me_id: int | None = None
        self._history: list[dict] = []  # conversation context

    async def start(self):
        """Register handlers and begin listening."""
        me = await self.client.get_me()
        self._me_id = me.id
        console.print(
            f"[bold green]🤖 Interactive AI Agent ONLINE[/bold green] "
            f"— send any command to your [bold]Saved Messages[/bold] in Telegram (@{me.username})"
        )

        # Listen for outgoing messages to Saved Messages (messages you send TO YOURSELF)
        async def _handler(client: Client, message: Message):
            if self._me_id is None:
                return
            # Saved Messages = private chat where chat.id == your own user id
            if message.chat.id != self._me_id:
                return
            text = (message.text or message.caption or "").strip()
            # Ignore our own bot replies (they start with 🤖)
            if not text or text.startswith("🤖") or text.startswith("✅") or text.startswith("⏳"):
                return
            asyncio.create_task(self._handle(text, message))

        # outgoing=True catches messages you send (to Saved Messages)
        self.client.add_handler(
            MessageHandler(_handler, filters.private & filters.outgoing)
        )

    async def _handle(self, user_text: str, message: Message):
        """Process one user request end-to-end."""
        started = datetime.now()
        console.print(f"\n[bold magenta]📨 USER:[/bold magenta] {user_text}")

        # Acknowledge immediately
        ack = await self.client.send_message(
            self._me_id,
            f"⏳ Got it! Working on: *{user_text[:80]}*\n\nPlanning steps...",
        )

        try:
            # Keep conversation history (last 6 exchanges)
            self._history.append({"role": "user", "content": user_text})
            if len(self._history) > 12:
                self._history = self._history[-12:]

            # AI plans steps
            history_str = "\n".join(
                f"{m['role'].upper()}: {m['content'][:200]}"
                for m in self._history[-6:]
            )
            plan_raw = ai_tools.think(
                system_addon=SYSTEM_PROMPT,
                user_prompt=f"CONVERSATION HISTORY:\n{history_str}\n\nCURRENT REQUEST: {user_text}\n\nJSON plan:",
                max_tokens=1000,
            )

            steps = []
            m = re.search(r'\[.*?\]', plan_raw, re.DOTALL)
            if m:
                try:
                    steps = json.loads(m.group())
                except Exception:
                    pass
            if not steps:
                steps = [{"step": 1, "tool": "get_stats", "args": {}, "reason": "Check current state"}]

            console.print(f"  [dim]📋 {len(steps)} steps planned[/dim]")

            # Update ack with plan preview
            plan_preview = "\n".join(
                f"  {i+1}. {s.get('tool','?')} — {s.get('reason','')[:60]}"
                for i, s in enumerate(steps)
            )
            await ack.edit(f"⏳ Working on: *{user_text[:60]}*\n\nPlan:\n{plan_preview}")

            # Execute steps
            results_log = []
            for step in steps:
                tool   = step.get("tool", "")
                args   = step.get("args", {})
                reason = step.get("reason", "")
                console.print(f"  [cyan]▶[/cyan] [{tool}] {reason}")

                # Handle new extended tools
                result = await self._call_extended(tool, **args)
                ok  = result.get("ok", False)
                out = result.get("result", result.get("error", ""))
                results_log.append({
                    "tool":    tool,
                    "success": ok,
                    "output":  str(out)[:400],
                })
                console.print(f"    {'[green]✅' if ok else '[red]❌'} {str(out)[:100]}[/]")
                await asyncio.sleep(1)

            # AI summarises
            summary = ai_tools.think(
                system_addon=(
                    "You are a Telegram assistant. The user gave you a task, you executed it. "
                    "Write a clear, concise reply (under 200 words) summarising EXACTLY what was done and the results. "
                    "Be specific — include numbers, names, and outcomes. Use bullet points if helpful."
                ),
                user_prompt=(
                    f"User request: {user_text}\n\n"
                    f"Steps executed:\n{json.dumps(results_log, indent=2)}\n\n"
                    "Reply:"
                ),
                max_tokens=350,
            )

            elapsed = (datetime.now() - started).seconds
            reply_text = f"🤖 **Done** ({elapsed}s)\n\n{summary}"
            self._history.append({"role": "assistant", "content": summary})

        except Exception as e:
            reply_text = f"🤖 ❌ Error: {e}"
            console.print(f"[red]Agent error: {e}[/red]")

        # Edit the ack message with final result
        try:
            await ack.edit(reply_text)
        except Exception:
            await self.client.send_message(self._me_id, reply_text)

    # ── Extended tool dispatcher ──────────────────────────────────────────────

    async def _call_extended(self, tool: str, **kwargs) -> dict:
        """Handle both standard ToolRegistry tools and new extended tools."""
        # New extended tools
        if tool == "post_news":
            return await self._post_news(kwargs.get("topic", "AI web3 crypto"))
        if tool == "bulk_join_groups":
            return await self._bulk_join_groups(
                kwargs.get("topic", "web3"), int(kwargs.get("count", 5))
            )
        if tool == "post_to_all_groups":
            return await self._post_to_all_groups(kwargs.get("text", ""))
        if tool == "generate_content":
            return await self._generate_content(kwargs.get("topic", ""))
        if tool == "fetch_url":
            content = await web_tools.fetch_page(kwargs.get("url", ""))
            return {"ok": bool(content), "result": content[:500]}
        if tool == "hunt_opportunities":
            return await self._hunt_opportunities(kwargs.get("role", ""))
        if tool == "send_to_username":
            return await self._send_to_username(
                kwargs.get("username", ""), kwargs.get("text", "")
            )
        if tool == "leave_group":
            return await self._leave_group(kwargs.get("username", ""))

        # Delegate to existing ToolRegistry
        return await self.tools.call(tool, **kwargs)

    async def _post_news(self, topic: str) -> dict:
        """Search web for latest news on topic and return formatted post."""
        results = await web_tools.web_search(f"latest {topic} news 2026", num=5)
        if not results:
            return {"ok": False, "error": "No news found"}
        headlines = "\n".join(
            f"• {r['title']}" for r in results[:5] if r.get("title")
        )
        post = ai_tools.think(
            system_addon="Write a short engaging Telegram post (3-5 bullet points) about these news headlines. No hashtags. Sound human.",
            user_prompt=f"Topic: {topic}\nHeadlines:\n{headlines}\n\nPost:",
            max_tokens=300,
        )
        # Post in all joined groups
        groups = await self.db.get_groups(joined=True)
        posted = 0
        for g in groups[:5]:
            try:
                from telegram_agents.tools import telegram_tools
                msg = await telegram_tools.send_message(self.client, g["tg_id"], post)
                if msg:
                    posted += 1
                await asyncio.sleep(3)
            except Exception:
                pass
        return {"ok": True, "result": f"Posted news about '{topic}' in {posted} groups.\n\nPost:\n{post[:200]}"}

    async def _bulk_join_groups(self, topic: str, count: int = 5) -> dict:
        """Find and join multiple Telegram groups on a topic."""
        groups = await web_tools.find_telegram_groups_online(topic)
        joined = 0
        for g in groups[:count]:
            username = g.get("username", "")
            if not username:
                continue
            try:
                from telegram_agents.tools import telegram_tools
                ok = await telegram_tools.join_chat(self.client, username)
                if ok:
                    await self.db.upsert_group(
                        tg_id=hash(username), username=username,
                        title=g.get("title", username), joined=1
                    )
                    joined += 1
                await asyncio.sleep(4)
            except Exception:
                pass
        return {"ok": True, "result": f"Joined {joined}/{min(count, len(groups))} groups about '{topic}'"}

    async def _post_to_all_groups(self, text: str) -> dict:
        """Post a message in all joined groups."""
        if not text:
            return {"ok": False, "error": "No text provided"}
        groups = await self.db.get_groups(joined=True)
        posted = 0
        for g in groups:
            try:
                from telegram_agents.tools import telegram_tools
                msg = await telegram_tools.send_message(self.client, g["tg_id"], text)
                if msg:
                    posted += 1
                await asyncio.sleep(3)
            except Exception:
                pass
        return {"ok": True, "result": f"Posted in {posted}/{len(groups)} groups"}

    async def _generate_content(self, topic: str) -> dict:
        """Generate a high-quality post about a topic."""
        post = ai_tools.think(
            system_addon=(
                "You are a Web3/AI content creator. Write an engaging, informative Telegram post "
                "(150-200 words). No hashtags. Sound human and knowledgeable. "
                "Include a call to action or thought-provoking question at the end."
            ),
            user_prompt=f"Write a Telegram post about: {topic}",
            max_tokens=400,
        )
        return {"ok": True, "result": post}

    async def _hunt_opportunities(self, role: str = "") -> dict:
        """Trigger the opportunity hunter for a specific role or all roles."""
        from telegram_agents.agents.opportunity_hunter import OpportunityHunterAgent
        hunter = OpportunityHunterAgent(self.client, self.db)
        result = await hunter.run(max_apply=10)
        return {
            "ok": True,
            "result": f"Opportunity hunt complete: found {result['found']}, applied to {result['applied']}",
        }

    async def _send_to_username(self, username: str, text: str) -> dict:
        """DM any Telegram @username."""
        if not username or not text:
            return {"ok": False, "error": "Missing username or text"}
        username = username.lstrip("@").strip()
        try:
            from telegram_agents.tools import telegram_tools
            msg = await telegram_tools.send_dm(self.client, f"@{username}", text)
            return {"ok": bool(msg), "result": f"Sent DM to @{username}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _leave_group(self, username: str) -> dict:
        """Leave a Telegram group."""
        username = username.lstrip("@").strip()
        try:
            await self.client.leave_chat(username)
            return {"ok": True, "result": f"Left @{username}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
