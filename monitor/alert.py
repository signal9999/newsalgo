import os
import time
import threading
import asyncio
from datetime import datetime


class AlertManager:
    def __init__(self):
        self._error_times: list[float] = []
        self._lock = threading.Lock()
        self._surge_alerted = False

    def send_alert(self, level: str, message: str, context: dict = {}):
        print(f"[ALERT][{level}] {message}")
        if context:
            print(f"  context: {context}")

        slack_url = os.environ.get("SLACK_WEBHOOK_URL")
        if slack_url:
            self._send_slack(slack_url, level, message, context)

        line_token = os.environ.get("LINE_NOTIFY_TOKEN")
        if line_token:
            self._send_line(line_token, level, message, context)

    def _send_slack(self, url: str, level: str, message: str, context: dict):
        try:
            asyncio.run(self._async_send_slack(url, level, message, context))
        except Exception as e:
            print(f"[ALERT] Slack送信失敗: {e}")

    async def _async_send_slack(self, url: str, level: str, message: str, context: dict):
        import aiohttp
        payload = {
            "text": f"[{level}] {message}",
            "attachments": [{"text": str(context)}] if context else [],
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    print(f"[ALERT] Slack HTTP {resp.status}")

    def _send_line(self, token: str, level: str, message: str, context: dict):
        try:
            asyncio.run(self._async_send_line(token, level, message, context))
        except Exception as e:
            print(f"[ALERT] LINE送信失敗: {e}")

    async def _async_send_line(self, token: str, level: str, message: str, context: dict):
        import aiohttp
        text = f"\n[{level}] {message}"
        if context:
            text += f"\n{context}"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": text}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://notify-api.line.me/api/notify",
                headers=headers,
                data=data,
            ) as resp:
                if resp.status != 200:
                    print(f"[ALERT] LINE HTTP {resp.status}")

    def alert_daily_loss(self, current_pct: float, limit_pct: float):
        self.send_alert(
            "WARNING",
            f"デイリー損失が制限の80%に到達: {current_pct:.2f}% / {limit_pct:.2f}%",
            {"current_pct": current_pct, "limit_pct": limit_pct},
        )

    def alert_strong_signal(self, signal: dict):
        self.send_alert(
            "INFO",
            f"強シグナル発生: {signal.get('symbol', 'N/A')} score={signal.get('score', 'N/A')}",
            signal,
        )

    def alert_error_surge(self, error_count: int, window_sec: int):
        self.send_alert(
            "CRITICAL",
            f"エラー連発検知: {window_sec}秒以内に{error_count}件のエラー",
            {"error_count": error_count, "window_sec": window_sec},
        )

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
