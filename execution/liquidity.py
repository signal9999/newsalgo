"""
流動性チェックモジュール
- Yahoo Finance の過去20営業日データから平均出来高・売買代金を算出
- MIN_DAILY_TURNOVER（デフォルト5億円）未満の銘柄を除外
- 結果を24時間キャッシュ（頻繁なAPI呼び出しを防ぐ）
"""
import json
import logging
import time
import urllib.request

from config.settings import MIN_DAILY_TURNOVER, MIN_AVG_VOLUME

logger = logging.getLogger(__name__)

# symbol → (result_dict, fetched_at)
_liquidity_cache: dict = {}
_CACHE_TTL = 86400  # 24時間


def check_liquidity(symbol: str) -> dict:
    """
    銘柄の流動性を確認する。

    Parameters
    ----------
    symbol : str
        証券コード（例: "7203" または "7203.T"）

    Returns
    -------
    dict
        {
            "liquid": bool,
            "avg_volume": float,       # 平均出来高（株）
            "avg_turnover": float,     # 平均売買代金（円）
            "reason": str,             # 除外理由（液体でない場合）
        }
    """
    now = time.time()
    cached = _liquidity_cache.get(symbol)
    if cached and now - cached[1] < _CACHE_TTL:
        return cached[0]

    result = _fetch_liquidity(symbol)
    _liquidity_cache[symbol] = (result, now)
    return result


def _fetch_liquidity(symbol: str) -> dict:
    """Yahoo Finance から過去1ヶ月の日足データを取得して流動性を算出する。"""
    # 日本株は .T サフィックスを付与
    ticker = (
        symbol
        if "." in symbol
        else (f"{symbol}.T" if symbol.isdigit() and len(symbol) <= 5 else symbol)
    )

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range=1mo"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())

        result_data = data["chart"]["result"][0]
        indicators  = result_data.get("indicators", {}).get("quote", [{}])[0]
        volumes     = [v for v in (indicators.get("volume") or []) if v is not None]
        closes      = [c for c in (indicators.get("close")  or []) if c is not None]

        if not volumes or not closes:
            return _illiquid(symbol, "出来高データなし")

        # 最新20営業日（データが少ない場合は全件）
        n = min(len(volumes), len(closes), 20)
        avg_volume   = sum(volumes[-n:]) / n
        avg_price    = sum(closes[-n:])  / n
        avg_turnover = avg_volume * avg_price  # 円建て

        if avg_turnover < MIN_DAILY_TURNOVER:
            return {
                "liquid":       False,
                "avg_volume":   avg_volume,
                "avg_turnover": avg_turnover,
                "reason": (
                    f"売買代金不足: 平均¥{avg_turnover/1e8:.1f}億円 "
                    f"< 基準¥{MIN_DAILY_TURNOVER/1e8:.0f}億円"
                ),
            }

        if avg_volume < MIN_AVG_VOLUME:
            return {
                "liquid":       False,
                "avg_volume":   avg_volume,
                "avg_turnover": avg_turnover,
                "reason": (
                    f"出来高不足: 平均{avg_volume:,.0f}株/日 "
                    f"< 基準{MIN_AVG_VOLUME:,}株/日"
                ),
            }

        logger.debug(
            "[Liquidity] %s OK: 出来高=%.0f株  売買代金=¥%.0f億",
            symbol, avg_volume, avg_turnover / 1e8,
        )
        return {
            "liquid":       True,
            "avg_volume":   avg_volume,
            "avg_turnover": avg_turnover,
            "reason":       "",
        }

    except Exception as e:
        logger.debug("[Liquidity] %s データ取得失敗: %s", symbol, e)
        # データ取得失敗時は「取引不可」として安全側に倒す
        return _illiquid(symbol, f"データ取得失敗: {e}")


def _illiquid(symbol: str, reason: str) -> dict:
    return {"liquid": False, "avg_volume": 0.0, "avg_turnover": 0.0, "reason": reason}
