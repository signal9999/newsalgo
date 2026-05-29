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
from config.settings import COMMISSION_RATE, COMMISSION_MIN

logger = logging.getLogger(__name__)

INITIAL_BALANCE = 1_000_000.0


def _calc_commission(fill_price: float, quantity: float) -> float:
    """取引手数料を計算する（片道）。"""
    trade_value = fill_price * quantity
    return max(COMMISSION_MIN, trade_value * COMMISSION_RATE)
# デフォルト状態保存先（後方互換）
_STATE_FILE = Path(__file__).parent.parent / "logs" / "paper_state.json"


_REJECTION_ALERT_THRESHOLD = 5    # 連続リジェクト数でアラート
_REJECTION_ALERT_INTERVAL  = 300  # 同一アラートの再送間隔（秒）


class PaperTrader(BrokerBase):
    def __init__(self, logger_obj=None, state_file: Path = None,
                 initial_balance: float = INITIAL_BALANCE):
        self._logger = logger_obj
        self._state_file = state_file or _STATE_FILE
        self._initial_balance = initial_balance
        self._consecutive_rejections = 0    # 連続 price_unavailable カウンター
        self._last_rejection_alert   = 0.0  # 最後にアラートを送った時刻（Unix秒）
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
        self._consecutive_rejections = 0
        self._last_rejection_alert   = 0.0
        self._state_file.unlink(missing_ok=True)
        logger.info("ペーパートレード状態をリセットしました")

    def _handle_price_unavailable(self, symbol: str):
        """
        連続 price_unavailable リジェクトを追跡し、
        閾値超えで AlertManager に CRITICAL を送る。
        """
        import time
        self._consecutive_rejections += 1
        count = self._consecutive_rejections

        if count >= _REJECTION_ALERT_THRESHOLD:
            now = time.time()
            if now - self._last_rejection_alert >= _REJECTION_ALERT_INTERVAL:
                self._last_rejection_alert = now
                try:
                    from monitor.alert import AlertManager
                    AlertManager().send_alert(
                        "CRITICAL",
                        f"🚨 価格取得連続失敗: {count}件リジェクト済み",
                        {
                            "symbol":   symbol,
                            "count":    count,
                            "impact":   "全注文がリジェクトされています（取引停止状態）",
                            "check":    "Yahoo Finance API / ネットワーク接続を確認",
                        },
                    )
                    logger.error("[PT] 価格取得連続失敗アラート送信: %d件", count)
                except Exception as e:
                    logger.warning("[PT] アラート送信失敗: %s", e)

    # ------------------------------------------------------------------
    # BrokerBase 実装
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> OrderResult:
        order_id = str(uuid.uuid4())
        pnl      = 0.0

        # 成行注文は現在値をフェッチ + スリッページ（0.1%）を加算
        if order.price is not None:
            fill_price = order.price
        else:
            raw_price  = self._fetch_price(order.symbol)
            if raw_price <= 0.0:
                logger.warning("[PT] 価格取得失敗: %s → 注文スキップ", order.symbol)
                self._handle_price_unavailable(order.symbol)
                return OrderResult(
                    order_id=order_id, symbol=order.symbol, side=order.side,
                    quantity=order.quantity, fill_price=0.0, status="rejected",
                    reason="price_unavailable",
                )
            self._consecutive_rejections = 0  # 成功したらリセット
            slippage   = 0.001  # 0.1%（成行のスリッページ想定）
            fill_price = raw_price * (1 + slippage if order.side == "buy" else 1 - slippage)

        commission = _calc_commission(fill_price, order.quantity)

        if order.side == "buy":
            cost = fill_price * order.quantity + commission
            # ── 残高チェック（マイナス残高防止）────────────────────────────
            if cost > self.balance:
                logger.warning(
                    "[PT] 残高不足: 必要=¥%.0f  残高=¥%.0f → %s スキップ",
                    cost, self.balance, order.symbol,
                )
                return OrderResult(
                    order_id=order_id, symbol=order.symbol, side=order.side,
                    quantity=order.quantity, fill_price=fill_price, status="rejected",
                    reason="insufficient_funds",
                )
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
            pnl      = (fill_price - pos["avg_price"]) * sold_qty - commission
            self.realized_pnl += pnl
            self.balance      += fill_price * sold_qty - commission
            remaining          = pos["quantity"] - sold_qty
            if remaining <= 0:
                self.positions.pop(order.symbol, None)
            else:
                self.positions[order.symbol] = {
                    "quantity": remaining, "avg_price": pos["avg_price"]
                }
        else:
            commission = 0.0

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
            "pnl":          pnl,
            "commission":   commission,
            "balance":      self.balance,
            "realized_pnl": self.realized_pnl,
            "timestamp":    datetime.now(timezone.utc).isoformat(),
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
            "[PT] %s %s ×%d  fill=%.1f  commission=¥%.0f  pnl=%+.0f  balance=¥%,.0f",
            order.side, order.symbol, int(order.quantity),
            fill_price, commission, pnl, self.balance
        )
        return result

    # ------------------------------------------------------------------
    # 現在株価取得（yfinance・TTL 60秒キャッシュ）
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_price(symbol: str) -> float:
        """Yahoo Finance JSON API で現在値を取得（numpy不要・Mixhost対応）。
        TTL 60秒のキャッシュ付き。日本株は自動的に .T サフィックスを付与。
        """
        import time, urllib.request
        now = time.time()
        cached = _price_cache.get(symbol)
        if cached and now - cached[1] < 60:
            return cached[0]
        try:
            # 日本株（4桁数字）は .T サフィックスが必要
            ticker = symbol if "." in symbol else (f"{symbol}.T" if symbol.isdigit() and len(symbol) <= 5 else symbol)
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
                   f"?interval=1m&range=1d")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            meta  = data["chart"]["result"][0]["meta"]
            price = float(meta.get("regularMarketPrice") or meta.get("previousClose") or 0)
            if price > 0:
                _price_cache[symbol] = (price, now)
            return price
        except Exception as e:
            logger.debug("価格取得失敗 %s: %s", symbol, e)
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
