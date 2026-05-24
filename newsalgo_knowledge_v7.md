# NewsAlgo ナレッジ文書 v7

> 最終更新: 2026-05-24 | 開発者: @signal9media

---

## 0. このプロジェクトの進め方

### 手動作業ゼロの原則

**「Claude Codeで全作業を行う」** が本プロジェクトの大原則。
コード生成・修正・テスト・デプロイのすべてを Claude Code 経由で実施する。

| フェーズ | 自動化手段 | 人間の作業 |
|---|---|---|
| コード変更 | Claude Code で編集 | レビューのみ |
| テスト実行 | pytest（GitHub Actions 連携済み） | 失敗時の原因調査 |
| 本番デプロイ | `git push` → GitHub Actions が自動実行 | なし |
| ログ保存 | Supabase REST API へ自動送信 | なし |
| 障害アラート | Slack / LINE Notify（トークン設定で自動送信） | 対応判断のみ |

### Claude Code 起動コマンド

```bash
cd ~/newsalgo
claude
```

### 新しいチャットでの開始手順

1. Claude Code を起動（上記コマンド）
2. **このファイル（newsalgo_knowledge_v7.md）をアップロード**してから作業開始
3. 作業完了後は `git push` で自動デプロイ

---

## 1. 事業概要

### システム名：NewsAlgo

**ニュース駆動型自動売買システム**

ニュース・SNS・企業情報をリアルタイム取得し、Claude API でセンチメント解析して
自動発注判断を行うシステム。現在はペーパートレードモードで稼働中。

```
[Collector] → [Credibility] → [Keyword] → [LLM] → [Signal] → [Risk] → [Execution]
  RSS/TDnet     信頼性評価     高速抽出    Claude    閾値判定   リスク管理  ペーパー発注
```

### ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 1 | パイプライン構築・ペーパートレード | ✅ 完了 |
| Phase 2 | バックテスト・精度検証 | ✅ 完了 |
| Phase 2.5 | Docker化・CD自動デプロイ・分析ツール整備 | ✅ 完了 |
| Phase 3 | ブローカーAPI接続・小額実口座 | 📋 計画中 |
| Phase 4 | リスク管理強化・複数銘柄対応 | 📋 計画中 |
| Phase 5 | 本格運用 | 📋 計画中 |

### GitHub

**https://github.com/signal9999/newsalgo**

---

## 2. 技術スタック

| カテゴリ | 技術 | バージョン |
|---|---|---|
| 言語 | Python | 3.11+（ローカルは 3.9.6） |
| LLM | Claude API（claude-sonnet-4-5） | anthropic>=0.25 |
| RSS取得 | aiohttp + feedparser | >=3.9 / >=6.0 |
| HTMLパース | BeautifulSoup4 | >=4.12 |
| DB | Supabase（REST API） | — |
| キャッシュ | Redis（Docker Compose 化済み） | >=5.0 |
| 株価取得 | yfinance（.T サフィックス） | >=0.2 |
| スケジューラー | APScheduler 3.11.2 | timezone="Asia/Tokyo" |
| コンテナ | Docker + docker-compose | Python 3.11-slim |
| CI/CD | GitHub Actions（test→build→deploy→notify） | — |
| テスト | pytest + pytest-asyncio | >=8.0 / >=0.23 |
| スクリプト置き場 | `~/newsalgo/` | — |

### LLM 呼び出し仕様

- モデル: `claude-sonnet-4-5`
- タイムアウト: 8秒
- 出力形式: JSON（sentiment / confidence / impact_score / event_type / affected_symbols）
- エラー時: sentiment=neutral, confidence=0.0 でフォールバック

---

## 3. Supabase テーブル構成

**プロジェクト URL:** `https://ibpfemdqqnafnbqjkyfn.supabase.co`

| テーブル | 内容 | 主なカラム |
|---|---|---|
| `news_log` | 取得した全ニュース | item_id, title, source, credibility, is_reliable, timestamp |
| `signal_log` | シグナルが出たもの（NONE はスキップ） | score, level, direction, affected_symbols |
| `order_log` | ペーパートレード発注記録 | order_id, symbol, side, quantity, fill_price, status |

### テーブル作成 SQL

```bash
cd ~/newsalgo
~/.local/share/supabase/supabase db query --linked -f create_tables.sql
```

---

## 4. GitHub Actions

**リポジトリ:** `github.com/signal9999/newsalgo`

### newsalgo.yml（定期実行ワークフロー）

| 時刻 (JST) | UTC cron | 内容 |
|---|---|---|
| 08:00 | `0 23 * * *` | `python main.py` を 30 分実行 |
| 08:30 | `30 23 * * *` | 同上 |
| 手動 | `workflow_dispatch` | テスト実行用 |

### deploy.yml（CD ワークフロー）

`git push main` で自動トリガー。パイプライン:

```
test（pytest）→ build（GHCR push）→ deploy（SSH VPS）→ notify（Slack）
```

- VPS デプロイは `VPS_DEPLOY_ENABLED=true` の場合のみ実行（GitHub Variables で制御）
- コンテナイメージ: `ghcr.io/signal9999/newsalgo:latest`

### 登録済み Secrets

| Secret 名 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー |
| `SUPABASE_URL` | `https://ibpfemdqqnafnbqjkyfn.supabase.co` |
| `SUPABASE_KEY` | Supabase anon key（JWT） |
| `VPS_HOST` | VPS の IP（未設定 → deploy スキップ） |
| `VPS_USER` | SSH ユーザー名（未設定 → deploy スキップ） |
| `VPS_SSH_KEY` | SSH 秘密鍵（未設定 → deploy スキップ） |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook（任意） |

---

## 5. 動作確認済みニュースソース

| ソース | URL | 件数/回 | 信頼性スコア | 状態 |
|---|---|---|---|---|
| NHK 総合 | `https://www3.nhk.or.jp/rss/news/cat0.xml` | 約 7 件 | 0.70 | ✅ |
| NHK 経済 | `https://www3.nhk.or.jp/rss/news/cat6.xml` | 約 123 件 | 0.75 | ✅ |
| Yahoo ビジネス | `https://news.yahoo.co.jp/rss/topics/business.xml` | 約 8 件 | 0.65 | ✅ |
| 東洋経済オンライン | `https://toyokeizai.net/list/feed/rss` | 約 20 件 | 0.72 | ✅ |
| Investing.com JP | `https://jp.investing.com/rss/news_285.rss` | 約 10 件 | 0.68 | ✅ |
| TDnet 適時開示 | HTMLスクレイピング（平日 08:00〜15:35 JST） | 数件〜数十件 | 0.90 | ✅ |

**合計: 約 168 件/回（TDnet除く）— 実動作確認済み**

> ※ みんかぶ RSS は 404・Yahoo 株式 RSS は 404 のため削除。東洋経済・Investing.com に差し替え済み。

### TDnet ポーリング仕様

- URL: `https://www.release.tdnet.info/inbs/I_list_001_{YYYYMMDD}.html`
- 当日 + 前日の 2 日分を並列取得
- **平日 08:00〜15:35 JST のみ動作**（土日・時間外はスキップ）
- 重複排除: Redis TTL 300 秒 / 未起動時はメモリ set
- **証券コード（4桁）・企業名を HTML テーブルから自動抽出**
- `affected_symbols` に証券コードをセット（LLM 不要で銘柄紐付け）
- `raw` フィールド = 「企業名 + タイトル」（LLM 精度向上）

---

## 5b. Docker 起動方法

```bash
cd ~/newsalgo

# フルスタック起動（Redis + スケジューラー）
docker compose up -d

# Redis のみ起動（ローカル開発時）
docker compose up -d redis

# ログ確認
docker compose logs -f scheduler

# バックテスト（単発実行）
docker compose run --rm backtest

# 停止
docker compose down
```

### docker-compose.yml 構成

| サービス | 内容 | プロファイル |
|---|---|---|
| `redis` | Redis 7-alpine, 最大 256MB LRU | デフォルト |
| `scheduler` | Python 3.11, scheduler.py 常時稼働 | デフォルト |
| `backtest` | 単発実行用（`docker compose run --rm backtest`） | `tools` |

### Dockerfile 仕様

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV TZ=Asia/Tokyo PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p logs/news logs/signal logs/order logs/error
CMD ["python3", "scheduler.py"]
HEALTHCHECK --interval=60s CMD python3 -c "import sys; sys.exit(0)"
```

---

## 5c. Slack / LINE アラート設定

`.env` に以下を追記すると自動送信が有効になる:

```env
# Slack Incoming Webhook URL（Slack App で取得）
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXXX/YYYY/ZZZZ

# LINE Notify トークン（https://notify-bot.line.me/ で取得）
LINE_NOTIFY_TOKEN=your_token_here
```

**送信タイミング:**
- `CRITICAL`: エラー連発（60秒以内に5件超）
- `WARNING`: デイリー損失が制限の80%到達
- `INFO`: 強シグナル発生・パイプライン開始/停止

**未設定時:** コンソール出力のみ（エラーは出ない）

---

## 6. バックテストシステム（Phase 2）

### ファイル構成

```
backtest/
  __init__.py
  data_loader.py   # ニュース・株価データ取得
  simulator.py     # ポジション管理・P&L計算
  runner.py        # バックテスト実行エンジン
  metrics.py       # 統計指標計算
  report.py        # レポート出力・CSV保存
run_backtest.py    # CLI エントリポイント
run_optimize.py    # hold × threshold グリッド最適化
run_analysis.py    # KW vs LLM 精度比較分析（HTML出力対応）
```

### 実行方法

```bash
cd ~/newsalgo

# サンプルデータでデモ実行
python3 run_backtest.py --mode sample --hold 1

# 実ニュースログ（logs/news/YYYYMMDD.jsonl）でバックテスト
python3 run_backtest.py --mode jsonl --hold 3 --threshold 0.5

# CSV 出力付き
python3 run_backtest.py --mode sample --csv --output backtest_result.csv

# KW vs LLM 精度比較分析（HTML レポート出力）
python3 run_analysis.py
python3 run_analysis.py --html --output report.html
python3 run_analysis.py --no-llm        # キーワードモードのみ
```

### バックテスト最適化結果（サンプルデータ）

| hold | threshold | 勝率 | PF | 判定 |
|---|---|---|---|---|
| 1日 | 0.7 | 66.7% | 2.28 | **BEST** |
| 1日 | 0.3 | 55.6% | 1.46 | — |
| 3日 | 0.7 | 33.3% | 1.13 | — |
| 5日 | 0.7 | 66.7% | 1.38 | — |

**推奨パラメータ: hold_days=1, SIGNAL_THRESHOLD=0.7**

### LLM バックテスト実測結果（2026-05-24）

| モード | 勝率 | PF | APIコスト |
|---|---|---|---|
| キーワードのみ（KW） | 66.7% | 2.28 | $0 |
| LLM（claude-sonnet-4-5） | 66.7% | 2.28 | ¥7.95/回 |

→ **精度は同等。KW モードを本番推奨。LLM は精度改善が見込める場合のみ使用。**

---

## 7. ペーパートレード永続化

`execution/paper_trade.py` は JSON ファイルで状態を永続化する。

### 状態ファイル

```
logs/paper_state.json
```

```json
{
  "balance": 980000.0,
  "realized_pnl": 5000.0,
  "positions": {
    "7203.T": {"quantity": 10.0, "avg_price": 2000.0}
  },
  "updated_at": "2026-05-24T10:00:00+00:00"
}
```

### PaperTrader API

```python
from execution.paper_trade import PaperTrader

trader = PaperTrader()        # 前回の状態を自動復元
trader.reset()                # 状態をリセット（テスト用）
print(trader.summary())       # 口座サマリー文字列

account = await trader.get_account()
# → {"balance": ..., "realized_pnl": ..., "return_pct": ...}
```

---

## 8. CLIモニタリングダッシュボード

```bash
# 一度表示
python3 scripts/dashboard.py

# 30秒ごとに自動更新
python3 scripts/dashboard.py --watch

# 更新間隔を変更（60秒）
python3 scripts/dashboard.py --watch --interval 60

# 最新N件のシグナルを表示
python3 scripts/dashboard.py --tail 20
```

**表示内容:**
- システム状態（SIGNAL_THRESHOLD / PAPER_TRADE / Redis 接続）
- 最新シグナル一覧（スコア・方向・銘柄）
- ペーパートレード損益サマリー（勝率・PF・総損益）
- ニュースソース別統計（棒グラフ付き）

---

## 9. VPS デプロイ

### 手動セットアップ（Ubuntu 22.04）

```bash
# VPS に SSH 接続後
bash deploy/setup_vps.sh
```

### GitHub Actions 自動デプロイ

1. GitHub Secrets に `VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY` を設定
2. GitHub Variables に `VPS_DEPLOY_ENABLED=true` を設定
3. `git push origin main` で自動デプロイ実行

### pm2 での運用

```bash
# pm2 設定ファイル
cat deploy/ecosystem.config.js

# pm2 起動
pm2 start deploy/ecosystem.config.js

# systemd 起動（pm2 不要の場合）
sudo systemctl enable newsalgo
sudo systemctl start newsalgo
```

---

## 10. IBKR 接続（Phase 3 準備）

```bash
pip install ib_insync                    # ライブラリインストール（0.9.86推奨）
python3 scripts/test_ibkr.py --check    # 要件確認
python3 scripts/test_ibkr.py --stub     # スタブ動作確認
python3 scripts/test_ibkr.py            # 実接続テスト（TWS 起動済みの場合）
python3 scripts/test_ibkr.py --order    # テスト発注（ペーパー口座のみ）
```

**TWS 設定:**
- File → Global Configuration → API → Settings
- Enable ActiveX and Socket Clients: ON
- Socket port: 7497（ペーパー） / 7496（本番）

**IBKRBroker 使い方:**

```python
from execution.ibkr import IBKRBroker

broker = IBKRBroker(paper=True)
await broker.connect()
result = await broker.submit_order(order)
await broker.disconnect()
```

- TWS 未起動時: 自動スタブモードで動作（実発注なし）

---

## 11. 既知の問題と対応状況

| 問題 | 状態 | 対応内容 |
|---|---|---|
| 日経・ロイター RSS が 404 / 認証エラー | ✅ 解決済 | NHK 経済・Yahoo Biz に差し替え |
| TDnet が JS レンダリング必要 | ✅ 解決済 | BeautifulSoup で HTML パース方式に変更 |
| LLM モデル名の誤り | ✅ 解決済 | `claude-sonnet-4-5` に修正 |
| LLM タイムアウト 3 秒が不足 | ✅ 解決済 | 8 秒に拡張 |
| `.env` が CWD 依存で読み込み失敗 | ✅ 解決済 | 絶対パスで読み込むよう修正 |
| Supabase 未接続 | ✅ 解決済 | anon key 取得・テーブル作成・書き込み確認済み |
| yfinance FutureWarning（Series→float） | ✅ 解決済 | `iloc[0]` 経由でスカラー変換 |
| Redis が未起動 | ✅ 解決済 | `docker compose up -d redis` で起動 |
| Slack/LINE アラート未実装 | ✅ 解決済 | `.env` に WEBHOOK URL/TOKEN を設定で自動送信 |
| asyncio.run() が既存ループで失敗 | ✅ 解決済 | `_run_coro()` で ThreadPoolExecutor 経由に切り替え |
| APScheduler ZoneInfoNotFoundError | ✅ 解決済 | `timezone=str(_JST)` → `timezone="Asia/Tokyo"` + tzdata |
| ペーパートレード状態がプロセス再起動で消える | ✅ 解決済 | JSON 永続化（`logs/paper_state.json`）追加 |
| テスト間でペーパートレード状態が干渉 | ✅ 解決済 | 各テスト冒頭で `trader.reset()` 呼び出し追加 |
| minkabu RSS 404 | ✅ 解決済 | 東洋経済オンライン RSS に差し替え |
| Yahoo 株式 RSS 404 | ✅ 解決済 | Investing.com JP RSS に差し替え |
| X (Twitter) API 未接続 | 📋 スタブ | APIキー取得後に `collectors/sns.py` を差し替え |

---

## 12. テスト

```bash
cd ~/newsalgo
python3 -m pytest tests/ -v
```

| テストファイル | テスト数 | 内容 |
|---|---|---|
| `tests/test_pipeline.py` | 20件 | パイプライン全体・各モジュール |
| `tests/test_backtest.py` | 5件 | バックテストエンジン |
| `tests/test_execution.py` | 2件 | RiskManager・PaperTrader |
| **合計** | **27件** | **全通過** |

---

## 13. コマンドリファレンス（全機能）

```bash
# テスト
python3 -m pytest tests/ -q

# バックテスト
python3 run_backtest.py --mode sample --hold 1
python3 run_backtest.py --mode jsonl --csv
python3 run_backtest.py --cost                # LLM コスト試算のみ

# 最適化
python3 run_optimize.py                       # hold × threshold グリッド探索
python3 run_optimize.py --mode jsonl

# LLM vs KW 精度比較分析
python3 run_analysis.py                       # コンソール出力
python3 run_analysis.py --html                # HTML レポートも出力

# ダッシュボード
python3 scripts/dashboard.py --watch          # リアルタイムモニタリング

# スケジューラー
python3 scheduler.py                          # 常時稼働
python3 scheduler.py --dry-run               # スケジュール確認
python3 scheduler.py --now                   # 即時1回実行

# アラートテスト
python3 scripts/test_alert.py
python3 scripts/test_alert.py --check

# IBKR テスト
python3 scripts/test_ibkr.py --check
python3 scripts/test_ibkr.py --stub

# Docker
docker compose up -d                          # フルスタック起動
docker compose run --rm backtest              # バックテスト
docker compose logs -f scheduler              # ログ確認

# Makefile ショートカット
make test / make backtest / make optimize / make run / make logs

# GitHub Secrets 登録
SLACK_WEBHOOK_URL=https://... LINE_NOTIFY_TOKEN=xxx bash scripts/add_github_secrets.sh
```

---

## 14. 更新履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| v1 | 2026-05-24 | 初版作成。基本パイプライン実装・テスト 20 件通過 |
| v2 | 2026-05-24 | Supabase 接続完了・GitHub Actions Secrets 登録・TDnet 市場時間対応 |
| v3 | 2026-05-24 | Phase 2 バックテストエンジン完成・テスト 27 件通過・yfinance 統合 |
| v4 | 2026-05-24 | TDnet 証券コード/企業名抽出・Slack/LINE アラート・Docker Compose Redis・実ログバックテスト |
| v5 | 2026-05-24 | Yahoo/みんかぶ RSS追加・hold_days最適化・LLMコスト試算・IBKRスタブ・Phase Bスケジューラー |
| v6 | 2026-05-24 | SIGNAL_THRESHOLD=0.7・RSS修正(東洋経済/Investing.com)・LLM実測・IBKR/VPSデプロイ整備・Makefile |
| v7 | 2026-05-24 | Dockerfile+docker-compose フルスタック・CD deploy.yml・run_analysis.py・dashboard.py・ペーパートレード JSON 永続化 |

---

## 15. 着手予定（次回）

- [ ] Slack/LINE: 実トークンを `.env` に設定して本番通知テスト
- [ ] Phase 3: IBKR ペーパートレード口座で実接続テスト（`python3 scripts/test_ibkr.py`）
- [ ] VPS デプロイ: `bash deploy/setup_vps.sh` を実サーバーで実行 or GitHub Secrets に VPS 情報設定
- [ ] バックテスト: 実 JSONL ログが蓄積されたら精度評価（`python3 run_backtest.py --mode jsonl`）
- [ ] ダッシュボード改善: unrealized PnL（現在価格からリアルタイム計算）
- [ ] LLM モードの本番適用検討（コスト vs 精度トレードオフ → 現状は KW モード推奨）
