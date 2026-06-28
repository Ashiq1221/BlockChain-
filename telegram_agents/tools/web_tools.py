"""Web search and scraping tools for enriching agent context."""
import aiohttp
from bs4 import BeautifulSoup
from telegram_agents.config import Config


async def web_search(query: str, num: int = 5) -> list[dict]:
    """Search via SerpAPI if key is configured, otherwise use DuckDuckGo lite."""
    if Config.SERPAPI_KEY:
        return await _serpapi_search(query, num)
    return await _ddg_search(query, num)


async def _serpapi_search(query: str, num: int) -> list[dict]:
    url = "https://serpapi.com/search"
    params = {"q": query, "num": num, "api_key": Config.SERPAPI_KEY, "engine": "google"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            results = []
            for item in data.get("organic_results", [])[:num]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results


async def _ddg_search(query: str, num: int) -> list[dict]:
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    results = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data={"q": query}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                for r in soup.select(".result__body")[:num]:
                    title_el = r.select_one(".result__title")
                    snippet_el = r.select_one(".result__snippet")
                    link_el = r.select_one(".result__url")
                    results.append({
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "url": link_el.get_text(strip=True) if link_el else "",
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
    except Exception:
        pass
    return results


async def fetch_page(url: str) -> str:
    """Fetch a web page and return clean text (no HTML tags)."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:4000]
    except Exception:
        return ""


async def find_telegram_groups_online(topic: str) -> list[dict]:
    """Search the web for public Telegram groups on a given topic."""
    results = await web_search(f"site:t.me {topic} group OR channel", num=10)
    groups = []
    for r in results:
        url = r.get("url", "")
        if "t.me/" in url:
            username = url.split("t.me/")[-1].split("?")[0].strip("/")
            if username:
                groups.append({
                    "username": username,
                    "title": r.get("title", username),
                    "snippet": r.get("snippet", ""),
                    "url": url,
                })
    return groups
