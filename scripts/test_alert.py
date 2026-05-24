#!/usr/bin/env python3
"""
Slack / LINE アラート動作テストスクリプト

使い方:
  python3 scripts/test_alert.py                # 全アラートタイプをテスト
  python3 scripts/test_alert.py --slack-only   # Slack のみ
  python3 scripts/test_alert.py --line-only    # LINE のみ
  python3 scripts/test_alert.py --check        # 設定確認のみ（送信なし）

.env に以下を設定してから実行してください:
  SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXXX/YYYY/ZZZZ
  LINE_NOTIFY_TOKEN=your_token_here
"""
import sys
import argparse
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env 読み込み
from config import settings  # noqa: F401
from monitor.alert import AlertManager


def check_config():
    """設定状況を確認して表示する。"""
    slack = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    line  = os.environ.get("LINE_NOTIFY_TOKEN",  "").strip()

    print("\n" + "=" * 50)
    print("  アラート設定状況")
    print("=" * 50)
    print(f"  Slack Webhook URL : {'✅ 設定済み' if slack else '❌ 未設定'}")
    if slack:
        masked = slack[:30] + "..." if len(slack) > 30 else slack
        print(f"    URL: {masked}")
    print(f"  LINE Notify Token : {'✅ 設定済み' if line else '❌ 未設定'}")
    if line:
        masked = line[:8] + "****" + line[-4:] if len(line) > 12 else "****"
        print(f"    Token: {masked}")

    if not slack and not line:
        print("\n  ⚠️  どちらも未設定です。.env ファイルを確認してください。")
        print("  コンソール出力のみで動作します。")
    print("=" * 50 + "\n")
    return bool(slack), bool(line)


def parse_args():
    p = argparse.ArgumentParser(description="Slack/LINE アラートテスト")
    p.add_argument("--slack-only", action="store_true", help="Slack のみテスト")
    p.add_argument("--line-only",  action="store_true", help="LINE のみテスト")
    p.add_argument("--check",      action="store_true", help="設定確認のみ（送信なし）")
    return p.parse_args()


def main():
    args = parse_args()
    has_slack, has_line = check_config()

    if args.check:
        return

    am = AlertManager()

    # LINE のみモード: Slack を一時的に無効化
    if args.line_only:
        os.environ["SLACK_WEBHOOK_URL"] = ""

    # Slack のみモード: LINE を一時的に無効化
    if args.slack_only:
        os.environ["LINE_NOTIFY_TOKEN"] = ""

    print("アラートテスト送信中...\n")

    # ── INFO: パイプライン開始 ─────────────────────────────────────────
    print("[1/4] INFO アラート...")
    am.send_alert("INFO", "NewsAlgo アラートテスト - INFO レベル", {"env": "test", "version": "v4"})

    # ── WARNING: デイリー損失警告 ─────────────────────────────────────
    print("[2/4] WARNING アラート...")
    am.alert_daily_loss(current_pct=8.2, limit_pct=10.0)

    # ── INFO: 強シグナル ───────────────────────────────────────────────
    print("[3/4] 強シグナルアラート...")
    am.alert_strong_signal({
        "score": 0.87,
        "level": "STRONG",
        "direction": "bullish",
        "affected_symbols": ["7203"],
    })

    # ── CRITICAL: エラー連発 ──────────────────────────────────────────
    print("[4/4] CRITICAL アラート...")
    am.alert_error_surge(error_count=7, window_sec=60)

    print("\nテスト完了。")
    if not has_slack and not has_line:
        print("⚠️  Slack/LINE が未設定のためコンソール出力のみです。")
        print("   .env に SLACK_WEBHOOK_URL または LINE_NOTIFY_TOKEN を設定してください。")


if __name__ == "__main__":
    main()
