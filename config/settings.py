import os
from pathlib import Path
from dotenv import load_dotenv

# newsalgo/ ディレクトリの .env を常に読む
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PAPER_TRADE = os.getenv("PAPER_TRADE", "true").lower() == "true"
MAX_POSITION_PCT = float(os.getenv("MAX_POSITION_PCT", "0.05"))
DAILY_LOSS_LIMIT_PCT = float(os.getenv("DAILY_LOSS_LIMIT_PCT", "0.10"))
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", "0.7"))

RSS_FEEDS = {
    "nhk_top":       "https://www3.nhk.or.jp/rss/news/cat0.xml",
    "nhk_economy":   "https://www3.nhk.or.jp/rss/news/cat6.xml",
    "yahoo_biz":     "https://news.yahoo.co.jp/rss/topics/business.xml",
    "toyo_keizai":   "https://toyokeizai.net/list/feed/rss",          # 東洋経済オンライン
    "investing_jp":  "https://jp.investing.com/rss/news_285.rss",     # Investing.com 株式全般
}

# ソース別信頼性スコア（collectors/credibility.py でも使用）
RSS_CREDIBILITY: dict = {
    "nhk_top":      0.70,
    "nhk_economy":  0.75,
    "yahoo_biz":    0.65,
    "toyo_keizai":  0.72,
    "investing_jp": 0.68,
}

POLL_INTERVAL_SEC = 60
MAX_PIPELINE_CONCURRENCY = 10
LLM_TIMEOUT_SEC = 8
KEYWORD_COOLDOWN_SEC = 60

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
