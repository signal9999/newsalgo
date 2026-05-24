#!/usr/bin/env python3
"""
NewsAlgo バックテスト最適化スクリプト
hold_days (1/3/5日) × threshold (0.3/0.5/0.7) の全組み合わせを比較して
最適パラメータを特定する。

使い方:
  python3 run_optimize.py               # サンプルデータ
  python3 run_optimize.py --mode jsonl  # 実ニュースログ
  python3 run_optimize.py --csv         # CSV 出力
"""
import sys
import asyncio
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backtest.data_loader import load_sample_news, load_news_from_jsonl
from backtest.runner import BacktestRunner

HOLD_DAYS_LIST   = [1, 3, 5]
THRESHOLD_LIST   = [0.3, 0.5, 0.7]


def parse_args():
    p = argparse.ArgumentParser(description="NewsAlgo バックテストパラメータ最適化")
    p.add_argument("--mode", choices=["sample", "jsonl"], default="sample")
    p.add_argument("--csv", action="store_true")
    p.add_argument("--output", default="optimize_result.csv")
    return p.parse_args()


async def run_one(news_items: list, hold_days: int, threshold: float) -> dict:
    runner = BacktestRunner(
        use_llm=False,
        hold_days=hold_days,
        signal_threshold=threshold,
    )
    result = await runner.run(news_items)
    m = result["metrics"]
    return {
        "hold_days":    hold_days,
        "threshold":    threshold,
        "trades":       m.get("total_trades", 0),
        "win_rate":     m.get("win_rate", 0.0),
        "total_pnl":    m.get("total_pnl", 0.0),
        "total_ret%":   m.get("total_return_pct", 0.0),
        "profit_factor":m.get("profit_factor", 0.0),
        "max_dd%":      m.get("max_drawdown_pct", 0.0),
        "sharpe":       m.get("sharpe_ratio", 0.0),
    }


async def main():
    args = parse_args()

    if args.mode == "jsonl":
        print("[最適化] JONSLログを読み込み中...")
        news_items = load_news_from_jsonl() or load_sample_news()
    else:
        print("[最適化] サンプルデータを使用")
        news_items = load_sample_news()

    print(f"[最適化] ニュース件数: {len(news_items)} 件")
    print(f"[最適化] hold_days: {HOLD_DAYS_LIST}  threshold: {THRESHOLD_LIST}")
    print(f"[最適化] 組み合わせ数: {len(HOLD_DAYS_LIST) * len(THRESHOLD_LIST)} パターン\n")

    rows = []
    for hold in HOLD_DAYS_LIST:
        for thr in THRESHOLD_LIST:
            r = await run_one(news_items, hold, thr)
            rows.append(r)

    # ── コンソール出力 ────────────────────────────────────────────────
    col_w = [6, 9, 7, 8, 12, 9, 13, 8, 7]
    headers = ["hold", "thresh", "trades", "win%", "pnl(¥)", "ret%", "PF", "maxDD%", "sharpe"]
    sep = "─" * (sum(col_w) + len(col_w) * 3 + 1)

    print("=" * len(sep))
    print("  NewsAlgo バックテスト最適化結果")
    print("=" * len(sep))
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, col_w))
    print(f"  {header_line}")
    print(f"  {sep}")

    best = max(rows, key=lambda r: (r["win_rate"], r["total_pnl"]))
    for r in rows:
        marker = " ◀ BEST" if r is best else ""
        vals = [
            str(r["hold_days"]),
            f"{r['threshold']:.1f}",
            str(r["trades"]),
            f"{r['win_rate']*100:.1f}%",
            f"¥{r['total_pnl']:,.0f}",
            f"{r['total_ret%']:+.2f}%",
            f"{r['profit_factor']:.2f}",
            f"{r['max_dd%']:.2f}%",
            f"{r['sharpe']:.2f}",
        ]
        row_line = " | ".join(v.ljust(w) for v, w in zip(vals, col_w))
        print(f"  {row_line}{marker}")

    print(f"  {sep}")
    print(f"\n  最適パラメータ: hold_days={best['hold_days']}日  threshold={best['threshold']}")
    print(f"  → 勝率 {best['win_rate']*100:.1f}%  総損益 ¥{best['total_pnl']:,.0f}  PF {best['profit_factor']:.2f}")
    print("=" * len(sep))

    # ── CSV 出力（オプション）─────────────────────────────────────────
    if args.csv:
        import csv
        out = Path(args.output)
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSVを保存しました: {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
