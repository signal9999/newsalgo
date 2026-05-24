"""バックテスト結果のレポート出力"""
import csv
from pathlib import Path
from typing import List


def print_report(
    metrics: dict,
    trades: List[dict],
    initial_balance: float = 1_000_000.0,
) -> None:
    """バックテスト結果をコンソールに整形出力する。"""

    SEP = "=" * 60

    # 期間を trades から算出
    dates = []
    for t in trades:
        for key in ("entry_time", "exit_time"):
            v = t.get(key)
            if v:
                dates.append(str(v)[:10])
    period_start = min(dates) if dates else "N/A"
    period_end = max(dates) if dates else "N/A"

    total_trades = metrics.get("total_trades", 0)
    win_trades = metrics.get("winning_trades", 0)
    loss_trades = metrics.get("losing_trades", 0)
    win_rate = metrics.get("win_rate", 0.0) * 100
    total_pnl = metrics.get("total_pnl", 0.0)
    total_return_pct = metrics.get("total_return_pct", 0.0)
    avg_win_pct = metrics.get("avg_win_pct", 0.0)
    avg_loss_pct = metrics.get("avg_loss_pct", 0.0)
    profit_factor = metrics.get("profit_factor", 0.0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    sharpe = metrics.get("sharpe_ratio", 0.0)

    print(SEP)
    print("  NewsAlgo バックテスト結果")
    print(SEP)
    print(f"期間:            {period_start} 〜 {period_end}")
    print(f"総トレード数:    {total_trades} 件")
    print(f"勝率:            {win_rate:.1f}%  (勝: {win_trades} / 負: {loss_trades})")
    pnl_sign = "+" if total_pnl >= 0 else ""
    ret_sign = "+" if total_return_pct >= 0 else ""
    print(f"総損益:          ¥{total_pnl:,.0f}  ({ret_sign}{total_return_pct:.2f}%)")
    print(f"平均勝ちトレード: +{avg_win_pct:.2f}%")
    print(f"平均負けトレード: {avg_loss_pct:.2f}%")
    print(f"プロフィットファクター: {profit_factor:.2f}")
    print(f"最大ドローダウン:  -{max_dd:.2f}%")
    print(f"シャープレシオ:    {sharpe:.2f}")

    # シグナル強度別勝率
    print()
    print("--- シグナル強度別勝率 ---")
    strong_wr = metrics.get("strong_signal_win_rate", 0.0) * 100
    medium_wr = metrics.get("medium_signal_win_rate", 0.0) * 100

    # 件数を trades から集計
    strong_count = sum(
        1 for t in trades if (t.get("signal_level") or "").upper() == "STRONG"
    )
    medium_count = sum(
        1 for t in trades if (t.get("signal_level") or "").upper() == "MEDIUM"
    )
    print(f"  STRONG:  {strong_wr:.1f}%  ({strong_count}件)")
    print(f"  MEDIUM:  {medium_wr:.1f}%  ({medium_count}件)")

    # ソース別勝率
    by_source = metrics.get("by_source", {})
    if by_source:
        print()
        print("--- ソース別勝率 ---")
        # 件数集計
        source_counts: dict = {}
        for t in trades:
            src = t.get("source") or "unknown"
            source_counts[src] = source_counts.get(src, 0) + 1
        for src, wr in sorted(by_source.items()):
            cnt = source_counts.get(src, 0)
            print(f"  {src:<14} {wr * 100:.1f}%  ({cnt}件)")

    # 最近の取引（最大10件）
    print()
    print("--- 最近の取引 (最大10件) ---")
    recent = trades[-10:] if len(trades) > 10 else trades
    for t in recent:
        date = str(t.get("entry_time", ""))[:10]
        symbol = t.get("symbol", "-")
        direction = t.get("direction", "-")
        pnl_pct = t.get("pnl_pct", 0.0) or 0.0
        sig = t.get("signal_level", "-")
        sign = "+" if pnl_pct >= 0 else ""
        print(
            f"  [{date}] {symbol:<8} {direction:<8} {sign}{pnl_pct:.2f}%  [{sig}]"
        )

    print(SEP)


def save_csv(
    trades: List[dict],
    output_path: str = "backtest_result.csv",
) -> None:
    """全トレードを CSV ファイルに保存する。"""
    fieldnames = [
        "trade_id",
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "quantity",
        "pnl",
        "pnl_pct",
        "direction",
        "signal_level",
        "news_title",
        "entry_time",
        "exit_time",
        "status",
    ]

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for t in trades:
            row = {field: t.get(field, "") for field in fieldnames}
            writer.writerow(row)

    print(f"CSVを保存しました: {output.resolve()}")
