# NewsAlgo ナレッジ文書 v9

> 最終更新: 2026-05-28 | 開発者: @signal9media

---

## 0. このプロジェクトの進め方

### 手動作業ゼロの原則

**「Claude Codeで全作業を行う」** が本プロジェクトの大原則。

| フェーズ | 自動化手段 | 人間の作業 |
|---|---|---|
| コード変更 | Claude Code で編集 | レビューのみ |
| テスト実行 | pytest（GitHub Actions 連携済み） | 失敗時の原因調査 |
| 本番デプロイ | `git push` → cron 自動 git pull | なし |
| 戦略レビュー | autonomous_review.py（毎朝07:30） | 判断のみ |
| 整合性監査 | 監査エージェント（毎週月曜09:00） | 修正作業 |

### Claude Code 起動コマンド

```bash
cd ~/newsalgo
claude
```

### 新しいチャットでの開始手順

1. Claude Code を起動
2. **このファイル（newsalgo_knowledge_v9.md）をアップロード**してから作業開始
3. 作業完了後は `git push` で Mixhost に自動反映（07:50 cron git pull）

---

## 1. 事業概要

### システム名：NewsAlgo

**ニュース駆動型自動売買システム（4戦略並列ペーパートレード中）**

```
[Collector] → [Credibility] → [Keyword] → [LLM] → [Signal]
  RSS/TDnet     信頼性評価     高速抽出    Claude    閾値判定
                                                        ↓
                                              [MultiOrchestrator]
                                              ├─ 戦略A: 速報反応型
                                              ├─ 戦略B: 精度重視型
                                              ├─ 戦略C: TDnetのみ
                                              └─ 戦略D: 逆張り型
                                                        ↓
                                              [Risk] → [PaperTrader]
                                              手数料・スリッページ込み
```

### ロードマップ

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 1 | パイプライン構築 + テスト27件 | ✅ 完了 |
| Phase 2 | バックテスト・Mixhost本番稼働 | ✅ 完了 |
| Phase 3 | マルチ戦略・IBKR接続・自律エージェント | ✅ 完了（2026-05-25）|
| Phase 4 | 戦略選定・VPS + IBKR本番移行 | 🔲 予定（勝率60%超えたら）|

---

## 2. インフラ構成

### Mixhost（本番サーバー）

| 項目 | 値 |
|---|---|
| ホスト | ik12002.mixhost.jp |
| ユーザー | jixxbvox |
| SSH鍵 | ~/.ssh/mixhost_jixxbvox |
| Python | 3.9.25 |
| 本番ディレクトリ | ~/newsalgo/ |
| Webダッシュボード | ~/public_html/newsalgo/index.html |

### Mixhost Crontab（JST・東証取引時間に最適化済み）

```cron
# メイン取引ループ（東証 08:00〜15:30）
0,30 8-14 * * 1-5  cd ~/newsalgo && timeout 1700 python3 main.py >> logs/cron.log 2>&1
0,30 15   * * 1-5  cd ~/newsalgo && timeout 1700 python3 main.py >> logs/cron.log 2>&1

# 自律戦略レビュー（毎朝07:30 取引前）
30 7 * * *         cd ~/newsalgo && python3 scripts/autonomous_review.py >> logs/strategy_review.log 2>&1

# Webダッシュボード生成（30分ごと）
*/30 * * * *       cd ~/newsalgo && python3 scripts/generate_web_dashboard.py >> logs/cron.log 2>&1

# コード自動更新（07:50 毎日）
50 7 * * *         cd ~/newsalgo && git pull origin main >> logs/cron.log 2>&1

# ログローテーション（16:00 取引終了後）
0 16 * * 1-5       find ~/newsalgo/logs -name "*.log" -size +10M -exec truncate -s 5M {} \;
```

### GitHub

| 項目 | 値 |
|---|---|
| リポジトリ | https://github.com/signal9999/newsalgo |
| デプロイフロー | git push → Mixhost cron git pull（07:50）|
| Workflows | newsalgo.yml / deploy.yml / strategy_review.yml |

### IBKR（Interactive Brokers）

| 項目 | 値 |
|---|---|
| アプリ | IB Gateway（Paper Trading）|
| ポート | 4002（IB Gatewayデフォルト）|
| 環境変数 | IBKR_HOST=127.0.0.1 / IBKR_PORT=4002 |
| 接続方式 | ib_insync + connectAsync（asyncio対応）|
| コントラクト | Stock(symbol, "SMART", "JPY") → primaryExch=TSEJ 自動設定 |
| 発注テスト | トヨタ7203×100株 ¥3,067 約定確認済み（2026-05-25）|
| 現状 | ペーパーアカウント稼働中（本番移行は戦略検証後）|

---

## 3. 戦略設定

### 4戦略並列運用（2026-05-25〜）

| ID | 名前 | min_score | 銘柄必須 | ソース | 方向 |
|---|---|---|---|---|---|
| **A** | 速報反応型 | 0.50 | 不要 | 全て | 順張り |
| **B** | 精度重視型 | 0.60 | 必須 | 全て | 順張り |
| **C** | TDnetのみ | 0.50 | 必須 | tdnetのみ | 順張り |
| **D** | 逆張り型 | 0.60 | 必須 | 全て | **逆張り** |

各戦略は独立した残高¥1,000,000・ログ・RiskManagerを持つ。

```
logs/
  strategy_a/signal/ order/ paper_state.json
  strategy_b/signal/ order/ paper_state.json
  strategy_c/signal/ order/ paper_state.json
  strategy_d/signal/ order/ paper_state.json
  news/   ← 共有
```

### シグナルスコア計算

```
score = credibility × llm_confidence × impact_score

score ≥ 0.8 → STRONG（発注）
score ≥ SIGNAL_THRESHOLD → MEDIUM（発注）
score < SIGNAL_THRESHOLD → NONE（スキップ）

現在の SIGNAL_THRESHOLD = 0.5（Mixhost .env）
スコア実績最大値: 0.606（2026-05-25時点）
```

### 取引コスト設定

```
COMMISSION_RATE = 0.0008  （0.08%、IBKRデフォルト）
COMMISSION_MIN  = 80      （最低¥80/注文）
スリッページ    = 0.1%    （成行注文時、buy:+0.1% / sell:-0.1%）

例：トヨタ100株（¥306,700）
  手数料: ¥245（往復¥490）
  スリッページ: ±¥307
```

---

## 4. 自律エージェントシステム

### 自動化レイヤー一覧

| レイヤー | ツール | 頻度 | 内容 |
|---|---|---|---|
| **Mixhost cron** | autonomous_review.py | 毎朝07:30 | 指標監視→閾値最適化→git push |
| **GitHub Actions** | strategy_review.yml | 毎日09:00/週次月曜 | 指標チェック→Slack通知 |
| **Claude Scheduled** | newsalgo-weekly-review | 毎週月曜08:00 | SSH接続→ログ分析→週次レポート |
| **Claude Scheduled** | newsalgo-system-audit | 毎週月曜09:00 | 14項目整合性監査→audit_report.md |

### autonomous_review.py の動作

```
指標確認（勝率/PF/DD/トレード数）
  ↓ 劣化検知（勝率<60% or PF<1.30 or DD>8%）
  ↓ グリッドサーチ（threshold: 0.5/0.6/0.65/0.7/0.75/0.8）
  ↓ 最適値で .env 更新
  ↓ git commit & push
  ↓ logs/strategy_log.jsonl に記録
```

### 週次監査チェックリスト（14項目）

**コスト・現実性**
- 手数料 buy/sell 両方反映
- スリッページ考慮
- 売買単位100株遵守
- 空売りコスト・規制

**リスク管理**
- 日次損失上限（DAILY_LOSS_LIMIT_PCT=10%）
- ポジションサイズ上限（MAX_POSITION_PCT=5%）
- 重複エントリー防止
- 流動性チェック

**データ品質**
- Lookahead bias なし
- ニュース重複処理防止

**戦略ロジック**
- 逆張り方向反転の正確性
- TDnetフィルター純粋性
- RiskManager独立性（クロス汚染なし）

---

## 5. .env 設定値一覧

```env
# 必須
ANTHROPIC_API_KEY=sk-ant-api03-...

# 取引設定
PAPER_TRADE=true
SIGNAL_THRESHOLD=0.5
MAX_POSITION_PCT=0.05
DAILY_LOSS_LIMIT_PCT=0.10

# 取引コスト
COMMISSION_RATE=0.0008
COMMISSION_MIN=80
IBKR_PORT=4002

# インフラ
REDIS_URL=redis://localhost:6379
SUPABASE_URL=https://ibpfemdqqnafnbqjkyfn.supabase.co
SUPABASE_KEY=eyJ...

# 通知（任意）
SLACK_WEBHOOK_URL=
LINE_NOTIFY_TOKEN=
```

---

## 6. 既知の残課題（次フェーズ）

### 🟡 近日対応

| 課題 | 内容 |
|---|---|
| ~~流動性チェック~~ | ~~出来高ベースの発注制限（小型株排除）~~ ✅ 2026-05-28 実装済 |
| 空売りポジション管理 | 戦略Dの逆張りを完全機能させる |
| ポジション累積上限 | 同銘柄への複数エントリー上限 |
| スリッページ動的計算 | 出来高に応じた可変スリッページ |

### 🔲 Phase 4（戦略検証完了後）

| 課題 | 内容 |
|---|---|
| Xserver VPS | IB Gateway常時起動環境の構築 |
| IBKR本番移行 | PAPER_TRADE=false + 資金入金 |
| 信用取引規制対応 | 日々公表銘柄・委託保証金率チェック |

---

## 7. 本番移行判断基準

以下を**2〜4週間のペーパートレードで達成**してから IBKR 本番移行：

| 指標 | 目標値 |
|---|---|
| 勝率 | ≥ 60% |
| Profit Factor | ≥ 1.30 |
| 最大 Drawdown | ≤ 8% |
| トレード数 | ≥ 30件（統計的有意性） |

---

## 8. 開発履歴サマリー

| 日付 | 主な実装 |
|---|---|
| 〜2026-05-23 | Phase 1-2: パイプライン・バックテスト・Mixhost本番稼働 |
| 2026-05-24 | 自律戦略レビュー・GHA・Scheduled Agent・Webダッシュボード |
| **2026-05-25** | **IBKR接続・4戦略並列・手数料/スリッページ・監査エージェント** |
| **2026-05-27** | **yfinance→Yahoo Finance JSON API置換・起動時ヘルスチェック追加** |
| **2026-05-28** | **TDnetコード抽出バグ修正・連続リジェクト検知・流動性フィルター実装** |

### 2026-05-25 の主要実装

1. **IBKR IB Gateway 完全接続**
   - connectAsync + SMART ルーティング
   - トヨタ7203×100株 ¥3,067 ペーパー約定確認

2. **4戦略マルチフレームワーク**
   - LLM分析1回共有 → 4戦略に並列分配
   - 独立PaperTrader/Logger/RiskManager

3. **取引コストの現実化**
   - 手数料: 0.08%（最低¥80）買い・売り両方
   - スリッページ: 0.1%（成行注文）
   - 成行fill_price=0バグ修正（現在値取得に変更）

4. **自律監査エージェント**
   - 毎週月曜09:00に14項目チェックリスト自動実行
   - 🔴重大/🟡警告/✅正常で分類・レポート出力

5. **Mixhostクロン時間修正**
   - 夜間（23:00〜06:30）→ 東証時間（08:00〜15:30）

### 2026-05-27〜28 のバグ修正（重要）

> ⚠️ これらは「静かに全注文がリジェクトされる」種類のバグ。ダッシュボードの残高が変わらないことで気づいた。

#### バグ1: yfinance が Mixhost で動かない（5/27修正）

- **原因**: yfinance → numpy → OpenBLAS がMixhostのスレッド数制限で import 失敗
- **症状**: 全注文 `status: "rejected" / reason: "price_unavailable"`
- **修正**: `execution/paper_trade.py` の `_fetch_price()` を `urllib` + Yahoo Finance JSON API に差し替え
- **教訓**: Mixhostで numpy 系ライブラリは使えない。純粋Python + 標準ライブラリで代替する。

```python
# 修正後（numpy不要）
url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=5) as resp:
    data = json.loads(resp.read())
price = float(data["chart"]["result"][0]["meta"].get("regularMarketPrice") or 0)
```

#### バグ2: TDnetの証券コードが取れない（5/28修正）

- **原因**: TDnetのHTMLは `kjCode` CSSクラスを使用し、コードが **5桁**（例: `39220`）
  - 旧コードの正規表現 `^\d{4}$` は4桁のみマッチ → 全件 `code: ""`
- **症状**: `affected_symbols: []` → `decision.py` でスキップ → 発注ゼロ
- **修正**: `collectors/tdnet.py` の `_extract_row()` をCSSクラスベースに書き替え
  - `kjCode` クラスのTDから取得、`digits[:4]` で4桁に正規化
- **教訓**: TDnetのHTMLはCSSクラスで列を識別する。正規表現パターンより CSS クラス（`kjTime/kjCode/kjName/kjTitle`）を使う。

```python
# TDnet の正しい抽出方法
for td in tds:
    classes = td.get("class", [])
    if "kjCode" in classes:
        digits = re.sub(r"\D", "", td.get_text(strip=True))
        code = digits[:4]  # 5桁 → 4桁に正規化
    elif "kjName" in classes:
        company = td.get_text(strip=True)
```

#### 追加した監視機能（再発防止）

| 機能 | 場所 | 動作 |
|---|---|---|
| 起動時ヘルスチェック | `main.py` | 7203.T / 9984.T の価格取得をテスト。取引時間中に失敗 → CRITICAL アラート＋exit(1) |
| 連続リジェクト検知 | `execution/paper_trade.py` | 5回連続 `price_unavailable` → CRITICAL アラート（5分間隔で再送） |
| シンボル優先順位 | `engine/multi_orchestrator.py` | TDnetコード（item）> LLM抽出 の順で使用・マージ |
