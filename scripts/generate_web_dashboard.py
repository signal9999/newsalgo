#!/usr/bin/env python3
"""
NewsAlgo Web ダッシュボード生成スクリプト
logs/ の JSONL ファイルを読み込み、HTML を生成して public_html/newsalgo/ に出力する。

使い方:
  python3 scripts/generate_web_dashboard.py
  python3 scripts/generate_web_dashboard.py --out /path/to/output/dir
"""
import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

_ROOT   = Path(__file__).parent.parent
_JST    = timezone(timedelta(hours=9))
_LOG    = _ROOT / "logs"
_STATE  = _LOG / "paper_state.json"


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
                    except Exception:
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


def load_state() -> dict:
    if not _STATE.exists():
        return {}
    try:
        with open(_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def level_badge(level: str) -> str:
    colors = {"STRONG": "#ff4444", "MEDIUM": "#ffaa00", "NONE": "#555"}
    c = colors.get(level, "#555")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.8em;">{level}</span>'


def dir_badge(direction: str) -> str:
    if direction == "bullish":
        return '<span style="color:#4caf50;">▲ 強気</span>'
    elif direction == "bearish":
        return '<span style="color:#f44336;">▼ 弱気</span>'
    return '<span style="color:#888;">→ 中立</span>'


def generate_html(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # データ読み込み
    signals = load_all_jsonl(_LOG / "signal")
    orders  = load_all_jsonl(_LOG / "order")
    news    = load_all_jsonl(_LOG / "news")
    state   = load_state()

    # 損益計算
    total_pnl = sum(o.get("pnl", 0) or 0 for o in orders)
    wins   = sum(1 for o in orders if (o.get("pnl") or 0) > 0)
    losses = sum(1 for o in orders if (o.get("pnl") or 0) < 0)
    trades = wins + losses
    win_rate = wins / trades * 100 if trades > 0 else 0.0
    balance  = state.get("balance", 1_000_000)
    r_pnl    = state.get("realized_pnl", 0)
    positions = state.get("positions", {})

    # シグナル（強いもの上位20件）
    strong_signals = [s for s in signals if s.get("level") in ("STRONG", "MEDIUM")][-20:]

    # ソース別統計
    src_count = defaultdict(int)
    for item in news:
        src_count[item.get("source", "unknown")] += 1
    src_top = sorted(src_count.items(), key=lambda x: -x[1])[:8]

    # ポジション行
    pos_rows = ""
    if positions:
        for sym, pos in positions.items():
            pos_rows += f"""
            <tr>
              <td>{sym}</td>
              <td>{int(pos.get('quantity', 0))}</td>
              <td>¥{pos.get('avg_price', 0):,.0f}</td>
              <td>-</td>
              <td>-</td>
            </tr>"""
    else:
        pos_rows = '<tr><td colspan="5" style="text-align:center;color:#666;">ポジションなし</td></tr>'

    # シグナル行
    sig_rows = ""
    for s in reversed(strong_signals):
        ts   = str(s.get("timestamp", ""))[:16].replace("T", " ")
        lvl  = level_badge(s.get("level", ""))
        dr   = dir_badge(s.get("direction", ""))
        syms = ", ".join(s.get("affected_symbols", [])) or "—"
        sc   = s.get("score", 0)
        sig_rows += f"""
        <tr>
          <td style="color:#888;font-size:0.85em;">{ts}</td>
          <td>{lvl}</td>
          <td>{dr}</td>
          <td>{syms}</td>
          <td>{sc:.2f}</td>
        </tr>"""
    if not sig_rows:
        sig_rows = '<tr><td colspan="5" style="text-align:center;color:#666;">シグナルなし</td></tr>'

    # ソース統計バー
    max_cnt = src_top[0][1] if src_top else 1
    src_html = ""
    for src, cnt in src_top:
        pct = cnt / max_cnt * 100
        src_html += f"""
        <div style="margin:6px 0;">
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="width:140px;font-size:0.85em;color:#ccc;">{src}</span>
            <div style="flex:1;background:#222;border-radius:4px;height:14px;">
              <div style="width:{pct:.0f}%;background:#4a9eff;border-radius:4px;height:14px;"></div>
            </div>
            <span style="width:50px;text-align:right;font-size:0.85em;color:#aaa;">{cnt}件</span>
          </div>
        </div>"""

    pnl_color  = "#4caf50" if total_pnl >= 0 else "#f44336"
    sign       = "+" if total_pnl >= 0 else ""
    bal_color  = "#4caf50" if balance >= 1_000_000 else "#f44336"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="300">
<title>NewsAlgo Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #0d1117; color: #e6edf3; padding: 16px; }}
  h1 {{ color: #58a6ff; font-size: 1.4em; margin-bottom: 4px; }}
  .subtitle {{ color: #8b949e; font-size: 0.85em; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; }}
  .card h3 {{ color: #8b949e; font-size: 0.78em; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }}
  .card .val {{ font-size: 1.6em; font-weight: bold; }}
  .card .sub {{ color: #8b949e; font-size: 0.82em; margin-top: 4px; }}
  .section {{ background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 16px; margin-bottom: 16px; }}
  .section h2 {{ color: #58a6ff; font-size: 1em; margin-bottom: 12px; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; }}
  th {{ color: #8b949e; text-align: left; padding: 6px 8px; border-bottom: 1px solid #30363d; font-weight: normal; }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #21262d; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1c2128; }}
  .updated {{ color: #555; font-size: 0.78em; text-align: right; margin-top: 16px; }}
  @media (max-width: 500px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} }}
</style>
</head>
<body>

<h1>📊 NewsAlgo Dashboard</h1>
<div class="subtitle">ニュース駆動型自動売買システム — ペーパートレードモード</div>

<!-- KPI カード -->
<div class="grid">
  <div class="card">
    <h3>残高</h3>
    <div class="val" style="color:{bal_color};">¥{balance:,.0f}</div>
    <div class="sub">初期: ¥1,000,000</div>
  </div>
  <div class="card">
    <h3>実現損益</h3>
    <div class="val" style="color:{pnl_color};">{sign}¥{r_pnl:,.0f}</div>
    <div class="sub">累計</div>
  </div>
  <div class="card">
    <h3>勝率</h3>
    <div class="val">{win_rate:.1f}%</div>
    <div class="sub">勝:{wins} / 負:{losses} / 計:{trades}件</div>
  </div>
  <div class="card">
    <h3>ニュース取得数</h3>
    <div class="val">{len(news):,}</div>
    <div class="sub">シグナル: {len(signals):,}件</div>
  </div>
</div>

<!-- オープンポジション -->
<div class="section">
  <h2>📈 オープンポジション</h2>
  <table>
    <tr><th>銘柄</th><th>数量</th><th>平均取得単価</th><th>現在値</th><th>含損益</th></tr>
    {pos_rows}
  </table>
</div>

<!-- 最新シグナル -->
<div class="section">
  <h2>⚡ 最新シグナル（MEDIUM以上 直近20件）</h2>
  <table>
    <tr><th>日時</th><th>レベル</th><th>方向</th><th>銘柄</th><th>スコア</th></tr>
    {sig_rows}
  </table>
</div>

<!-- ソース統計 -->
<div class="section">
  <h2>📰 ニュースソース別取得数</h2>
  {src_html}
</div>

<div class="updated">最終更新: {now_jst()} （5分ごとに自動更新）</div>

</body>
</html>"""

    out_path = out_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ ダッシュボード生成完了: {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=None, help="出力ディレクトリ")
    args = p.parse_args()

    if args.out:
        out_dir = Path(args.out)
    else:
        # デフォルト: public_html/newsalgo/（Mixhost 想定）
        out_dir = Path.home() / "public_html" / "newsalgo"

    generate_html(out_dir)


if __name__ == "__main__":
    main()
