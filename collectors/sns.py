"""X API stub — replace with real implementation when API key is available."""
import asyncio
from datetime import datetime, timezone


STUB_ITEMS = [
    {"text": "トヨタ自動車が上方修正を発表、市場に好影響か", "author": "market_watcher"},
    {"text": "日銀が金利据え置きを決定", "author": "finance_news"},
]


async def fetch_sns_mentions(keywords: list[str]) -> list[dict]:
    await asyncio.sleep(0)
    results = []
    for item in STUB_ITEMS:
        if any(kw in item["text"] for kw in keywords):
            results.append({
                "id": f"stub_{hash(item['text'])}",
                "title": item["text"],
                "source": "x_stub",
                "credibility": 0.3,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw": item["text"],
            })
    return results
