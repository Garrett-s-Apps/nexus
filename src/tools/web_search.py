"""
Web search capability for NEXUS agents and Slack interactions.

Uses Google Custom Search API when available, falls back to
DuckDuckGo via the ddgs package (free, no API key needed).
"""

import asyncio
import logging

import aiohttp

from src.config import get_key

logger = logging.getLogger("nexus.web_search")


async def search(query: str, num_results: int = 5) -> list[dict]:
    """Search the web and return structured results.

    Tries Google Custom Search first (higher quality), falls back
    to DuckDuckGo via ddgs package (free, no API key needed).
    """
    google_key = get_key("GOOGLE_AI_API_KEY")
    google_cx = get_key("GOOGLE_SEARCH_CX")

    if google_key and google_cx:
        return await _google_search(query, google_key, google_cx, num_results)
    return await _ddg_search(query, num_results)


async def _google_search(query: str, api_key: str, cx: str, n: int) -> list[dict]:
    """Google Custom Search JSON API."""
    url = "https://www.googleapis.com/customsearch/v1"
    params = {"key": api_key, "cx": cx, "q": query, "num": str(min(n, 10))}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning("Google search returned %d, falling back to DDG", resp.status)
                    return await _ddg_search(query, n)
                data = await resp.json()
                return [
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                    for item in data.get("items", [])[:n]
                ]
    except Exception as e:
        logger.warning("Google search failed: %s, falling back to DDG", e)
        return await _ddg_search(query, n)


async def _ddg_search(query: str, n: int) -> list[dict]:
    """DuckDuckGo search via the ddgs package — runs sync call in executor."""
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _ddg_sync, query, n)
        return results
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)
        return [{"title": "Search error", "url": "", "snippet": str(e)}]


def _ddg_sync(query: str, n: int) -> list[dict]:
    """Synchronous DDG search — called from executor to avoid blocking."""
    from ddgs import DDGS
    raw = DDGS().text(query, max_results=n)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in raw
    ]


def format_results_for_context(results: list[dict]) -> str:
    """Format search results as context for LLM consumption."""
    if not results:
        return "(No search results found)"

    lines = ["Web search results:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        if r.get("url"):
            lines.append(f"   {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


def format_results_for_slack(results: list[dict], query: str) -> str:
    """Format search results as Slack mrkdwn."""
    if not results:
        return f"No results found for: _{query}_"

    lines = [f"*Web search results for:* _{query}_\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        if url:
            lines.append(f"{i}. <{url}|{title}>")
        else:
            lines.append(f"{i}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)
