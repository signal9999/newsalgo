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


def level_dot(level: str) -> str:
    colors = {"STRONG": "#ef4444", "MEDIUM": "#f59e0b"}
    c = colors.get(level, "#374151")
    label = {"STRONG": "STRONG", "MEDIUM": "MED"}.get(level, level)
    return (f'<span style="display:inline-flex;align-items:center;gap:5px;">'
            f'<span style="width:6px;height:6px;border-radius:50%;background:{c};'
            f'box-shadow:0 0 6px {c}88;"></span>'
            f'<span style="color:{c};font-size:0.78em;letter-spacing:0.08em;">{label}</span></span>')


def dir_chip(direction: str) -> str:
    if direction == "bullish":
        return '<span style="color:#10b981;font-size:0.85em;">↑ 強気</span>'
    elif direction == "bearish":
        return '<span style="color:#f87171;font-size:0.85em;">↓ 弱気</span>'
    return '<span style="color:#6b7280;font-size:0.85em;">— 中立</span>'


def generate_html(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    signals  = load_all_jsonl(_LOG / "signal")
    orders   = load_all_jsonl(_LOG / "order")
    news     = load_all_jsonl(_LOG / "news")
    state    = load_state()

    total_pnl = sum(o.get("pnl", 0) or 0 for o in orders)
    wins      = sum(1 for o in orders if (o.get("pnl") or 0) > 0)
    losses    = sum(1 for o in orders if (o.get("pnl") or 0) < 0)
    trades    = wins + losses
    win_rate  = wins / trades * 100 if trades > 0 else 0.0
    balance   = state.get("balance", 1_000_000)
    r_pnl     = state.get("realized_pnl", 0)
    positions = state.get("positions", {})
    ret_pct   = (balance - 1_000_000) / 1_000_000 * 100

    strong_signals = [s for s in signals if s.get("level") in ("STRONG", "MEDIUM")][-15:]

    src_count = defaultdict(int)
    for item in news:
        src_count[item.get("source", "unknown")] += 1
    src_top = sorted(src_count.items(), key=lambda x: -x[1])[:6]

    # ポジション行
    pos_rows = ""
    if positions:
        for sym, pos in positions.items():
            pos_rows += (f'<tr><td class="mono">{sym}</td>'
                         f'<td>{int(pos.get("quantity",0))}</td>'
                         f'<td class="mono">¥{pos.get("avg_price",0):,.0f}</td>'
                         f'<td class="dim">—</td><td class="dim">—</td></tr>')
    else:
        pos_rows = '<tr><td colspan="5" class="empty">No open positions</td></tr>'

    # シグナル行
    sig_rows = ""
    for s in reversed(strong_signals):
        ts   = str(s.get("timestamp",""))[:16].replace("T"," ")
        syms = ", ".join(s.get("affected_symbols",[])) or "—"
        sc   = s.get("score", 0)
        bar_w = int(sc * 60)
        sig_rows += f"""<tr>
          <td class="dim ts">{ts}</td>
          <td>{level_dot(s.get("level",""))}</td>
          <td>{dir_chip(s.get("direction",""))}</td>
          <td class="mono sym">{syms}</td>
          <td>
            <div style="display:flex;align-items:center;gap:6px;">
              <div style="width:60px;height:3px;background:#1f2937;border-radius:2px;">
                <div style="width:{bar_w}px;height:3px;background:#6366f1;border-radius:2px;"></div>
              </div>
              <span class="mono" style="font-size:0.8em;color:#9ca3af;">{sc:.2f}</span>
            </div>
          </td>
        </tr>"""
    if not sig_rows:
        sig_rows = '<tr><td colspan="5" class="empty">No signals yet</td></tr>'

    # ソースバー
    max_cnt  = src_top[0][1] if src_top else 1
    src_html = ""
    for src, cnt in src_top:
        pct = cnt / max_cnt * 100
        src_html += f"""
        <div class="src-row">
          <span class="src-name">{src}</span>
          <div class="src-track"><div class="src-fill" style="width:{pct:.0f}%"></div></div>
          <span class="src-cnt">{cnt}</span>
        </div>"""

    pnl_c  = "#10b981" if r_pnl  >= 0 else "#f87171"
    bal_c  = "#10b981" if balance >= 1_000_000 else "#f87171"
    ret_c  = "#10b981" if ret_pct >= 0 else "#f87171"
    psign  = "+" if r_pnl  >= 0 else ""
    rsign  = "+" if ret_pct >= 0 else ""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>NewsAlgo</title>
<style>
:root{{
  --bg:#080c14;--surface:#0e1420;--border:#1a2236;
  --text:#e2e8f0;--muted:#4b5563;--dim:#6b7280;
  --accent:#6366f1;--green:#10b981;--red:#f87171;--amber:#f59e0b;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif;
      background:var(--bg);color:var(--text);min-height:100vh;padding:24px 20px 40px}}
.header{{display:flex;align-items:baseline;justify-content:space-between;
         margin-bottom:32px;flex-wrap:wrap;gap:8px}}
.logo{{font-size:1.05em;font-weight:600;letter-spacing:0.15em;
       text-transform:uppercase;color:var(--accent)}}
.live{{display:flex;align-items:center;gap:6px;font-size:0.75em;color:var(--dim)}}
.pulse{{width:6px;height:6px;border-radius:50%;background:var(--green);
        animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
      gap:1px;background:var(--border);border:1px solid var(--border);
      border-radius:12px;overflow:hidden;margin-bottom:24px}}
.kpi-item{{background:var(--surface);padding:20px 18px}}
.kpi-label{{font-size:0.7em;letter-spacing:0.1em;text-transform:uppercase;
            color:var(--muted);margin-bottom:8px}}
.kpi-val{{font-size:1.55em;font-weight:700;line-height:1;letter-spacing:-0.02em}}
.kpi-sub{{font-size:0.72em;color:var(--dim);margin-top:5px}}
.block{{background:var(--surface);border:1px solid var(--border);
        border-radius:12px;padding:20px;margin-bottom:16px}}
.block-title{{font-size:0.7em;letter-spacing:0.12em;text-transform:uppercase;
              color:var(--muted);margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;font-size:0.84em}}
th{{color:var(--muted);text-align:left;padding:0 10px 10px;
    font-size:0.72em;letter-spacing:0.08em;text-transform:uppercase;font-weight:400}}
td{{padding:10px;border-top:1px solid var(--border);vertical-align:middle}}
tr:first-child td{{border-top:none}}
.mono{{font-family:'SF Mono',Monaco,monospace;font-size:0.9em}}
.dim{{color:var(--dim)}}
.ts{{font-size:0.78em;white-space:nowrap}}
.sym{{color:#a5b4fc}}
.empty{{text-align:center;color:var(--muted);padding:20px;font-size:0.83em}}
.src-row{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.src-name{{width:130px;font-size:0.8em;color:var(--dim);
           white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.src-track{{flex:1;height:2px;background:var(--border);border-radius:1px}}
.src-fill{{height:2px;background:var(--accent);border-radius:1px;
           transition:width .3s}}
.src-cnt{{width:36px;text-align:right;font-size:0.75em;color:var(--muted);
          font-family:'SF Mono',Monaco,monospace}}
.footer{{text-align:center;font-size:0.72em;color:var(--muted);
         letter-spacing:0.05em;margin-top:32px}}
@media(max-width:480px){{
  .kpi{{grid-template-columns:1fr 1fr}}
  .header{{margin-bottom:20px}}
}}
</style>
</head>
<body>

<div class="header">
  <div class="logo">NewsAlgo</div>
  <div class="live">
    <div class="pulse"></div>
    Paper Trading
  </div>
</div>

<div class="kpi">
  <div class="kpi-item">
    <div class="kpi-label">Balance</div>
    <div class="kpi-val" style="color:{bal_c}">¥{balance:,.0f}</div>
    <div class="kpi-sub">Initial ¥1,000,000</div>
  </div>
  <div class="kpi-item">
    <div class="kpi-label">Return</div>
    <div class="kpi-val" style="color:{ret_c}">{rsign}{ret_pct:.2f}%</div>
    <div class="kpi-sub">Realized {psign}¥{r_pnl:,.0f}</div>
  </div>
  <div class="kpi-item">
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-val">{win_rate:.1f}%</div>
    <div class="kpi-sub">{wins}W / {losses}L / {trades} trades</div>
  </div>
  <div class="kpi-item">
    <div class="kpi-label">News Collected</div>
    <div class="kpi-val">{len(news):,}</div>
    <div class="kpi-sub">{len(signals):,} signals generated</div>
  </div>
</div>

<div class="block">
  <div class="block-title">Open Positions</div>
  <table>
    <tr>
      <th>Symbol</th><th>Qty</th><th>Avg Cost</th><th>Last</th><th>Unrealized</th>
    </tr>
    {pos_rows}
  </table>
</div>

<div class="block">
  <div class="block-title">Recent Signals — Medium &amp; Strong</div>
  <table>
    <tr><th>Time</th><th>Level</th><th>Direction</th><th>Symbol</th><th>Score</th></tr>
    {sig_rows}
  </table>
</div>

<div class="block">
  <div class="block-title">News Sources</div>
  {src_html}
</div>

<div class="footer">Updated {now_jst()} &nbsp;·&nbsp; Auto-refresh every 5 min</div>

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
