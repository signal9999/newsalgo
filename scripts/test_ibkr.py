#!/usr/bin/env python3
"""
IBKR 接続テストスクリプト（ib_insync 0.9.86 対応）

使い方:
  python3 scripts/test_ibkr.py            # 接続テスト（TWS 起動済みなら実接続）
  python3 scripts/test_ibkr.py --stub     # スタブモードのみ
  python3 scripts/test_ibkr.py --check    # 要件確認のみ
  python3 scripts/test_ibkr.py --order    # テスト発注（ペーパートレード口座のみ）

TWS 起動手順:
  1. TWS をダウンロード: https://www.interactivebrokers.com/en/trading/tws.php
  2. ペーパートレード口座でログイン
  3. File → Global Configuration → API → Settings
     - Enable ActiveX and Socket Clients: ON
     - Socket port: 7497
     - Trusted IP Addresses に 127.0.0.1 を追加
  4. python3 scripts/test_ibkr.py を実行
"""
import sys
import asyncio
import argparse
import os
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: F401
from execution.ibkr import IBKRBroker
from execution.broker import Order

_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
_PORT = int(os.environ.get("IBKR_PORT", "7497"))


def check_requirements() -> dict:
    results = {}

    # ib_insync インストール確認
    try:
        import ib_insync
        results["ib_insync"] = f"✅ ib_insync v{ib_insync.__version__} インストール済み"
    except ImportError:
        results["ib_insync"] = "❌ 未インストール → pip install ib_insync"

    # TWS ポート確認
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2):
            results["tws"] = f"✅ TWS/IB Gateway が起動中 ({_HOST}:{_PORT})"
    except (ConnectionRefusedError, OSError):
        results["tws"] = f"❌ TWS/IB Gateway が未起動 ({_HOST}:{_PORT})"

    results["env"] = f"IBKR_HOST={_HOST}  IBKR_PORT={_PORT}"
    return results


def print_requirements(results: dict):
    print("\n" + "=" * 54)
    print("  IBKR 接続要件チェック")
    print("=" * 54)
    for v in results.values():
        print(f"  {v}")
    print("=" * 54 + "\n")


async def run_stub_test():
    """スタブモード（TWS 不要）で動作確認。"""
    print("─" * 50)
    print("  IBKR スタブモード動作確認")
    print("─" * 50)

    broker = IBKRBroker(paper=True)

    orders = [
        Order("7203", "buy",  100, 2800.0, "market", "test-buy-001"),
        Order("6758", "sell", 50,  13000.0, "limit",  "test-sell-001"),
    ]

    for o in orders:
        result = await broker.submit_order(o)
        print(f"  {o.side:5s} {o.symbol} ×{o.quantity:4.0f}  → "
              f"status={result.status}  id={result.order_id[:8]}")

    pos  = await broker.get_position("7203")
    acct = await broker.get_account()
    print(f"\n  ポジション(7203): qty={pos['quantity']}  avg={pos['avg_price']}")
    print(f"  口座情報: cash={acct['cash']:,.0f} {acct['currency']}")
    print("\n  ✅ スタブモード OK\n")


async def run_live_test(do_order: bool = False):
    """TWS に実接続してテスト。"""
    print("─" * 50)
    print("  IBKR TWS 実接続テスト")
    print("─" * 50)

    broker = IBKRBroker(paper=True)
    connected = await broker.connect()

    if not connected:
        print("  ❌ 接続失敗。スタブモードに切り替えます。\n")
        await run_stub_test()
        return

    print("  ✅ TWS 接続成功！")

    # 口座情報
    acct = await broker.get_account()
    cash = acct.get("cash", 0)
    nav  = acct.get("net_liquidation", 0)
    ccy  = acct.get("currency", "JPY")
    print(f"\n  現金残高  : {cash:>14,.0f} {ccy}")
    print(f"  純資産    : {nav:>14,.0f} {ccy}")

    # 既存ポジション確認
    for sym in ["7203", "6758", "9984"]:
        pos = await broker.get_position(sym)
        if pos["quantity"] != 0:
            print(f"  ポジション: {sym} × {pos['quantity']:.0f}  avg={pos['avg_price']:.1f}")

    # テスト発注（ペーパートレードのみ・--order フラグ時）
    if do_order:
        print("\n  [発注テスト] 7203(トヨタ) × 1 株 成行買い")
        order = Order("7203", "buy", 1, None, "market", "paper-test-001")
        result = await broker.submit_order(order)
        print(f"  結果: status={result.status}  fill_price={result.fill_price:.1f}")
        print(f"  order_id: {result.order_id}")

    print("\n  ✅ 実接続テスト完了")
    await broker.disconnect()


def parse_args():
    p = argparse.ArgumentParser(description="IBKR 接続テスト")
    p.add_argument("--stub",  action="store_true", help="スタブモードのみ")
    p.add_argument("--check", action="store_true", help="要件確認のみ")
    p.add_argument("--order", action="store_true", help="テスト発注も実行（ペーパー限定）")
    return p.parse_args()


async def main():
    args = parse_args()
    results = check_requirements()
    print_requirements(results)

    if args.check:
        return

    tws_up = "✅" in results.get("tws", "")

    if args.stub or not tws_up:
        if not args.stub and not tws_up:
            print("  ⚠️  TWS 未起動のためスタブモードで実行します。\n")
        await run_stub_test()
    else:
        await run_live_test(do_order=args.order)


if __name__ == "__main__":
    asyncio.run(main())
