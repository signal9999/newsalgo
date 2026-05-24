"""
アラート通知マネージャー
- Slack Incoming Webhook（SLACK_WEBHOOK_URL 環境変数）
- LINE Notify（LINE_NOTIFY_TOKEN 環境変数）
- 未設定時はコンソール出力のみ
- asyncio ループ内外どちらからでも安全に呼び出せる
"""

import os
import time
import threading
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _run_coro(coro):
    """
    asyncio の実行コンテキストに関わらずコルーチンを実行する。
    - 既存ループが走っている場合: 新規スレッドでループを作って実行
    - ループがない場合: asyncio.run() で新規実行
    """
    try:
        asyncio.get_running_loop()
        # 非同期コンテキスト内: 新スレッドで独立ループを実行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(asyncio.run, coro)
            future.result(timeout=10)
    except RuntimeError:
        # 実行中のループがない（同期コンテキスト）
        asyncio.run(coro)


class AlertManager:
    def __init__(self):
        self._error_times: list = []
        self._lock = threading.Lock()
        self._surge_alerted = False

    # ------------------------------------------------------------------
    # メイン送信
    # ------------------------------------------------------------------

    def send_alert(self, level: str, message: str, context: dict = {}):
        """
        アラートを送信する。Slack・LINE の両方が設定されていれば両方送る。
        未設定の場合はコンソール出力のみ。
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[ALERT][{level}] {ts} {message}")
        if context:
            print(f"  context: {context}")

        slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
        if slack_url:
            try:
                _run_coro(self._async_send_slack(slack_url, level, message, context))
            except Exception as e:
                logger.warning("Slack送信失敗: %s", e)

        line_token = os.environ.get("LINE_NOTIFY_TOKEN", "").strip()
        if line_token:
            try:
                _run_coro(self._async_send_line(line_token, level, message, context))
            except Exception as e:
                logger.warning("LINE送信失敗: %s", e)

    # ------------------------------------------------------------------
    # Slack Incoming Webhook
    # ------------------------------------------------------------------

    async def _async_send_slack(self, url: str, level: str, message: str, context: dict):
        import aiohttp

        emoji = {
            "CRITICAL": ":rotating_light:",
            "WARNING": ":warning:",
            "INFO": ":information_source:",
        }.get(level, ":bell:")

        payload = {"text": f"{emoji} *[{level}]* {message}"}
        if context:
            payload["attachments"] = [
                {
                    "color": "danger" if level == "CRITICAL" else "warning" if level == "WARNING" else "good",
                    "text": "\n".join(f"`{k}`: {v}" for k, v in context.items()),
                }
            ]

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("Slack HTTP %s: %s", resp.status, body[:100])

    # ------------------------------------------------------------------
    # LINE Notify
    # ------------------------------------------------------------------

    async def _async_send_line(self, token: str, level: str, message: str, context: dict):
        import aiohttp

        text = f"\n[{level}] {message}"
        if context:
            text += "\n" + "\n".join(f"{k}: {v}" for k, v in context.items())

        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": text}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://notify-api.line.me/api/notify",
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning("LINE HTTP %s: %s", resp.status, body[:100])

    # ------------------------------------------------------------------
    # 定型アラート
    # ------------------------------------------------------------------

    def alert_daily_loss(self, current_pct: float, limit_pct: float):
        self.send_alert(
            "WARNING",
            f"デイリー損失が制限の80%に到達: {current_pct:.2f}% / {limit_pct:.2f}%",
            {"current_pct": current_pct, "limit_pct": limit_pct},
        )

    def alert_strong_signal(self, signal: dict):
        symbol = (
            signal.get("symbol")
            or ", ".join(signal.get("affected_symbols", []))
            or "N/A"
        )
        self.send_alert(
            "INFO",
            f"強シグナル発生: {symbol} score={signal.get('score', 'N/A')} dir={signal.get('direction', '')}",
            {k: v for k, v in signal.items() if k in ("score", "level", "direction", "affected_symbols")},
        )

    def alert_error_surge(self, error_count: int, window_sec: int):
        self.send_alert(
            "CRITICAL",
            f"エラー連発検知: {window_sec}秒以内に{error_count}件のエラー",
            {"error_count": error_count, "window_sec": window_sec},
        )

    def alert_pipeline_start(self):
        self.send_alert("INFO", "NewsAlgo パイプライン開始")

    def alert_pipeline_stop(self, stats: dict = {}):
        self.send_alert("INFO", "NewsAlgo パイプライン停止", stats)

    # ------------------------------------------------------------------
    # エラー頻度監視
    # ------------------------------------------------------------------

    def _check_error_surge(self):
        now = time.time()
        window = 60
        threshold = 5

        with self._lock:
            self._error_times = [t for t in self._error_times if now - t <= window]
            count = len(self._error_times)

        if count > threshold and not self._surge_alerted:
            self._surge_alerted = True
            self.alert_error_surge(count, window)
        elif count <= threshold:
            self._surge_alerted = False

    def record_error(self):
        with self._lock:
            self._error_times.append(time.time())
        self._check_error_surge()
