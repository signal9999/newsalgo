"""
Interactive Brokers (IBKR) ブローカーアダプター

【接続要件】
  - TWS (Trader Workstation) または IB Gateway が起動済みであること
  - ib_insync のインストール: pip install ib_insync
  - TWS の設定: API → Settings → Enable ActiveX and Socket Clients = ON
                Socket port: 7497 (paper) / 7496 (live)

【起動手順】
  1. `pip install ib_insync` でライブラリをインストール
  2. TWS を起動してペーパートレードアカウントにログイン
  3. .env に IBKR_HOST=127.0.0.1 / IBKR_PORT=7497 を追記
  4. PAPER_TRADE=false に変更（実際の発注に切り替える場合）

【現在の状態】
  スタブ実装（ib_insync 未インストール時はシミュレーションで動作）
"""

import asyncio
import uuid
import logging
from typing import Optional

from execution.broker import BrokerBase, Order, OrderResult

logger = logging.getLogger(__name__)

# IBKR 接続設定（.env から読み込むことが望ましい）
_IBKR_HOST = "127.0.0.1"
_IBKR_PORT_PAPER = 7497  # ペーパートレード
_IBKR_PORT_LIVE  = 7496  # 本番口座
_IBKR_CLIENT_ID  = 1

# 東証コード → IBKR コントラクト変換
# IBKR は東証銘柄を "symbol.T" ではなく "symbol" + exchange="TSE" + currency="JPY" で扱う
def _make_contract(symbol: str):
    """
    東証コード（例: "7203"）から IBKR Contract オブジェクトを生成する。
    ib_insync が利用可能な場合のみ動作する。
    """
    try:
        from ib_insync import Stock
        return Stock(symbol, "TSE", "JPY")
    except ImportError:
        return None


class IBKRBroker(BrokerBase):
    """
    Interactive Brokers ブローカーアダプター。
    ib_insync が未インストールの場合はスタブとして動作し、
    実際の注文は送信しない（ログのみ出力）。
    """

    def __init__(self, paper: bool = True):
        self._paper = paper
        self._port  = _IBKR_PORT_PAPER if paper else _IBKR_PORT_LIVE
        self._ib    = None  # ib_insync.IB インスタンス
        self._connected = False

    async def connect(self) -> bool:
        """TWS/IB Gateway に接続する。"""
        try:
            from ib_insync import IB
            self._ib = IB()
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._ib.connect(_IBKR_HOST, self._port, clientId=_IBKR_CLIENT_ID)
            )
            self._connected = True
            logger.info("IBKR 接続成功: host=%s port=%s paper=%s", _IBKR_HOST, self._port, self._paper)
            return True
        except ImportError:
            logger.warning("ib_insync が未インストールです。スタブモードで動作します。")
            logger.warning("インストール: pip install ib_insync")
            return False
        except Exception as e:
            logger.error("IBKR 接続失敗: %s", e)
            return False

    async def disconnect(self):
        if self._ib and self._connected:
            self._ib.disconnect()
            self._connected = False
            logger.info("IBKR 切断")

    # ------------------------------------------------------------------
    # BrokerBase 実装
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> OrderResult:
        """注文を送信する。未接続時はスタブとして動作する。"""
        order_id = str(uuid.uuid4())

        if not self._connected:
            # スタブ動作: 注文をログするだけ（実際には送信しない）
            logger.info(
                "[IBKR-STUB] 注文シミュレーション: %s %s %s × %d @ market",
                order.side, order.symbol, order.order_type, int(order.quantity)
            )
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                fill_price=order.price or 0.0,
                status="filled",  # スタブでは常に約定成功とする
                reason="stub_mode",
            )

        # ── 実際の IBKR 注文送信 ──────────────────────────────────────
        try:
            from ib_insync import MarketOrder, LimitOrder

            contract = _make_contract(order.symbol)
            if contract is None:
                raise RuntimeError("コントラクト生成失敗")

            # コントラクト詳細を取得
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._ib.qualifyContracts(contract)
            )

            # 注文種別
            action = "BUY" if order.side == "buy" else "SELL"
            if order.order_type == "limit" and order.price:
                ib_order = LimitOrder(action, order.quantity, order.price)
            else:
                ib_order = MarketOrder(action, order.quantity)

            trade = self._ib.placeOrder(contract, ib_order)
            self._ib.sleep(1)  # 約定待機

            fill_price = trade.orderStatus.avgFillPrice or order.price or 0.0
            status = "filled" if trade.orderStatus.status == "Filled" else "pending"

            logger.info(
                "[IBKR] 注文送信完了: id=%s %s %s × %d fill=%.2f status=%s",
                order_id, order.side, order.symbol, int(order.quantity), fill_price, status
            )
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                fill_price=fill_price,
                status=status,
            )

        except Exception as e:
            logger.error("[IBKR] 注文エラー: %s", e)
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                fill_price=0.0,
                status="rejected",
                reason=str(e),
            )

    async def get_position(self, symbol: str) -> dict:
        if not self._connected:
            return {"symbol": symbol, "quantity": 0.0, "avg_price": 0.0}
        try:
            positions = self._ib.positions()
            for p in positions:
                if p.contract.localSymbol == symbol or p.contract.symbol == symbol:
                    return {
                        "symbol":    symbol,
                        "quantity":  p.position,
                        "avg_price": p.avgCost,
                    }
        except Exception as e:
            logger.error("[IBKR] ポジション取得エラー: %s", e)
        return {"symbol": symbol, "quantity": 0.0, "avg_price": 0.0}

    async def get_account(self) -> dict:
        if not self._connected:
            return {"cash": 0.0, "net_liquidation": 0.0, "currency": "JPY"}
        try:
            summary = {v.tag: v.value for v in self._ib.accountSummary()}
            return {
                "cash":            float(summary.get("TotalCashValue", 0)),
                "net_liquidation": float(summary.get("NetLiquidation", 0)),
                "currency":        summary.get("Currency", "JPY"),
            }
        except Exception as e:
            logger.error("[IBKR] 口座情報取得エラー: %s", e)
            return {"cash": 0.0, "net_liquidation": 0.0, "currency": "JPY"}

    async def cancel_order(self, order_id: str) -> bool:
        logger.warning("[IBKR] cancel_order は order_id による取消しに未対応（trade オブジェクトが必要）")
        return False
