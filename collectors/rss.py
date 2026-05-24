"""
RSS フィードコレクター
- NHK 総合 / NHK 経済 / Yahoo ビジネス / Yahoo 株式 / みんかぶ
- ソース別信頼性スコアを自動付与
- Redis TTL 300秒 / 未起動時はメモリ set でフォールバック
"""

import asyncio
import hashlib
from datetime import datetime, timezone

import aiohttp
import feedparser

from config.settings import RSS_FEEDS, RSS_CREDIBILITY, REDIS_URL

_seen: set = set()
_redis = None

# ソースごとのデフォルト信頼性スコア（settings.RSS_CREDIBILITY にない場合）
_DEFAULT_CREDIBILITY = 0.65


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


async def _fetch_feed(session: aiohttp.ClientSession, name: str, url: str) -> list:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsAlgo/1.0)"}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
    except Exception:
        return []

    feed = feedparser.parse(text)
    if not feed.entries:
        return []

    credibility = RSS_CREDIBILITY.get(name, _DEFAULT_CREDIBILITY)
    results = []

    for entry in feed.entries:
        raw_id = entry.get("id") or entry.get("link", "") or entry.get("title", "")
        content_id = hashlib.md5(raw_id.encode()).hexdigest()

        if await _is_duplicate(content_id):
            continue

        # タイムスタンプ
        timestamp = datetime.now(timezone.utc).isoformat()
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                import time
                timestamp = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
        elif hasattr(entry, "published") and entry.published:
            timestamp = entry.published

        # 本文（summary または title）
        raw = entry.get("summary", "") or entry.get("title", "")
        # HTML タグを簡易除去
        import re
        raw = re.sub(r"<[^>]+>", "", raw).strip()

        results.append({
            "id": content_id,
            "title": entry.get("title", ""),
            "source": name,
            "credibility": credibility,
            "timestamp": timestamp,
            "raw": raw,
            "url": entry.get("link", ""),
        })

    return results


async def fetch_all_rss() -> list:
    """
    全 RSS フィードを並列取得してニュースアイテムのリストを返す。

    Returns
    -------
    list[dict]
        各アイテム: id, title, source, credibility, timestamp, raw, url
    """
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_feed(session, name, url) for name, url in RSS_FEEDS.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    items = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items
