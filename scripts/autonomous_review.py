#!/usr/bin/env python3
"""
NewsAlgo 自律戦略レビュースクリプト

指標を監視し、パフォーマンス劣化を検知したら自動でパラメータを調整・git commit する。
GitHub Actions / Mixhost cron から週次・日次で呼び出される。

使い方:
  python3 scripts/autonomous_review.py           # 通常レビュー
  python3 scripts/autonomous_review.py --dry-run # 変更なしで確認のみ
  python3 scripts/autonomous_review.py --force   # 強制最適化実行
"""
import json
import sys
import os
import asyncio
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

_ROOT = Path(__file__).parent.parent
_LOG  = _ROOT / "logs"
_ENV  = _ROOT / ".env"
_JST  = timezone(timedelta(hours=9))

# ── パフォーマンス目標値 ──────────────────────────────────────────────────────
TARGETS = {
    "win_rate":     0.60,   # 最低勝率 60%
    "profit_factor": 1.30,  # 最低 PF
    "max_drawdown": 0.08,   # 最大 DD 上限 8%
    "min_trades":   5,      # 判断に必要な最小トレード数
}

# SIGNAL_THRESHOLD 調整候補
THRESHOLD_CANDIDATES = [0.5, 0.6, 0.65, 0.7, 0.75, 0.8]


# ── ユーティリティ ────────────────────────────────────────────────────────────

def now_jst() -> str:
    return datetime.now(_JST).strftime("%Y-%m-%d %H:%M JST")

def log(msg: str):
    print(f"[{now_jst()}] {msg}", flush=True)

def read_jsonl(path: Path, limit: int = 0) -> list:
    if not path.exists():
        return []
    lines = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except Exception:
                        pass
    except OSError:
        pass
    return lines[-limit:] if limit else lines

def load_all_jsonl(directory: Path) -> list:
    items = []
    if not directory.exists():
        return []
    for f in sorted(directory.glob("*.jsonl")):
        items.extend(read_jsonl(f))
    return items

def read_env_threshold() -> float:
    """現在の SIGNAL_THRESHOLD を .env から読む"""
    if not _ENV.exists():
        return 0.7
    for line in _ENV.read_text().splitlines():
        if line.startswith("SIGNAL_THRESHOLD="):
            try:
                return float(line.split("=", 1)[1].strip())
            except Exception:
                pass
    return 0.7

def write_env_threshold(value: float, dry_run: bool = False):
    """SIGNAL_THRESHOLD を .env に書き戻す"""
    if not _ENV.exists():
        log("  ⚠️  .env が見つかりません")
        return
    text = _ENV.read_text()
    new_text = "\n".join(
        f"SIGNAL_THRESHOLD={value}" if line.startswith("SIGNAL_THRESHOLD=") else line
        for line in text.splitlines()
    )
    if dry_run:
        log(f"  [DRY-RUN] SIGNAL_THRESHOLD → {value}")
    else:
        _ENV.write_text(new_text)
        log(f"  ✅ .env 更新: SIGNAL_THRESHOLD={value}")


# ── 指標計算 ─────────────────────────────────────────────────────────────────

def calc_metrics(orders: list) -> dict:
    if not orders:
        return {"win_rate": 0, "profit_factor": 0, "max_drawdown": 0,
                "total_pnl": 0, "trades": 0, "wins": 0, "losses": 0}
    pnls  = [o.get("pnl", 0) or 0 for o in orders]
    wins  = [p for p in pnls if p > 0]
    losses= [abs(p) for p in pnls if p < 0]
    trades= len([p for p in pnls if p != 0])
    win_rate = len(wins) / trades if trades else 0
    pf       = sum(wins) / sum(losses) if losses else (99.0 if wins else 0.0)

    # 最大 drawdown
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    initial = 1_000_000
    for p in pnls:
        cumulative += p
        peak = max(peak, cumulative)
        dd = (peak - cumulative) / (initial + peak) if (initial + peak) > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "win_rate":      win_rate,
        "profit_factor": pf,
        "max_drawdown":  max_dd,
        "total_pnl":     sum(pnls),
        "trades":        trades,
        "wins":          len(wins),
        "losses":        len(losses),
    }

def is_degraded(m: dict) -> list:
    """パフォーマンス劣化の原因リストを返す（空なら問題なし）"""
    issues = []
    if m["trades"] < TARGETS["min_trades"]:
        return []  # データ不足は判断しない
    if m["win_rate"] < TARGETS["win_rate"]:
        issues.append(f"勝率低下 {m['win_rate']*100:.1f}% < 目標 {TARGETS['win_rate']*100:.0f}%")
    if m["profit_factor"] < TARGETS["profit_factor"]:
        issues.append(f"PF低下 {m['profit_factor']:.2f} < 目標 {TARGETS['profit_factor']:.2f}")
    if m["max_drawdown"] > TARGETS["max_drawdown"]:
        issues.append(f"DD超過 {m['max_drawdown']*100:.1f}% > 上限 {TARGETS['max_drawdown']*100:.0f}%")
    return issues


# ── パラメータ自動最適化 ─────────────────────────────────────────────────────

async def optimize_threshold(signals: list, orders: list) -> float:
    """backtest を複数 threshold で走らせて最良を返す"""
    sys.path.insert(0, str(_ROOT))
    try:
        from backtest.runner import BacktestRunner
        from backtest.data_loader import load_news_from_jsonl
    except ImportError:
        log("  ⚠️  backtest モジュール未インストール。threshold 変更をスキップ")
        return read_env_threshold()

    news = load_news_from_jsonl()
    if not news:
        log("  ⚠️  JSONL ニュースなし。threshold 変更をスキップ")
        return read_env_threshold()

    best_thresh = read_env_threshold()
    best_score  = -999.0
    log(f"  threshold 候補 {THRESHOLD_CANDIDATES} でグリッドサーチ中...")

    for th in THRESHOLD_CANDIDATES:
        runner = BacktestRunner(use_llm=False, hold_days=1, signal_threshold=th)
        result = await runner.run(news)
        m = result["metrics"]
        trades = m.get("total_trades", 0)
        if trades < 3:
            continue
        wr = m.get("win_rate", 0)
        pf = m.get("profit_factor", 0)
        score = wr * 0.6 + min(pf / 3, 1) * 0.4  # 勝率60% + PF40% の複合スコア
        log(f"    th={th}: trades={trades} wr={wr*100:.1f}% pf={pf:.2f} score={score:.3f}")
        if score > best_score:
            best_score  = score
            best_thresh = th

    log(f"  最適 threshold: {best_thresh} (score={best_score:.3f})")
    return best_thresh


# ── Git コミット ─────────────────────────────────────────────────────────────

def git_commit(message: str, dry_run: bool = False):
    if dry_run:
        log(f"  [DRY-RUN] git commit: {message}")
        return
    try:
        subprocess.run(["git", "-C", str(_ROOT), "add", ".env"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "-C", str(_ROOT), "commit", "-m", message],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            log(f"  ✅ git commit 完了")
        else:
            log(f"  ℹ️  コミットなし（変更なし）: {result.stderr.strip()}")
    except Exception as e:
        log(f"  ⚠️  git commit 失敗: {e}")

def git_push(dry_run: bool = False):
    if dry_run:
        log("  [DRY-RUN] git push")
        return
    try:
        result = subprocess.run(
            ["git", "-C", str(_ROOT), "push", "origin", "main"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            log("  ✅ git push 完了 → Mixhost 次回 cron で自動反映")
        else:
            log(f"  ⚠️  push 失敗: {result.stderr.strip()}")
    except Exception as e:
        log(f"  ⚠️  git push 例外: {e}")


# ── レポート保存 ─────────────────────────────────────────────────────────────

def save_report(m: dict, issues: list, action: str, threshold: float):
    report = {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "win_rate":        round(m["win_rate"], 4),
        "profit_factor":   round(m["profit_factor"], 3),
        "max_drawdown":    round(m["max_drawdown"], 4),
        "total_pnl":       round(m["total_pnl"], 0),
        "trades":          m["trades"],
        "issues":          issues,
        "action":          action,
        "threshold_after": threshold,
    }
    log_path = _LOG / "strategy_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")
    log(f"  レポート保存: {log_path}")


# ── メイン ───────────────────────────────────────────────────────────────────

async def main(dry_run: bool = False, force: bool = False):
    print("=" * 60)
    print(f"  NewsAlgo 自律戦略レビュー  {now_jst()}")
    print("=" * 60)

    # データ読み込み
    orders  = load_all_jsonl(_LOG / "order")
    signals = load_all_jsonl(_LOG / "signal")
    news    = load_all_jsonl(_LOG / "news")
    log(f"ログ: orders={len(orders)} signals={len(signals)} news={len(news)}")

    # 指標計算
    m = calc_metrics(orders)
    log(f"指標: 勝率={m['win_rate']*100:.1f}% PF={m['profit_factor']:.2f} "
        f"DD={m['max_drawdown']*100:.1f}% trades={m['trades']}")

    current_threshold = read_env_threshold()
    log(f"現在の SIGNAL_THRESHOLD={current_threshold}")

    # 劣化チェック
    issues = is_degraded(m)
    action = "no_action"

    if not issues and not force:
        log("✅ パフォーマンス正常 — 変更なし")
        save_report(m, [], "no_action", current_threshold)
        return

    if issues:
        for iss in issues:
            log(f"⚠️  {iss}")

    # 最適化実行
    log("🔍 パラメータ最適化を実行中...")
    new_threshold = await optimize_threshold(signals, orders)

    if new_threshold != current_threshold or force:
        log(f"📝 threshold 変更: {current_threshold} → {new_threshold}")
        write_env_threshold(new_threshold, dry_run)
        git_commit(
            f"auto: SIGNAL_THRESHOLD {current_threshold}→{new_threshold} "
            f"(wr={m['win_rate']*100:.1f}% pf={m['profit_factor']:.2f})",
            dry_run
        )
        git_push(dry_run)
        action = f"threshold_updated_{current_threshold}_{new_threshold}"
    else:
        log(f"ℹ️  最適値は現在値と同じ ({current_threshold}) — .env 変更なし")
        action = "no_change_needed"

    save_report(m, issues, action, new_threshold)

    print("=" * 60)
    print(f"  レビュー完了  action={action}")
    print("=" * 60)


def parse_args():
    p = argparse.ArgumentParser(description="NewsAlgo 自律戦略レビュー")
    p.add_argument("--dry-run", action="store_true", help="変更なしで確認のみ")
    p.add_argument("--force",   action="store_true", help="劣化なしでも最適化実行")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(dry_run=args.dry_run, force=args.force))
