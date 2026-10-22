"""Row rendering: turn view_rows output into <details> HTML with no JavaScript."""
import base64
import html

import pandas as pd

from stockmonitor import config

UP, DOWN, MUTED = "#00a86b", "#e5484d", "#8994a7"
MINUS = "−"
RETURNS = [("1D", "R1D"), ("1W", "R1W"), ("1M", "R1M"), ("3M", "R3M"),
           ("6M", "R6M"), ("1Y", "R1Y"), ("3Y", "R3Y")]
INDEX_LABEL = {"US": "S&P 500", "IN": "NIFTY 500"}
CURRENCY = {"US": "$", "IN": "₹"}

STYLES = """<style>
.sm-card{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0e1726;font-size:13px;background:#fff;border-radius:14px;border:1px solid #e3e7ed;padding:2px 14px}
.sm-row{border-bottom:1px solid #f1f3f6}
.sm-row:last-child{border-bottom:none}
.sm-row summary{list-style:none;display:flex;align-items:center;padding:10px 0;cursor:pointer}
.sm-row summary::-webkit-details-marker{display:none}
.sm-row summary:hover{background:#fafbfc}
.sm-chev{width:16px;flex:none;color:#b4bccb;font-size:11px;transition:transform .15s}
.sm-row[open] .sm-chev{transform:rotate(90deg);color:#00a86b}
.sm-id{flex:1;min-width:0}
.sm-id b{font-weight:700}
.sm-when{font-size:11px;color:#8994a7;white-space:nowrap}
.sm-sub{font-size:11px;color:#8994a7;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sm-spark{flex:none;margin:0 6px}
.sm-key{width:62px;flex:none;text-align:right}
.sm-right{width:78px;flex:none;text-align:right}
.sm-num{width:56px;flex:none;text-align:right}
.sm-up{color:#00a86b}
.sm-dn{color:#e5484d}
.sm-panel{padding:4px 0 14px 16px}
.sm-rets{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-bottom:10px}
.sm-ret{background:#f7f8fa;border-radius:10px;padding:7px 4px;text-align:center}
.sm-ret .sm-k{font-size:10px;color:#8994a7}
.sm-ret .sm-v{font-size:13px;font-weight:700}
.sm-range{margin:10px 0 2px}
.sm-bar{position:relative;height:6px;background:#e9edf2;border-radius:6px}
.sm-dot{position:absolute;top:-4px;width:14px;height:14px;border-radius:50%;background:#00a86b;border:2px solid #fff;box-shadow:0 0 0 1px #00a86b;transform:translateX(-50%)}
.sm-rl{display:flex;justify-content:space-between;font-size:10px;color:#8994a7;margin-top:4px}
.sm-listed{font-size:10px;color:#8994a7;margin-top:2px}
.sm-facts{display:flex;gap:16px;font-size:11px;color:#5b6577;flex-wrap:wrap;margin-top:8px}
.sm-facts b{color:#0e1726}
.sm-empty{font-family:Inter,system-ui,sans-serif;color:#8994a7;font-size:13px;text-align:center;padding:24px 0;background:#fff;border:1px solid #e3e7ed;border-radius:14px}
@media (max-width:480px){
.sm-rets{grid-template-columns:repeat(4,1fr)}
.sm-panel{padding-left:8px}
.sm-key{width:54px}
.sm-right{width:70px}
.sm-num{width:48px}
}
</style>"""


def _nan(v) -> bool:
    return v is None or bool(pd.isna(v))


def _group_indian(n: int) -> str:
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + s


def fmt_mcap(v: float, market: str) -> str:
    if _nan(v):
        return "—"
    if market == "IN":
        return f"₹{_group_indian(int(round(v / 1e7)))} Cr"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.0f}B"
    return f"${v / 1e6:.0f}M"


def fmt_pct(v: float, signed: bool = True) -> str:
    if _nan(v):
        return "—"
    text = f"{abs(v):.1f}%"
    if round(v, 1) == 0:
        return text
    if v < 0:
        return MINUS + text
    return "+" + text if signed else text


def fmt_of_high(from_high: float) -> str:
    """Price as a % of the 52-week high, from its % distance below it (−15 → 85.0%)."""
    return "—" if _nan(from_high) else f"{100.0 + from_high:.1f}%"


def fmt_price(v: float, market: str) -> str:
    if _nan(v):
        return "—"
    whole, frac = f"{v:.2f}".split(".")
    whole = _group_indian(int(whole)) if market == "IN" else f"{int(whole):,}"
    return f"{CURRENCY[market]}{whole}.{frac}"


def sparkline_svg(points: list[float], width: int = 64, height: int = 20,
                  color: str | None = None) -> str:
    if not points:
        return ""
    if color is None:
        color = UP if points[-1] >= points[0] else DOWN
    lo, hi = min(points), max(points)
    span = (hi - lo) or 1.0
    pad = 2
    n = len(points)
    coords = []
    for i, p in enumerate(points):
        x = width * i / (n - 1) if n > 1 else width / 2
        y = height - pad - (p - lo) / span * (height - 2 * pad) if hi != lo else height / 2
        coords.append(f"{x:.1f},{y:.1f}")
    return (f'<svg class="sm-spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{" ".join(coords)}"/></svg>')


def _spark_img(svg: str, width: int = 64, height: int = 20) -> str:
    """st.html strips inline <svg> (DOMPurify HTML profile), so embed it as an image."""
    if not svg:
        return ""
    svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return (f'<img class="sm-spark" src="data:image/svg+xml;base64,{b64}" '
            f'width="{width}" height="{height}" alt="">')


def _tone(v) -> str:
    if _nan(v) or round(v, 1) == 0:
        return ""
    return "sm-up" if v > 0 else "sm-dn"


def _range_pos(price, low, high) -> float:
    if _nan(price) or _nan(low) or _nan(high) or high <= low:
        return 0.0
    return min(100.0, max(0.0, (price - low) / (high - low) * 100.0))


def _row(r, view: str, market: str, session) -> str:
    e = html.escape
    mc = fmt_mcap(r["MarketCap"], market)
    name = e(str(r["Name"]))
    sub = f"{name} · {e(mc)}"
    when = ""
    spark_pts = list(r["Spark"]) if isinstance(r["Spark"], (list, tuple)) else []
    if view == "fallen":
        spark = _spark_img(sparkline_svg(spark_pts, color=MUTED))
        key = f'<span class="sm-key">{fmt_of_high(r["FromHigh52"])}</span>'
        right = "".join(f'<span class="sm-num {_tone(r[c])}">{fmt_pct(r[c])}</span>'
                        for c in ("R1W", "R1M"))
    else:
        spark = _spark_img(sparkline_svg(spark_pts[-config.SPARK_SHORT:]))
        shown = fmt_pct(r["FromATH"], signed=False) if view == "ath" else fmt_of_high(r["FromHigh52"])
        key = f'<span class="sm-key">{shown}</span>'
        right = (f'<div class="sm-right">{e(fmt_price(r["Price"], market))}'
                 f'<div class="sm-sub {_tone(r["R1W"])}">{fmt_pct(r["R1W"])} 1W</div></div>')

    tiles = "".join(
        f'<div class="sm-ret"><div class="sm-k">{label}</div>'
        f'<div class="sm-v {_tone(r[col])}">{fmt_pct(r[col])}</div></div>'
        for label, col in RETURNS)
    pos = _range_pos(r["Price"], r["Low52"], r["High52"])
    listed = ""
    if not _nan(r["ListedDate"]):
        d = pd.Timestamp(r["ListedDate"])
        text = f'Listed {d.strftime("%b")} {d.day}, {d.year}'
        listed = f'<div class="sm-listed">{text}</div>'
        # A short history explains a high; say so without opening the row.
        when += f'<div class="sm-when">{text}</div>'
    facts = [f'<span>Price <b>{e(fmt_price(r["Price"], market))}</b></span>',
             f'<span>All-time high <b>{e(fmt_price(r["ATH"], market))}</b></span>',
             f'<span>Market cap <b>{e(mc)}</b></span>']
    if not _nan(r["InIndex"]) and bool(r["InIndex"]):
        facts.append(f"<span>In <b>{e(INDEX_LABEL[market])}</b></span>")

    return (
        '<details class="sm-row"><summary><span class="sm-chev">▶</span>'
        f'<div class="sm-id"><b>{e(str(r["Ticker"]))}</b><div class="sm-sub">{sub}</div>{when}</div>'
        f"{spark}{key}{right}</summary>"
        f'<div class="sm-panel"><div class="sm-rets">{tiles}</div>'
        f'<div class="sm-range"><div class="sm-bar"><div class="sm-dot" style="left:{pos:.1f}%"></div></div>'
        f'<div class="sm-rl"><span>52w low {e(fmt_price(r["Low52"], market))}</span>'
        f'<span>52w high {e(fmt_price(r["High52"], market))}</span></div></div>'
        f'{listed}<div class="sm-facts">{"".join(facts)}</div></div></details>')


# The list's columns per view: (label, sort column or None, width class).
# app.py draws these as the sortable header; the widths match the row cells.
HEADERS = {
    "pth": [("Stock", "Ticker", "sm-h-id"), ("1M trend", None, "sm-h-spark"),
            ("% of 52w high", "FromHigh52", "sm-key"), ("Price · 1W", "R1W", "sm-right")],
    "fallen": [("Stock", "Ticker", "sm-h-id"), ("3M trend", None, "sm-h-spark"),
               ("% of 52w high", "FromHigh52", "sm-key"), ("5D", "R1W", "sm-num"),
               ("1M", "R1M", "sm-num")],
    "ath": [("Stock", "Ticker", "sm-h-id"), ("1M trend", None, "sm-h-spark"),
            ("From ATH", "FromATH", "sm-key"), ("Price · 1W", "R1W", "sm-right")],
}

# Width of each header cell, desktop and phone, matching the row CSS above
# (the trend cell is the 64px image plus 6px margins either side).
HEADER_WIDTHS = {"sm-h-spark": (76, 76), "sm-key": (62, 54), "sm-right": (78, 70),
                 "sm-num": (56, 48)}


def rows_html(df: pd.DataFrame, view: str, market: str, session: pd.Timestamp | None) -> str:
    if df.empty:
        return '<div class="sm-empty">No stocks match right now.</div>'
    rows = "".join(_row(r, view, market, session) for _, r in df.iterrows())
    return f'<div class="sm-card">{rows}</div>'
