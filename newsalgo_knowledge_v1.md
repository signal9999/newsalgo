# NewsAlgo ナレッジ文書 v1

> 最終更新: 2025-05-24 | 開発者: @signal9media

---

## 0. このプロジェクトの進め方（手動作業ゼロの原則）

### 基本方針

**「Claude Codeで全作業を行う」** が本プロジェクトの大原則です。
コードの生成・修正・テスト・デプロイのすべてを Claude Code 経由で実施し、
ターミナルを直接操作する場面を最小化します。

### 自動化の全体像

| フェーズ | 自動化手段 | 人間の作業 |
|---|---|---|
| コード変更 | Claude Code で編集 | レビューのみ |
| テスト実行 | pytest（GitHub Actions 連携後は自動） | 失敗時の原因調査 |
| 本番デプロイ | `git push` → GitHub Actions が自動実行 | なし |
| ログ保存 | Supabase REST API へ自動送信 | なし |
| 障害アラート | Slack / LINE Notify で自動通知 | 対応判断のみ |
| 重複排除 | Redis（未起動時はインメモリ set） | なし |

### 手動で行う作業（現時点）

以下の2点のみ手動設定が必要です。それ以外はすべて Claude Code が担います。

1. **APIキー設定** — `.env` に各サービスのキーを記載する
   - `ANTHROPIC_API_KEY`（Claude API）
   - `SUPABASE_URL` / `SUPABASE_ANON_KEY`
   - `X_BEARER_TOKEN`（X API、取得後）
   - Slack / LINE の Webhook URL（通知設定時）
2. **Supabase テーブル作成** — `create_tables.sql` を Supabase SQL Editor で1回実行する

### 守るべきルール

- `.env` は絶対に Git にコミットしない（`.gitignore` 登録済み）
- ロジック変更後は必ず `pytest tests/` を実行してからコミットする
- 本番移行前に paper_trade モードで1週間以上の動作確認を行う

---

## 1. 事業概要

### システムの目的

**NewsAlgo** は、ニュース・SNS・企業開示情報をリアルタイムに取得し、
Claude API による自然言語解析を通じてマーケットへのインパクトを判断し、
自動発注まで一気通貫で実行するニュース駆動型自動売買システムです。

### ビジネスロジックの流れ

```
情報収集 → フィルタリング → LLM解析 → シグナルスコア → 取引判断 → 発注
  (Collector)  (Keyword)     (Claude)    (Signal)        (Decision)  (Broker)
```

1. **情報収集**（collectors/）: RSS・TDnet・X API・経済指標カレンダーから非同期並列取得
2. **キーワードフィルター**（analyzers/keyword.py）: 10ms 以内で不要ニュースを除外
3. **LLM 解析**（analyzers/llm.py）: Claude によるセンチメント分析（タイムアウト 8 秒）
4. **シグナルスコアリング**（analyzers/signal.py）: 三積スコアで総合判断値を算出
5. **取引判断**（engine/decision.py）: スコア閾値・リスク上限・クールダウン時間を評価
6. **発注**（execution/）: ペーパートレード または 実ブローカー API に送信

### 稼働ロードマップ

| フェーズ | 内容 | 条件 |
|---|---|---|
| Phase 1（現在） | ペーパートレード・パイプライン検証 | Redis なし・Supabase なし |
| Phase 2 | Supabase 接続・GitHub Actions CI | `.env` 設定完了 |
| Phase 3 | TDnet・X API 本番連携 | API キー取得完了 |
| Phase 4 | バックテスト実装 | Phase 3 安定稼働後 |
| Phase 5 | 実口座発注（小ロット） | Phase 4 で有意なシグナル確認後 |

### ペーパートレードの設定

- 初期残高: **100万円**
- 最大日次損失上限: 設定ファイルで管理（`execution/risk.py`）
- 発注後クールダウン: **60秒**

---

## 2. 技術スタック

### コア依存ライブラリ

| 役割 | ライブラリ | バージョン |
|---|---|---|
| 非同期 HTTP | aiohttp | 3.x |
| RSS パース | feedparser | 6.x |
| HTML スクレイピング | BeautifulSoup4 | 4.x |
| LLM | anthropic SDK | 0.25+ |
| LLM モデル | claude-sonnet-4-5 | — |
| キャッシュ・重複排除 | Redis（未起動時はインメモリ set） | 5.x |
| ログ | JSONL（構造化ログ） | — |
| テスト | pytest + pytest-asyncio | 8.x + 0.23+ |
| 環境変数 | python-dotenv | — |
| 将来予定 | Supabase（REST API） | — |
| CI/CD | GitHub Actions | — |

### Python バージョン

| 環境 | バージョン |
|---|---|
| ローカル（現在） | 3.9.6 |
| 本番要件 | 3.11 以上推奨 |

### LLM 呼び出し仕様

- モデル: `claude-sonnet-4-5`
- タイムアウト: 8 秒（以前の 3 秒から拡張済み）
- 用途: センチメント分析（ポジティブ / ネガティブ / ニュートラル + 強度スコア）

### Redis の動作モード

| 状態 | 動作 |
|---|---|
| 起動中 | Redis に重複排除キーを保存（TTL 付き） |
| 未起動（現在） | インメモリ `set` でフォールバック。プロセス再起動で消える |

> **本番では Redis 起動が必須です。** インメモリモードはプロセス終了時に重複排除履歴が消えます。

---

## 3. ディレクトリ構成

```
~/newsalgo/
├── collectors/
│   ├── __init__.py
│   ├── tdnet.py          # TDnet適時開示（BeautifulSoupでHTMLスクレイピング）
│   ├── rss.py            # NHK・Yahoo Biz RSS（動作確認済み）
│   ├── sns.py            # X API スタブ（APIキー取得後に実装）
│   ├── macro.py          # 経済指標カレンダー スタブ
│   └── credibility.py    # 信頼性スコアリング
├── analyzers/
│   ├── __init__.py
│   ├── keyword.py        # キーワードフィルター（10ms以内）
│   ├── llm.py            # Claude API センチメント分析（タイムアウト8秒）
│   └── signal.py         # シグナルスコアリング（三積スコア）
├── engine/
│   ├── __init__.py
│   ├── decision.py       # 取引判断エンジン
│   └── orchestrator.py   # asyncioパイプライン（最大10並列）
├── execution/
│   ├── __init__.py
│   ├── risk.py           # リスク管理（日次損失上限・60秒クールダウン）
│   ├── broker.py         # ブローカー抽象クラス
│   └── paper_trade.py    # ペーパートレード（初期残高100万円）
├── monitor/
│   ├── __init__.py
│   ├── logger.py         # JSONL構造化ログ
│   ├── alert.py          # コンソール + Slack/LINE（設定時のみ）
│   └── supabase_logger.py # Supabase REST API（フォールバックあり）
├── config/
│   ├── __init__.py
│   └── settings.py       # .env 読み込み
├── .github/
│   └── workflows/
│       └── newsalgo.yml  # GitHub Actions（リポジトリ作成後に有効化）
├── tests/
│   ├── test_collectors.py
│   ├── test_analyzers.py
│   └── test_execution.py
├── logs/                  # 実行時に自動生成
│   └── {type}/
│       └── YYYYMMDD.jsonl
├── create_tables.sql      # Supabase DDL（SQL Editorで1回実行）
├── .env                   # 実環境（gitignore対象）
├── .env.example           # 設定項目テンプレート
├── requirements.txt
├── main.py                # エントリポイント
├── run_check.py           # 動作確認スクリプト
└── newsalgo_knowledge_v1.md  # このファイル
```

### 各モジュールの役割メモ

- `orchestrator.py`: 最大 10 並列で collectors を非同期実行し、パイプライン全体を統制する
- `credibility.py`: ソース別の信頼性スコアを付与し、シグナル計算に利用する
- `supabase_logger.py`: Supabase 未接続時はローカル JSONL にフォールバックして動作継続する

---

## 4. 環境情報

### ローカル開発環境

| 項目 | 内容 |
|---|---|
| OS | macOS |
| Python | 3.9.6 |
| 作業ディレクトリ | `~/newsalgo/` |
| Redis | 未起動（インメモリ fallback 動作中） |

### 外部サービス接続状況

| サービス | 状態 | 有効化手順 |
|---|---|---|
| Anthropic Claude API | 接続済み | `.env` に `ANTHROPIC_API_KEY` 設定済み |
| Supabase | 未接続 | `.env` に `SUPABASE_URL` / `SUPABASE_ANON_KEY` を設定後、`create_tables.sql` を実行 |
| GitHub Actions | 設定済み・未有効化 | GitHubリポジトリ作成後に自動有効化 |
| X（Twitter）API | スタブ実装 | `X_BEARER_TOKEN` 取得後に `sns.py` を実装 |
| Redis | 未起動 | `brew install redis && brew services start redis`（ローカル） |

### .env.example の主要設定項目

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_ANON_KEY=
X_BEARER_TOKEN=
SLACK_WEBHOOK_URL=
LINE_NOTIFY_TOKEN=
```

---

## 5. 動作確認済みニュースソース一覧

確認日: 2025-05-24

| ソースID | URL | 取得件数/回 | 信頼性スコア | 実装方式 | 状態 |
|---|---|---|---|---|---|
| nhk_top | https://www3.nhk.or.jp/rss/news/cat0.xml | 約 7 件 | 0.70 | RSS (feedparser) | 動作確認済み |
| nhk_economy | https://www3.nhk.or.jp/rss/news/cat6.xml | 約 120 件 | 0.75 | RSS (feedparser) | 動作確認済み |
| yahoo_biz | https://news.yahoo.co.jp/rss/topics/business.xml | 約 8 件 | 0.65 | RSS (feedparser) | 動作確認済み |
| tdnet | https://www.release.tdnet.info/ | 未確認 | 0.90 | HTML スクレイピング（BeautifulSoup） | 実装中 |

### 差し替え経緯

- 日経・ロイター RSS → **404 のため削除**。NHK 経済・Yahoo Biz に差し替え済み
- TDnet RSS → **RSS 自体が存在しないため**、BeautifulSoup による HTML スクレイピングに変更

### 信頼性スコアの考え方

| スコア範囲 | 意味 |
|---|---|
| 0.85 以上 | 一次情報・公式開示（TDnet など） |
| 0.70〜0.84 | 大手メディア（NHK 等） |
| 0.60〜0.69 | キュレーション系（Yahoo Biz 等） |
| 0.60 未満 | SNS・未検証情報（現時点では採用なし） |

---

## 6. 既知の問題と対応状況

| # | 問題 | 状態 | 対応内容 |
|---|---|---|---|
| 1 | TDnet RSS が存在しない | 解決済み | BeautifulSoup で HTML スクレイピングに変更 |
| 2 | 日経・ロイター RSS が 404 | 解決済み | NHK 経済・Yahoo Biz に差し替え |
| 3 | LLM モデル名の誤り | 解決済み | `claude-sonnet-4-5` に修正 |
| 4 | LLM タイムアウト 3 秒が不足 | 解決済み | 8 秒に拡張 |
| 5 | Supabase 未接続 | 実装済・未接続 | `.env` に URL/KEY を設定すれば即時有効化 |
| 6 | TDnet 本番取得の動作未確認 | 実装中 | HTML 構造調査・テスト中 |
| 7 | GitHub Actions 未有効化 | 設計済み | リポジトリ作成後に有効化 |
| 8 | X API 未接続 | スタブ実装 | API キー取得後に `sns.py` に差し替え |
| 9 | Redis が未起動 | 暫定動作中 | インメモリ fallback で動作。本番では Redis 起動必須 |

### 対応優先度（次のアクション）

1. TDnet HTML 構造の確認と本番取得テスト（高）
2. Supabase テーブル作成・接続確認（中）
3. GitHub リポジトリ作成と Actions 有効化（中）
4. Redis のローカル起動（低・本番前に必須）

---

## 7. 更新履歴

| バージョン | 日付 | 内容 |
|---|---|---|
| v1 | 2025-05-24 | 初版作成。基本パイプライン実装・テスト 20 件通過 |

---

## 8. 着手予定（次回）

### 優先順位付きタスク一覧

#### 高優先度

- [ ] **TDnet 取得の本番確認**
  - `collectors/tdnet.py` の HTML スクレイピングロジックを実際のページで検証
  - 取得件数・フィールドマッピングの確認
  - テストケース追加（`tests/test_collectors.py`）

#### 中優先度

- [ ] **Supabase 接続とテーブル作成**
  - `create_tables.sql` を Supabase SQL Editor で実行
  - `.env` に `SUPABASE_URL` / `SUPABASE_ANON_KEY` を設定
  - `monitor/supabase_logger.py` の接続確認

- [ ] **GitHub リポジトリ作成と Actions 有効化**
  - プライベートリポジトリを作成し `git push`
  - `.github/workflows/newsalgo.yml` が自動実行されることを確認
  - Secrets に `ANTHROPIC_API_KEY` 等を登録

#### 低優先度（Phase 3 以降）

- [ ] **追加ニュースソースの統合**
  - Yahoo Finance RSS
  - 株探（Kabutan）RSS
  - 各ソースの信頼性スコア設定

- [ ] **バックテスト機能の追加**
  - 過去ログ（JSONL）を入力として疑似シグナル評価
  - シグナル → 発注の精度指標（適合率・再現率）の計算

- [ ] **X（Twitter）API 接続**
  - `X_BEARER_TOKEN` 取得後に `collectors/sns.py` のスタブを実装に置き換え
  - ストリーミング API vs. 検索 API の選択

- [ ] **Redis 本番起動**
  - ローカル: `brew services start redis`
  - 本番サーバー: Docker コンテナまたはマネージドサービスの検討

---

*このファイルは Claude Code によって自動生成・管理されます。手動編集の際は「更新履歴」セクションを更新してください。*
