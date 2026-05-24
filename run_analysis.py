#!/usr/bin/env python3
"""
NewsAlgo バックテスト精度分析スクリプト

複数の設定でバックテストを実行し、詳細なレポートを生成する。

使い方:
  python3 run_analysis.py                  # 全分析（キーワード + LLM）
  python3 run_analysis.py --no-llm         # キーワードモードのみ
  python3 run_analysis.py --mode sample    # サンプルデータのみ
  python3 run_analysis.py --html           # HTML レポート出力
"""
import sys
import asyncio
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backtest.data_loader import load_sample_news, load_news_from_jsonl
from backtest.runner import BacktestRunner
from backtest.metrics import calculate_metrics

# LLM API コスト（claude-sonnet-4-5）
_PRICE_IN  = 3.0   # USD/1M input tokens
_PRICE_OUT = 15.0  # USD/1M output tokens
_AVG_IN    = 300
_AVG_OUT   = 120
_JPY       = 155.0


def cost(n: int) -> float:
    return ((n * _AVG_IN / 1_000_000) * _PRICE_IN +
            (n * _AVG_OUT / 1_000_000) * _PRICE_OUT) * _JPY


async def run_config(news: list, label: str, use_llm: bool,
                     hold: int, threshold: float) -> dict:
    runner = BacktestRunner(use_llm=use_llm, hold_days=hold,
                            signal_threshold=threshold)
    result = await runner.run(news)
    m = result["metrics"]
    m["label"]     = label
    m["use_llm"]   = use_llm
    m["hold_days"] = hold
    m["threshold"] = threshold
    m["n_news"]    = len(news)
    m["llm_cost_jpy"] = cost(len(news)) if use_llm else 0.0
    return m


def bar(val: float, max_val: float = 1.0, width: int = 20) -> str:
    filled = int(width * (val / max_val)) if max_val > 0 else 0
    return "█" * filled + "░" * (width - filled)


def print_analysis(results: list):
    sep = "═" * 74
    print(f"\n{sep}")
    print("  NewsAlgo バックテスト精度分析レポート")
    print(f"  実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(sep)

    for m in results:
        llm_tag  = "🤖 LLM" if m["use_llm"] else "🔑 KW "
        print(f"\n  ┌─ {llm_tag} | {m['label']}")
        print(f"  │  hold={m['hold_days']}日  threshold={m['threshold']}  "
              f"ニュース{m['n_news']}件")
        print(f"  ├─ トレード数  : {m['total_trades']:3d} 件")
        wr = m.get("win_rate", 0) * 100
        print(f"  ├─ 勝率        : {wr:5.1f}%  {bar(wr, 100)}")
        pnl = m.get("total_pnl", 0)
        ret = m.get("total_return_pct", 0)
        sign = "+" if pnl >= 0 else ""
        print(f"  ├─ 総損益      : {sign}¥{pnl:,.0f}  ({sign}{ret:.2f}%)")
        pf  = m.get("profit_factor", 0)
        print(f"  ├─ PF          : {pf:.2f}  {bar(min(pf, 3), 3)}")
        dd  = m.get("max_drawdown_pct", 0)
        shr = m.get("sharpe_ratio", 0)
        print(f"  ├─ 最大DD      : {dd:.2f}%")
        print(f"  ├─ シャープ比  : {shr:.2f}")
        if m["use_llm"]:
            print(f"  ├─ LLMコスト   : ¥{m['llm_cost_jpy']:.2f}（推定）")
        print(f"  └{'─' * 50}")

    # サマリー比較
    if len(results) >= 2:
        print(f"\n{sep}")
        print("  比較サマリー")
        print(sep)
        headers = ["設定", "勝率", "PF", "総損益", "LLMコスト"]
        widths  = [22, 8, 6, 12, 12]
        hline = "  " + " | ".join(h.ljust(w) for h, w in zip(headers, widths))
        print(hline)
        print("  " + "-" * (sum(widths) + len(widths) * 3))
        for m in results:
            tag   = ("🤖 LLM " if m["use_llm"] else "🔑 KW  ") + m["label"][:15]
            wr    = f"{m.get('win_rate',0)*100:.1f}%"
            pf    = f"{m.get('profit_factor',0):.2f}"
            pnl   = f"¥{m.get('total_pnl',0):,.0f}"
            lcost = f"¥{m['llm_cost_jpy']:.2f}" if m["use_llm"] else "—"
            vals  = [tag, wr, pf, pnl, lcost]
            print("  " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)))
        print(sep + "\n")

        # LLM vs キーワード 差分
        llm_results = [r for r in results if r["use_llm"]]
        kw_results  = [r for r in results if not r["use_llm"]]
        if llm_results and kw_results:
            llm_wr = sum(r.get("win_rate", 0) for r in llm_results) / len(llm_results)
            kw_wr  = sum(r.get("win_rate", 0) for r in kw_results)  / len(kw_results)
            diff   = (llm_wr - kw_wr) * 100
            total_cost = sum(r["llm_cost_jpy"] for r in llm_results)
            print(f"  📊 LLM vs キーワード 勝率差: {diff:+.1f}%")
            print(f"  💰 LLM 総コスト:             ¥{total_cost:.2f}")
            if diff > 0:
                print(f"  → LLM を使うと勝率が {diff:.1f}% 向上（コスト: ¥{total_cost:.2f}/回）")
            else:
                print(f"  → キーワードモードで十分（LLM 使用でコスト ¥{total_cost:.2f} の価値なし）")


def save_html(results: list, path: str = "analysis_report.html"):
    rows = ""
    for m in results:
        tag  = ("LLM" if m["use_llm"] else "KW")
        wr   = f"{m.get('win_rate',0)*100:.1f}%"
        pf   = f"{m.get('profit_factor',0):.2f}"
        pnl  = f"¥{m.get('total_pnl',0):,.0f}"
        ret  = f"{m.get('total_return_pct',0):+.2f}%"
        dd   = f"{m.get('max_drawdown_pct',0):.2f}%"
        cost_str = f"¥{m['llm_cost_jpy']:.2f}" if m["use_llm"] else "—"
        rows += f"""<tr>
          <td>{tag}</td><td>{m['label']}</td>
          <td>{m['hold_days']}日</td><td>{m['threshold']}</td>
          <td>{m['total_trades']}</td><td>{wr}</td>
          <td>{pf}</td><td>{pnl}</td><td>{ret}</td>
          <td>{dd}</td><td>{cost_str}</td>
        </tr>\n"""

    html = f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8">
<title>NewsAlgo バックテスト分析レポート</title>
<style>
  body {{ font-family: 'Hiragino Sans', sans-serif; padding: 20px; background: #0d1117; color: #e6edf3; }}
  h1 {{ color: #58a6ff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ background: #161b22; padding: 8px 12px; text-align: left; color: #58a6ff; border: 1px solid #30363d; }}
  td {{ padding: 8px 12px; border: 1px solid #30363d; }}
  tr:hover {{ background: #161b22; }}
  .kw {{ color: #3fb950; }} .llm {{ color: #d2a8ff; }}
  .ts {{ color: #8b949e; font-size: 0.85em; }}
</style>
</head><body>
<h1>NewsAlgo バックテスト分析レポート</h1>
<p class="ts">生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
<table>
<tr>
  <th>モード</th><th>データ</th><th>hold</th><th>閾値</th>
  <th>件数</th><th>勝率</th><th>PF</th><th>総損益</th><th>リターン</th>
  <th>最大DD</th><th>LLMコスト</th>
</tr>
{rows}
</table>
</body></html>"""

    Path(path).write_text(html, encoding="utf-8")
    print(f"  HTML レポートを保存しました: {Path(path).resolve()}")


def parse_args():
    p = argparse.ArgumentParser(description="NewsAlgo バックテスト精度分析")
    p.add_argument("--mode", choices=["sample", "jsonl", "both"], default="both")
    p.add_argument("--no-llm",  action="store_true", help="LLM なしのみ")
    p.add_argument("--html",    action="store_true", help="HTML レポート出力")
    p.add_argument("--output",  default="analysis_report.html")
    return p.parse_args()


async def main():
    args = parse_args()

    # データセット準備
    datasets = []
    if args.mode in ("sample", "both"):
        datasets.append(("サンプル", load_sample_news()))
    if args.mode in ("jsonl", "both"):
        items = load_news_from_jsonl()
        if items:
            datasets.append(("JSOALログ", items))
        else:
            print("  ⚠️  JSONL ログが見つかりません。サンプルのみで実行します。")

    results = []
    use_llm_options = [False] if args.no_llm else [False, True]

    for label, news in datasets:
        for use_llm in use_llm_options:
            mode_label = f"{label}({'LLM' if use_llm else 'KW'})"
            print(f"  実行中: {mode_label} ({len(news)}件) ...", end=" ", flush=True)
            m = await run_config(news, label, use_llm,
                                 hold=1, threshold=0.7)
            results.append(m)
            print("完了")

    print_analysis(results)

    if args.html:
        save_html(results, args.output)


if __name__ == "__main__":
    asyncio.run(main())
