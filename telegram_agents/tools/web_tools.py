"""Web search — multiple engines with automatic fallback."""
import re
import aiohttp
from bs4 import BeautifulSoup
from telegram_agents.config import Config

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}


async def web_search(query: str, num: int = 5) -> list[dict]:
    """Try multiple search engines until one returns results."""
    if Config.SERPAPI_KEY:
        r = await _serpapi(query, num)
        if r: return r

    r = await _ddg(query, num)
    if r: return r

    r = await _ddg_lite(query, num)
    if r: return r

    return []


async def _serpapi(query: str, num: int) -> list[dict]:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://serpapi.com/search",
                params={"q": query, "num": num, "api_key": Config.SERPAPI_KEY, "engine": "google"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                return [{"title": i.get("title",""), "url": i.get("link",""), "snippet": i.get("snippet","")}
                        for i in data.get("organic_results", [])[:num]]
    except Exception:
        return []


async def _ddg(query: str, num: int) -> list[dict]:
    """DuckDuckGo HTML search."""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": "", "kl": "us-en"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for r in soup.select(".result")[:num]:
                    title_el   = r.select_one(".result__title")
                    snippet_el = r.select_one(".result__snippet")
                    link_el    = r.select_one(".result__url")
                    a_el       = r.select_one(".result__title a")
                    url = ""
                    if a_el and a_el.get("href"):
                        url = a_el["href"]
                    elif link_el:
                        url = link_el.get_text(strip=True)
                    results.append({
                        "title":   title_el.get_text(strip=True)   if title_el   else "",
                        "url":     url,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
                return [r for r in results if r["title"]]
    except Exception:
        return []


async def _ddg_lite(query: str, num: int) -> list[dict]:
    """DuckDuckGo lite fallback."""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for a in soup.select("a.result-link")[:num]:
                    results.append({
                        "title":   a.get_text(strip=True),
                        "url":     a.get("href", ""),
                        "snippet": "",
                    })
                return results
    except Exception:
        return []


async def fetch_page(url: str) -> str:
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script","style","nav","footer","header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:5000]
    except Exception:
        return ""


async def find_telegram_groups_online(topic: str) -> list[dict]:
    results = await web_search(f"t.me {topic} telegram group channel", num=10)
    groups = []
    for r in results:
        url = r.get("url", "")
        text = r.get("title","") + " " + r.get("snippet","") + " " + url
        # Extract t.me links from anywhere in the result
        found = re.findall(r't\.me/([\w]+)', text)
        for username in found:
            if len(username) > 3 and username not in ("joinchat","s","share"):
                groups.append({
                    "username": username,
                    "title": r.get("title", username),
                    "snippet": r.get("snippet",""),
                    "url": f"https://t.me/{username}",
                })
    return groups


async def search_x_opportunities(role: str) -> list[dict]:
    """Search for Web3/AI opportunities on X via web search."""
    queries = [
        f'"{role}" web3 crypto 2025 telegram apply',
        f'"{role}" AI project hiring 2025 telegram contact',
        f'site:twitter.com "{role}" web3 crypto 2025',
    ]
    all_results = []
    for q in queries:
        results = await web_search(q, num=5)
        all_results.extend(results)
    return all_results
