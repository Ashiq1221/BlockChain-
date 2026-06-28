"""
500 IQ Agentic Orchestrator
Full pipeline: Discover Projects → Join TG Group → Identify CEO/Founder → Craft DM → Send

General loop (every cycle): Observe → Think → Plan → Act → Reflect → Learn
Smart hunt (every 3rd cycle): the full 6-phase strategic pipeline above

Two rules that never break:
  1. NEVER auto-reply to incoming DMs from strangers
  2. NEVER post to groups on a timer with no strategic goal
"""
import asyncio
import json
import re
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from telegram_agents.tools import ai_tools, web_tools, telegram_tools
from telegram_agents.config import Config as _Cfg
from telegram_agents.tools.memory import Memory
from telegram_agents.tools.tool_registry import ToolRegistry
from telegram_agents.database import Database
from telegram_agents.config import Config

console = Console()

MASTER_GOAL = """
You are a 500 IQ autonomous agent managing a Telegram account for a Web3/AI developer.
Priority goals:
1. Find Web3/AI/blockchain projects actively hiring or seeking ambassadors, CM, mods
2. Join their Telegram groups, identify the CEO/founder/owner, send personalized outreach
3. Join relevant professional groups (blockchain, Python dev, remote jobs)
4. Apply to job postings found online
5. Post valuable content in groups only when it serves a clear networking goal

HARD RULES (never break):
- DO NOT auto-reply to incoming DMs from strangers
- DO NOT post to groups on a schedule without a strategic reason
- DO NOT sound like a bot — every message must sound human
- Rate limit: pause 5+ seconds between any sends
"""

# Web search queries for discovering opportunities
DISCOVERY_QUERIES = [
    "web3 blockchain project hiring ambassador community manager 2026",
    "DeFi NFT AI project we are hiring moderator content creator 2026",
    "blockchain startup hiring remote developer python engineer 2026",
    "crypto project open roles ambassador social media manager 2026",
    "web3 AI project community lead content creator opening 2026",
    "site:t.me web3 project hiring community manager ambassador 2026",
    "telegram web3 group hiring team member 2026",
    "new crypto project launch team community builder 2026",
]


class AgentBrain:
    def __init__(self, tools: ToolRegistry, db: Database, memory: Memory, user_client=None):
        self.tools        = tools
        self.db           = db
        self.memory       = memory
        self.client       = user_client or tools.client
        self.cycle        = 0
        self.action_log: list[str] = []
        self._contacted: set[str]  = set()
        self._paused      = False   # set True/False via bot /pause /resume
        self._hunt_every  = 2       # run smart hunt every N cycles (default: every 2nd)

    # ══════════════════════════════════════════════════════════════════════════
    #  500 IQ SMART HUNT PIPELINE
    # ══════════════════════════════════════════════════════════════════════════

    # ── Phase 1: DISCOVER ────────────────────────────────────────────────────

    async def discover_opportunities(self) -> list[dict]:
        """
        Source priority: X/Twitter API → Tavily (web_search) → Grok → scraping.
        Returns: [{"name","role","tg_username","website","description"}, ...]
        """
        parts = []

        # ── PRIMARY: X/Twitter developer API — real-time tweets ─────────────
        if _Cfg.X_BEARER_TOKEN:
            console.print("    [dim cyan]X/Twitter live search...[/dim cyan]")
            x_text = await web_tools.x_search_jobs()
            if x_text and len(x_text) > 100:
                parts.append(f"[X/TWITTER LIVE]\n{x_text}")
                console.print(f"    [green]X/Twitter: {len(x_text)} chars[/green]")

        # ── SECONDARY: Tavily web search ─────────────────────────────────────
        console.print("    [dim]Tavily web search...[/dim]")
        snippets = []
        for q in DISCOVERY_QUERIES[:6]:
            results = await web_tools.web_search(q, num=6)
            for r in results:
                snippets.append(
                    f"Title: {r.get('title','')}\n"
                    f"Snippet: {r.get('snippet','')}\n"
                    f"URL: {r.get('url','')}"
                )
        if snippets:
            parts.append(f"[WEB SEARCH]\n" + "\n---\n".join(snippets[:20]))
            console.print(f"    [green]Web: {len(snippets)} results[/green]")

        # ── TERTIARY: Grok (if credits available) ────────────────────────────
        if _Cfg.XAI_API_KEY and not parts:
            grok_projects, grok_jobs = await asyncio.gather(
                web_tools.grok_find_projects(),
                web_tools.grok_find_jobs(),
            )
            combined = "\n\n".join(filter(None, [grok_projects, grok_jobs]))
            if combined and len(combined) > 100:
                parts.append(f"[GROK]\n{combined}")

        raw_text = "\n\n".join(parts)[:6000]

        if not raw_text:
            return []

        # ── AI structures the raw data ────────────────────────────────────────
        structured = ai_tools.think(
            system_addon="""Extract Web3/AI/blockchain projects that are ACTIVELY hiring or seeking roles.
Return ONLY valid JSON array (no markdown, no extra text):
[{"name":"ProjectName","role":"developer|ambassador|CM|moderator|creator","tg_username":"@handle_or_empty","website":"url_or_empty","description":"one sentence about project + role"}]
Rules:
- Only include projects with a clear, real hiring/role signal
- Max 10 entries, no duplicates
- tg_username: only if you see t.me/ or @handle clearly mentioned, else leave empty string
- description: include the SOURCE URL or tweet link if available""",
            user_prompt=f"Data (from live Grok search + web):\n{raw_text[:4000]}",
            max_tokens=1200,
        )

        try:
            m = re.search(r'\[.*?\]', structured, re.DOTALL)
            projects = json.loads(m.group()) if m else []
            return [p for p in projects if isinstance(p, dict) and p.get("name") not in self._contacted]
        except Exception:
            return []

    # ── Phase 2: INFILTRATE ──────────────────────────────────────────────────

    async def infiltrate_project(self, project: dict) -> str | None:
        """
        Find and join the project's Telegram group via multiple strategies.
        Returns: username/id of the joined group, or None.
        """
        name     = project.get("name", "")
        tg_hint  = project.get("tg_username", "").strip().lstrip("@t.me/")

        # Strategy A: direct join if we found a TG handle
        if tg_hint:
            ok = await telegram_tools.join_chat(self.client, tg_hint)
            if ok:
                console.print(f"    [green]✅ Joined @{tg_hint}[/green]")
                await asyncio.sleep(4)
                return tg_hint

        # Strategy B: find their group via web search
        groups = await web_tools.find_telegram_groups_online(name)
        for g in groups[:3]:
            u = g.get("username", "").strip().lstrip("@")
            if not u:
                continue
            ok = await telegram_tools.join_chat(self.client, u)
            if ok:
                console.print(f"    [green]✅ Joined @{u} (web find)[/green]")
                await asyncio.sleep(4)
                return u

        # Strategy C: Telegram's own global search
        try:
            hits = await telegram_tools.search_public_groups(self.client, name, limit=5)
            for h in hits:
                u = h.get("username", "")
                if not u:
                    continue
                ok = await telegram_tools.join_chat(self.client, u)
                if ok:
                    console.print(f"    [green]✅ Joined @{u} (TG search)[/green]")
                    await asyncio.sleep(4)
                    return u
        except Exception:
            pass

        return None

    # ── Phase 3: READ THE ROOM ───────────────────────────────────────────────

    async def read_room(self, chat_id: str) -> str:
        """
        Read recent group messages to understand project vibe and who is active.
        Returns a compact text summary for AI context.
        """
        try:
            msgs = await telegram_tools.get_chat_history(self.client, chat_id, limit=40)
            lines = [
                f"[user_{m.get('from_id','')}]: {m.get('text','')[:120]}"
                for m in msgs[:25]
            ]
            return "\n".join(lines)
        except Exception:
            return ""

    # ── Phase 4: IDENTIFY CEO / FOUNDER ─────────────────────────────────────

    async def identify_decision_maker(self, chat_id: str, project_name: str,
                                      room_context: str) -> dict | None:
        """
        Harvest group members → AI identifies the CEO/founder/owner.
        Returns: {"tg_id","username","first_name","reason","confidence"} or None.
        """
        members = await telegram_tools.get_group_members(self.client, chat_id, limit=150)
        if not members:
            return None

        raw = ai_tools.think(
            system_addon="""You are a detective identifying the CEO, founder, owner, or key decision maker of a Web3 project from its Telegram group.

Signals to look for (in order of importance):
1. Username or name contains: founder, ceo, owner, lead, core, official, admin, dev
2. Name closely matches the project name
3. They posted announcements or authority-level messages in the group chat
4. Single unique name that sounds like a founder (rare name pattern)
5. Low user ID (early Telegram accounts often belong to founders)

Return ONLY valid JSON (no markdown):
{"tg_id": 12345, "username": "handle_or_empty", "first_name": "Name", "reason": "specific reason you chose them", "confidence": 75}

If confidence < 35, return the single word: null""",
            user_prompt=(
                f"Project: {project_name}\n\n"
                f"Recent group messages (who's talking like an authority):\n{room_context[:700]}\n\n"
                f"Full member list ({len(members)} members — first 80 shown):\n"
                + json.dumps(members[:80], indent=2)
            ),
            max_tokens=400,
        )

        try:
            raw_s = raw.strip()
            if raw_s.lower() in ("null", "none", ""):
                return None
            m = re.search(r'\{.*?\}', raw_s, re.DOTALL)
            if not m:
                return None
            result = json.loads(m.group())
            if result and int(result.get("confidence", 0)) >= 35:
                return result
        except Exception:
            pass
        return None

    # ── Phase 5: CRAFT PERSONALIZED DM ──────────────────────────────────────

    def craft_outreach_dm(self, target: dict, project: dict, room_context: str) -> str:
        """AI writes a hyper-personalized DM using Ashiq's real stats."""
        MY_PROFILE = (
            "NAME: Ashiq (@ashiq80) | Kashmir, India | fully remote\n"
            "STATS: 16,000+ Web3 Twitter/X followers (100% organic) | "
            "6,000+ member community (Telegram, Discord, OpenChat, DSCVR)\n"
            "PAST: EMC Protocol, ICPepeworld, Network3, LingoAI, RIDO, JarvisBot_AI\n"
            "SKILLS: Community Manager, Content Creator, Social Media Manager, "
            "AI prompt engineering, agentic AI systems, data annotation\n"
            "EDGE: builds autonomous AI systems — can automate growth, outreach, community ops"
        )
        role = project.get("role", "community/content")
        stat = ("16K Twitter followers" if "social" in role or "content" in role or "marketing" in role
                else "6K-member community" if "community" in role or "moderator" in role
                else "autonomous agentic AI systems")
        return ai_tools.think(
            system_addon=f"""You are writing a Telegram DM for Ashiq, a Web3/AI community specialist.

ASHIQ'S PROFILE:
{MY_PROFILE}

RULES — ALL must be followed:
- MAX 3 sentences — brevity is confidence
- Open with something SPECIFIC about the project (not "I saw your project")
- Drop ONE concrete stat that matches their need: {stat}
- End with ONE soft, specific question — not "are you hiring?"
- NO emojis, NO hashtags, NO "Dear", NO "Hi there!", NO "I came across"
- Sign off: Ashiq | @ashiq80
- Return ONLY the message text — no quotes, no extra lines""",
            user_prompt=(
                f"Project: {project.get('name')}\n"
                f"Role needed: {role}\n"
                f"What they do: {project.get('description', '')}\n"
                f"Recipient: {target.get('first_name', '')} (@{target.get('username', '')})\n"
                f"Why likely founder: {target.get('reason', '')}\n"
                f"Group vibe: {room_context[:200]}\n\n"
                "Write the DM:"
            ),
            max_tokens=220,
        )

    # ── Phase 6: SEND + LOG ──────────────────────────────────────────────────

    async def send_outreach(self, target: dict, project: dict, msg: str) -> bool:
        if not msg or len(msg) < 15 or msg.startswith("["):
            return False

        tg_id    = target.get("tg_id") or target.get("user_id")
        username = target.get("username", "")

        sent = False
        try:
            if username:
                r = await telegram_tools.send_dm(self.client, f"@{username}", msg)
                sent = bool(r)
            if not sent and tg_id:
                r = await telegram_tools.send_dm(self.client, int(tg_id), msg)
                sent = bool(r)
        except Exception as e:
            console.print(f"    [red]DM error: {e}[/red]")

        if sent:
            await self.db.log_message("out", tg_id or 0, "user", msg, 0)
            name = project.get("name", "")
            who  = target.get("first_name", username)
            console.print(f"    [bold green]✉️  Sent to {who} at {name}[/bold green]")
            console.print(f"    [dim]\"{msg[:90]}...\"[/dim]")

        return sent

    # ── FULL PIPELINE ────────────────────────────────────────────────────────

    async def smart_hunt_cycle(self) -> int:
        """
        Execute the full 6-phase 500 IQ pipeline.
        Returns number of outreach DMs successfully sent.
        """
        console.print(Rule("[bold cyan]🧠 500 IQ SMART HUNT[/bold cyan]"))

        # Phase 1
        console.print("[dim]🔍 Discovering projects via web + X...[/dim]")
        projects = await self.discover_opportunities()
        if not projects:
            console.print("[yellow]No new projects found this cycle.[/yellow]")
            return 0
        console.print(f"[cyan]→ {len(projects)} candidate projects[/cyan]")

        contacted = 0
        for project in projects[:8]:  # up to 8 per cycle
            name = project.get("name", "unknown")
            role = project.get("role", "role")
            console.print(f"\n  [bold]◆ {name}[/bold] — {role}")

            try:
                # Phase 2
                console.print("  [dim]📡 Infiltrating Telegram group...[/dim]")
                chat_id = await self.infiltrate_project(project)
                if not chat_id:
                    console.print("  [yellow]No group found — skipping[/yellow]")
                    continue

                # Phase 3
                console.print("  [dim]👁  Reading the room...[/dim]")
                room = await self.read_room(chat_id)

                # Phase 4
                console.print("  [dim]🎯 Identifying decision maker...[/dim]")
                target = await self.identify_decision_maker(chat_id, name, room)
                if not target:
                    console.print("  [yellow]No clear founder/CEO found — skipping[/yellow]")
                    continue

                fname = target.get("first_name", "?")
                uname = target.get("username", "")
                conf  = target.get("confidence", 0)
                console.print(f"  [green]🎯 {fname} (@{uname}) — {conf}% confidence[/green]")
                console.print(f"  [dim]Reason: {target.get('reason','')[:80]}[/dim]")

                # Dedup guard
                key = f"{name}__{target.get('tg_id', uname)}"
                if key in self._contacted:
                    console.print("  [dim]Already contacted — skipping[/dim]")
                    continue

                # Phase 5
                console.print("  [dim]✍️  Crafting personalized DM...[/dim]")
                msg = self.craft_outreach_dm(target, project, room)

                # Phase 6
                sent = await self.send_outreach(target, project, msg)
                if sent:
                    contacted += 1
                    self._contacted.add(key)
                    await self.memory.remember(
                        key=f"outreach_{key}",
                        value=f"DM to {fname} at {name} for {role}: {msg[:120]}",
                        memory_type="outreach",
                        score=1.0,
                    )

                # Rate limit between sends
                await asyncio.sleep(Config.RATE_LIMIT_SLEEP * 5)

            except Exception as e:
                console.print(f"  [red]Error on {name}: {e}[/red]")
                continue

        # Mark all projects seen this cycle so we don't re-process next cycle
        for p in projects[:8]:
            self._contacted.add(p.get("name", ""))

        console.print(f"\n[bold green]Hunt done: {contacted} DMs sent[/bold green]")
        return contacted

    # ══════════════════════════════════════════════════════════════════════════
    #  GENERAL OBSERVE → THINK → PLAN → ACT LOOP
    # ══════════════════════════════════════════════════════════════════════════

    # Tools the general loop may NOT use (only smart_hunt sends strategically)
    _GENERAL_BLOCKED = {"post_in_group", "post_to_all_groups", "send_dm",
                        "reply_to_dm", "send_to_username"}

    async def observe(self) -> str:
        stats  = await self.db.get_stats()
        groups = await self.db.get_groups(joined=True)
        jobs   = await self.db.get_jobs(applied=False)
        best   = await self.memory.best_strategies()
        return (
            f"STATE (cycle {self.cycle}) — {datetime.now().strftime('%H:%M %d/%m')}:\n"
            f"Groups joined: {len(groups)} | Jobs pending: {len(jobs)} | "
            f"Messages sent: {stats.get('messages_sent', 0)} | "
            f"Outreach this session: {len(self._contacted)}\n\n"
            f"TOP STRATEGIES:\n{best}\n\n"
            f"RECENT ACTIONS:\n" + "\n".join(self.action_log[-5:] or ["None yet"])
        )

    def think(self, obs: str) -> str:
        return ai_tools.think(
            system_addon=MASTER_GOAL + "\nThink in 2 sentences then output: CONCLUSION: [what to do now]",
            user_prompt=f"STATE:\n{obs}\n\nTOOLS:\n{self.tools.descriptions}\n\nReason:",
            max_tokens=300,
        )

    def plan(self, thought: str, obs: str) -> list[dict]:
        raw = ai_tools.think(
            system_addon=(
                "Convert reasoning into a JSON action plan. "
                "Return ONLY a JSON array, no markdown:\n"
                '[{"step":1,"reason":"why","tool":"tool_name","args":{"k":"v"}}]\n'
                "Max 4 steps. Only use available tools. "
                "DO NOT plan post_in_group, send_dm, reply_to_dm — the smart hunt handles sends."
            ),
            user_prompt=f"THOUGHT:\n{thought}\n\nSTATE:\n{obs}\n\nTOOLS:\n{self.tools.descriptions}\n\nJSON:",
            max_tokens=500,
        )
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            try:
                steps = json.loads(m.group())
                return [s for s in steps if isinstance(s, dict) and "tool" in s]
            except Exception:
                pass
        return [{"step": 1, "reason": "Check state", "tool": "get_stats", "args": {}}]

    async def act(self, plan: list[dict]) -> list[dict]:
        results = []
        for step in plan:
            tool   = step.get("tool", "")
            args   = step.get("args", {})
            reason = step.get("reason", "")

            # General loop cannot send messages — only smart_hunt does targeted sends
            if tool in self._GENERAL_BLOCKED:
                console.print(f"  [yellow]⚠ Blocked {tool} in general loop — use /hunt for sends[/yellow]")
                results.append({"step": step, "result": {"ok": False, "error": "blocked"}})
                continue

            console.print(f"  [cyan]▶ [{tool}][/cyan] {reason}")
            result = await self.tools.call(tool, **args)
            results.append({"step": step, "result": result})

            ts = datetime.now().strftime("%H:%M")
            ok_str = "✅" if result.get("ok") else "❌"
            self.action_log.append(f"[{ts}] {tool} → {ok_str}")

            if result.get("ok"):
                out = result.get("result", "")
                console.print(f"    [green]✅ {str(out)[:80]}[/green]")
            else:
                console.print(f"    [red]❌ {result.get('error','?')}[/red]")

            await asyncio.sleep(2)
        return results

    async def reflect(self, obs: str, results: list[dict]) -> str:
        summary = json.dumps([
            {"tool": r["step"]["tool"], "ok": r["result"].get("ok"),
             "out": str(r["result"].get("result",""))[:80]}
            for r in results
        ])
        return ai_tools.think(
            system_addon="Analyze what happened in 2 sentences. What to do differently next cycle?",
            user_prompt=f"STATE: {obs[:250]}\nRESULTS: {summary}\nAnalysis:",
            max_tokens=150,
        )

    async def learn(self, reflection: str, results: list[dict]):
        for r in results:
            score = 1.0 if r["result"].get("ok") else -0.5
            await self.memory.remember(
                key=f"tool_{r['step']['tool']}_c{self.cycle}",
                value=f"{r['step']['tool']}: {'ok' if r['result'].get('ok') else 'fail'}",
                memory_type="tool_performance",
                score=score,
            )
        if reflection and not reflection.startswith("["):
            await self.memory.remember(
                key=f"strategy_c{self.cycle}",
                value=reflection[:200],
                memory_type="strategy",
                score=0,
            )

    async def handle_inbox(self):
        """Log unread count — NEVER auto-reply to strangers."""
        try:
            dialogs = await telegram_tools.get_dialogs(self.client, limit=20)
            unread  = [d for d in dialogs if d.get("unread", 0) > 0]
            if unread:
                console.print(f"  [yellow]📬 {len(unread)} unread — reply manually if needed[/yellow]")
        except Exception as e:
            console.print(f"  [red]Inbox check: {e}[/red]")

    def _sleep_minutes(self, results: list[dict]) -> int:
        if not results:
            return 20
        rate = sum(1 for r in results if r["result"].get("ok")) / len(results)
        return 10 if rate >= 0.8 else (20 if rate >= 0.5 else 30)

    # ══════════════════════════════════════════════════════════════════════════
    #  MAIN AUTONOMOUS LOOP
    # ══════════════════════════════════════════════════════════════════════════

    async def run_forever(self):
        console.print(Panel(
            "[bold magenta]🧠 500 IQ AGENTIC ORCHESTRATOR — ONLINE[/bold magenta]\n\n"
            "[white]Every cycle:[/white]\n"
            "  Observe → Think → Plan → Act → Reflect → Learn\n\n"
            "[white]Every 3rd cycle (SMART HUNT):[/white]\n"
            "  🔍 Discover projects via web + X/Twitter\n"
            "  📡 Find & join their Telegram group\n"
            "  👁  Read the room\n"
            "  🎯 Identify CEO / Founder\n"
            "  ✍️  Craft personalized DM\n"
            "  ✉️  Send outreach\n\n"
            "[dim]No auto-replies. No random posts. Only strategic sends.[/dim]",
            border_style="magenta",
        ))

        while True:
            # Respect pause flag — check every 10s while paused
            if self._paused:
                await asyncio.sleep(10)
                continue

            self.cycle += 1
            console.print(Rule(f"[bold]CYCLE {self.cycle} — {datetime.now().strftime('%H:%M:%S')}[/bold]"))

            try:
                # Smart hunt on every Nth cycle (default every 2nd)
                if self.cycle % self._hunt_every == 0:
                    await self.smart_hunt_cycle()

                # General loop — always runs
                obs        = await self.observe()
                thought    = self.think(obs)
                console.print(f"[dim italic]{thought[:200]}[/dim italic]")
                plan       = self.plan(thought, obs)
                results    = await self.act(plan)
                await self.handle_inbox()
                reflection = await self.reflect(obs, results)
                await self.learn(reflection, results)

                sleep_min = self._sleep_minutes(results)
                console.print(f"[dim]💤 Sleeping {sleep_min} min[/dim]")
                await asyncio.sleep(sleep_min * 60)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                console.print(f"[red]Cycle {self.cycle} crashed: {e}[/red]")
                await asyncio.sleep(300)
