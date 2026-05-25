from execution.risk import RiskManager
from execution.paper_trade import PaperTrader
from execution.broker import Order
from monitor.logger import StructuredLogger
from monitor.alert import AlertManager
import uuid


class DecisionEngine:
    def __init__(self, broker: PaperTrader, risk: RiskManager,
                 logger: StructuredLogger, alert: AlertManager):
        self.broker = broker
        self.risk   = risk
        self.logger = logger
        self.alert  = alert

    async def execute(self, signal: dict, news_item: dict) -> dict:
        if signal["level"] == "NONE":
            return {"action": "skip", "reason": "signal_too_weak"}

        account   = await self.broker.get_account()
        balance   = account["balance"]
        risk_check = self.risk.check_risk(
            {"source": news_item.get("source", "unknown"), **signal},
            balance,
        )

        if not risk_check["approved"]:
            self.logger.log_error("risk_rejected", {"reason": risk_check["reason"], "signal": signal})
            return {"action": "rejected", "reason": risk_check["reason"]}

        symbols = signal.get("affected_symbols", [])
        if not symbols:
            return {"action": "skip", "reason": "no_affected_symbols"}

        side = "buy" if signal["direction"] == "bullish" else "sell"

        orders = []
        for symbol in symbols[:3]:
            # ── 重複エントリー防止 ─────────────────────────────────────────
            existing = await self.broker.get_position(symbol)
            if side == "buy" and existing["quantity"] > 0:
                self.logger.log_error("duplicate_entry_skipped",
                                      {"symbol": symbol, "existing_qty": existing["quantity"]})
                continue
            # 空売り（sell）でポジションなし → スキップ（未実装につきサイレント失敗を防ぐ）
            if side == "sell" and existing["quantity"] <= 0:
                self.logger.log_error("no_position_to_sell",
                                      {"symbol": symbol, "side": side})
                continue

            # ── 発注サイズ計算（現在値ベース）─────────────────────────────
            current_price = existing.get("current_price", 0.0) or \
                            self.broker._fetch_price(symbol)
            if current_price > 0:
                # 予算内で100株単位に切り捨て
                raw_qty = risk_check["position_size"] / current_price
                qty = max(100, int(raw_qty / 100) * 100)
            else:
                qty = 100  # 価格取得失敗時のフォールバック

            order = Order(
                symbol=symbol,
                side=side,
                quantity=qty,
                price=None,
                order_type="market",
                signal_id=str(uuid.uuid4()),
            )
            result = await self.broker.submit_order(order)

            # ── 日次損失上限に実損失を記録 ──────────────────────────────────
            pnl = result.__dict__.get("pnl", 0.0) or 0.0
            if pnl < 0:
                self.risk.record_loss(abs(pnl))

            self.logger.log_order({**result.__dict__, "pnl": pnl})
            orders.append(result.__dict__)

        if not orders:
            return {"action": "skip", "reason": "all_symbols_filtered"}

        if signal["level"] == "STRONG":
            self.alert.alert_strong_signal(signal)

        return {"action": "executed", "orders": orders}
