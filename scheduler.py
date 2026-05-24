#!/usr/bin/env python3
"""
NewsAlgo Phase B — Python 自前スケジューラー

GitHub Actions 依存なしでローカル/VPS 上で常時稼働させるためのスケジューラー。
APScheduler を使って JST 08:00 / 08:30 に main.py のパイプラインを自動実行する。

使い方:
  python3 scheduler.py              # スケジューラー起動（Ctrl+C で停止）
  python3 scheduler.py --now        # 即時1回実行（テスト用）
  python3 scheduler.py --dry-run    # スケジュール確認のみ（実行しない）

設定:
  SCHEDULER_INTERVAL_MIN=30   # ポーリング間隔（分）デフォルト: 30
  SCHEDULER_START_HOUR=8      # 開始時刻（JST 時）デフォルト: 8
  SCHEDULER_END_HOUR=16       # 終了時刻（JST 時）デフォルト: 16
  PIPELINE_DURATION_SEC=1800  # 1回あたりの実行時間（秒）デフォルト: 1800
"""

import asyncio
import sys
import argparse
import logging
import signal
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False
    logger.warning("apscheduler が未インストールです。pip install apscheduler で導入してください。")

# ── 設定 ─────────────────────────────────────────────────────────────────
import os
from config import settings  # noqa: F401（.env 読み込みのため）

_JST = timezone(timedelta(hours=9))
_START_HOUR = int(os.environ.get("SCHEDULER_START_HOUR", "8"))
_END_HOUR   = int(os.environ.get("SCHEDULER_END_HOUR",   "16"))
_INTERVAL   = int(os.environ.get("SCHEDULER_INTERVAL_MIN", "30"))
_DURATION   = int(os.environ.get("PIPELINE_DURATION_SEC", "1800"))

# ── 実行状態 ──────────────────────────────────────────────────────────────
_running_task = None
_shutdown = False


def _is_market_day() -> bool:
    """平日（月〜金）のみ True。"""
    return datetime.now(_JST).weekday() < 5


def _is_active_hours() -> bool:
    """スケジューラー稼働時間帯（デフォルト JST 8:00〜16:00）か判定。"""
    now = datetime.now(_JST)
    return _START_HOUR <= now.hour < _END_HOUR


async def run_pipeline_once():
    """
    NewsAlgo パイプラインを 1 セッション実行する。
    `_DURATION` 秒後に自動停止する。
    """
    global _running_task

    now_jst = datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S JST")
    logger.info("=" * 60)
    logger.info("パイプライン開始: %s", now_jst)
    logger.info("=" * 60)

    if not _is_market_day():
        logger.info("土日のため実行をスキップします")
        return

    if not _is_active_hours():
        logger.info("稼働時間外（%d:00〜%d:00 JST）のためスキップします", _START_HOUR, _END_HOUR)
        return

    try:
        from engine.orchestrator import Orchestrator
        from monitor.alert import AlertManager

        alert = AlertManager()
        alert.alert_pipeline_start()

        orch = Orchestrator()

        # _DURATION 秒後にパイプラインを停止するタイマー
        async def _stop_after():
            await asyncio.sleep(_DURATION)
            await orch.stop()
            logger.info("パイプライン停止（%d秒タイムアウト）", _DURATION)

        stopper = asyncio.create_task(_stop_after())
        _running_task = asyncio.create_task(orch.run())

        try:
            await asyncio.gather(_running_task, stopper)
        except asyncio.CancelledError:
            pass
        finally:
            stopper.cancel()
            _running_task = None

        stats = {
            "duration_sec": _DURATION,
            "ended_at": datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S JST"),
        }
        alert.alert_pipeline_stop(stats)

    except Exception as e:
        logger.exception("パイプライン実行エラー: %s", e)


def parse_args():
    p = argparse.ArgumentParser(description="NewsAlgo スケジューラー")
    p.add_argument("--now",     action="store_true", help="即時1回実行（テスト用）")
    p.add_argument("--dry-run", action="store_true", help="スケジュール確認のみ（実行しない）")
    return p.parse_args()


async def main():
    global _shutdown
    args = parse_args()

    # ── 即時実行モード ─────────────────────────────────────────────────
    if args.now:
        logger.info("即時実行モード")
        await run_pipeline_once()
        return

    if not _HAS_APSCHEDULER:
        logger.error("apscheduler が必要です: pip install apscheduler")
        sys.exit(1)

    # ── スケジューラー設定 ─────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")

    # JST での cron 設定（_START_HOUR 時から _END_HOUR 時まで _INTERVAL 分ごと）
    trigger = CronTrigger(
        hour=f"{_START_HOUR}-{_END_HOUR - 1}",
        minute=f"0/{_INTERVAL}",
        timezone="Asia/Tokyo",
    )
    scheduler.add_job(run_pipeline_once, trigger, id="pipeline", max_instances=1)

    # ── Dry run ────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n=== スケジュール設定確認 ===")
        print(f"  実行時間帯  : JST {_START_HOUR:02d}:00 〜 {_END_HOUR:02d}:00 (平日のみ)")
        print(f"  実行間隔    : {_INTERVAL} 分ごと")
        print(f"  1回の実行時間: {_DURATION} 秒 ({_DURATION // 60} 分)")
        print(f"  タイムゾーン: {_JST}")
        print(f"  次回予定    : (スケジューラー起動後に確認可能)")
        print("=== Dry run 完了（実行しませんでした） ===\n")
        return

    # ── シグナルハンドラ ───────────────────────────────────────────────
    def _handle_signal(sig, frame):
        global _shutdown
        logger.info("シグナル受信 (%s)。シャットダウン中...", sig)
        _shutdown = True
        scheduler.shutdown(wait=False)
        if _running_task:
            _running_task.cancel()

    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── 起動 ──────────────────────────────────────────────────────────
    scheduler.start()
    now_jst = datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S")

    print(f"""
╔═══════════════════════════════════════════════════════╗
║          NewsAlgo スケジューラー 起動                ║
╚═══════════════════════════════════════════════════════╝
  起動時刻  : {now_jst} JST
  実行時間帯: JST {_START_HOUR:02d}:00 〜 {_END_HOUR:02d}:00 (平日のみ)
  実行間隔  : {_INTERVAL} 分ごと
  1回の実行 : {_DURATION} 秒 ({_DURATION // 60} 分)
  停止方法  : Ctrl+C
""")

    try:
        while not _shutdown:
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass
    finally:
        scheduler.shutdown(wait=True)
        logger.info("スケジューラー停止")


if __name__ == "__main__":
    asyncio.run(main())
