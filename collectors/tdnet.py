"""
TDnet 適時開示スクレイパー
- BeautifulSoup で HTML をパース（JSレンダリング不要）
- 証券コード・企業名・開示タイトルを抽出
- affected_symbols に証券コードを自動セット
- Redis TTL 300秒 / 未起動時はメモリ set でフォールバック
"""

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

_seen: set = set()
_redis = None

# 4桁証券コード正規表現
_CODE_RE = re.compile(r"^\d{4}$")
# HH:MM 形式
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


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


def _extract_row(tds):
    """
    TDnet の <tr> 内の <td> リストから開示情報を抽出する。

    TDnet は CSS クラスで列を明示している:
      kjTime  → 時刻 (HH:MM)
      kjCode  → 証券コード（4〜5桁: TDnet内部コードは5桁なので先頭4桁を使用）
      kjName  → 会社名
      kjTitle → 表題（aタグ付き）

    CSS クラス優先、フォールバックとして内容パターン判定。
    """
    time_str = ""
    code = ""
    company = ""
    title = ""
    href = ""

    for td in tds:
        classes = td.get("class", [])
        text = td.get_text(strip=True)

        if "kjTime" in classes:
            time_str = text

        elif "kjCode" in classes:
            # TDnet の内部コードは 5 桁（例: 39220 → 株式コード 3922）
            # 数字だけ取り出して先頭 4 桁を証券コードとして使う
            digits = re.sub(r"\D", "", text)
            if len(digits) >= 4:
                code = digits[:4]
            elif digits:
                code = digits  # 4桁未満はそのまま（ETF等）

        elif "kjName" in classes:
            company = text

        elif "kjTitle" in classes:
            a = td.find("a", href=True)
            if a and a.get_text(strip=True):
                title = a.get_text(strip=True)
                href = a["href"]

    # CSS クラスで取れなかった場合のフォールバック（旧形式）
    if not title:
        for td in tds:
            a = td.find("a", href=True)
            if a and a.get_text(strip=True):
                title = a.get_text(strip=True)
                href = a["href"]
                break

    if not code:
        texts = [td.get_text(strip=True) for td in tds]
        for text in texts:
            if _CODE_RE.match(text):
                code = text
                break

    if not title or not href:
        return None

    return {
        "time_str": time_str,
        "code": code,
        "company": company,
        "title": title,
        "href": href,
    }


async def _fetch_page(session: aiohttp.ClientSession, date_str: str) -> list:
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

    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)

    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        row = _extract_row(tds)
        if not row:
            continue

        # 絶対 URL 構築
        href = row["href"]
        if href.startswith("/"):
            doc_url = BASE_URL + href
        elif href.startswith("http"):
            doc_url = href
        else:
            doc_url = BASE_URL + "/inbs/" + href

        # タイムスタンプ構築（JST のまま ISO 形式で保存）
        if row["time_str"]:
            try:
                h, m = map(int, row["time_str"].split(":"))
                dt_jst = now_jst.replace(hour=h, minute=m, second=0, microsecond=0)
                timestamp = dt_jst.isoformat()
            except ValueError:
                timestamp = now_jst.isoformat()
        else:
            timestamp = now_jst.isoformat()

        content_id = hashlib.md5(doc_url.encode()).hexdigest()

        items.append({
            "_id": content_id,
            "title": row["title"],
            "code": row["code"],
            "company": row["company"],
            "doc_url": doc_url,
            "timestamp": timestamp,
        })

    return items


async def fetch_tdnet() -> list:
    """
    TDnet 開示一覧から本日・前日分を取得してニュースアイテムリストを返す。

    Returns
    -------
    list[dict]
        各アイテム: id, title, source, credibility, timestamp, raw,
                   url, affected_symbols, company, code
    """
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

            # raw: 企業名＋タイトルで LLM への入力を充実させる
            raw_parts = []
            if item["company"]:
                raw_parts.append(item["company"])
            raw_parts.append(item["title"])
            raw = " ".join(raw_parts)

            # affected_symbols: 証券コードが取れた場合はセット
            affected_symbols = [item["code"]] if item["code"] else []

            results.append({
                "id": item["_id"],
                "title": item["title"],
                "source": "tdnet",
                "credibility": 0.9,
                "timestamp": item["timestamp"],
                "raw": raw,
                "url": item["doc_url"],
                "company": item["company"],
                "code": item["code"],
                "affected_symbols": affected_symbols,
            })

    return results
