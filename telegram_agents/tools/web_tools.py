"""Web search — Firecrawl + Tavily + multi-engine fallback."""
import json
import re
import aiohttp
from bs4 import BeautifulSoup
from telegram_agents.config import Config

_TIMEOUT = aiohttp.ClientTimeout(total=30)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def x_search_jobs() -> str:
    """X/Twitter developer API — real-time search for Web3/AI job opportunities."""
    bearer = Config.X_BEARER_TOKEN
    if not bearer:
        return ""

    queries = [
        "web3 blockchain hiring community manager ambassador telegram",
        "crypto AI project moderator content creator hiring remote 2026",
        "DeFi NFT gaming startup ambassador role apply t.me",
    ]
    tweets = []
    for q in queries:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.twitter.com/2/tweets/search/recent",
                    headers={"Authorization": f"Bearer {bearer}"},
                    params={
                        "query":        f"({q}) -is:retweet lang:en",
                        "max_results":  10,
                        "tweet.fields": "author_id,created_at,text",
                        "expansions":   "author_id",
                        "user.fields":  "name,username",
                    },
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        users = {u["id"]: u for u in d.get("includes", {}).get("users", [])}
                        for t in d.get("data", []):
                            author = users.get(t.get("author_id", ""), {})
                            uname  = author.get("username", "")
                            tweets.append(
                                f"@{uname}: {t['text']}\n"
                                f"  url: https://twitter.com/{uname}/status/{t['id']}"
                            )
        except Exception:
            pass
        await asyncio.sleep(1)

    return "\n\n".join(tweets[:25]) if tweets else ""


async def _firecrawl_search(query: str, num: int) -> list[dict]:
    """Firecrawl Search API — returns clean, structured web results."""
    if not Config.FIRECRAWL_KEY:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.firecrawl.dev/v1/search",
                headers={
                    "Authorization": f"Bearer {Config.FIRECRAWL_KEY}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "limit": num, "scrapeOptions": {"formats": ["markdown"]}},
                timeout=aiohttp.ClientTimeout(total=25),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    results = []
                    for x in d.get("data", [])[:num]:
                        results.append({
                            "title":   x.get("title", ""),
                            "url":     x.get("url", ""),
                            "snippet": (x.get("description") or x.get("markdown", ""))[:300],
                        })
                    return results
    except Exception:
        pass
    return []


async def _firecrawl_scrape(url: str) -> str:
    """Firecrawl Scrape API — returns clean markdown from any URL."""
    if not Config.FIRECRAWL_KEY:
        return ""
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Authorization": f"Bearer {Config.FIRECRAWL_KEY}",
                    "Content-Type": "application/json",
                },
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return (d.get("data", {}).get("markdown") or "")[:6000]
    except Exception:
        pass
    return ""


async def _tavily(query: str, num: int) -> list[dict]:
    """Tavily API — reliable HTTPS search, works in all environments."""
    if not Config.TAVILY_KEY:
        return []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.tavily.com/search",
                json={"api_key": Config.TAVILY_KEY, "query": query,
                      "search_depth": "advanced", "max_results": num},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status == 200:
                    d = await r.json()
                    return [{"title": x.get("title", ""), "url": x.get("url", ""),
                             "snippet": x.get("content", "")[:300]}
                            for x in d.get("results", [])]
    except Exception:
        pass
    return []


async def web_search(query: str, num: int = 5) -> list[dict]:
    """Try Firecrawl → Tavily → scraping engines in order."""
    r = await _firecrawl_search(query, num)
    if r:
        return r

    r = await _tavily(query, num)
    if r:
        return r

    if Config.SERPAPI_KEY:
        r = await _serpapi(query, num)
        if r:
            return r

    r = await _bing(query, num)
    if r:
        return r

    r = await _ddg(query, num)
    if r:
        return r

    r = await _ddg_lite(query, num)
    if r:
        return r

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
                return [
                    {"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")}
                    for i in data.get("organic_results", [])[:num]
                ]
    except Exception:
        return []


async def _bing(query: str, num: int) -> list[dict]:
    """Bing web search — most reliable free fallback."""
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(
                "https://www.bing.com/search",
                params={"q": query, "count": min(num, 10)},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                results = []
                for r in soup.select(".b_algo")[:num]:
                    title_el   = r.select_one("h2 a")
                    snippet_el = r.select_one(".b_caption p, .b_algoSlug")
                    url   = title_el.get("href", "") if title_el else ""
                    title = title_el.get_text(strip=True) if title_el else ""
                    snip  = snippet_el.get_text(strip=True) if snippet_el else ""
                    if title and url:
                        results.append({"title": title, "url": url, "snippet": snip})
                return results
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
                for r in soup.select(".result, .web-result")[:num]:
                    title_el   = r.select_one(".result__title, .result__a")
                    snippet_el = r.select_one(".result__snippet, .result__body")
                    a_el       = r.select_one("a[href]")
                    url = ""
                    if a_el:
                        href = a_el.get("href", "")
                        # DDG wraps URLs — extract the real one
                        m = re.search(r'uddg=([^&]+)', href)
                        url = m.group(1) if m else href
                        if url.startswith("//duckduckgo"):
                            url = ""
                    results.append({
                        "title":   title_el.get_text(strip=True) if title_el else "",
                        "url":     url,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    })
                return [r for r in results if r["title"]]
    except Exception:
        return []


async def _ddg_lite(query: str, num: int) -> list[dict]:
    """DuckDuckGo lite — simplest fallback."""
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
                # DDG lite: links are in table rows
                for a in soup.find_all("a", class_="result-link")[:num]:
                    results.append({
                        "title":   a.get_text(strip=True),
                        "url":     a.get("href", ""),
                        "snippet": "",
                    })
                # Alternate selector if no results
                if not results:
                    for a in soup.select("td a[href^='http']")[:num]:
                        t = a.get_text(strip=True)
                        u = a.get("href", "")
                        if t and u and "duckduckgo" not in u:
                            results.append({"title": t, "url": u, "snippet": ""})
                return results
    except Exception:
        return []


async def fetch_page(url: str) -> str:
    """Fetch and clean a page — Firecrawl first (clean markdown), then raw HTML parse."""
    content = await _firecrawl_scrape(url)
    if content:
        return content
    try:
        async with aiohttp.ClientSession(headers=HEADERS) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:5000]
    except Exception:
        return ""


async def find_telegram_groups_online(topic: str) -> list[dict]:
    results = await web_search(f"t.me {topic} telegram group channel", num=10)
    groups = []
    for r in results:
        url  = r.get("url", "")
        text = r.get("title", "") + " " + r.get("snippet", "") + " " + url
        found = re.findall(r't\.me/([\w]+)', text)
        for username in found:
            if len(username) > 3 and username not in ("joinchat", "s", "share"):
                groups.append({
                    "username": username,
                    "title":    r.get("title", username),
                    "snippet":  r.get("snippet", ""),
                    "url":      f"https://t.me/{username}",
                })
    return groups


async def search_x_opportunities(role: str) -> list[dict]:
    """Search X/Twitter for Web3/AI role opportunities (via search engines)."""
    queries = [
        f'site:twitter.com "{role}" web3 crypto 2026 telegram',
        f'site:twitter.com "{role}" AI project hiring 2026 apply',
        f'"{role}" web3 AI 2026 telegram apply site:x.com',
        f'nitter "{role}" web3 crypto 2026 telegram DM',
        f'"{role}" "web3" OR "crypto" OR "AI" 2026 telegram apply',
    ]
    all_results = []
    for q in queries:
        results = await web_search(q, num=5)
        all_results.extend(results)
    return all_results


async def search_new_web3_projects(role: str = "") -> list[dict]:
    """Find newly launched 2026 Web3/AI projects that might need roles filled."""
    queries = [
        f"new web3 project launched 2026 ambassador CM moderator telegram",
        f"new AI crypto project 2026 community team open telegram apply",
        f"DeFi project 2026 launching ambassador program telegram",
        f"AI blockchain startup 2026 hiring community telegram",
        f'site:twitter.com "new project" web3 AI 2026 ambassador telegram',
        f'site:twitter.com "launching" web3 crypto 2026 telegram community',
    ]
    if role:
        queries.insert(0, f"new web3 AI project 2026 {role} wanted telegram")
    all_results = []
    for q in queries:
        results = await web_search(q, num=5)
        all_results.extend(results)
    return all_results
