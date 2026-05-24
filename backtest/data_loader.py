"""
バックテスト用データローダー
- ニュース: Supabase news_log または JSONL ファイルから読み込み
- 価格: yfinance で日本株を取得（.T サフィックス）
- サンプルデータ: デモ用の日本株金融ニュースセット
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# yfinance のインポート（未インストール時は明示的なエラーを出す）
try:
    import yfinance as yf
except ImportError as e:
    raise ImportError("yfinance が未インストールです。`pip3 install yfinance` を実行してください。") from e

# ─────────────────────────────────────────────
# サンプルニュースデータ（デモ用）
# ─────────────────────────────────────────────

SAMPLE_NEWS = [
    {
        "id": "s1",
        "title": "トヨタ自動車 増配・自社株買いを発表 株主還元を強化",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-20T09:00:00+09:00",
        "raw": "トヨタ自動車が増配・自社株買いを発表",
        "affected_symbols": ["7203"],
    },
    {
        "id": "s2",
        "title": "ソニーグループ 最高益更新 上方修正を発表",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-20T10:00:00+09:00",
        "raw": "ソニーグループが上方修正",
        "affected_symbols": ["6758"],
    },
    {
        "id": "s3",
        "title": "任天堂 業績下方修正 減益見通し",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-20T11:00:00+09:00",
        "raw": "任天堂が下方修正",
        "affected_symbols": ["7974"],
    },
    {
        "id": "s4",
        "title": "日産自動車 赤字転落 大幅な下方修正を発表",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-21T09:30:00+09:00",
        "raw": "日産自動車が赤字転落",
        "affected_symbols": ["7201"],
    },
    {
        "id": "s5",
        "title": "ファーストリテイリング 最高益 増配を発表",
        "source": "nhk_economy",
        "credibility": 0.75,
        "timestamp": "2025-05-21T14:00:00+09:00",
        "raw": "ユニクロ親会社が最高益",
        "affected_symbols": ["9983"],
    },
    {
        "id": "s6",
        "title": "ソフトバンクグループ 大規模自社株買いを実施",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-22T09:00:00+09:00",
        "raw": "ソフトバンクグループが自社株買い",
        "affected_symbols": ["9984"],
    },
    {
        "id": "s7",
        "title": "三菱UFJフィナンシャル 不正取引問題が発覚",
        "source": "nhk_economy",
        "credibility": 0.75,
        "timestamp": "2025-05-22T10:30:00+09:00",
        "raw": "三菱UFJが不正問題",
        "affected_symbols": ["8306"],
    },
    {
        "id": "s8",
        "title": "日本製鉄 買収完了 シナジー効果に期待",
        "source": "tdnet",
        "credibility": 0.9,
        "timestamp": "2025-05-23T09:00:00+09:00",
        "raw": "日本製鉄が買収完了",
        "affected_symbols": ["5401"],
    },
    {
        "id": "s9",
        "title": "リクルートホールディングス リコール問題で株価急落",
        "source": "yahoo_biz",
        "credibility": 0.65,
        "timestamp": "2025-05-23T11:00:00+09:00",
        "raw": "リクルートがリコール問題",
        "affected_symbols": ["6098"],
    },
    {
        "id": "s10",
        "title": "中部電力 破綻リスク浮上 財務危機報道",
        "source": "nhk_economy",
        "credibility": 0.75,
        "timestamp": "2025-05-24T09:30:00+09:00",
        "raw": "中部電力の財務危機",
        "affected_symbols": ["9502"],
    },
]

# ─────────────────────────────────────────────
# JSONL ニュースローダー
# ─────────────────────────────────────────────

# プロジェクトルート（このファイルの2階層上）
_PROJECT_ROOT = Path(__file__).parent.parent
_NEWS_LOG_DIR = _PROJECT_ROOT / "logs" / "news"


def load_news_from_jsonl(date_str: Optional[str] = None) -> list:
    """
    logs/news/YYYYMMDD.jsonl からニュースを読み込む。

    Parameters
    ----------
    date_str : str | None
        "YYYYMMDD" 形式の日付文字列。None の場合は全ファイルを結合して返す。

    Returns
    -------
    list[dict]
        ニュースアイテムのリスト。
    """
    news_dir = _NEWS_LOG_DIR

    if not news_dir.exists():
        return []

    if date_str is not None:
        # 特定日付のファイルのみ
        target = news_dir / f"{date_str}.jsonl"
        files = [target] if target.exists() else []
    else:
        # ディレクトリ内の全 JSONL ファイル（日付順）
        files = sorted(news_dir.glob("*.jsonl"))

    items: list = []
    for filepath in files:
        try:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        items.append(item)
                    except json.JSONDecodeError:
                        # 壊れた行はスキップ
                        continue
        except OSError:
            continue

    return items


# ─────────────────────────────────────────────
# サンプルニュース
# ─────────────────────────────────────────────


def load_sample_news() -> list:
    """
    デモ用のサンプルニュースを返す。

    Returns
    -------
    list[dict]
        SAMPLE_NEWS のコピー（10件）。
    """
    return [item.copy() for item in SAMPLE_NEWS]


# ─────────────────────────────────────────────
# 価格取得（yfinance）
# ─────────────────────────────────────────────

# モジュールレベルキャッシュ: { "7203": DataFrame }
_price_cache: dict = {}

# キャッシュが存在しない場合にダウンロードする期間（前後バッファ付き）
_FETCH_WINDOW_DAYS = 30


def _get_ticker_df(symbol: str):
    """
    yfinance から symbol の日足 DataFrame を取得してキャッシュする。
    symbol は東証コード（例: "7203"）。
    """
    if symbol in _price_cache:
        return _price_cache[symbol]

    ticker = f"{symbol}.T"
    try:
        # 十分な期間をまとめてダウンロード（余裕を持って過去2年分）
        df = yf.download(ticker, period="2y", auto_adjust=True, progress=False)
        _price_cache[symbol] = df
        return df
    except Exception:
        _price_cache[symbol] = None
        return None


def _parse_date(dt_str: str) -> Optional[datetime]:
    """ISO 形式の日時文字列を date オブジェクトに変換する。"""
    try:
        # Python 3.7+ の fromisoformat はタイムゾーン付きを処理できる
        # ただし "2025-05-20T09:00:00+09:00" の形式に対応
        dt = datetime.fromisoformat(dt_str)
        return dt
    except (ValueError, TypeError):
        return None


def get_price_at(symbol: str, dt_str: str) -> Optional[float]:
    """
    指定日付の東証銘柄の終値を返す。

    Parameters
    ----------
    symbol : str
        東証コード（例: "7203"）。".T" サフィックスは自動付与。
    dt_str : str
        ISO 形式の日時文字列（例: "2025-05-20T09:00:00+09:00"）。

    Returns
    -------
    float | None
        終値。取得失敗時は None。
    """
    try:
        dt = _parse_date(dt_str)
        if dt is None:
            return None

        target_date = dt.date()
        df = _get_ticker_df(symbol)
        if df is None or df.empty:
            return None

        # DataFrame のインデックスを date に変換して検索
        df_dates = df.index.date

        # 完全一致を優先
        mask = df_dates == target_date
        if mask.any():
            close_val = df.loc[mask, "Close"].iloc[0]
            return float(close_val.iloc[0]) if hasattr(close_val, "iloc") else float(close_val)

        # 当日データがない場合は直近の過去日（土日・祝日対応）
        past_mask = df_dates < target_date
        if past_mask.any():
            latest_close = df[past_mask]["Close"].iloc[-1]
            return float(latest_close.iloc[0]) if hasattr(latest_close, "iloc") else float(latest_close)

        return None

    except Exception:
        return None


def get_exit_price(symbol: str, entry_dt_str: str, hold_days: int = 1) -> Optional[float]:
    """
    エントリー日から hold_days 営業日後の終値を返す。
    yfinance の日足データのみ使用（分足は使用しない）。

    Parameters
    ----------
    symbol : str
        東証コード（例: "7203"）。
    entry_dt_str : str
        エントリー日時（ISO 形式）。
    hold_days : int
        保有日数（デフォルト: 1）。

    Returns
    -------
    float | None
        終値。取得失敗時は None。
    """
    try:
        dt = _parse_date(entry_dt_str)
        if dt is None:
            return None

        entry_date = dt.date()
        df = _get_ticker_df(symbol)
        if df is None or df.empty:
            return None

        df_dates = df.index.date

        # エントリー日以降の行を抽出
        future_mask = df_dates > entry_date
        future_df = df[future_mask]

        if future_df.empty:
            return None

        # hold_days 番目（0-indexed）の行を選択
        idx = min(hold_days - 1, len(future_df) - 1)
        close_val = future_df["Close"].iloc[idx]
        return float(close_val.iloc[0]) if hasattr(close_val, "iloc") else float(close_val)

    except Exception:
        return None
