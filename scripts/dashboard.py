#!/usr/bin/env python3
"""
NewsAlgo CLI モニタリングダッシュボード

リアルタイムでシステム状態・最新シグナル・トレード損益を表示する。

使い方:
  python3 scripts/dashboard.py            # 一度表示
  python3 scripts/dashboard.py --watch    # 30秒ごとに自動更新
  python3 scripts/dashboard.py --tail 20  # 最新N件のシグナルを表示
"""
import sys
import os
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))


_JST = timezone(timedelta(hours=9))
_LOG_ROOT = Path(__file__).parent.parent / "logs"


def now_jst() -> str:
    return datetime.now(_JST).strftime("%Y-%m-%d %H:%M:%S JST")


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
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return lines[-limit:] if limit else lines


def load_all_jsonl(directory: Path, limit: int = 0) -> list:
    items = []
    if not directory.exists():
        return []
    for f in sorted(directory.glob("*.jsonl")):
        items.extend(read_jsonl(f))
    return items[-limit:] if limit else items


def redis_status() -> str:
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        r.ping()
        info = r.info("server")
        return f"✅ 稼働中 (Redis {info.get('redis_version', '?')})"
    except Exception:
        return "⚠️  未起動（メモリキャッシュで代替）"


def calc_pnl(orders: list) -> dict:
    total = 0.0
    wins = 0
    losses = 0
    for o in orders:
        pnl = o.get("pnl", 0) or 0
        total += pnl
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
    trades = wins + losses
    win_rate = wins / trades * 100 if trades > 0 else 0.0
    return {"total": total, "wins": wins, "losses": losses,
            "trades": trades, "win_rate": win_rate}


def print_dashboard(tail: int = 10):
    os.system("clear" if os.name != "nt" else "cls")
    w = 72

    print("╔" + "═" * (w - 2) + "╗")
    print(f"║{'NewsAlgo モニタリングダッシュボード':^{w-2}}║")
    print(f"║{now_jst():^{w-2}}║")
    print("╠" + "═" * (w - 2) + "╣")

    # ── システム状態 ────────────────────────────────────────────────────
    print(f"║{'  [ システム状態 ]':<{w-2}}║")

    from config import settings
    print(f"║  SIGNAL_THRESHOLD : {settings.SIGNAL_THRESHOLD:<{w-22}}║")
    print(f"║  PAPER_TRADE      : {'ON (ペーパー)' if settings.PAPER_TRADE else '🔴 OFF (実取引！)'}{'':>{w-36}}║")
    redis_s = redis_status()
    print(f"║  Redis            : {redis_s:<{w-22}}║")

    # ログファイル数
    news_count = len(list((_LOG_ROOT / "news").glob("*.jsonl"))) if (_LOG_ROOT / "news").exists() else 0
    print(f"║  ニュースログ     : {news_count} ファイル{'':>{w-24}}║")
    print("╠" + "═" * (w - 2) + "╣")

    # ── シグナル履歴 ─────────────────────────────────────────────────────
    signals = load_all_jsonl(_LOG_ROOT / "signal", limit=tail)
    print(f"║  [ 最新シグナル (直近 {tail} 件) ]{'':>{w-33}}║")
    if signals:
        for s in signals[-tail:]:
            ts  = str(s.get("timestamp", ""))[:16]
            lvl = s.get("level", "?")
            dir = s.get("direction", "?")[:8]
            syms = ",".join(s.get("affected_symbols", []))[:12] or "N/A"
            sc  = s.get("score", 0)
            line = f"  {ts}  [{lvl:6s}] {dir:8s}  {syms:12s}  score={sc:.2f}"
            print(f"║{line:<{w-2}}║")
    else:
        print(f"║{'  シグナルログなし':^{w-2}}║")
    print("╠" + "═" * (w - 2) + "╣")

    # ── 損益サマリー ──────────────────────────────────────────────────────
    orders = load_all_jsonl(_LOG_ROOT / "order")
    pnl    = calc_pnl(orders)
    print(f"║  [ ペーパートレード損益サマリー ]{'':>{w-35}}║")
    if pnl["trades"] > 0:
        sign = "+" if pnl["total"] >= 0 else ""
        print(f"║  総トレード数 : {pnl['trades']:4d} 件{'':>{w-23}}║")
        print(f"║  勝率         : {pnl['win_rate']:5.1f}%  "
              f"(勝:{pnl['wins']} / 負:{pnl['losses']}){'':>{w-38}}║")
        print(f"║  総損益       : {sign}¥{pnl['total']:,.0f}{'':>{w-26}}║")
    else:
        print(f"║{'  トレード記録なし':^{w-2}}║")
    print("╠" + "═" * (w - 2) + "╣")

    # ── ニュースソース別統計 ──────────────────────────────────────────────
    news_items = load_all_jsonl(_LOG_ROOT / "news")
    print(f"║  [ ニュースソース別統計 (全期間) ]{'':>{w-36}}║")
    if news_items:
        src_count = defaultdict(int)
        for item in news_items:
            src_count[item.get("source", "unknown")] += 1
        for src, cnt in sorted(src_count.items(), key=lambda x: -x[1])[:6]:
            bar = "▓" * min(cnt // 2, 20)
            line = f"  {src:15s} {cnt:4d}件  {bar}"
            print(f"║{line:<{w-2}}║")
    else:
        print(f"║{'  ニュースログなし':^{w-2}}║")

    print("╚" + "═" * (w - 2) + "╝")
    print("  終了: Ctrl+C  |  更新: --watch オプション")


def parse_args():
    p = argparse.ArgumentParser(description="NewsAlgo モニタリングダッシュボード")
    p.add_argument("--watch",    action="store_true", help="30秒ごとに自動更新")
    p.add_argument("--interval", type=int, default=30, help="更新間隔（秒）")
    p.add_argument("--tail",     type=int, default=8,  help="表示するシグナル件数")
    return p.parse_args()


def main():
    args = parse_args()
    print_dashboard(args.tail)

    if args.watch:
        try:
            while True:
                time.sleep(args.interval)
                print_dashboard(args.tail)
        except KeyboardInterrupt:
            print("\n  ダッシュボードを終了しました。")


if __name__ == "__main__":
    main()
