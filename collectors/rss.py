import asyncio
import hashlib
from datetime import datetime, timezone

import aiohttp
import feedparser

from config.settings import RSS_FEEDS, REDIS_URL

_seen: set[str] = set()
_redis = None


async def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(REDIS_URL, socket_connect_timeout=2)
        await client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


async def _is_duplicate(content_id: str) -> bool:
    r = await _get_redis()
    if r:
        try:
            added = await r.set(f"rss:{content_id}", "1", nx=True, ex=300)
            return added is None
        except Exception:
            pass
    if content_id in _seen:
        return True
    _seen.add(content_id)
    return False


async def _fetch_feed(session: aiohttp.ClientSession, name: str, url: str) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            text = await resp.text()
    except Exception:
        return []

    feed = feedparser.parse(text)
    results = []

    for entry in feed.entries:
        content_id = hashlib.md5((entry.get("id") or entry.get("link", "") or entry.get("title", "")).encode()).hexdigest()

        if await _is_duplicate(content_id):
            continue

        timestamp = datetime.now(timezone.utc).isoformat()
        if hasattr(entry, "published"):
            timestamp = entry.published

        results.append({
            "id": content_id,
            "title": entry.get("title", ""),
            "source": name,
            "credibility": 0.7,
            "timestamp": timestamp,
            "raw": entry.get("summary", entry.get("title", "")),
        })

    return results


async def fetch_all_rss() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_feed(session, name, url) for name, url in RSS_FEEDS.items()]
        results = await asyncio.gather(*tasks)

    return [item for feed_items in results for item in feed_items]
