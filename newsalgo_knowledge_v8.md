# NewsAlgo ナレッジ文書 v8

> 最終更新: 2026-05-24 | 開発者: @signal9media

---

## 0. このプロジェクトの進め方

### 手動作業ゼロの原則

**「Claude Codeで全作業を行う」** が本プロジェクトの大原則。

| フェーズ | 自動化手段 | 人間の作業 |
|---|---|---|
| コード変更 | Claude Code で編集 | レビューのみ |
| テスト実行 | pytest（GitHub Actions 連携済み） | 失敗時の原因調査 |
| 本番デプロイ | `git push` → cron 自動 git pull | なし |
| ログ保存 | Supabase REST API へ自動送信 | なし |
| 障害アラート | Slack Webhook（設定任意） | 対応判断のみ |

### Claude Code 起動コマンド

```bash
cd ~/newsalgo
claude
```

### 新しいチャットでの開始手順

1. Claude Code を起動
2. **このファイル（newsalgo_knowledge_v8.md）をアップロード**してから作業開始
3. 作業完了後は `git push` で Mixhost に自動反映（cron git pull）

---

## 1. 事業概要

### システム名：NewsAlgo

**ニュース駆動型自動売買システム**

```
[Collector] → [Credibility] → [Keyword] → [LLM] → [Signal] → [Risk] → [Execution]
  RSS/TDnet     信頼性評価     高速抽出    Claude    閾値判定   リスク管理  ペーパー発注
```

### ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 1 | パイプライン構築・ペーパートレード | ✅ 完了 |
| Phase 2 | バックテスト・精度検証 | ✅ 完了 |
| Phase 2.5 | Docker化・CD・分析ツール・Mixhost 本番稼働 | ✅ 完了 |
| Phase 3 | ブローカーAPI接続・小額実口座 | 📋 計画中（TWS 起動待ち） |
| Phase 4 | リスク管理強化・複数銘柄対応 | 📋 計画中 |
| Phase 5 | 本格運用 | 📋 計画中 |

### GitHub

**https://github.com/signal9999/newsalgo**

---

## 2. 技術スタック

| カテゴリ | 技術 | バージョン |
|---|---|---|
| 言語 | Python | 3.11+（Mixhost は 3.9.25） |
| LLM | Claude API（claude-sonnet-4-5） | anthropic>=0.25 |
| RSS取得 | aiohttp + feedparser | >=3.9 / >=6.0 |
| HTMLパース | BeautifulSoup4 | >=4.12 |
| DB | Supabase（REST API） | — |
| キャッシュ | Redis（Docker Compose 化済み） | >=5.0 |
| 株価取得 | yfinance（.T サフィックス、60秒キャッシュ） | >=0.2 |
| スケジューラー | APScheduler 3.11.2 | timezone="Asia/Tokyo" |
| 本番環境 | Mixhost 共有サーバー + cron | Python 3.9.25 |
| コンテナ（ローカル） | Docker + docker-compose | Python 3.11-slim |
| CI/CD | GitHub Actions（test→build） | — |
| テスト | pytest + pytest-asyncio | >=8.0 / >=0.23 |

### LLM 呼び出し仕様

- モデル: `claude-sonnet-4-5`
- タイムアウト: 8秒
- 出力形式: JSON（sentiment / confidence / impact_score / event_type / affected_symbols）
- エラー時: sentiment=neutral, confidence=0.0 でフォールバック
- **本番: KW モード（LLM なし）推奨 → コスト $0、精度同等**

---

## 3. Supabase テーブル構成

**プロジェクト URL:** `https://ibpfemdqqnafnbqjkyfn.supabase.co`

| テーブル | 内容 | 主なカラム |
|---|---|---|
| `news_log` | 取得した全ニュース | item_id, title, source, credibility, is_reliable, timestamp |
| `signal_log` | シグナルが出たもの（NONE はスキップ） | score, level, direction, affected_symbols |
| `order_log` | ペーパートレード発注記録 | order_id, symbol, side, quantity, fill_price, status |

---

## 4. GitHub Actions

**リポジトリ:** `github.com/signal9999/newsalgo`

### newsalgo.yml（定期実行）

| 時刻 (JST) | UTC cron | 内容 |
|---|---|---|
| 08:00 | `0 23 * * *` | `python main.py` |
| 08:30 | `30 23 * * *` | 同上 |
| 手動 | `workflow_dispatch` | テスト実行用 |

### deploy.yml（CD）

`git push main` で自動トリガー: test → build (GHCR) → deploy (SSH VPS, 未設定) → notify (Slack)

### 登録済み Secrets

| Secret 名 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー |
| `SUPABASE_URL` | Supabase URL |
| `SUPABASE_KEY` | Supabase anon key |
| `VPS_HOST` / `VPS_USER` / `VPS_SSH_KEY` | 未設定（deploy スキップ中） |
| `SLACK_WEBHOOK_URL` | 任意（未設定） |

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

**合計: 約 168 件/回（TDnet除く）— Mixhost で実動作確認済み**

---

## 5b. Mixhost 本番サーバー

### 接続情報

| 項目 | 値 |
|---|---|
| ホスト | `ik12002.mixhost.jp` |
| SSH ユーザー | `jixxbvox` |
| SSH キー | `~/.ssh/mixhost_jixxbvox` |
| SSH 設定名 | `mixhost-signal9`（~/.ssh/config） |
| Python | 3.9.25 |
| ディレクトリ | `/home/jixxbvox/newsalgo/` |

```bash
# ローカルから接続
ssh mixhost-signal9

# ログ確認
ssh mixhost-signal9 tail -f ~/newsalgo/logs/cron.log
ssh mixhost-signal9 ls -la ~/newsalgo/logs/signal/
```

### cron 設定（稼働中）

平日 08:00〜15:30 JST に 30 分ごとに `main.py` を実行。毎朝 git pull で自動コード更新。

```
# 08:00, 08:30 JST (Sun-Thu 23:xx UTC)
0,30 23 * * 0-4  cd ~/newsalgo && timeout 1700 python3 main.py >> logs/cron.log 2>&1

# 09:00-15:30 JST (Mon-Fri 00:00-06:30 UTC)
0,30 0-5 * * 1-5 cd ~/newsalgo && timeout 1700 python3 main.py >> logs/cron.log 2>&1
0,30 6 * * 1-5   cd ~/newsalgo && timeout 1700 python3 main.py >> logs/cron.log 2>&1

# ログローテーション (JST 07:45)
45 22 * * 1-5 find ~/newsalgo/logs -name "cron.log" -size +10M -exec truncate -s 5M {} \;

# git pull 自動更新 (JST 07:50) — git push だけで本番反映
50 22 * * * cd ~/newsalgo && git pull origin main >> logs/cron.log 2>&1
```

### コード更新フロー

```
ローカルで git push origin main
   ↓ 毎朝 07:50 JST に自動
Mixhost が git pull origin main
   ↓ 次の cron 実行（08:00 JST）から新コードで動作
```

### 動作確認済み（2026-05-24）

```
RSS取得: 168件
news log: 20260524.jsonl（404件）
signal log: 20260524.jsonl（315件）
```

---

## 5c. ローカル Docker 起動方法

```bash
cd ~/newsalgo

# フルスタック（Redis + スケジューラー）
docker compose up -d

# Redis のみ
docker compose up -d redis

# ログ確認
docker compose logs -f scheduler

# バックテスト
docker compose run --rm backtest

docker compose down
```

---

## 5d. アラート通知設定

> ⚠️ **LINE Notify は 2025年3月31日にサービス終了**。利用不可。
> 現状はコンソール出力のみで運用中。

Slack を使う場合: https://api.slack.com/apps → Incoming Webhooks → `.env` の `SLACK_WEBHOOK_URL=` に設定

---

## 6. バックテストシステム

```bash
python3 run_backtest.py --mode sample --hold 1      # サンプル
python3 run_backtest.py --mode jsonl --hold 1       # 実ログ（ログ蓄積後）
python3 run_analysis.py                              # KW vs LLM 比較
python3 run_analysis.py --html                       # HTML レポート出力
python3 run_optimize.py                              # hold × threshold 最適化
```

### 最適化結果（サンプルデータ）

| hold | threshold | 勝率 | PF | 判定 |
|---|---|---|---|---|
| 1日 | 0.7 | 66.7% | 2.28 | **BEST** |

**推奨: hold_days=1, SIGNAL_THRESHOLD=0.7, use_llm=False**

### 実 JSONL バックテスト結果（2026-05-24）

```
総トレード数: 5件 / 勝率: 60.0% / 総損益: ¥883 / PF: 1.56
```

---

## 7. ペーパートレード

### 状態永続化

`logs/paper_state.json` に残高・ポジション・実現損益を保存。プロセス再起動後も継続。

### unrealized PnL

`get_position()` / `get_account()` が yfinance で現在値を取得し含損益を計算（TTL 60秒キャッシュ）。

```python
account = await trader.get_account()
# → {"balance": ..., "realized_pnl": ..., "unrealized_pnl": ..., "total": ..., "return_pct": ...}
```

---

## 8. CLIモニタリングダッシュボード

```bash
python3 scripts/dashboard.py           # 一度表示
python3 scripts/dashboard.py --watch   # 30秒自動更新
python3 scripts/dashboard.py --tail 20
```

**表示内容:** システム状態 / 最新シグナル / オープンポジション＋含損益（yfinance リアルタイム）/ P&L サマリー / ソース別統計

---

## 9. IBKR 接続（Phase 3 準備）

```bash
python3 scripts/test_ibkr.py --check   # 要件確認
python3 scripts/test_ibkr.py --stub    # スタブ OK 確認済み
python3 scripts/test_ibkr.py           # 実接続（TWS 起動後）
```

- TWS 未起動時: 自動スタブモード（発注シミュレーション）
- ポート: 7497（ペーパー）/ 7496（本番）

---

## 10. 既知の問題と対応状況

| 問題 | 状態 | 対応内容 |
|---|---|---|
| 日経・ロイター RSS 404 | ✅ 解決済 | NHK 経済・Yahoo Biz に差し替え |
| TDnet JS レンダリング | ✅ 解決済 | BeautifulSoup HTML パース |
| LLM タイムアウト不足 | ✅ 解決済 | 8 秒に拡張 |
| Supabase 未接続 | ✅ 解決済 | anon key 設定・テーブル作成済み |
| yfinance FutureWarning | ✅ 解決済 | `iloc[0]` 経由でスカラー変換 |
| Redis 未起動 | ✅ 解決済 | Docker / メモリキャッシュ代替 |
| APScheduler ZoneInfoNotFoundError | ✅ 解決済 | `timezone="Asia/Tokyo"` + tzdata |
| ペーパートレード状態消失 | ✅ 解決済 | JSON 永続化 |
| unrealized PnL がゼロ固定 | ✅ 解決済 | yfinance リアルタイム取得（60秒キャッシュ） |
| minkabu / Yahoo 株式 RSS 404 | ✅ 解決済 | 東洋経済・Investing.com に差し替え |
| LINE Notify サービス終了 | ✅ 対応済 | 現状は通知なし運用（Slack は設定可） |
| VPS に SSH キーなし | ✅ 解決済 | Mixhost に HTTPS clone + cron で本番稼働 |
| X (Twitter) API 未接続 | 📋 スタブ | API キー取得後に差し替え |
| IBKR TWS 未起動 | 📋 保留 | TWS 起動時に実接続テスト |

---

## 11. テスト

```bash
python3 -m pytest tests/ -q   # → 27件全通過
```

| ファイル | 件数 | 内容 |
|---|---|---|
| `tests/test_pipeline.py` | 20件 | パイプライン全体 |
| `tests/test_backtest.py` | 5件 | バックテストエンジン |
| `tests/test_execution.py` | 2件 | RiskManager・PaperTrader |

---

## 12. コマンドリファレンス

```bash
# テスト
python3 -m pytest tests/ -q

# バックテスト / 分析
python3 run_backtest.py --mode jsonl
python3 run_analysis.py --html
python3 run_optimize.py

# ダッシュボード
python3 scripts/dashboard.py --watch

# ローカルスケジューラー
python3 scheduler.py --now      # 即時1回
python3 scheduler.py            # 常時稼働

# Docker（ローカル）
docker compose up -d
docker compose logs -f scheduler

# Mixhost ログ確認
ssh mixhost-signal9 tail -f ~/newsalgo/logs/cron.log
ssh mixhost-signal9 tail -20 ~/newsalgo/logs/signal/$(date +%Y%m%d).jsonl

# Makefile
make test / make backtest / make optimize / make run / make logs
```

---

## 13. 更新履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| v1 | 2026-05-24 | 初版。基本パイプライン・テスト 20 件 |
| v2 | 2026-05-24 | Supabase・GitHub Actions・TDnet 市場時間対応 |
| v3 | 2026-05-24 | バックテストエンジン・テスト 27 件・yfinance |
| v4 | 2026-05-24 | TDnet 証券コード抽出・Slack/LINE・Docker Redis |
| v5 | 2026-05-24 | RSS追加・最適化・LLMコスト・IBKRスタブ・スケジューラー |
| v6 | 2026-05-24 | SIGNAL_THRESHOLD=0.7・RSS修正・LLM実測・Makefile |
| v7 | 2026-05-24 | Dockerfile/CD・run_analysis.py・dashboard.py・永続化 |
| v8 | 2026-05-24 | Mixhost 本番稼働（cron + git pull）・unrealized PnL・バックテスト実ログ評価 |

---

## 14. Web ダッシュボード

**URL: https://signal9media.net/newsalgo/**

`scripts/generate_web_dashboard.py` が JSONL ログから HTML を生成。cron で 30 分ごとに自動更新。

**表示内容:** Balance / Return / Win Rate / News 件数 / Open Positions / Recent Signals / News Sources

**デザイン:** Inter + JetBrains Mono / 深黒 `#05080f` / インディゴアクセント / 4列 KPI グリッド / glow パルスアニメーション

```bash
# 手動再生成
python3 scripts/generate_web_dashboard.py

# ローカル確認用
python3 scripts/generate_web_dashboard.py --out /tmp/dash
```

---

## 15. 着手予定（次回）

- [ ] Phase 3: IBKR IB Gateway でログイン → 実接続テスト（口座承認翌日以降）
- [ ] バックテスト: Mixhost のログが蓄積したら精度評価（`python3 run_backtest.py --mode jsonl`）
- [ ] 通知: Slack Webhook URL を `.env` に設定（任意）
- [ ] LLM モード: KW と精度差が出たときに本番適用検討
