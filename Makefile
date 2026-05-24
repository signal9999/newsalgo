# NewsAlgo Makefile — よく使うコマンドのショートカット

.PHONY: help test backtest optimize rss alert scheduler deploy logs

help:
	@echo "NewsAlgo コマンド一覧"
	@echo "================================="
	@echo "  make test          全テスト実行 (pytest)"
	@echo "  make backtest      バックテスト（サンプル、hold=1）"
	@echo "  make backtest-llm  LLM モードでバックテスト"
	@echo "  make optimize      hold_days × threshold 最適化"
	@echo "  make cost          LLM API コスト試算"
	@echo "  make rss           RSS フィード取得テスト"
	@echo "  make alert         アラート設定確認"
	@echo "  make alert-test    アラートテスト送信"
	@echo "  make ibkr          IBKR 接続テスト（スタブ）"
	@echo "  make scheduler     スケジューラー dry-run"
	@echo "  make run           スケジューラー起動（常時稼働）"
	@echo "  make logs          最新ログ確認"
	@echo "  make push          git add → commit → push"

test:
	python3 -m pytest tests/ -v

backtest:
	python3 run_backtest.py --mode sample --hold 1

backtest-llm:
	python3 run_backtest.py --mode sample --hold 1 --llm

optimize:
	python3 run_optimize.py --mode sample --csv

cost:
	python3 run_backtest.py --mode sample --cost

rss:
	python3 -c "\
import asyncio, sys; sys.path.insert(0,'.');\
from collectors.rss import fetch_all_rss;\
from collections import Counter;\
async def t():\
    items = await fetch_all_rss();\
    [print(f'  {s:15s} {n:4d}件') for s,n in sorted(Counter(i['source'] for i in items).items())];\
    print(f'  合計: {len(items)}件');\
asyncio.run(t())"

alert:
	python3 scripts/test_alert.py --check

alert-test:
	python3 scripts/test_alert.py

ibkr:
	python3 scripts/test_ibkr.py --stub

scheduler:
	python3 scheduler.py --dry-run

run:
	python3 scheduler.py

logs:
	@ls -lt logs/news/*.jsonl 2>/dev/null | head -5 || echo "ログファイルなし"
	@echo "---"
	@ls -lt logs/signal/*.jsonl 2>/dev/null | head -3 || echo "シグナルログなし"

push:
	git add -A
	git status
	@read -p "コミットメッセージ: " msg; git commit -m "$$msg"
	git push origin main
