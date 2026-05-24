from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    symbol: str
    side: str  # "buy" | "sell"
    quantity: float
    price: Optional[float]
    order_type: str  # "market" | "limit"
    signal_id: str


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: str
    quantity: float
    fill_price: float
    status: str  # "filled" | "rejected" | "pending"
    reason: str = ""


class BrokerBase(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult:
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> dict:
        ...

    @abstractmethod
    async def get_account(self) -> dict:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        ...
