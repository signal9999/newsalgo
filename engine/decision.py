from execution.risk import RiskManager
from execution.paper_trade import PaperTrader
from execution.broker import Order
from monitor.logger import StructuredLogger
from monitor.alert import AlertManager
import uuid


class DecisionEngine:
    def __init__(self, broker: PaperTrader, risk: RiskManager, logger: StructuredLogger, alert: AlertManager):
        self.broker = broker
        self.risk = risk
        self.logger = logger
        self.alert = alert

    async def execute(self, signal: dict, news_item: dict) -> dict:
        if signal["level"] == "NONE":
            return {"action": "skip", "reason": "signal_too_weak"}

        account = await self.broker.get_account()
        balance = account["balance"]
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
        qty = risk_check["position_size"] / 1000

        orders = []
        for symbol in symbols[:3]:
            order = Order(
                symbol=symbol,
                side=side,
                quantity=qty,
                price=None,
                order_type="market",
                signal_id=str(uuid.uuid4()),
            )
            result = await self.broker.submit_order(order)
            self.logger.log_order(result.__dict__)
            orders.append(result.__dict__)

        if signal["level"] == "STRONG":
            self.alert.alert_strong_signal(signal)

        return {"action": "executed", "orders": orders}
