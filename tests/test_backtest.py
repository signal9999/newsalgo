import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from backtest.metrics import calculate_metrics
from backtest.simulator import BacktestSimulator
from backtest.data_loader import load_sample_news
from backtest.runner import BacktestRunner


# ──────────────────────────────────────────────────────────────────────────────
# calculate_metrics テスト
# ──────────────────────────────────────────────────────────────────────────────

def test_metrics_empty():
    """空のトレードリストで calculate_metrics を呼んでもエラーにならない"""
    result = calculate_metrics([])
    assert result["win_rate"] == 0.0


def test_metrics_basic():
    """2件のトレードで基本指標を正しく計算できる"""
    trade1 = {
        "pnl": 5000.0,
        "pnl_pct": 0.05,
        "signal_level": "STRONG",
        "source": "tdnet",
        "status": "closed",
    }
    trade2 = {
        "pnl": -3000.0,
        "pnl_pct": -0.03,
        "signal_level": "MEDIUM",
        "source": "nhk_economy",
        "status": "closed",
    }
    result = calculate_metrics([trade1, trade2])

    assert result["total_trades"] == 2
    assert result["winning_trades"] == 1
    assert result["win_rate"] == pytest.approx(0.5)
    assert result["total_pnl"] == pytest.approx(2000.0)
    assert result["profit_factor"] > 1.0


# ──────────────────────────────────────────────────────────────────────────────
# BacktestSimulator テスト
# ──────────────────────────────────────────────────────────────────────────────

def _make_signal(direction: str = "bullish", level: str = "STRONG", symbols: list = None) -> dict:
    return {
        "direction": direction,
        "level": level,
        "score": 0.9,
        "affected_symbols": symbols or ["7203"],
    }


def _make_news(symbol: str = "7203") -> dict:
    return {
        "id": "test_001",
        "title": "テストニュース",
        "source": "tdnet",
        "timestamp": "2026-05-20T09:00:00+09:00",
        "affected_symbols": [symbol],
    }


def test_simulator_buy():
    """bullish/STRONG シグナルで execute_signal がトレードを返す"""
    sim = BacktestSimulator()
    signal = _make_signal(direction="bullish", level="STRONG")
    news = _make_news()
    trade = sim.execute_signal(signal, news, entry_price=3500.0)

    assert trade is not None
    assert trade["side"] == "buy"
    assert trade["status"] == "open"
    assert trade["symbol"] == "7203"
    assert trade["entry_price"] == pytest.approx(3500.0)


def test_simulator_close():
    """buy → close_position で pnl が計算される"""
    sim = BacktestSimulator()
    signal = _make_signal(direction="bullish", level="STRONG")
    news = _make_news()
    sim.execute_signal(signal, news, entry_price=3500.0)

    closed = sim.close_position("7203", exit_price=3640.0)
    assert closed is not None
    assert closed["status"] == "closed"
    assert closed["exit_price"] == pytest.approx(3640.0)
    # 価格が上昇したので pnl > 0
    assert closed["pnl"] > 0


def test_simulator_bearish():
    """bearish シグナルで side が 'sell_short' になる"""
    sim = BacktestSimulator()
    signal = _make_signal(direction="bearish", level="STRONG", symbols=["9201"])
    news = _make_news(symbol="9201")
    trade = sim.execute_signal(signal, news, entry_price=2800.0)

    assert trade is not None
    assert trade["side"] == "sell_short"
    assert trade["direction"] == "bearish"


# ──────────────────────────────────────────────────────────────────────────────
# load_sample_news テスト
# ──────────────────────────────────────────────────────────────────────────────

def test_load_sample_news():
    """load_sample_news() が 10 件返す"""
    items = load_sample_news()
    assert len(items) == 10


# ──────────────────────────────────────────────────────────────────────────────
# BacktestRunner テスト
# ──────────────────────────────────────────────────────────────────────────────

def test_runner_with_sample():
    """BacktestRunner(use_llm=False).run_sync() が dict を返し 'metrics' と 'trades' を持つ"""
    runner = BacktestRunner(use_llm=False)
    news_items = load_sample_news()[:3]
    result = runner.run_sync(news_items)

    assert isinstance(result, dict)
    assert "metrics" in result
    assert "trades" in result
