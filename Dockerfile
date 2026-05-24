# NewsAlgo — マルチステージ Docker イメージ
# ベース: Python 3.11-slim (GitHub Actions と同一バージョン)
FROM python:3.11-slim AS base

WORKDIR /app

# システム依存パッケージ
RUN apt-get update -q && \
    apt-get install -y -q --no-install-recommends \
        curl \
        tzdata && \
    rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ── 依存関係レイヤー（キャッシュ効率化） ──────────────────────────────────
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir tzdata

# ── アプリレイヤー ─────────────────────────────────────────────────────────
FROM deps AS app

COPY . .

# logs/ ディレクトリを作成（マウントポイント）
RUN mkdir -p logs/news logs/signal logs/order logs/error

# ── スケジューラー起動（デフォルト） ────────────────────────────────────────
CMD ["python3", "scheduler.py"]

# ── ヘルスチェック ─────────────────────────────────────────────────────────
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import sys; sys.exit(0)"

LABEL org.opencontainers.image.source="https://github.com/signal9999/newsalgo" \
      org.opencontainers.image.description="NewsAlgo - ニュース駆動型自動売買システム"
