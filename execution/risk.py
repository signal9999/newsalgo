import time
from config.settings import MAX_POSITION_PCT, DAILY_LOSS_LIMIT_PCT


class RiskManager:
    def __init__(self):
        self.daily_loss: float = 0.0
        self.last_signal_time: dict[str, float] = {}

    def check_risk(self, signal: dict, account_balance: float) -> dict:
        loss_limit = account_balance * DAILY_LOSS_LIMIT_PCT
        if self.daily_loss >= loss_limit:
            return {
                "approved": False,
                "reason": f"daily loss limit reached ({self.daily_loss:.0f}/{loss_limit:.0f})",
                "position_size": 0.0,
            }

        source = signal.get("source", "unknown")
        now = time.time()
        last = self.last_signal_time.get(source, 0.0)
        if now - last < 60.0:
            remaining = int(60.0 - (now - last))
            return {
                "approved": False,
                "reason": f"cooldown active for source '{source}' ({remaining}s remaining)",
                "position_size": 0.0,
            }

        self.last_signal_time[source] = now
        return {
            "approved": True,
            "reason": "",
            "position_size": account_balance * MAX_POSITION_PCT,
        }

    def record_loss(self, amount: float) -> None:
        self.daily_loss += amount

    def reset_daily(self) -> None:
        self.daily_loss = 0.0
