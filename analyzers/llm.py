import asyncio
import json
import anthropic

from config.settings import ANTHROPIC_API_KEY

MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are a Japanese financial news sentiment analyzer.
Analyze the given news text and respond ONLY with a raw JSON object (no markdown, no code blocks).
Use exactly this format:
{"sentiment": "bullish", "confidence": 0.85, "impact_score": 0.7, "event_type": "earnings", "is_surprise": false, "affected_symbols": ["7201"], "reasoning": "..."}

Rules:
- sentiment: "bullish" or "bearish" or "neutral"
- confidence: float 0.0-1.0
- impact_score: float 0.0-1.0
- event_type: "earnings" or "dividend" or "macro" or "guidance" or "other"
- is_surprise: true or false
- affected_symbols: list of Japanese stock codes (e.g. "7201") or empty list
- reasoning: brief English explanation
Output raw JSON only. No markdown. No explanation."""

_DEFAULT = {
    "sentiment": "neutral",
    "confidence": 0.0,
    "impact_score": 0.0,
    "event_type": "other",
    "is_surprise": False,
    "affected_symbols": [],
    "reasoning": "",
}


async def analyze_with_llm(text: str, api_key: str = ANTHROPIC_API_KEY) -> dict:
    async def _call() -> dict:
        client = anthropic.Anthropic(api_key=api_key)
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = response.content[0].text.strip()
        # markdownコードブロックを除去
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())

    try:
        result = await asyncio.wait_for(_call(), timeout=8.0)
        return {**_DEFAULT, **result}
    except Exception:
        return dict(_DEFAULT)
