import os
import json
import aiohttp
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from config import settings
from monitor.logger import StructuredLogger

_LOG_DIR = Path(__file__).parent.parent / "logs"


class SupabaseLogger:
    """
    Supabase REST API へ非同期で書き込む。
    SUPABASE_URL / SUPABASE_KEY が未設定の場合は JSONL ファイルへフォールバック。
    """

    def __init__(self):
        self._url = settings.SUPABASE_URL.rstrip("/")
        self._key = settings.SUPABASE_KEY
        self.use_supabase = bool(self._url and self._key)
        self._fallback = StructuredLogger(log_dir=str(_LOG_DIR))

        if not self.use_supabase:
            print(
                "[SupabaseLogger] SUPABASE_URL / SUPABASE_KEY が未設定です。"
                " JSONLフォールバックモードで動作します。"
            )

    # ------------------------------------------------------------------
    # 内部: Supabase REST POST
    # ------------------------------------------------------------------

    async def _insert(self, table: str, data: dict) -> bool:
        """
        Supabase REST API へ POST する。
        成功時 True、失敗時 False（例外は投げない）。
        """
        endpoint = f"{self._url}/rest/v1/{table}"
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint,
                    headers=headers,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        return True
                    body = await resp.text()
                    print(
                        f"[SupabaseLogger] INSERT失敗 table={table} "
                        f"status={resp.status} body={body[:200]}"
                    )
                    return False
        except Exception as exc:
            print(f"[SupabaseLogger] INSERT例外 table={table} error={exc}")
            return False

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def log_news(self, item: dict):
        """news_log テーブルへ書き込む（失敗時はJSONLフォールバック）。"""
        if self.use_supabase:
            ok = asyncio.get_event_loop().run_until_complete(
                self._insert("news_log", item)
            )
            if not ok:
                self._fallback.log_news(item)
        else:
            self._fallback.log_news(item)

    def log_signal(self, signal: dict):
        """
        signal_log テーブルへ書き込む。
        signal["level"] == "NONE" の場合はスキップ。
        """
        if signal.get("level") == "NONE":
            return

        if self.use_supabase:
            ok = asyncio.get_event_loop().run_until_complete(
                self._insert("signal_log", signal)
            )
            if not ok:
                self._fallback.log_signal(signal)
        else:
            self._fallback.log_signal(signal)

    def log_order(self, order: dict):
        """order_log テーブルへ書き込む（失敗時はJSONLフォールバック）。"""
        if self.use_supabase:
            ok = asyncio.get_event_loop().run_until_complete(
                self._insert("order_log", order)
            )
            if not ok:
                self._fallback.log_order(order)
        else:
            self._fallback.log_order(order)

    def log_error(self, error: str, context: dict = {}):
        """エラーは常にJSONLのみ（Supabaseには書かない）。"""
        self._fallback.log_error(error, context)

    # ------------------------------------------------------------------
    # 非同期バリアント（async/await コンテキストから呼ぶ場合）
    # ------------------------------------------------------------------

    async def alog_news(self, item: dict) -> bool:
        if self.use_supabase:
            ok = await self._insert("news_log", item)
            if not ok:
                self._fallback.log_news(item)
            return ok
        self._fallback.log_news(item)
        return True

    async def alog_signal(self, signal: dict) -> bool:
        if signal.get("level") == "NONE":
            return True
        if self.use_supabase:
            ok = await self._insert("signal_log", signal)
            if not ok:
                self._fallback.log_signal(signal)
            return ok
        self._fallback.log_signal(signal)
        return True

    async def alog_order(self, order: dict) -> bool:
        if self.use_supabase:
            ok = await self._insert("order_log", order)
            if not ok:
                self._fallback.log_order(order)
            return ok
        self._fallback.log_order(order)
        return True
