"""
backtest/runner.py — バックテスト実行オーケストレーター

BacktestRunner がニュースアイテムのリストを受け取り、
アナライザー → シミュレーター → メトリクス計算 の全パイプラインを実行する。
"""

from __future__ import annotations

import asyncio
from typing import Optional

from analyzers.keyword import analyze_keywords
from analyzers.signal import compute_signal
from backtest.data_loader import get_price_at, get_exit_price
from backtest.simulator import BacktestSimulator
from backtest.metrics import calculate_metrics


# --------------------------------------------------------------------------
# BacktestRunner
# --------------------------------------------------------------------------

class BacktestRunner:
    """
    ニュースリストに対してバックテスト全体を実行するクラス。

    Parameters
    ----------
    use_llm : bool
        LLM アナライザーを使うか否か。False の場合はキーワードのみ使用。
    hold_days : int
        保有日数（デフォルト: 1）。
    initial_balance : float
        初期残高（デフォルト: 1,000,000 円）。
    signal_threshold : float
        シグナルスコアの最低閾値（デフォルト: 0.3）。
        ``threshold`` でも同じ意味として受け付ける（後方互換）。
    position_pct : float
        1銘柄あたりポジションサイズ（残高比率、デフォルト: 0.05）。
    """

    def __init__(
        self,
        use_llm: bool = False,
        hold_days: int = 1,
        initial_balance: float = 1_000_000.0,
        signal_threshold: float = 0.3,
        position_pct: float = 0.05,
        # 後方互換エイリアス
        threshold: Optional[float] = None,
    ):
        self.use_llm = use_llm
        self.hold_days = hold_days
        self.initial_balance = initial_balance
        # threshold は signal_threshold の後方互換エイリアス
        self.signal_threshold = threshold if threshold is not None else signal_threshold
        # 旧名も保持（既存コードとの互換性）
        self.threshold = self.signal_threshold
        self.position_pct = position_pct

    # ------------------------------------------------------------------
    # シグナル生成（キーワードベース）
    # ------------------------------------------------------------------

    def _build_signal(self, news_item: dict) -> dict:
        """
        ニュースアイテムからシグナルを生成する。

        既にシグナル情報が含まれている場合はそれを優先し、
        なければキーワードアナライザーで生成する。
        """
        # すでにシグナルフィールドがある場合はそのまま使う
        if "signal_level" in news_item and "direction" in news_item:
            level = news_item["signal_level"]
            direction = news_item["direction"]
            score = news_item.get("signal_score", 0.5)
            symbols = news_item.get("affected_symbols", [])
            return {
                "level": level,
                "direction": direction,
                "score": score,
                "affected_symbols": symbols,
            }

        # キーワードアナライザーでシグナル生成
        text = news_item.get("title", "") + " " + news_item.get("raw", "")
        kw_result = analyze_keywords(text)
        direction = kw_result["direction"]

        credibility = float(news_item.get("credibility", 0.7))
        # キーワードスコアを 0〜1 に正規化
        kw_score = abs(kw_result["keyword_score"])
        signal = compute_signal(
            credibility_score=credibility,
            llm_confidence=kw_score if kw_score > 0 else 0.5,
            impact_score=0.8,
            direction=direction,
        )
        signal["affected_symbols"] = news_item.get("affected_symbols", [])
        return signal

    # ------------------------------------------------------------------
    # 価格取得ヘルパー（モック互換）
    # ------------------------------------------------------------------

    @staticmethod
    def _get_entry_price(symbol: str, timestamp: str) -> float:
        price = get_price_at(symbol, timestamp)
        if price is None or price <= 0:
            return 1000.0
        return price

    @staticmethod
    def _get_exit_price_for(symbol: str, timestamp: str, hold_days: int) -> float:
        price = get_exit_price(symbol, timestamp, hold_days)
        if price is None or price <= 0:
            return 1000.0
        return price

    # ------------------------------------------------------------------
    # 単一ニュースアイテム処理
    # ------------------------------------------------------------------

    def _process_one(
        self, news_item: dict, sim: BacktestSimulator
    ) -> tuple[Optional[dict], bool]:
        """
        ニュースアイテムに対してシグナル生成 → エントリー → クローズを実行する。

        Returns
        -------
        (trade_dict | None, skipped: bool)
            クローズ済みトレード辞書とスキップフラグのタプル。
            price 取得失敗 = スキップ、シグナル弱すぎ = スキップだが count しない。
        """
        signal = self._build_signal(news_item)

        # NONE シグナルは除外（スキップカウントしない）
        if signal.get("level") == "NONE":
            return None, False

        # 閾値チェック（スキップカウントしない）
        if signal.get("score", 0.0) < self.signal_threshold:
            return None, False

        symbols = signal.get("affected_symbols", [])
        if not symbols:
            # symbols なし → スキップカウント
            return None, True

        symbol = symbols[0]
        timestamp = news_item.get("timestamp", "")

        # エントリー価格取得
        entry_price = get_price_at(symbol, timestamp)
        if entry_price is None or entry_price <= 0:
            # 価格取得失敗 → スキップカウント
            return None, True
        entry_price = float(entry_price)

        trade = sim.execute_signal(signal, news_item, entry_price)
        if trade is None:
            return None, True

        # イグジット価格取得
        exit_price = get_exit_price(symbol, timestamp, self.hold_days)
        if exit_price is None or exit_price <= 0:
            # クローズ失敗 → ポジションを破棄してスキップカウント
            sim.open_positions.pop(symbol, None)
            return None, True
        exit_price = float(exit_price)

        closed = sim.close_position(symbol, exit_price)
        if closed:
            # ソース情報を付加（metrics の by_source に使用）
            closed["source"] = news_item.get("source", "unknown")
        return closed, False

    # ------------------------------------------------------------------
    # 非同期実行（メインエントリー）
    # ------------------------------------------------------------------

    async def run(self, news_items: list[dict]) -> dict:
        """
        ニュースアイテムリストに対してバックテストを非同期実行する。

        Returns
        -------
        dict
            {
                "metrics": dict,         # calculate_metrics の結果
                "trades": list[dict],    # クローズ済みトレード
                "skipped": int,          # 価格取得失敗等でスキップしたシグナル数
            }
        """
        sim = BacktestSimulator(
            initial_balance=self.initial_balance,
            position_pct=self.position_pct,
        )

        trades: list[dict] = []
        skipped: int = 0

        for item in news_items:
            result, was_skipped = self._process_one(item, sim)
            if was_skipped:
                skipped += 1
            if result is not None:
                trades.append(result)

        metrics = calculate_metrics(trades, initial_balance=self.initial_balance)
        summary = sim.get_summary()

        return {
            "metrics": metrics,
            "trades": trades,
            "skipped": skipped,
            # 後方互換のため summary も残す
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # 同期ラッパー（テスト・CLI 用）
    # ------------------------------------------------------------------

    def run_sync(self, news_items: list[dict]) -> dict:
        """run() の同期ラッパー。asyncio.run() を使用して実行する。"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 既存のイベントループがある場合（Jupyter 等）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self.run(news_items))
                    return future.result()
            else:
                return loop.run_until_complete(self.run(news_items))
        except RuntimeError:
            return asyncio.run(self.run(news_items))
