"""
Remote Command Channel — bridges Claude chat ↔ your phone agent.

Two channels:
  1. GitHub polling  — Claude writes command.json → agent executes → pushes result.json
  2. Saved Messages  — you message yourself in Telegram → agent executes instantly
"""
import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from rich.console import Console
from telegram_agents.tools import ai_tools
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database

console = Console()

INBOX_DIR    = "telegram_agents/inbox"
COMMAND_FILE = f"{INBOX_DIR}/command.json"
RESULT_FILE  = f"{INBOX_DIR}/result.json"
POLL_INTERVAL = 90  # seconds between git pulls


class CommanderChannel:
    def __init__(self, client: Client, tools: ToolRegistry, db: Database):
        self.client = client
        self.tools  = tools
        self.db     = db
        self._last_cmd_id = "init"

    # ── Execute any natural language command ─────────────────────────────────

    async def execute(self, command: str) -> str:
        """1000 IQ execution: AI reasons about command → picks tools → runs them → summarises."""
        console.print(f"\n[bold magenta]📡 COMMAND RECEIVED:[/bold magenta] {command}")

        # Step 1: AI plans the execution
        plan_raw = ai_tools.think(
            system_addon="""You are an autonomous Telegram agent executing a user command.
Plan the exact steps using available tools. Return JSON array:
[{"tool": "tool_name", "args": {"key": "value"}, "reason": "why"}]
Available tools: search_groups, join_group, post_in_group, send_dm,
get_group_members, get_dialogs, get_chat_history, search_web,
find_tg_groups_web, get_stats, get_unapplied_jobs, save_job,
apply_to_job, get_contacts, harvest_members, reply_to_dm, get_inbox
Keep it to 1-5 steps. Be precise.""",
            user_prompt=f"Command: {command}\n\nJSON plan:",
            max_tokens=800,
        )

        # Parse plan
        import re
        steps = []
        match = re.search(r'\[.*?\]', plan_raw, re.DOTALL)
        if match:
            try:
                steps = json.loads(match.group())
            except Exception:
                pass

        if not steps:
            steps = [{"tool": "get_stats", "args": {}, "reason": "Check current state"}]

        # Step 2: Execute each step
        results_log = []
        for step in steps:
            tool   = step.get("tool", "")
            args   = step.get("args", {})
            reason = step.get("reason", "")
            console.print(f"  [cyan]▶[/cyan] {tool} — {reason}")
            result = await self.tools.call(tool, **args)
            results_log.append({
                "tool":    tool,
                "args":    args,
                "success": result.get("ok", False),
                "output":  str(result.get("result", result.get("error", "")))[:300],
            })
            await asyncio.sleep(2)

        # Step 3: AI summarises what happened
        summary = ai_tools.think(
            system_addon="Summarise what the agent did and the outcome. Be concise and clear. Max 150 words.",
            user_prompt=f"Command: {command}\nSteps taken:\n{json.dumps(results_log, indent=2)}\n\nSummary:",
            max_tokens=250,
        )

        console.print(f"[green]✅ Done:[/green] {summary[:150]}")
        return summary

    # ── Channel 1: GitHub polling ─────────────────────────────────────────────

    async def _git_pull(self):
        try:
            subprocess.run(["git", "pull", "--rebase", "-q"], capture_output=True, timeout=30)
        except Exception:
            pass

    async def _git_push_result(self, cmd_id: str, command: str, result: str):
        payload = {
            "id":        cmd_id,
            "command":   command,
            "result":    result,
            "status":    "done",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(RESULT_FILE, "w") as f:
            json.dump(payload, f, indent=2)
        try:
            subprocess.run(["git", "add", RESULT_FILE], capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"result: {cmd_id}"],
                capture_output=True,
            )
            subprocess.run(["git", "push", "-q"], capture_output=True, timeout=30)
        except Exception:
            pass

    async def poll_github(self):
        """Continuously poll GitHub for new commands from Claude chat."""
        console.print("[dim]📡 GitHub command channel: listening...[/dim]")
        while True:
            try:
                await self._git_pull()
                if os.path.exists(COMMAND_FILE):
                    with open(COMMAND_FILE) as f:
                        data = json.load(f)

                    cmd_id  = data.get("id", "")
                    command = data.get("command", "").strip()
                    status  = data.get("status", "idle")

                    # New command detected
                    if cmd_id != self._last_cmd_id and command and status == "pending":
                        self._last_cmd_id = cmd_id
                        console.print(f"\n[bold yellow]📡 GitHub command:[/bold yellow] {command}")

                        # Mark as running
                        data["status"] = "running"
                        with open(COMMAND_FILE, "w") as f:
                            json.dump(data, f, indent=2)

                        result = await self.execute(command)
                        await self._git_push_result(cmd_id, command, result)

            except Exception as e:
                console.print(f"[dim red]GitHub poll error: {e}[/dim red]")

            await asyncio.sleep(POLL_INTERVAL)

    # ── Channel 2: Saved Messages (Telegram self-chat) ────────────────────────

    async def listen_saved_messages(self):
        """Listen for commands sent to your own Saved Messages in Telegram."""
        me = await self.client.get_me()
        my_id = me.id
        console.print(f"[dim]💬 Saved Messages channel: listening (send commands to yourself @{me.username})[/dim]")

        async def handler(client: Client, message: Message):
            # Only process messages sent by the user to themselves
            if not message.from_user:
                return
            if message.from_user.id != my_id:
                return
            if message.chat.id != my_id:
                return

            text = (message.text or "").strip()
            if not text or text.startswith("✅") or text.startswith("🤖"):
                return

            # Execute the command
            result = await self.execute(text)

            # Reply back in Saved Messages
            reply = f"🤖 Done!\n\n{result}\n\n[{datetime.now().strftime('%H:%M')}]"
            await client.send_message(my_id, reply)

        self.client.add_handler(MessageHandler(handler, filters.private & filters.incoming))
        console.print("[green]✅ Send any command to your own Saved Messages in Telegram![/green]")

    async def start(self):
        """Start both command channels simultaneously."""
        await self.listen_saved_messages()
        asyncio.create_task(self.poll_github())
