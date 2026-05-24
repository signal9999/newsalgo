"""Economic calendar stub — fetches scheduled macro events."""
import asyncio
from datetime import datetime, timezone


UPCOMING_EVENTS = [
    {"name": "日銀政策決定会合", "date": "2025-06-13", "impact": "high"},
    {"name": "米CPI発表", "date": "2025-06-12", "impact": "high"},
    {"name": "GDP速報値", "date": "2025-06-16", "impact": "medium"},
]


async def fetch_macro_calendar() -> list[dict]:
    await asyncio.sleep(0)
    now = datetime.now(timezone.utc)
    return [
        {
            "id": f"macro_{e['name']}_{e['date']}",
            "title": f"[マクロ指標] {e['name']}",
            "source": "macro_calendar",
            "credibility": 0.8,
            "timestamp": now.isoformat(),
            "raw": str(e),
            "event_date": e["date"],
            "impact": e["impact"],
        }
        for e in UPCOMING_EVENTS
    ]
