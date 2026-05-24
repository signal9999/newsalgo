"""
バックテスト仮想売買シミュレーター
シグナルに基づいて仮想取引を実行し、P&L を記録する
"""

import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

INITIAL_BALANCE = 1_000_000.0  # 初期残高100万円
POSITION_PCT = 0.05            # 1銘柄あたり5%


def _now_iso() -> str:
    """現在時刻を ISO 形式文字列で返す（UTC）。"""
    return datetime.now(tz=timezone.utc).isoformat()


# ─────────────────────────────────────────────
# BacktestSimulator
# ─────────────────────────────────────────────

class BacktestSimulator:
    """
    シグナルに基づいて仮想取引を実行し、P&L を追跡するシミュレーター。

    Attributes
    ----------
    balance : float
        現在の残高（実現損益を反映）。
    position_pct : float
        1銘柄あたりのポジションサイズ（残高に対する比率）。
    trades : list[dict]
        全クローズ済みトレードの履歴。
    open_positions : dict[str, dict]
        オープン中のポジション { symbol: trade_dict }。
    """

    def __init__(
        self,
        initial_balance: float = INITIAL_BALANCE,
        position_pct: float = POSITION_PCT,
    ):
        self.balance: float = initial_balance
        self.position_pct: float = position_pct
        self.trades: list = []
        self.open_positions: dict = {}

    # ─────────────────────────────────────────
    # ポジションサイズ計算
    # ─────────────────────────────────────────

    def _calc_quantity(self, entry_price: float) -> float:
        """残高の position_pct 分に相当する株数を計算する（端数切り捨て）。"""
        if entry_price <= 0:
            return 0.0
        invest_amount = self.balance * self.position_pct
        return invest_amount / entry_price

    # ─────────────────────────────────────────
    # シグナル実行
    # ─────────────────────────────────────────

    def execute_signal(
        self,
        signal: dict,
        news_item: dict,
        entry_price: float,
    ) -> Optional[dict]:
        """
        シグナルに基づいて仮想発注を行う。

        Parameters
        ----------
        signal : dict
            アナライザーが出力したシグナル辞書。
            必須キー: "level" ("NONE" | "MEDIUM" | "STRONG"),
                      "direction" ("bullish" | "bearish"),
                      "affected_symbols" (list[str])
        news_item : dict
            対応するニュースアイテム。
        entry_price : float
            エントリー価格。

        Returns
        -------
        dict | None
            トレード辞書（オープン状態）。NONE シグナルまたは価格が 0 以下の場合は None。
        """
        # NONE シグナルは無視
        level = signal.get("level", "NONE")
        if level == "NONE":
            return None

        if entry_price <= 0:
            return None

        direction = signal.get("direction", "bullish")
        side = "buy" if direction == "bullish" else "sell_short"

        # シグナルに含まれる最初の銘柄をメインとして使用
        # （複数銘柄は execute_signal を複数回呼ぶ想定）
        symbols = signal.get("affected_symbols", [])
        symbol = symbols[0] if symbols else news_item.get("affected_symbols", [""])[0]

        if not symbol:
            return None

        # 同一銘柄に既存ポジションがある場合は追加しない
        if symbol in self.open_positions:
            return None

        quantity = self._calc_quantity(entry_price)
        if quantity <= 0:
            return None

        trade_id = str(uuid.uuid4())
        trade: dict = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": None,
            "quantity": quantity,
            "pnl": None,
            "pnl_pct": None,
            "direction": direction,
            "signal_level": level,
            "news_title": news_item.get("title", ""),
            "entry_time": news_item.get("timestamp", _now_iso()),
            "exit_time": None,
            "status": "open",
        }

        self.open_positions[symbol] = trade
        return trade

    # ─────────────────────────────────────────
    # ポジションクローズ
    # ─────────────────────────────────────────

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "hold_expired",
    ) -> Optional[dict]:
        """
        指定銘柄のポジションをクローズして P&L を確定する。

        Parameters
        ----------
        symbol : str
            東証コード。
        exit_price : float
            決済価格。
        reason : str
            クローズ理由（ログ用）。

        Returns
        -------
        dict | None
            クローズ済みトレード辞書。ポジションが存在しない場合は None。
        """
        if symbol not in self.open_positions:
            return None

        trade = self.open_positions.pop(symbol)
        qty = trade["quantity"]
        entry_price = trade["entry_price"]
        direction = trade["direction"]

        # P&L 計算
        if direction == "bullish":
            # ロング: 価格上昇で利益
            raw_pnl = (exit_price - entry_price) * qty
        else:
            # ショート: 価格下落で利益
            raw_pnl = (entry_price - exit_price) * qty

        pnl_pct = (exit_price - entry_price) / entry_price * 100.0
        if direction == "bearish":
            pnl_pct = -pnl_pct

        # 残高更新
        self.balance += raw_pnl

        # トレード情報を更新
        trade["exit_price"] = exit_price
        trade["pnl"] = raw_pnl
        trade["pnl_pct"] = pnl_pct
        trade["exit_time"] = _now_iso()
        trade["status"] = "closed"
        trade["close_reason"] = reason

        self.trades.append(trade)
        return trade

    # ─────────────────────────────────────────
    # 全ポジション強制クローズ
    # ─────────────────────────────────────────

    def close_all(self, price_fn: Callable) -> list:
        """
        全オープンポジションを強制クローズする（バックテスト終了時）。

        Parameters
        ----------
        price_fn : Callable[[str], float]
            symbol を受け取り現在値を返す関数。
            例: lambda sym: get_price_at(sym, "2026-05-24T15:00:00+09:00")

        Returns
        -------
        list[dict]
            クローズ済みトレードのリスト。
        """
        closed: list = []
        symbols = list(self.open_positions.keys())

        for symbol in symbols:
            try:
                price = price_fn(symbol)
            except Exception:
                price = None

            if price is None or price <= 0:
                # 価格取得失敗時はエントリー価格でクローズ（P&L=0）
                price = self.open_positions[symbol]["entry_price"]

            result = self.close_position(symbol, price, reason="force_close")
            if result is not None:
                closed.append(result)

        return closed

    # ─────────────────────────────────────────
    # サマリー
    # ─────────────────────────────────────────

    def get_summary(self) -> dict:
        """
        バックテスト結果のサマリーを返す。

        Returns
        -------
        dict
            {
                "total_trades": int,        # クローズ済みトレード数
                "balance": float,           # 現在残高
                "realized_pnl": float,      # 実現損益合計
                "open_positions": int,      # オープン中ポジション数
                "win_trades": int,          # 勝ちトレード数
                "loss_trades": int,         # 負けトレード数
                "win_rate": float,          # 勝率（0.0〜1.0）
                "avg_pnl_pct": float,       # 平均損益率（%）
            }
        """
        realized_pnl = sum(t.get("pnl", 0.0) or 0.0 for t in self.trades)
        win_trades = sum(1 for t in self.trades if (t.get("pnl") or 0.0) > 0)
        loss_trades = sum(1 for t in self.trades if (t.get("pnl") or 0.0) <= 0)
        total = len(self.trades)
        win_rate = win_trades / total if total > 0 else 0.0

        pnl_pcts = [t.get("pnl_pct") or 0.0 for t in self.trades]
        avg_pnl_pct = sum(pnl_pcts) / len(pnl_pcts) if pnl_pcts else 0.0

        return {
            "total_trades": total,
            "balance": self.balance,
            "realized_pnl": realized_pnl,
            "open_positions": len(self.open_positions),
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "win_rate": win_rate,
            "avg_pnl_pct": avg_pnl_pct,
        }
