#!/usr/bin/env python3
"""
NewsAlgo バックテスト実行スクリプト

使い方:
  python run_backtest.py              # サンプルデータでデモ実行
  python run_backtest.py --jsonl      # ローカルJSONLログから実行
  python run_backtest.py --hold 3     # 3日保有モード
  python run_backtest.py --csv        # CSVレポート保存
"""
import sys, argparse, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from backtest.data_loader import load_sample_news, load_news_from_jsonl
from backtest.runner import BacktestRunner
from backtest.report import print_report, save_csv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NewsAlgo バックテスト実行スクリプト",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=["sample", "jsonl"],
        default="sample",
        help="データ取得モード: sample（デフォルト）または jsonl",
    )
    parser.add_argument(
        "--jsonl",
        action="store_const",
        const="jsonl",
        dest="mode",
        help="--mode jsonl の短縮形",
    )
    parser.add_argument(
        "--hold",
        type=int,
        default=1,
        metavar="DAYS",
        help="保有日数（デフォルト: 1）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        metavar="FLOAT",
        help="シグナル閾値（デフォルト: 0.3）",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="CSVファイルを保存する",
    )
    parser.add_argument(
        "--output",
        default="backtest_result.csv",
        metavar="PATH",
        help="CSV保存先（デフォルト: backtest_result.csv）",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # ── 1. データ読み込み ──────────────────────────────────────────────
    if args.mode == "jsonl":
        print("[NewsAlgo] ローカルJSONLログからニュースを読み込み中...")
        try:
            news_items = load_news_from_jsonl()
        except FileNotFoundError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)
        if not news_items:
            print("[WARN] JONSLファイルが見つからないか空です。サンプルデータに切り替えます。")
            news_items = load_sample_news()
    else:
        print("[NewsAlgo] サンプルデータを使用してバックテストを実行します。")
        news_items = load_sample_news()

    print(f"[NewsAlgo] ニュース件数: {len(news_items)} 件")
    print(f"[NewsAlgo] 保有日数: {args.hold} 日  閾値: {args.threshold}")

    # ── 2. バックテスト実行 ────────────────────────────────────────────
    runner = BacktestRunner(
        hold_days=args.hold,
        threshold=args.threshold,
        use_llm=False,
    )
    result = await runner.run(news_items)
    trades = result["trades"]
    metrics = result["metrics"]

    # ── 3. コンソールレポート出力 ──────────────────────────────────────
    print_report(metrics, trades)

    # ── 4. CSV保存（オプション） ───────────────────────────────────────
    if args.csv:
        save_csv(trades, output_path=args.output)


if __name__ == "__main__":
    asyncio.run(main())
