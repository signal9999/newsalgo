import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone, timedelta

import aiohttp
from bs4 import BeautifulSoup

from config.settings import REDIS_URL

logger = logging.getLogger(__name__)

BASE_URL = "https://www.release.tdnet.info"
LIST_URL_TEMPLATE = BASE_URL + "/inbs/I_list_001_{date}.html"

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
            added = await r.set(f"tdnet:{content_id}", "1", nx=True, ex=300)
            return added is None
        except Exception:
            pass
    if content_id in _seen:
        return True
    _seen.add(content_id)
    return False


async def _fetch_page(session: aiohttp.ClientSession, date_str: str) -> list[dict]:
    url = LIST_URL_TEMPLATE.format(date=date_str)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsAlgo/1.0)"}
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                logger.warning("TDnet: HTTP %s for %s", resp.status, url)
                return []
            html = await resp.text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("TDnet: failed to fetch %s: %s", url, exc)
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []

    # TDnet の開示一覧テーブル: <table> 内の各 <tr> に時刻・企業名・タイトルの <td> が並ぶ
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        # aタグ（開示タイトルリンク）を探す
        link_tag = None
        title = ""
        href = ""
        for td in tds:
            a = td.find("a", href=True)
            if a and a.get_text(strip=True):
                link_tag = a
                title = a.get_text(strip=True)
                href = a["href"]
                break

        if not title or not href:
            continue

        # 相対パスを絶対URLに変換
        if href.startswith("/"):
            doc_url = BASE_URL + href
        elif href.startswith("http"):
            doc_url = href
        else:
            doc_url = BASE_URL + "/inbs/" + href

        # 開示時刻を探す（HH:MM 形式のテキストを持つ td）
        time_str = ""
        for td in tds:
            text = td.get_text(strip=True)
            if re.match(r"^\d{1,2}:\d{2}$", text):
                time_str = text
                break

        # タイムスタンプ構築（JST = UTC+9）
        jst = timezone(timedelta(hours=9))
        now_jst = datetime.now(jst)
        if time_str:
            try:
                h, m = map(int, time_str.split(":"))
                dt_jst = now_jst.replace(hour=h, minute=m, second=0, microsecond=0)
                timestamp = dt_jst.astimezone(timezone.utc).isoformat()
            except ValueError:
                timestamp = datetime.now(timezone.utc).isoformat()
        else:
            timestamp = datetime.now(timezone.utc).isoformat()

        content_id = hashlib.md5(doc_url.encode()).hexdigest()

        items.append({
            "_id": content_id,
            "title": title,
            "doc_url": doc_url,
            "timestamp": timestamp,
        })

    return items


async def fetch_tdnet() -> list[dict]:
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    dates = [
        now_jst.strftime("%Y%m%d"),
        (now_jst - timedelta(days=1)).strftime("%Y%m%d"),
    ]

    results = []
    async with aiohttp.ClientSession() as session:
        pages = await asyncio.gather(*[_fetch_page(session, d) for d in dates])

    for page_items in pages:
        for item in page_items:
            if await _is_duplicate(item["_id"]):
                continue
            results.append({
                "id": item["_id"],
                "title": item["title"],
                "source": "tdnet",
                "credibility": 0.9,
                "timestamp": item["timestamp"],
                "raw": item["title"],
                "url": item["doc_url"],
            })

    return results
