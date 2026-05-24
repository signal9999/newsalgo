#!/bin/bash
# NewsAlgo VPS セットアップスクリプト
# 対象: Ubuntu 22.04 LTS
# 使い方: bash deploy/setup_vps.sh

set -e
REPO_URL="git@github.com:signal9999/newsalgo.git"
INSTALL_DIR="/home/ubuntu/newsalgo"
PYTHON="python3"

echo "╔════════════════════════════════════════════╗"
echo "║    NewsAlgo VPS セットアップ               ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ── 1. システムパッケージ ─────────────────────────────────────────────
echo "[1/6] システムパッケージのインストール..."
sudo apt-get update -q
sudo apt-get install -y -q python3 python3-pip git redis-server

# Redis 自動起動
sudo systemctl enable redis-server
sudo systemctl start redis-server
echo "  ✅ Redis 起動済み"

# ── 2. リポジトリ取得 ────────────────────────────────────────────────
echo "[2/6] リポジトリのクローン..."
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull origin main
    echo "  ✅ git pull 完了"
else
    git clone "$REPO_URL" "$INSTALL_DIR"
    echo "  ✅ git clone 完了"
fi

# ── 3. Python 依存関係 ────────────────────────────────────────────────
echo "[3/6] Python パッケージのインストール..."
cd "$INSTALL_DIR"
pip3 install -r requirements.txt --quiet
pip3 install tzdata --quiet
echo "  ✅ pip install 完了"

# ── 4. .env 設定 ─────────────────────────────────────────────────────
echo "[4/6] .env 設定..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat <<EOF > "$INSTALL_DIR/.env"
ANTHROPIC_API_KEY=your_key_here
SUPABASE_URL=https://ibpfemdqqnafnbqjkyfn.supabase.co
SUPABASE_KEY=your_supabase_key_here
REDIS_URL=redis://localhost:6379
PAPER_TRADE=true
MAX_POSITION_PCT=0.05
DAILY_LOSS_LIMIT_PCT=0.10
SIGNAL_THRESHOLD=0.7
SLACK_WEBHOOK_URL=
LINE_NOTIFY_TOKEN=
EOF
    echo "  ⚠️  $INSTALL_DIR/.env を編集して API キーを設定してください"
else
    echo "  ✅ .env 既存（スキップ）"
fi

# ── 5. デプロイ方法の選択 ─────────────────────────────────────────────
echo "[5/6] デプロイ方法の設定..."

if command -v pm2 &> /dev/null; then
    echo "  pm2 が見つかりました。pm2 でデプロイします..."
    cd "$INSTALL_DIR"
    pm2 start deploy/ecosystem.config.js
    pm2 save
    echo "  ✅ pm2 起動完了"
    echo "  pm2 logs newsalgo-scheduler    # ログ確認"
    echo "  pm2 stop newsalgo-scheduler    # 停止"
    echo "  pm2 restart newsalgo-scheduler # 再起動"
else
    echo "  systemd でデプロイします..."
    # User を現在のユーザーに置き換え
    CURRENT_USER=$(whoami)
    sed "s/User=ubuntu/User=$CURRENT_USER/g" \
        "$INSTALL_DIR/deploy/newsalgo.service" | \
        sed "s|/home/ubuntu/newsalgo|$INSTALL_DIR|g" > \
        /tmp/newsalgo.service
    sudo cp /tmp/newsalgo.service /etc/systemd/system/newsalgo.service
    sudo systemctl daemon-reload
    sudo systemctl enable newsalgo
    sudo systemctl start newsalgo
    echo "  ✅ systemd 起動完了"
    echo "  sudo systemctl status newsalgo     # 状態確認"
    echo "  sudo journalctl -u newsalgo -f     # ログ確認"
    echo "  sudo systemctl restart newsalgo    # 再起動"
fi

# ── 6. 動作確認 ─────────────────────────────────────────────────────
echo "[6/6] 動作確認..."
cd "$INSTALL_DIR"
$PYTHON -m pytest tests/ -q 2>&1 | tail -3
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║    セットアップ完了！                      ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "次のステップ:"
echo "  1. $INSTALL_DIR/.env の API キーを設定"
echo "  2. python3 scheduler.py --now  # 手動テスト実行"
echo "  3. python3 scripts/test_alert.py  # アラートテスト"
