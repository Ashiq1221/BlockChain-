"""
AI Provider abstraction — Claude, Gemini, Groq, DeepSeek, OpenAI, Search.
All use direct HTTP calls — no SDKs, works on Android/Termux.
Auto-fallback: Claude → Gemini → Groq → OpenAI.
"""
import asyncio
import json
import re
import aiohttp
from bs4 import BeautifulSoup
from .config import AOSConfig as C

_TIMEOUT = aiohttp.ClientTimeout(total=30)
_DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


# ── Core callers ──────────────────────────────────────────────────────────────

async def call_claude(prompt: str, system: str = "", max_tokens: int = 1000) -> str:
    if not C.CLAUDE_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": C.CLAUDE_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": C.CLAUDE_MODEL,
                    "max_tokens": max_tokens,
                    "system": system or "You are a helpful, precise assistant.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return data.get("content", [{}])[0].get("text", "").strip()
    except Exception as e:
        return f"[claude_error: {e}]"


async def call_gemini(prompt: str, system: str = "", max_tokens: int = 1000) -> str:
    if not C.GEMINI_KEY:
        return ""
    try:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{C.GEMINI_MODEL}:generateContent",
                params={"key": C.GEMINI_KEY},
                json={
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
                },
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return (data.get("candidates", [{}])[0]
                        .get("content", {}).get("parts", [{}])[0]
                        .get("text", "")).strip()
    except Exception as e:
        return f"[gemini_error: {e}]"


async def call_groq(prompt: str, system: str = "", max_tokens: int = 1000,
                    model: str = "") -> str:
    if not C.GROQ_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {C.GROQ_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": model or C.GROQ_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system or "You are a helpful assistant."},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[groq_error: {e}]"


async def call_deepseek(prompt: str, system: str = "", max_tokens: int = 2000) -> str:
    if not C.DEEPSEEK_KEY:
        # Fall back to Groq for coding tasks
        return await call_groq(prompt, system, max_tokens, model="llama-3.3-70b-versatile")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {C.DEEPSEEK_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": C.DEEPSEEK_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system or "You are an expert programmer."},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[deepseek_error: {e}]"


async def call_openai(prompt: str, system: str = "", max_tokens: int = 1000) -> str:
    if not C.OPENAI_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {C.OPENAI_KEY}",
                         "Content-Type": "application/json"},
                json={
                    "model": C.OPENAI_MODEL,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": system or "You are a helpful assistant."},
                        {"role": "user",   "content": prompt},
                    ],
                },
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[openai_error: {e}]"


async def think(prompt: str, system: str = "", max_tokens: int = 1000,
                prefer: str = "claude") -> str:
    """Auto-select provider with fallback chain."""
    order = {
        "claude":   [call_claude, call_gemini, call_groq, call_openai],
        "gemini":   [call_gemini, call_claude, call_groq, call_openai],
        "groq":     [call_groq, call_claude, call_gemini, call_openai],
        "deepseek": [call_deepseek, call_claude, call_groq, call_openai],
        "openai":   [call_openai, call_claude, call_gemini, call_groq],
    }.get(prefer, [call_claude, call_gemini, call_groq, call_openai])

    for caller in order:
        result = await caller(prompt, system, max_tokens)
        if result and not result.startswith("[") and len(result) > 5:
            return result
    return "Unable to generate response — all providers failed."


# ── Search ────────────────────────────────────────────────────────────────────

async def search_tavily(query: str, num: int = 5) -> list[dict]:
    if not C.TAVILY_KEY:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.tavily.com/search",
                json={"api_key": C.TAVILY_KEY, "query": query,
                      "max_results": num, "search_depth": "advanced"},
                timeout=_TIMEOUT,
            ) as r:
                data = await r.json()
                return [{"title": i.get("title",""), "url": i.get("url",""),
                         "snippet": i.get("content","")} for i in data.get("results",[])]
    except Exception:
        return []


async def search_bing(query: str, num: int = 5) -> list[dict]:
    try:
        async with aiohttp.ClientSession(headers=_DDG_HEADERS) as s:
            async with s.get("https://www.bing.com/search",
                             params={"q": query, "count": num},
                             timeout=_TIMEOUT) as r:
                html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for item in soup.select(".b_algo")[:num]:
                    a   = item.select_one("h2 a")
                    snip = item.select_one(".b_caption p")
                    if a:
                        results.append({
                            "title":   a.get_text(strip=True),
                            "url":     a.get("href",""),
                            "snippet": snip.get_text(strip=True) if snip else "",
                        })
                return results
    except Exception:
        return []


async def search_ddg(query: str, num: int = 5) -> list[dict]:
    try:
        async with aiohttp.ClientSession(headers=_DDG_HEADERS) as s:
            async with s.post("https://html.duckduckgo.com/html/",
                              data={"q": query}, timeout=_TIMEOUT) as r:
                html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for item in soup.select(".result")[:num]:
                    t = item.select_one(".result__title")
                    sn = item.select_one(".result__snippet")
                    a  = item.select_one("a[href]")
                    if t:
                        href = a.get("href","") if a else ""
                        m = re.search(r'uddg=([^&]+)', href)
                        results.append({
                            "title":   t.get_text(strip=True),
                            "url":     m.group(1) if m else href,
                            "snippet": sn.get_text(strip=True) if sn else "",
                        })
                return [r for r in results if r["title"]]
    except Exception:
        return []


async def search(query: str, num: int = 5) -> list[dict]:
    """Best available search: Tavily → Bing → DDG."""
    r = await search_tavily(query, num)
    if r: return r
    r = await search_bing(query, num)
    if r: return r
    return await search_ddg(query, num)


async def fetch_page(url: str) -> str:
    try:
        async with aiohttp.ClientSession(headers=_DDG_HEADERS) as s:
            async with s.get(url, timeout=_TIMEOUT) as r:
                html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script","style","nav","footer","header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:4000]
    except Exception:
        return ""
