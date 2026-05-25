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

_price_cache: dict = {}  # symbol → (price, fetched_at)

from execution.broker import BrokerBase, Order, OrderResult

logger = logging.getLogger(__name__)

INITIAL_BALANCE = 1_000_000.0
# デフォルト状態保存先（後方互換）
_STATE_FILE = Path(__file__).parent.parent / "logs" / "paper_state.json"


class PaperTrader(BrokerBase):
    def __init__(self, logger_obj=None, state_file: Path = None,
                 initial_balance: float = INITIAL_BALANCE):
        self._logger = logger_obj
        self._state_file = state_file or _STATE_FILE
        self._initial_balance = initial_balance
        self._load_state()

    # ------------------------------------------------------------------
    # 状態の永続化
    # ------------------------------------------------------------------

    def _load_state(self):
        """JSON ファイルから前回の状態を復元する。"""
        if self._state_file.exists():
            try:
                with open(self._state_file, encoding="utf-8") as f:
                    state = json.load(f)
                self.balance       = float(state.get("balance",      self._initial_balance))
                self.realized_pnl  = float(state.get("realized_pnl", 0.0))
                self.positions     = state.get("positions", {})
                self.orders: list  = []
                logger.info("ペーパートレード状態を復元: balance=¥%,.0f  positions=%d件",
                            self.balance, len(self.positions))
                return
            except Exception as e:
                logger.warning("状態ファイルの読み込み失敗（リセット）: %s", e)

        # 初期状態
        self.balance      = self._initial_balance
        self.realized_pnl = 0.0
        self.positions: dict = {}
        self.orders: list    = []

    def _save_state(self):
        """現在の状態を JSON ファイルに保存する。"""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "balance":      self.balance,
            "realized_pnl": self.realized_pnl,
            "positions":    self.positions,
            "updated_at":   datetime.now(timezone.utc).isoformat(),
        }
        try:
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("状態ファイルの保存失敗: %s", e)

    def reset(self):
        """ポジションと残高を初期化する（テスト用）。"""
        self.balance      = self._initial_balance
        self.realized_pnl = 0.0
        self.positions    = {}
        self.orders       = []
        self._state_file.unlink(missing_ok=True)
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

    # ------------------------------------------------------------------
    # 現在株価取得（yfinance・TTL 60秒キャッシュ）
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_price(symbol: str) -> float:
        """yfinance で現在値を取得。失敗時は 0.0。TTL 60秒のキャッシュ付き。"""
        import time
        now = time.time()
        cached = _price_cache.get(symbol)
        if cached and now - cached[1] < 60:
            return cached[0]
        try:
            import yfinance as yf
            hist = yf.Ticker(symbol).history(period="2d")
            if hist.empty:
                return 0.0
            raw = hist["Close"].iloc[-1]
            price = float(raw.iloc[0]) if hasattr(raw, "iloc") else float(raw)
            _price_cache[symbol] = (price, now)
            return price
        except Exception:
            return 0.0

    async def get_position(self, symbol: str) -> dict:
        pos = self.positions.get(symbol)
        if pos is None:
            return {"symbol": symbol, "quantity": 0.0, "avg_price": 0.0,
                    "current_price": 0.0, "unrealized_pnl": 0.0}
        current = self._fetch_price(symbol)
        unrealized = (current - pos["avg_price"]) * pos["quantity"] if current else 0.0
        return {
            "symbol":          symbol,
            "quantity":        pos["quantity"],
            "avg_price":       pos["avg_price"],
            "current_price":   current,
            "unrealized_pnl":  unrealized,
        }

    async def get_account(self) -> dict:
        unrealized = 0.0
        for symbol, pos in self.positions.items():
            current = self._fetch_price(symbol)
            if current:
                unrealized += (current - pos["avg_price"]) * pos["quantity"]
        total = self.balance + unrealized
        return {
            "balance":        self.balance,
            "realized_pnl":   self.realized_pnl,
            "unrealized_pnl": unrealized,
            "total":          total,
            "initial":        INITIAL_BALANCE,
            "return_pct":     (total - INITIAL_BALANCE) / INITIAL_BALANCE * 100,
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
