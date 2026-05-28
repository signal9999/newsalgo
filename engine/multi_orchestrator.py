"""
マルチ戦略オーケストレーター

ニュース収集・LLM分析は1回だけ実行し、4戦略で並列評価する。
各戦略は独立したPaperTrader・StructuredLogger・RiskManagerを持つ。

ログ構造:
  logs/
    strategy_a/signal/ order/ paper_state.json
    strategy_b/signal/ order/ paper_state.json
    strategy_c/signal/ order/ paper_state.json
    strategy_d/signal/ order/ paper_state.json
    news/        ← 共有（全戦略で同じニュースを見ている）
"""
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from collectors.tdnet import fetch_tdnet
from collectors.rss import fetch_all_rss
from collectors.credibility import calculate_credibility
from analyzers.keyword import analyze_keywords
from analyzers.llm import analyze_with_llm
from analyzers.signal import compute_signal
from engine.decision import DecisionEngine
from execution.risk import RiskManager
from execution.paper_trade import PaperTrader
from monitor.logger import StructuredLogger
from monitor.alert import AlertManager
from config.settings import ANTHROPIC_API_KEY, MAX_PIPELINE_CONCURRENCY, POLL_INTERVAL_SEC
from config.strategies import STRATEGIES, StrategyConfig

_ROOT = Path(__file__).parent.parent
_LOG  = _ROOT / "logs"

# 東京証券取引所 取引時間 (JST)
_JST          = timezone(timedelta(hours=9))
_MARKET_OPEN  = (8,  0)
_MARKET_CLOSE = (15, 35)


def _is_market_hours() -> bool:
    now = datetime.now(_JST)
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return _MARKET_OPEN <= t <= _MARKET_CLOSE


class StrategyRunner:
    """1戦略分のパイプライン（発注・ログ）を保持する。"""

    def __init__(self, cfg: StrategyConfig):
        self.cfg    = cfg
        log_dir     = _LOG / f"strategy_{cfg.id.lower()}"
        state_file  = log_dir / "paper_state.json"

        self.logger   = StructuredLogger(log_dir=str(log_dir))
        self.broker   = PaperTrader(
            logger_obj=self.logger,
            state_file=state_file,
            initial_balance=cfg.initial_balance,
        )
        self.risk     = RiskManager()
        self.decision = DecisionEngine(
            self.broker, self.risk, self.logger, AlertManager()
        )

    def should_process(self, item: dict, llm_result: dict, score: float) -> bool:
        """この戦略でこのシグナルを処理すべきか判定する。"""
        # ソースフィルター
        if self.cfg.allowed_sources is not None:
            if item.get("source", "") not in self.cfg.allowed_sources:
                return False
        # スコア閾値
        if score < self.cfg.min_score:
            return False
        # シンボル必須
        if self.cfg.require_symbols and not llm_result.get("affected_symbols"):
            return False
        return True

    def build_signal(self, base_signal: dict, llm_result: dict, item: dict = None) -> dict:
        """逆張り戦略の場合、方向を反転させたシグナルを返す。

        銘柄コードの優先順位:
          1. item["affected_symbols"] — TDnet が直接提供するコード（最も信頼性高）
          2. llm_result["affected_symbols"] — LLM が本文から抽出したコード
        重複を除去して結合する。
        """
        signal = dict(base_signal)

        # item 由来のシンボル（TDnetコード等）を優先し、LLMの結果を補完に使う
        item_symbols = list(item.get("affected_symbols", [])) if item else []
        llm_symbols  = llm_result.get("affected_symbols", [])
        # 重複除去しながら item 優先で結合
        merged = list(dict.fromkeys(item_symbols + llm_symbols))
        signal["affected_symbols"] = merged

        if self.cfg.contrarian:
            signal["direction"] = (
                "bearish" if base_signal["direction"] == "bullish" else "bullish"
            )
        return signal


class MultiOrchestrator:
    """
    4戦略を同時に走らせるオーケストレーター。
    ニュース収集とLLM分析は共有し、判定・発注だけ戦略ごとに分岐する。
    """

    def __init__(self):
        self.queue:    asyncio.Queue = asyncio.Queue()
        self.runners:  list[StrategyRunner] = [
            StrategyRunner(cfg) for cfg in STRATEGIES
        ]
        self._shared_logger = StructuredLogger(log_dir=str(_LOG))  # news ログ共有
        self._alert   = AlertManager()
        self._running = False
        self._seen_titles: list[str] = []

        ids = ", ".join(r.cfg.id for r in self.runners)
        print(f"[MultiOrchestrator] 戦略 [{ids}] を並列実行します")

    async def _collect_loop(self):
        while self._running:
            try:
                tdnet_items = await fetch_tdnet() if _is_market_hours() else []
                rss_items   = await fetch_all_rss()
                all_items   = tdnet_items + rss_items
                if all_items:
                    print(
                        f"[Collector] {len(all_items)}件キューへ追加 "
                        f"(tdnet={len(tdnet_items)}, rss={len(rss_items)})"
                    )
                for item in all_items:
                    await self.queue.put(item)
            except Exception as e:
                self._shared_logger.log_error("collect_error", {"error": str(e)})
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _process_item(self, item: dict):
        try:
            # ── 共通処理（LLM は1回だけ呼ぶ）────────────────────────────
            enriched = calculate_credibility(item, self._seen_titles)
            self._seen_titles.append(item.get("title", ""))
            if len(self._seen_titles) > 500:
                self._seen_titles = self._seen_titles[-500:]

            self._shared_logger.log_news(enriched)

            if not enriched.get("is_reliable", True):
                return

            text       = item.get("title", "") + " " + item.get("raw", "")
            kw_result  = analyze_keywords(text)
            llm_result = await analyze_with_llm(text, ANTHROPIC_API_KEY)

            base_signal = compute_signal(
                credibility_score=enriched.get("credibility", 0.0),
                llm_confidence=llm_result.get("confidence", 0.0),
                impact_score=llm_result.get("impact_score", 0.0),
                direction=llm_result.get("sentiment", kw_result["direction"]),
            )
            score = base_signal["score"]

            # ── 戦略ごとの評価・発注（並列実行）──────────────────────────
            tasks = []
            for runner in self.runners:
                if runner.should_process(item, llm_result, score):
                    signal = runner.build_signal(base_signal, llm_result, item)
                    runner.logger.log_signal({
                        **signal,
                        "strategy": runner.cfg.id,
                        "item_id":  item.get("id"),
                        "source":   item.get("source"),
                    })
                    tasks.append(runner.decision.execute(signal, item))
                else:
                    # フィルタで除外 → NONEシグナルのみ記録
                    runner.logger.log_signal({
                        **base_signal,
                        "affected_symbols": [],
                        "strategy": runner.cfg.id,
                        "item_id":  item.get("id"),
                        "source":   item.get("source"),
                        "filtered": True,
                    })

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self._shared_logger.log_error(
                "pipeline_error", {"error": str(e), "item_id": item.get("id")}
            )

    async def _worker(self):
        while self._running:
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._process_item(item)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self._shared_logger.log_error("worker_error", {"error": str(e)})

    async def run(self):
        self._running = True
        print("[MultiOrchestrator] Starting NewsAlgo multi-strategy pipeline...")
        workers   = [asyncio.create_task(self._worker())
                     for _ in range(MAX_PIPELINE_CONCURRENCY)]
        collector = asyncio.create_task(self._collect_loop())
        try:
            await asyncio.gather(collector, *workers)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self._running = False
        for runner in self.runners:
            runner.logger.close()
        self._shared_logger.close()
        print("[MultiOrchestrator] Shutdown complete.")

    def summary(self):
        """全戦略の損益サマリーを表示する。"""
        print("\n" + "=" * 60)
        print("  戦略別パフォーマンスサマリー")
        print("=" * 60)
        for runner in self.runners:
            b   = runner.broker.balance
            pnl = runner.broker.realized_pnl
            ret = (b - runner.cfg.initial_balance) / runner.cfg.initial_balance * 100
            sign = "+" if ret >= 0 else ""
            print(f"  [{runner.cfg.id}] {runner.cfg.name:12s}  "
                  f"残高=¥{b:>10,.0f}  PnL={'+' if pnl>=0 else ''}¥{pnl:,.0f}  "
                  f"Return={sign}{ret:.2f}%")
        print("=" * 60)
