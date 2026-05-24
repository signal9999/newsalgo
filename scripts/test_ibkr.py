#!/usr/bin/env python3
"""
IBKR 接続テストスクリプト

使い方:
  python3 scripts/test_ibkr.py            # 接続テスト（スタブ or 実接続）
  python3 scripts/test_ibkr.py --stub     # スタブモードで動作確認のみ
  python3 scripts/test_ibkr.py --check    # 事前要件確認のみ

接続要件:
  1. pip install ib_insync
  2. TWS (Trader Workstation) を起動
     - ペーパートレード口座でログイン
     - File → Global Configuration → API → Settings
       - Enable ActiveX and Socket Clients: ON
       - Socket port: 7497
       - Read-Only API: OFF（発注するため）
  3. .env に追記（任意）:
     IBKR_HOST=127.0.0.1
     IBKR_PORT=7497
"""
import sys
import asyncio
import argparse
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa
from execution.ibkr import IBKRBroker
from execution.broker import Order


def check_requirements() -> dict:
    """事前要件チェック。"""
    results = {}

    # ib_insync インストール確認
    try:
        import ib_insync
        results["ib_insync"] = f"✅ インストール済み (v{ib_insync.__version__})"
    except ImportError:
        results["ib_insync"] = "❌ 未インストール → pip install ib_insync"

    # TWS ポート確認
    import socket
    host = os.environ.get("IBKR_HOST", "127.0.0.1")
    port = int(os.environ.get("IBKR_PORT", "7497"))
    try:
        with socket.create_connection((host, port), timeout=2):
            results["tws"] = f"✅ TWS/IB Gateway が起動中 ({host}:{port})"
    except (ConnectionRefusedError, OSError):
        results["tws"] = f"❌ TWS/IB Gateway が起動していません ({host}:{port})"

    # 環境変数確認
    results["env_host"] = f"IBKR_HOST={host}"
    results["env_port"] = f"IBKR_PORT={port}"

    return results


def print_requirements(results: dict):
    print("\n" + "=" * 54)
    print("  IBKR 接続要件チェック")
    print("=" * 54)
    for k, v in results.items():
        print(f"  {v}")
    print("=" * 54)
    print()


async def run_stub_test():
    """スタブモードで動作確認（実際の接続なし）。"""
    print("[IBKR-STUB] スタブモードテスト開始")

    broker = IBKRBroker(paper=True)
    # 接続しない（スタブとして動作）

    test_order = Order(
        symbol="7203",
        side="buy",
        quantity=100,
        price=2800.0,
        order_type="market",
        signal_id="test-001",
    )

    print(f"[IBKR-STUB] テスト注文: {test_order.side} {test_order.symbol} × {test_order.quantity}")
    result = await broker.submit_order(test_order)
    print(f"[IBKR-STUB] 結果: status={result.status} order_id={result.order_id[:8]}...")

    pos = await broker.get_position("7203")
    print(f"[IBKR-STUB] ポジション: {pos}")

    acct = await broker.get_account()
    print(f"[IBKR-STUB] 口座: {acct}")

    print("[IBKR-STUB] ✅ スタブモードテスト完了\n")


async def run_live_test():
    """実際に TWS に接続してテスト（発注はしない）。"""
    broker = IBKRBroker(paper=True)
    connected = await broker.connect()

    if not connected:
        print("❌ 接続失敗。スタブモードに切り替えます...")
        await run_stub_test()
        return

    print("✅ IBKR TWS 接続成功！")

    # 口座情報取得
    acct = await broker.get_account()
    print(f"  口座情報: 現金={acct.get('cash', 0):,.0f} {acct.get('currency', 'JPY')}")
    print(f"  純資産  : {acct.get('net_liquidation', 0):,.0f} {acct.get('currency', 'JPY')}")

    # ポジション確認（7203=トヨタ）
    pos = await broker.get_position("7203")
    print(f"  7203(トヨタ) ポジション: {pos}")

    print("\n✅ 接続テスト完了（発注は行いませんでした）")
    await broker.disconnect()


def parse_args():
    p = argparse.ArgumentParser(description="IBKR 接続テスト")
    p.add_argument("--stub",  action="store_true", help="スタブモードのみ（TWS 不要）")
    p.add_argument("--check", action="store_true", help="要件確認のみ")
    return p.parse_args()


async def main():
    args = parse_args()

    results = check_requirements()
    print_requirements(results)

    if args.check:
        return

    if args.stub or "❌ 未インストール" in results.get("ib_insync", ""):
        await run_stub_test()
    else:
        if "❌" in results.get("tws", ""):
            print("⚠️  TWS が起動していません。スタブモードで実行します。\n")
            await run_stub_test()
        else:
            await run_live_test()


if __name__ == "__main__":
    asyncio.run(main())
