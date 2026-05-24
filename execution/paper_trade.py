import uuid
from execution.broker import BrokerBase, Order, OrderResult

INITIAL_BALANCE = 1_000_000.0


class PaperTrader(BrokerBase):
    def __init__(self, logger=None):
        self.balance: float = INITIAL_BALANCE
        self.realized_pnl: float = 0.0
        self.positions: dict[str, dict] = {}
        self.orders: list[OrderResult] = []
        self._logger = logger

    async def submit_order(self, order: Order) -> OrderResult:
        order_id = str(uuid.uuid4())
        fill_price = order.price if order.price is not None else 0.0

        if order.side == "buy":
            cost = fill_price * order.quantity
            self.balance -= cost
            pos = self.positions.get(order.symbol, {"quantity": 0.0, "avg_price": 0.0})
            total_qty = pos["quantity"] + order.quantity
            avg_price = (pos["avg_price"] * pos["quantity"] + fill_price * order.quantity) / total_qty
            self.positions[order.symbol] = {"quantity": total_qty, "avg_price": avg_price}

        elif order.side == "sell":
            pos = self.positions.get(order.symbol, {"quantity": 0.0, "avg_price": 0.0})
            sold_qty = min(order.quantity, pos["quantity"])
            pnl = (fill_price - pos["avg_price"]) * sold_qty
            self.realized_pnl += pnl
            self.balance += fill_price * sold_qty
            remaining = pos["quantity"] - sold_qty
            if remaining <= 0:
                self.positions.pop(order.symbol, None)
            else:
                self.positions[order.symbol] = {"quantity": remaining, "avg_price": pos["avg_price"]}

        result = OrderResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            status="filled",
        )
        self.orders.append(result)

        try:
            if self._logger:
                self._logger.log_order(result.__dict__)
            else:
                logger_mod = __import__("monitor.logger", fromlist=["StructuredLogger"])
                logger_mod.StructuredLogger().log_order(result.__dict__)
        except Exception:
            pass

        return result

    async def get_position(self, symbol: str) -> dict:
        pos = self.positions.get(symbol)
        if pos is None:
            return {"symbol": symbol, "quantity": 0.0, "avg_price": 0.0, "unrealized_pnl": 0.0}
        mock_current_price = pos["avg_price"]
        unrealized_pnl = (mock_current_price - pos["avg_price"]) * pos["quantity"]
        return {
            "symbol": symbol,
            "quantity": pos["quantity"],
            "avg_price": pos["avg_price"],
            "current_price": mock_current_price,
            "unrealized_pnl": unrealized_pnl,
        }

    async def get_account(self) -> dict:
        unrealized_pnl = sum(
            (pos["avg_price"] - pos["avg_price"]) * pos["quantity"]
            for pos in self.positions.values()
        )
        return {
            "balance": self.balance,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "total": self.balance + unrealized_pnl,
        }

    async def cancel_order(self, order_id: str) -> bool:
        for result in self.orders:
            if result.order_id == order_id and result.status == "pending":
                result.status = "cancelled"
                return True
        return False
