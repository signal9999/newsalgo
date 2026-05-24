import asyncio
from typing import Optional

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


class Orchestrator:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.logger = StructuredLogger()
        self.alert = AlertManager()
        self.broker = PaperTrader(self.logger)
        self.risk = RiskManager()
        self.decision = DecisionEngine(self.broker, self.risk, self.logger, self.alert)
        self._running = False
        self._seen_titles: list[str] = []

    async def _collect_loop(self):
        while self._running:
            try:
                tdnet_items = await fetch_tdnet()
                rss_items = await fetch_all_rss()
                for item in tdnet_items + rss_items:
                    await self.queue.put(item)
            except Exception as e:
                self.logger.log_error("collect_error", {"error": str(e)})
                self.alert.record_error()
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _process_item(self, item: dict):
        try:
            enriched = calculate_credibility(item, self._seen_titles)
            self._seen_titles.append(item.get("title", ""))
            if len(self._seen_titles) > 500:
                self._seen_titles = self._seen_titles[-500:]

            self.logger.log_news(enriched)

            if not enriched.get("is_reliable", True):
                return

            text = item.get("title", "") + " " + item.get("raw", "")
            kw_result = analyze_keywords(text)

            llm_result = await analyze_with_llm(text, ANTHROPIC_API_KEY)

            signal = compute_signal(
                credibility_score=enriched.get("credibility", 0.0),
                llm_confidence=llm_result.get("confidence", 0.0),
                impact_score=llm_result.get("impact_score", 0.0),
                direction=llm_result.get("sentiment", kw_result["direction"]),
            )
            signal["affected_symbols"] = llm_result.get("affected_symbols", [])
            self.logger.log_signal({**signal, "item_id": item.get("id"), "source": item.get("source")})

            await self.decision.execute(signal, item)

        except Exception as e:
            self.logger.log_error("pipeline_error", {"error": str(e), "item_id": item.get("id")})
            self.alert.record_error()

    async def _worker(self):
        while self._running:
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._process_item(item)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.log_error("worker_error", {"error": str(e)})

    async def run(self):
        self._running = True
        print("[Orchestrator] Starting NewsAlgo pipeline...")

        workers = [asyncio.create_task(self._worker()) for _ in range(MAX_PIPELINE_CONCURRENCY)]
        collector = asyncio.create_task(self._collect_loop())

        try:
            await asyncio.gather(collector, *workers)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self._running = False
        self.logger.close()
        print("[Orchestrator] Shutdown complete.")
