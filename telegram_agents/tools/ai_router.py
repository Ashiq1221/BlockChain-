"""
2-provider AI router — Groq + OpenAI race in parallel.

  RACE  (default): both providers fire simultaneously, first to respond wins.
  DEBATE: both answer, then the other synthesizes the best combined answer.

Key pools (up to 5 keys each, auto-rotate + rate-limit cooldown):
  GROQ_KEY_1…5   / GROQ_API_KEY1…5   (+ legacy GROQ_API_KEY)
  OPENAI_KEY_1…5 / OPENAI_API_KEY1…5 (+ legacy OPENAI_API_KEY)
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from rich.console import Console

from telegram_agents.tools.key_pool import KeyPool
from telegram_agents.config import Config

console = Console()

# ── Key pools ─────────────────────────────────────────────────────────────────

_GROQ_POOL   = KeyPool(Config.GROQ_KEYS,   cooldown_secs=60)
_OPENAI_POOL = KeyPool(Config.OPENAI_KEYS, cooldown_secs=90)

# ── Thread pool ───────────────────────────────────────────────────────────────

_EXECUTOR    = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ai_parallel")
_AGENT_SLOTS = None


def _get_gate() -> asyncio.Semaphore:
    global _AGENT_SLOTS
    if _AGENT_SLOTS is None:
        _AGENT_SLOTS = asyncio.Semaphore(6)
    return _AGENT_SLOTS


class _RateLimit(Exception):
    pass


# ── Provider callers ──────────────────────────────────────────────────────────

import httpx as _httpx


def _call_groq(key: str, system: str, prompt: str, max_tokens: int) -> str:
    resp = _httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": prompt}],
        },
        timeout=30,
    )
    if resp.status_code == 429:
        raise _RateLimit()
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_openai(key: str, system: str, prompt: str, max_tokens: int) -> str:
    resp = _httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-4o-mini",
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user",   "content": prompt}],
        },
        timeout=45,
    )
    if resp.status_code in (429, 402):
        raise _RateLimit()
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── Provider registry ─────────────────────────────────────────────────────────

_PROVIDERS: list[tuple[str, KeyPool, callable]] = [
    ("Groq",   _GROQ_POOL,   _call_groq),
    ("OpenAI", _OPENAI_POOL, _call_openai),
]

_busy_agents = 0


# ── Sync race ─────────────────────────────────────────────────────────────────

def route(system: str, prompt: str, max_tokens: int = 1024) -> str:
    """Fire Groq + OpenAI in parallel — first success wins."""
    global _busy_agents
    _busy_agents += 1
    errors: list[str] = []

    try:
        tasks = []
        for name, pool, call_fn in _PROVIDERS:
            key = pool.next()
            if key is not None:
                tasks.append((name, key, pool, call_fn))

        if not tasks:
            return "[AI router: all keys cooling — try again in 60s]"

        with ThreadPoolExecutor(max_workers=len(tasks)) as exe:
            future_map = {
                exe.submit(call_fn, key, system, prompt, max_tokens): (name, pool, key)
                for name, key, pool, call_fn in tasks
            }
            for fut in as_completed(future_map):
                name, pool, key = future_map[fut]
                try:
                    result = fut.result()
                    console.print(f"[dim green]⚡ {name} answered first[/dim green]")
                    return result
                except _RateLimit:
                    pool.mark_rate_limited(key)
                    errors.append(f"{name}: rate-limited")
                except Exception as e:
                    errors.append(f"{name}: {str(e)[:80]}")

        return f"[AI router: all providers failed — {' | '.join(errors)}]"
    finally:
        _busy_agents -= 1


# ── Sync debate ───────────────────────────────────────────────────────────────

def route_debate(system: str, prompt: str, max_tokens: int = 1024) -> str:
    """Both providers answer, then the other synthesizes the best combined answer."""
    global _busy_agents
    _busy_agents += 1
    errors: list[str] = []
    results: dict[str, str] = {}

    try:
        tasks = []
        for name, pool, call_fn in _PROVIDERS:
            key = pool.next()
            if key is not None:
                tasks.append((name, key, pool, call_fn))

        if not tasks:
            return "[AI debate: all keys cooling — try again in 60s]"

        with ThreadPoolExecutor(max_workers=len(tasks)) as exe:
            future_map = {
                exe.submit(call_fn, key, system, prompt, max_tokens): (name, pool, key)
                for name, key, pool, call_fn in tasks
            }
            for fut in as_completed(future_map):
                name, pool, key = future_map[fut]
                try:
                    results[name] = fut.result()
                    console.print(f"[dim cyan]💬 {name} responded[/dim cyan]")
                except _RateLimit:
                    pool.mark_rate_limited(key)
                    errors.append(f"{name}: rate-limited")
                except Exception as e:
                    errors.append(f"{name}: {str(e)[:80]}")

        if not results:
            return f"[AI debate: all providers failed — {' | '.join(errors)}]"
        if len(results) == 1:
            return next(iter(results.values()))

        debate_block = "\n\n".join(f"=== {n} ===\n{r}" for n, r in results.items())
        synth_prompt = (
            f"Original question:\n{prompt}\n\n"
            f"Two AI systems answered independently:\n\n{debate_block}\n\n"
            "Synthesize the strongest points into one definitive, concise answer. "
            "Do not mention the AI names — just give the best answer."
        )
        console.print("[dim yellow]🤝 Synthesizing...[/dim yellow]")
        return route(system, synth_prompt, max_tokens)

    finally:
        _busy_agents -= 1


# ── Sync wrappers ─────────────────────────────────────────────────────────────

def think_sync(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    from telegram_agents.tools.ai_tools import SYSTEM_BASE
    return route(SYSTEM_BASE + "\n" + system_addon, user_prompt, max_tokens)


def think_debate_sync(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    from telegram_agents.tools.ai_tools import SYSTEM_BASE
    return route_debate(SYSTEM_BASE + "\n" + system_addon, user_prompt, max_tokens)


# ── Async race ────────────────────────────────────────────────────────────────

async def think(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    from telegram_agents.tools.ai_tools import SYSTEM_BASE
    system = SYSTEM_BASE + "\n" + system_addon

    gate = _get_gate()
    async with gate:
        loop = asyncio.get_event_loop()
        errors: list[str] = []
        future_map: dict[asyncio.Future, tuple[str, KeyPool, str]] = {}

        for name, pool, call_fn in _PROVIDERS:
            key = pool.next()
            if key is None:
                errors.append(f"{name}: all keys cooling")
                continue
            fut = loop.run_in_executor(_EXECUTOR, call_fn, key, system, user_prompt, max_tokens)
            future_map[fut] = (name, pool, key)

        if not future_map:
            return f"[AI router: all keys cooling — {' | '.join(errors)}]"

        pending = set(future_map.keys())
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for fut in done:
                name, pool, key = future_map[fut]
                try:
                    result = fut.result()
                    console.print(f"[dim green]⚡ {name} answered first[/dim green]")
                    for p in pending:
                        p.cancel()
                    return result
                except _RateLimit:
                    pool.mark_rate_limited(key)
                    errors.append(f"{name}: rate-limited")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    errors.append(f"{name}: {str(e)[:80]}")

        return f"[AI router: all providers failed — {' | '.join(errors)}]"


# ── Async debate ──────────────────────────────────────────────────────────────

async def think_debate(system_addon: str, user_prompt: str, max_tokens: int = 1024) -> str:
    from telegram_agents.tools.ai_tools import SYSTEM_BASE
    system = SYSTEM_BASE + "\n" + system_addon

    gate = _get_gate()
    async with gate:
        loop = asyncio.get_event_loop()
        errors: list[str] = []
        results: dict[str, str] = {}
        future_map: dict[asyncio.Future, tuple[str, KeyPool, str]] = {}

        for name, pool, call_fn in _PROVIDERS:
            key = pool.next()
            if key is None:
                errors.append(f"{name}: all keys cooling")
                continue
            fut = loop.run_in_executor(_EXECUTOR, call_fn, key, system, user_prompt, max_tokens)
            future_map[fut] = (name, pool, key)

        if not future_map:
            return f"[AI debate: all keys cooling — {' | '.join(errors)}]"

        done, _ = await asyncio.wait(future_map.keys(), return_when=asyncio.ALL_COMPLETED)
        for fut in done:
            name, pool, key = future_map[fut]
            try:
                results[name] = fut.result()
                console.print(f"[dim cyan]💬 {name} responded[/dim cyan]")
            except _RateLimit:
                pool.mark_rate_limited(key)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                errors.append(f"{name}: {str(e)[:80]}")

        if not results:
            return f"[AI debate: all providers failed — {' | '.join(errors)}]"
        if len(results) == 1:
            return next(iter(results.values()))

        debate_block = "\n\n".join(f"=== {n} ===\n{r}" for n, r in results.items())
        synth_prompt = (
            f"Original question:\n{user_prompt}\n\n"
            f"Two AI systems answered independently:\n\n{debate_block}\n\n"
            "Synthesize the strongest points into one definitive, concise answer. "
            "Do not mention the AI names — just give the best answer."
        )
        console.print("[dim yellow]🤝 Synthesizing debate...[/dim yellow]")
        return await think(system_addon, synth_prompt, max_tokens)


# ── Status ────────────────────────────────────────────────────────────────────

def router_status() -> str:
    lines = [f"Providers: Groq + OpenAI | Busy: {_busy_agents}"]
    for name, pool, _ in _PROVIDERS:
        s   = pool.status()
        bar = ("🟢" * s["available"]) + ("🔴" * s["cooling"]) + ("⚫" * (s["total"] - s["available"] - s["cooling"]))
        lines.append(f"  {name:<8} {bar}  ({s['available']}/{s['total']} live)")
    return "\n".join(lines)
