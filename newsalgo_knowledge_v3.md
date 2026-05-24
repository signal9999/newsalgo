# NewsAlgo ナレッジ文書 v3

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
| 障害アラート | コンソール出力（Slack/LINE は設定時のみ） | 対応判断のみ |

### Claude Code 起動コマンド

```bash
cd ~/newsalgo
claude
```

### 新しいチャットでの開始手順

1. Claude Code を起動（上記コマンド）
2. **このファイル（newsalgo_knowledge_v3.md）をアップロード**してから作業開始
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
| キャッシュ | Redis（未起動時はメモリset） | >=5.0 |
| 株価取得 | yfinance（.T サフィックス） | >=0.2 |
| CI/CD | GitHub Actions | — |
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

### Supabase 接続確認

```bash
cd ~/newsalgo && python3 -c "
import sys, asyncio
sys.path.insert(0, '.')
from monitor.supabase_logger import SupabaseLogger
async def t():
    sl = SupabaseLogger()
    print('Mode:', 'supabase' if sl.use_supabase else 'jsonl_fallback')
asyncio.run(t())
"
```

---

## 4. GitHub Actions スケジュール

**リポジトリ:** `github.com/signal9999/newsalgo`

### スケジュール

| 時刻 (JST) | UTC cron | 内容 |
|---|---|---|
| 08:00 | `0 23 * * *` | `python main.py` を 30 分実行 |
| 08:30 | `30 23 * * *` | 同上 |
| 手動 | `workflow_dispatch` | テスト実行用 |

### 登録済み Secrets

| Secret 名 | 内容 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API キー |
| `SUPABASE_URL` | `https://ibpfemdqqnafnbqjkyfn.supabase.co` |
| `SUPABASE_KEY` | Supabase anon key（JWT） |

### ログ保存

実行後の `logs/` ディレクトリを artifact として 7 日間保持。

---

## 5. 動作確認済みニュースソース

| ソース | URL | 件数/回 | 信頼性スコア | 状態 |
|---|---|---|---|---|
| NHK 総合 | `https://www3.nhk.or.jp/rss/news/cat0.xml` | 約 7 件 | 0.70 | ✅ |
| NHK 経済 | `https://www3.nhk.or.jp/rss/news/cat6.xml` | 約 120 件 | 0.75 | ✅ |
| Yahoo Biz | `https://news.yahoo.co.jp/rss/topics/business.xml` | 約 8 件 | 0.65 | ✅ |
| TDnet 適時開示 | HTMLスクレイピング（平日 08:00〜15:35 JST） | 数件〜数十件 | 0.90 | ✅ |

**合計: 約 135 件/回（TDnet除く）**

### TDnet ポーリング仕様

- URL: `https://www.release.tdnet.info/inbs/I_list_001_{YYYYMMDD}.html`
- 当日 + 前日の 2 日分を並列取得
- **平日 08:00〜15:35 JST のみ動作**（土日・時間外はスキップ）
- 重複排除: Redis TTL 300 秒 / 未起動時はメモリ set

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
```

### CLIオプション

| オプション | デフォルト | 内容 |
|---|---|---|
| `--mode` | `sample` | `sample`（デモデータ）or `jsonl`（実ログ） |
| `--hold` | `1` | 保有日数（1〜30） |
| `--threshold` | `0.3` | シグナルスコア閾値 |
| `--csv` | off | CSV 出力フラグ |
| `--output` | `backtest_result.csv` | CSV ファイルパス |
| `--llm` | off | LLM 解析を使用（API コスト注意） |

### 算出指標

| 指標 | 説明 |
|---|---|
| 勝率 | 利益トレード / 総トレード |
| 総損益 | 全トレードのP&L合計（円） |
| 平均勝ち/負け% | 勝ちトレードの平均リターン |
| プロフィットファクター | 総利益 / 総損失 |
| 最大ドローダウン | 累積損益の最大下落率 |
| シャープレシオ | リターン / 標準偏差（年換算なし） |
| STRONG/MEDIUM別勝率 | シグナルレベル別の勝率 |
| ソース別勝率 | ニュースソース別の勝率 |

### デモ結果（2025-05-20〜24、5銘柄、hold=1）

```
総トレード数:     5 件
勝率:             60.0%  (勝: 3 / 負: 2)
総損益:           ¥2,712  (+0.27%)
平均勝ち:         +2.42%
平均負け:         -0.91%
プロフィットファクター: 3.96
最大ドローダウン: -0.07%
シャープレシオ:   8.60
```

### 設計メモ

- `BacktestRunner(use_llm=False)`: LLM をスキップしてキーワード解析のみ → API コスト節約
- `signal_threshold=0.3`: ペーパートレード本番より低め（テスト用）
- yfinance キャッシュ: モジュールレベル `_price_cache` で銘柄ごとに2年分をキャッシュ
- 土日・祝日の価格欠損: 直近の過去営業日終値にフォールバック
- yfinance FutureWarning 対応: `float(x.iloc[0]) if hasattr(x, "iloc") else float(x)`

---

## 7. 既知の問題と対応状況

| 問題 | 状態 | 対応内容 |
|---|---|---|
| 日経・ロイター RSS が 404 / 認証エラー | ✅ 解決済 | NHK 経済・Yahoo Biz に差し替え |
| TDnet が JS レンダリング必要 | ✅ 解決済 | BeautifulSoup で HTML パース方式に変更 |
| LLM モデル名の誤り | ✅ 解決済 | `claude-sonnet-4-5` に修正 |
| LLM タイムアウト 3 秒が不足 | ✅ 解決済 | 8 秒に拡張 |
| LLM が Markdown コードブロックで返却 | ✅ 解決済 | レスポンス正規化ロジック追加 |
| `.env` が CWD 依存で読み込み失敗 | ✅ 解決済 | 絶対パスで読み込むよう修正 |
| Supabase 未接続 | ✅ 解決済 | anon key 取得・テーブル作成・書き込み確認済み |
| yfinance FutureWarning（Series→float） | ✅ 解決済 | `iloc[0]` 経由でスカラー変換 |
| Redis が未起動 | ⚠️ 動作中 | メモリ set でフォールバック。本番は Redis 必須 |
| X (Twitter) API 未接続 | 📋 スタブ | APIキー取得後に `collectors/sns.py` を差し替え |

---

## 8. テスト

```bash
cd ~/newsalgo
python3 -m pytest tests/ -v
```

| テストファイル | テスト数 | 内容 |
|---|---|---|
| `tests/test_pipeline.py` | 20件 | パイプライン全体・各モジュール |
| `tests/test_backtest.py` | 7件 | バックテストエンジン |
| **合計** | **27件** | **全通過** |

### test_backtest.py の内容

- `test_metrics_empty`: 空トレードでゼロ返却
- `test_metrics_basic`: 基本指標計算の正確性
- `test_simulator_buy`: 買いエントリー・クローズ
- `test_simulator_close`: P&L 計算の正確性
- `test_simulator_bearish`: 空売りエントリー
- `test_load_sample_news`: サンプルニュース10件読み込み
- `test_runner_with_sample`: Runner エンドツーエンド（価格取得モック）

---

## 9. 更新履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| v1 | 2026-05-24 | 初版作成。基本パイプライン実装・テスト 20 件通過 |
| v2 | 2026-05-24 | Supabase 接続完了・GitHub Actions Secrets 登録・TDnet 市場時間対応 |
| v3 | 2026-05-24 | Phase 2 バックテストエンジン完成・テスト 27 件通過・yfinance 統合 |

---

## 10. 着手予定（次回）

- [ ] TDnet スクレイピング精度向上（企業名・証券コード抽出の改善）
- [ ] ブローカー API 選定（Interactive Brokers 候補）
- [ ] アラート通知（LINE または Slack）
- [ ] Yahoo Finance / 株探 RSS 追加
- [ ] Redis 本番起動（Docker Compose 化）
- [ ] バックテスト: LLM モード検証（`--llm` フラグ使用）
- [ ] バックテスト: 実 JSONL ログでの勝率検証
- [ ] Python 自前オーケストレーターへの移行（Phase B）
