"""10秒動作確認スクリプト"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from collectors.tdnet import fetch_tdnet
from collectors.rss import fetch_all_rss
from collectors.credibility import calculate_credibility
from analyzers.keyword import analyze_keywords
from analyzers.llm import analyze_with_llm
from analyzers.signal import compute_signal
from config.settings import ANTHROPIC_API_KEY

news_counts = {}
pipeline_results = []


async def run_pipeline(item: dict):
    enriched = calculate_credibility(item, [])
    text = item.get("title", "") + " " + item.get("raw", "")
    kw = analyze_keywords(text)

    # LLMは最初の3件のみ（コスト節約）
    llm = None
    if len(pipeline_results) < 3:
        llm = await analyze_with_llm(text, ANTHROPIC_API_KEY)

    signal = compute_signal(
        credibility_score=enriched.get("credibility", 0.0),
        llm_confidence=(llm or {}).get("confidence", 0.0),
        impact_score=(llm or {}).get("impact_score", 0.0),
        direction=(llm or kw)["sentiment"] if llm else kw["direction"],
    )

    pipeline_results.append({
        "id": item.get("id", ""),
        "title": item.get("title", "")[:60],
        "source": item.get("source"),
        "credibility": enriched.get("credibility"),
        "is_reliable": enriched.get("is_reliable"),
        "direction": kw["direction"],
        "keywords": kw["matched_keywords"],
        "signal_level": signal["level"],
        "signal_score": round(signal["score"], 3),
        "llm_sentiment": (llm or {}).get("sentiment", "skipped"),
        "llm_confidence": (llm or {}).get("confidence", 0.0),
    })


async def main():
    print("=" * 60)
    print("[NewsAlgo 動作確認] RSSフィード取得中...")
    print("=" * 60)

    # TDnet取得
    print("\n[1/3] TDnet 適時開示 RSS 取得中...")
    try:
        tdnet_items = await fetch_tdnet()
        news_counts["tdnet"] = len(tdnet_items)
        print(f"  ✅ TDnet: {len(tdnet_items)}件取得")
        for item in tdnet_items[:3]:
            print(f"     - {item['title'][:55]}")
    except Exception as e:
        print(f"  ❌ TDnet エラー: {e}")
        tdnet_items = []

    # RSS取得
    print("\n[2/3] 日経・NHK・ロイター RSS 取得中...")
    try:
        rss_items = await fetch_all_rss()
        by_source = {}
        for item in rss_items:
            by_source.setdefault(item["source"], []).append(item)
        for src, items in by_source.items():
            news_counts[src] = len(items)
            print(f"  ✅ {src}: {len(items)}件取得")
            for item in items[:2]:
                print(f"     - {item['title'][:55]}")
    except Exception as e:
        print(f"  ❌ RSS エラー: {e}")
        rss_items = []

    all_items = tdnet_items + rss_items
    print(f"\n  📰 合計: {len(all_items)}件")

    # パイプライン実行
    print("\n[3/3] 解析パイプライン実行中（最初の10件）...")
    tasks = [run_pipeline(item) for item in all_items[:10]]
    await asyncio.gather(*tasks, return_exceptions=True)

    print("\n" + "=" * 60)
    print("パイプライン結果:")
    print("=" * 60)
    for r in pipeline_results:
        level_mark = {"STRONG": "🔴", "MEDIUM": "🟡", "NONE": "⚪"}.get(r["signal_level"], "")
        print(f"{level_mark} [{r['source']}] {r['title']}")
        print(f"   信頼性:{r['credibility']:.2f} | 方向:{r['direction']} | シグナル:{r['signal_level']}({r['signal_score']}) | LLM:{r['llm_sentiment']}")
        if r["keywords"]:
            print(f"   キーワード: {r['keywords']}")
    print("=" * 60)
    print(f"\n✅ 動作確認完了。取得件数: {news_counts}")


if __name__ == "__main__":
    asyncio.run(main())
