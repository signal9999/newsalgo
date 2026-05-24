#!/bin/bash
# GitHub Actions Secrets に Slack/LINE トークンを登録するスクリプト
# 使い方:
#   SLACK_WEBHOOK_URL=https://hooks.slack.com/... \
#   LINE_NOTIFY_TOKEN=xxx \
#   bash scripts/add_github_secrets.sh

set -e
REPO="signal9999/newsalgo"

echo "=== GitHub Secrets 登録スクリプト ==="
echo "リポジトリ: $REPO"
echo ""

if [ -z "$SLACK_WEBHOOK_URL" ] && [ -z "$LINE_NOTIFY_TOKEN" ]; then
    echo "使い方:"
    echo "  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/... \\"
    echo "  LINE_NOTIFY_TOKEN=your_token \\"
    echo "  bash scripts/add_github_secrets.sh"
    echo ""
    echo "Slack Webhook URL の取得:"
    echo "  1. https://api.slack.com/apps にアクセス"
    echo "  2. 新しいアプリを作成 → Incoming Webhooks を有効化"
    echo "  3. Add New Webhook to Workspace → URL をコピー"
    echo ""
    echo "LINE Notify Token の取得:"
    echo "  1. https://notify-bot.line.me/my/ にアクセス"
    echo "  2. トークンを発行 → Token をコピー"
    exit 1
fi

if [ -n "$SLACK_WEBHOOK_URL" ]; then
    echo "Slack Webhook URL を登録中..."
    gh secret set SLACK_WEBHOOK_URL --repo "$REPO" --body "$SLACK_WEBHOOK_URL"
    echo "✅ SLACK_WEBHOOK_URL 登録完了"
fi

if [ -n "$LINE_NOTIFY_TOKEN" ]; then
    echo "LINE Notify Token を登録中..."
    gh secret set LINE_NOTIFY_TOKEN --repo "$REPO" --body "$LINE_NOTIFY_TOKEN"
    echo "✅ LINE_NOTIFY_TOKEN 登録完了"
fi

echo ""
echo "登録済み Secrets 一覧:"
gh secret list --repo "$REPO"
