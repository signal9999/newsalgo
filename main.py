import asyncio
import signal
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent))

from engine.multi_orchestrator import MultiOrchestrator
from config.settings import PAPER_TRADE
from monitor.alert import AlertManager

_JST = timezone(timedelta(hours=9))


def _is_market_hours() -> bool:
    now = datetime.now(_JST)
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return (8, 0) <= t <= (15, 35)


def _startup_health_check(alert: AlertManager) -> bool:
    """
    起動前ヘルスチェック: 価格取得が正常に動作するか確認する。
    東証取引時間中に失敗した場合はCRITICALアラートを送って False を返す。
    """
    from execution.paper_trade import PaperTrader
    test_symbols = ["7203.T", "9984.T"]
    failed = []
    results = {}
    for sym in test_symbols:
        price = PaperTrader._fetch_price(sym)
        results[sym] = price
        if price <= 0:
            failed.append(sym)

    if not failed:
        print(f"[HealthCheck] ✅ 価格取得OK: " +
              ", ".join(f"{s}=¥{p:,.0f}" for s, p in results.items()))
        return True

    # 取引時間中の失敗 → CRITICAL（時間外は警告のみ）
    if _is_market_hours():
        alert.send_alert(
            "CRITICAL",
            f"⚠️ 価格取得ヘルスチェック失敗: {failed}",
            {
                "failed_symbols": str(failed),
                "impact": "全注文がprice_unavailableでリジェクトされます",
                "action": "システムを停止しました。原因を確認してください",
            },
        )
        print(f"[HealthCheck] ❌ 価格取得失敗: {failed} → 取引を停止します")
        return False
    else:
        # 取引時間外（例: 夜間テスト）は警告のみで続行
        print(f"[HealthCheck] ⚠️ 価格取得失敗（取引時間外のため続行）: {failed}")
        return True


async def main():
    mode = "PAPER TRADE" if PAPER_TRADE else "LIVE TRADE"
    print(f"[NewsAlgo] Starting in {mode} mode")

    alert = AlertManager()

    # 起動前ヘルスチェック
    if not _startup_health_check(alert):
        sys.exit(1)

    orchestrator = MultiOrchestrator()

    loop = asyncio.get_running_loop()

    def _shutdown():
        print("\n[NewsAlgo] Shutting down...")
        orchestrator.summary()
        asyncio.ensure_future(orchestrator.stop())
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
