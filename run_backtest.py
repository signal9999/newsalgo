#!/usr/bin/env python3
"""
NewsAlgo バックテスト実行スクリプト

使い方:
  python3 run_backtest.py                      # サンプルデータでデモ実行
  python3 run_backtest.py --mode jsonl         # ローカルJSONLログから実行
  python3 run_backtest.py --hold 3             # 3日保有モード
  python3 run_backtest.py --csv                # CSVレポート保存
  python3 run_backtest.py --llm                # LLM解析を使用（API課金）
  python3 run_backtest.py --cost               # LLMコスト試算のみ（API呼出なし）
"""
import sys
import argparse
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backtest.data_loader import load_sample_news, load_news_from_jsonl
from backtest.runner import BacktestRunner
from backtest.report import print_report, save_csv

# ── Claude API 料金（claude-sonnet-4-5、2025年5月時点）──────────────────────
_PRICE_IN_PER_1M  = 3.0   # USD / 1M input tokens
_PRICE_OUT_PER_1M = 15.0  # USD / 1M output tokens
_AVG_IN_TOKENS    = 300   # 1記事あたり推定 input tokens
_AVG_OUT_TOKENS   = 120   # 1記事あたり推定 output tokens
_JPY_PER_USD      = 155.0  # 為替レート（概算）


def estimate_llm_cost(n_items: int) -> dict:
    in_usd  = (n_items * _AVG_IN_TOKENS  / 1_000_000) * _PRICE_IN_PER_1M
    out_usd = (n_items * _AVG_OUT_TOKENS / 1_000_000) * _PRICE_OUT_PER_1M
    total   = in_usd + out_usd
    return {"cost_usd": total, "cost_jpy": total * _JPY_PER_USD, "n_items": n_items}


def print_cost_estimate(n_items: int):
    e = estimate_llm_cost(n_items)
    print("\n" + "=" * 54)
    print("  LLM API コスト試算（claude-sonnet-4-5）")
    print("=" * 54)
    print(f"  対象ニュース数    : {e['n_items']:,} 件")
    print(f"  推定 input tokens : {n_items * _AVG_IN_TOKENS:,}")
    print(f"  推定 output tokens: {n_items * _AVG_OUT_TOKENS:,}")
    print(f"  推定コスト(USD)   : ${e['cost_usd']:.4f}")
    print(f"  推定コスト(JPY)   : ¥{e['cost_jpy']:.2f}  (1USD={_JPY_PER_USD:.0f}円)")
    print(f"  input 単価        : ${_PRICE_IN_PER_1M}/1M tokens")
    print(f"  output 単価       : ${_PRICE_OUT_PER_1M}/1M tokens")
    print("=" * 54)
    print("  ※ --llm フラグを付けると実際に API が呼ばれます")
    print("=" * 54 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NewsAlgo バックテスト実行スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mode", choices=["sample", "jsonl"], default="sample",
                        help="データ取得モード: sample（デフォルト）または jsonl")
    parser.add_argument("--jsonl", action="store_const", const="jsonl", dest="mode",
                        help="--mode jsonl の短縮形")
    parser.add_argument("--hold", type=int, default=1, metavar="DAYS",
                        help="保有日数（デフォルト: 1）")
    parser.add_argument("--threshold", type=float, default=0.3, metavar="FLOAT",
                        help="シグナル閾値（デフォルト: 0.3）")
    parser.add_argument("--llm", action="store_true",
                        help="LLM アナライザーを使用（claude-sonnet-4-5 API 課金あり）")
    parser.add_argument("--cost", action="store_true",
                        help="LLM API コスト試算のみ（API 呼出なし）")
    parser.add_argument("--csv", action="store_true", help="CSVファイルを保存する")
    parser.add_argument("--output", default="backtest_result.csv", metavar="PATH",
                        help="CSV保存先（デフォルト: backtest_result.csv）")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # ── 1. データ読み込み ──────────────────────────────────────────────
    if args.mode == "jsonl":
        print("[NewsAlgo] ローカルJSONLログからニュースを読み込み中...")
        news_items = load_news_from_jsonl()
        if not news_items:
            print("[WARN] JONSLファイルが見つからないか空です。サンプルデータに切り替えます。")
            news_items = load_sample_news()
    else:
        print("[NewsAlgo] サンプルデータを使用してバックテストを実行します。")
        news_items = load_sample_news()

    print(f"[NewsAlgo] ニュース件数: {len(news_items)} 件")
    print(f"[NewsAlgo] 保有日数: {args.hold} 日  閾値: {args.threshold}")
    if args.llm:
        print("[NewsAlgo] LLM モード: 有効（claude-sonnet-4-5 API を使用）")

    # ── 2. コスト試算のみ ──────────────────────────────────────────────
    if args.cost:
        print_cost_estimate(len(news_items))
        return

    # ── 3. LLM 使用時はコスト警告 ─────────────────────────────────────
    if args.llm:
        est = estimate_llm_cost(len(news_items))
        print(f"[COST] 推定APIコスト: ${est['cost_usd']:.4f} (¥{est['cost_jpy']:.1f})")

    # ── 4. バックテスト実行 ────────────────────────────────────────────
    runner = BacktestRunner(
        hold_days=args.hold,
        threshold=args.threshold,
        use_llm=args.llm,
    )
    result = await runner.run(news_items)
    trades  = result["trades"]
    metrics = result["metrics"]

    # ── 5. コンソールレポート出力 ──────────────────────────────────────
    print_report(metrics, trades)

    # ── 6. LLM 使用時は実コスト表示 ───────────────────────────────────
    if args.llm:
        actual_calls = result.get("llm_calls", len(news_items))
        est = estimate_llm_cost(actual_calls)
        print(f"\n  [LLM実行] API呼出数: {actual_calls}件")
        print(f"  [LLM実行] 推定コスト: ${est['cost_usd']:.4f} (¥{est['cost_jpy']:.1f})")

    # ── 7. CSV保存（オプション） ───────────────────────────────────────
    if args.csv:
        save_csv(trades, output_path=args.output)


if __name__ == "__main__":
    asyncio.run(main())
