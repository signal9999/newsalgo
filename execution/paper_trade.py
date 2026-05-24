"""
ペーパートレードブローカー
- セッション間でポジション・残高を JSON ファイルに永続化
- Supabase order_log へも非同期で記録
"""
import uuid
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from execution.broker import BrokerBase, Order, OrderResult

logger = logging.getLogger(__name__)

INITIAL_BALANCE = 1_000_000.0
# 状態保存先
_STATE_FILE = Path(__file__).parent.parent / "logs" / "paper_state.json"


class PaperTrader(BrokerBase):
    def __init__(self, logger_obj=None):
        self._logger = logger_obj
        self._load_state()

    # ------------------------------------------------------------------
    # 状態の永続化
    # ------------------------------------------------------------------

    def _load_state(self):
        """JSON ファイルから前回の状態を復元する。"""
        if _STATE_FILE.exists():
            try:
                with open(_STATE_FILE, encoding="utf-8") as f:
                    state = json.load(f)
                self.balance       = float(state.get("balance",      INITIAL_BALANCE))
                self.realized_pnl  = float(state.get("realized_pnl", 0.0))
                self.positions     = state.get("positions", {})
                self.orders: list  = []
                logger.info("ペーパートレード状態を復元: balance=¥%,.0f  positions=%d件",
                            self.balance, len(self.positions))
                return
            except Exception as e:
                logger.warning("状態ファイルの読み込み失敗（リセット）: %s", e)

        # 初期状態
        self.balance      = INITIAL_BALANCE
        self.realized_pnl = 0.0
        self.positions: dict = {}
        self.orders: list    = []

    def _save_state(self):
        """現在の状態を JSON ファイルに保存する。"""
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "balance":      self.balance,
            "realized_pnl": self.realized_pnl,
            "positions":    self.positions,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("状態ファイルの保存失敗: %s", e)

    def reset(self):
        """ポジションと残高を初期化する（テスト用）。"""
        self.balance      = INITIAL_BALANCE
        self.realized_pnl = 0.0
        self.positions    = {}
        self.orders       = []
        _STATE_FILE.unlink(missing_ok=True)
        logger.info("ペーパートレード状態をリセットしました")

    # ------------------------------------------------------------------
    # BrokerBase 実装
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> OrderResult:
        order_id   = str(uuid.uuid4())
        fill_price = order.price if order.price is not None else 0.0
        pnl        = 0.0

        if order.side == "buy":
            cost = fill_price * order.quantity
            self.balance -= cost
            pos       = self.positions.get(order.symbol, {"quantity": 0.0, "avg_price": 0.0})
            total_qty = pos["quantity"] + order.quantity
            avg_price = (
                (pos["avg_price"] * pos["quantity"] + fill_price * order.quantity) / total_qty
                if total_qty > 0 else fill_price
            )
            self.positions[order.symbol] = {"quantity": total_qty, "avg_price": avg_price}

        elif order.side == "sell":
            pos      = self.positions.get(order.symbol, {"quantity": 0.0, "avg_price": 0.0})
            sold_qty = min(order.quantity, pos["quantity"])
            pnl      = (fill_price - pos["avg_price"]) * sold_qty
            self.realized_pnl += pnl
            self.balance      += fill_price * sold_qty
            remaining          = pos["quantity"] - sold_qty
            if remaining <= 0:
                self.positions.pop(order.symbol, None)
            else:
                self.positions[order.symbol] = {
                    "quantity": remaining, "avg_price": pos["avg_price"]
                }

        result = OrderResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            status="filled",
        )
        self.orders.append(result)

        # 状態を永続化
        self._save_state()

        # ログ記録
        log_data = {
            **result.__dict__,
            "pnl":         pnl,
            "balance":     self.balance,
            "realized_pnl": self.realized_pnl,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }
        try:
            if self._logger:
                self._logger.log_order(log_data)
            else:
                from monitor.logger import StructuredLogger
                StructuredLogger().log_order(log_data)
        except Exception:
            pass

        logger.info(
            "[PT] %s %s ×%d  fill=%.1f  pnl=%+.0f  balance=¥%,.0f",
            order.side, order.symbol, int(order.quantity),
            fill_price, pnl, self.balance
        )
        return result

    async def get_position(self, symbol: str) -> dict:
        pos = self.positions.get(symbol)
        if pos is None:
            return {"symbol": symbol, "quantity": 0.0, "avg_price": 0.0, "unrealized_pnl": 0.0}
        # unrealized は現在価格が不明なためゼロ表示（将来: yfinance で取得）
        return {
            "symbol":          symbol,
            "quantity":        pos["quantity"],
            "avg_price":       pos["avg_price"],
            "unrealized_pnl":  0.0,
        }

    async def get_account(self) -> dict:
        return {
            "balance":        self.balance,
            "realized_pnl":   self.realized_pnl,
            "unrealized_pnl": 0.0,
            "total":          self.balance,
            "initial":        INITIAL_BALANCE,
            "return_pct":     (self.balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100,
        }

    async def cancel_order(self, order_id: str) -> bool:
        for result in self.orders:
            if result.order_id == order_id and result.status == "pending":
                result.status = "cancelled"
                self._save_state()
                return True
        return False

    def summary(self) -> str:
        """口座サマリー文字列を返す（ログ用）。"""
        ret = (self.balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100
        sign = "+" if ret >= 0 else ""
        return (
            f"残高=¥{self.balance:,.0f}  "
            f"実現損益=¥{self.realized_pnl:+,.0f}  "
            f"リターン={sign}{ret:.2f}%  "
            f"ポジション={len(self.positions)}件"
        )
