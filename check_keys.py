"""
API Key Status Checker
Run: python check_keys.py

Tests every provider with a real ping and shows what's working.
"""
import asyncio, sys, subprocess

for pkg in ["aiohttp", "python-dotenv", "rich"]:
    try: __import__(pkg.replace("-","_"))
    except ImportError:
        subprocess.call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                        stderr=subprocess.DEVNULL)

import aiohttp
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
load_dotenv()

import os
console = Console()

TIMEOUT = aiohttp.ClientTimeout(total=10)

PROVIDERS = {
    "Claude (Anthropic)":   "ANTHROPIC_API_KEY",
    "OpenAI (GPT)":         "OPENAI_API_KEY",
    "Groq (fast/free)":     "GROQ_API_KEY",
    "Gemini (Google)":      "GEMINI_API_KEY",
    "DeepSeek (coding)":    "DEEPSEEK_API_KEY",
    "Tavily (search)":      "TAVILY_API_KEY",
    "Telegram Bot Token":   "TELEGRAM_BOT_TOKEN",
    "Telegram Owner ID":    "TELEGRAM_OWNER_ID",
}


async def test_claude(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": "claude-haiku-4-5-20251001", "max_tokens": 10,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200:
                    return True, "✅ Working"
                elif r.status == 401:
                    return False, "❌ Invalid key"
                elif r.status in (429, 529):
                    return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def test_openai(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200: return True, "✅ Working"
                if r.status == 401: return False, "❌ Invalid key"
                if r.status == 429: return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def test_groq(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "llama-3.3-70b-versatile", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200: return True, "✅ Working"
                if r.status == 401: return False, "❌ Invalid key"
                if r.status == 429: return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def test_gemini(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}",
                json={"contents": [{"parts": [{"text": "hi"}]}],
                      "generationConfig": {"maxOutputTokens": 5}},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200: return True, "✅ Working"
                if r.status == 400: return False, "❌ Invalid key / bad request"
                if r.status == 403: return False, "❌ API not enabled"
                if r.status == 429: return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def test_deepseek(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "max_tokens": 5,
                      "messages": [{"role": "user", "content": "hi"}]},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200: return True, "✅ Working"
                if r.status == 401: return False, "❌ Invalid key"
                if r.status == 429: return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def test_tavily(key: str) -> tuple[bool, str]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.tavily.com/search",
                json={"api_key": key, "query": "test", "max_results": 1},
                timeout=TIMEOUT,
            ) as r:
                if r.status == 200: return True, "✅ Working"
                if r.status == 401: return False, "❌ Invalid key"
                if r.status == 429: return True, "⚠️  Rate limited (key valid)"
                return False, f"❌ HTTP {r.status}"
    except Exception as e:
        return False, f"❌ {str(e)[:40]}"


async def main():
    console.print("\n[bold magenta]🔑 AOS API Key Status[/bold magenta]\n")

    keys = {name: os.getenv(env, "") for name, env in PROVIDERS.items()}

    t = Table(show_header=True, header_style="bold cyan", border_style="dim")
    t.add_column("Provider",   width=24)
    t.add_column("Key",        width=18)
    t.add_column("Status",     width=32)
    t.add_column("Role in AOS", width=28)

    ROLES = {
        "Claude (Anthropic)":  "Orchestrator + Final Writer",
        "OpenAI (GPT)":        "Fallback (critics/judge)",
        "Groq (fast/free)":    "Critics + fast tasks (FREE)",
        "Gemini (Google)":     "Reasoning + Vision Agent",
        "DeepSeek (coding)":   "Coding + Math Agent",
        "Tavily (search)":     "Best web search (optional)",
        "Telegram Bot Token":  "Bot chat interface",
        "Telegram Owner ID":   "Security filter",
    }

    TEST_FNS = {
        "Claude (Anthropic)":  test_claude,
        "OpenAI (GPT)":        test_openai,
        "Groq (fast/free)":    test_groq,
        "Gemini (Google)":     test_gemini,
        "DeepSeek (coding)":   test_deepseek,
        "Tavily (search)":     test_tavily,
    }

    console.print("[dim]Testing live connections...[/dim]\n")

    for name, key in keys.items():
        role = ROLES.get(name, "")
        masked = (key[:6] + "..." + key[-4:]) if len(key) > 12 else ("(not set)" if not key else key)

        if not key:
            status = "[dim]— not set[/dim]"
        elif name in TEST_FNS:
            ok, msg = await TEST_FNS[name](key)
            status = msg
        else:
            status = "✅ Set" if key else "[dim]— not set[/dim]"

        t.add_row(name, masked, status, f"[dim]{role}[/dim]")

    console.print(t)

    # Summary
    working = sum(1 for n, k in keys.items() if k and n in TEST_FNS)
    total   = len(TEST_FNS)
    console.print(f"\n[bold]{working}/{total}[/bold] AI providers configured\n")

    # Missing key instructions
    missing = []
    if not keys.get("DeepSeek (coding)"):
        missing.append("DeepSeek  → https://platform.deepseek.com/api_keys  (free credits, best for code)")
    if not keys.get("Tavily (search)"):
        missing.append("Tavily    → https://app.tavily.com  (free tier, best web search for AOS)")
    if not keys.get("Telegram Bot Token"):
        missing.append("Bot Token → message @BotFather on Telegram → /newbot")
    if not keys.get("Telegram Owner ID"):
        missing.append("Owner ID  → message @userinfobot on Telegram")

    if missing:
        console.print("[yellow]Optional — add these to .env for full functionality:[/yellow]")
        for m in missing:
            console.print(f"  • {m}")
    else:
        console.print("[bold green]✅ All keys configured![/bold green]")

    console.print("\n[dim]To add a key: nano .env → paste value → Ctrl+O → Enter → Ctrl+X[/dim]\n")


asyncio.run(main())
