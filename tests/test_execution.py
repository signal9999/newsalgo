import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import asyncio
from unittest.mock import MagicMock
from execution.risk import RiskManager
from execution.paper_trade import PaperTrader
from execution.broker import Order


def test_risk_approved():
    rm = RiskManager()
    signal = {"source": "tdnet", "level": "STRONG", "direction": "bullish"}
    result = rm.check_risk(signal, 1_000_000)
    assert result["approved"] is True
    assert result["position_size"] == pytest.approx(50_000, rel=0.01)

def test_risk_cooldown():
    rm = RiskManager()
    signal = {"source": "tdnet", "level": "STRONG", "direction": "bullish"}
    rm.check_risk(signal, 1_000_000)
    result = rm.check_risk(signal, 1_000_000)
    assert result["approved"] is False
    assert "cooldown" in result["reason"].lower() or "クールダウン" in result["reason"]

def test_risk_daily_loss_limit():
    rm = RiskManager()
    rm.record_loss(100_001)
    signal = {"source": "tdnet", "level": "STRONG", "direction": "bullish"}
    result = rm.check_risk(signal, 1_000_000)
    assert result["approved"] is False

def test_risk_reset_daily():
    rm = RiskManager()
    rm.record_loss(200_000)
    rm.reset_daily()
    signal = {"source": "tdnet", "level": "STRONG", "direction": "bullish"}
    result = rm.check_risk(signal, 1_000_000)
    assert result["approved"] is True


@pytest.mark.asyncio
async def test_paper_trade_buy():
    mock_logger = MagicMock()
    mock_logger.log_order = MagicMock()
    trader = PaperTrader(mock_logger)
    trader.reset()  # 永続化ファイルをクリアして初期状態に
    order = Order("7203.T", "buy", 10, 2500.0, "market", "sig1")
    result = await trader.submit_order(order)
    assert result.status == "filled"
    assert result.symbol == "7203.T"
    account = await trader.get_account()
    assert account["balance"] < 1_000_000

@pytest.mark.asyncio
async def test_paper_trade_sell_pnl():
    mock_logger = MagicMock()
    mock_logger.log_order = MagicMock()
    trader = PaperTrader(mock_logger)
    trader.reset()  # 永続化ファイルをクリアして初期状態に
    buy = Order("7203.T", "buy", 10, 2000.0, "market", "sig1")
    await trader.submit_order(buy)
    sell = Order("7203.T", "sell", 10, 2500.0, "market", "sig2")
    await trader.submit_order(sell)
    account = await trader.get_account()
    assert account["realized_pnl"] == pytest.approx(5000.0, rel=0.01)
