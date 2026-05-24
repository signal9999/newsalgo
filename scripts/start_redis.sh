#!/bin/bash
# Redis 起動スクリプト
# Docker / Homebrew / 直接インストール を自動判定して起動する

set -e

REDIS_PORT=6379

echo "=== NewsAlgo Redis 起動スクリプト ==="

# 既に起動中か確認
if redis-cli -p $REDIS_PORT ping > /dev/null 2>&1; then
    echo "✅ Redis はすでに起動しています (port $REDIS_PORT)"
    redis-cli -p $REDIS_PORT info server | grep redis_version
    exit 0
fi

# Docker Compose で起動
if command -v docker &> /dev/null; then
    echo "Docker を検出しました。docker compose で起動します..."
    cd "$(dirname "$0")/.."
    docker compose up -d redis
    sleep 2
    if redis-cli -p $REDIS_PORT ping > /dev/null 2>&1; then
        echo "✅ Redis (Docker) 起動完了"
        exit 0
    fi
fi

# Homebrew redis で起動
if command -v brew &> /dev/null && brew list redis &> /dev/null 2>&1; then
    echo "Homebrew Redis を検出しました。起動します..."
    brew services start redis
    sleep 2
    if redis-cli -p $REDIS_PORT ping > /dev/null 2>&1; then
        echo "✅ Redis (Homebrew) 起動完了"
        exit 0
    fi
fi

# redis-server コマンドで直接起動
if command -v redis-server &> /dev/null; then
    echo "redis-server を検出しました。バックグラウンドで起動します..."
    redis-server --daemonize yes --port $REDIS_PORT \
        --maxmemory 256mb --maxmemory-policy allkeys-lru \
        --save "" --appendonly no
    sleep 1
    if redis-cli -p $REDIS_PORT ping > /dev/null 2>&1; then
        echo "✅ Redis (redis-server) 起動完了"
        exit 0
    fi
fi

# 全て失敗
echo "❌ Redis の起動に失敗しました。"
echo ""
echo "以下のいずれかでインストールしてください:"
echo "  Docker:   docker compose up -d redis"
echo "  Homebrew: brew install redis && brew services start redis"
echo ""
echo "⚠️  Redis なしでも NewsAlgo はメモリキャッシュで動作します（プロセス再起動で重複排除がリセットされます）"
exit 1
