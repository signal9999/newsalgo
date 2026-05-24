"""バックテストのパフォーマンス指標計算"""
import math
from typing import List


def calculate_metrics(trades: List[dict], initial_balance: float = 1_000_000.0) -> dict:
    """closed トレードリストからパフォーマンス指標を計算する。

    Args:
        trades: simulator の trade dict リスト（closed のみ）
        initial_balance: 初期残高（total_return_pct 計算に使用）

    Returns:
        各種パフォーマンス指標の dict
    """
    _empty = {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "total_return_pct": 0.0,
        "avg_pnl_per_trade": 0.0,
        "avg_win_pct": 0.0,
        "avg_loss_pct": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": 0.0,
        "sharpe_ratio": 0.0,
        "strong_signal_win_rate": 0.0,
        "medium_signal_win_rate": 0.0,
        "by_source": {},
    }

    if not trades:
        return _empty

    total_trades = len(trades)
    winning_trades = 0
    losing_trades = 0
    total_pnl = 0.0
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    win_pcts: List[float] = []
    loss_pcts: List[float] = []
    pnl_per_trade: List[float] = []
    cumulative_pnl: List[float] = []

    strong_wins = 0
    strong_total = 0
    medium_wins = 0
    medium_total = 0

    # ソース別集計: {"source": [wins, total]}
    source_stats: dict[str, List[int]] = {}

    running = 0.0
    for t in trades:
        pnl = t.get("pnl", 0.0) or 0.0
        pnl_pct = t.get("pnl_pct", 0.0) or 0.0
        is_win = pnl > 0

        total_pnl += pnl
        running += pnl
        cumulative_pnl.append(running)
        pnl_per_trade.append(pnl)

        if is_win:
            winning_trades += 1
            total_gross_profit += pnl
            win_pcts.append(pnl_pct)
        elif pnl < 0:
            losing_trades += 1
            total_gross_loss += abs(pnl)
            loss_pcts.append(pnl_pct)

        # シグナル強度別
        level = (t.get("signal_level") or "").upper()
        if level == "STRONG":
            strong_total += 1
            if is_win:
                strong_wins += 1
        elif level == "MEDIUM":
            medium_total += 1
            if is_win:
                medium_wins += 1

        # ソース別
        source = t.get("source") or "unknown"
        if source not in source_stats:
            source_stats[source] = [0, 0]
        source_stats[source][1] += 1
        if is_win:
            source_stats[source][0] += 1

    # 基本指標
    win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
    total_return_pct = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0.0
    avg_pnl_per_trade = total_pnl / total_trades if total_trades > 0 else 0.0
    avg_win_pct = sum(win_pcts) / len(win_pcts) if win_pcts else 0.0
    avg_loss_pct = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0.0
    profit_factor = (
        total_gross_profit / total_gross_loss if total_gross_loss > 0 else 0.0
    )

    # 最大ドローダウン
    max_drawdown_pct = 0.0
    if cumulative_pnl:
        peak = cumulative_pnl[0]
        for v in cumulative_pnl:
            if v > peak:
                peak = v
            dd = (peak - v) / initial_balance * 100 if initial_balance > 0 else 0.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

    # シャープレシオ（年率換算: sqrt(252)）
    sharpe_ratio = 0.0
    if len(pnl_per_trade) > 1:
        returns = [p / initial_balance for p in pnl_per_trade]
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        if std_r > 0:
            sharpe_ratio = mean_r / std_r * math.sqrt(252)

    # シグナル強度別勝率
    strong_signal_win_rate = strong_wins / strong_total if strong_total > 0 else 0.0
    medium_signal_win_rate = medium_wins / medium_total if medium_total > 0 else 0.0

    # ソース別勝率
    by_source = {
        src: stats[0] / stats[1] if stats[1] > 0 else 0.0
        for src, stats in source_stats.items()
    }

    return {
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "total_return_pct": total_return_pct,
        "avg_pnl_per_trade": avg_pnl_per_trade,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_drawdown_pct,
        "sharpe_ratio": sharpe_ratio,
        "strong_signal_win_rate": strong_signal_win_rate,
        "medium_signal_win_rate": medium_signal_win_rate,
        "by_source": by_source,
    }
