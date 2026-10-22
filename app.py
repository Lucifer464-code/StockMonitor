"""Stock Monitor: stocks near their highs, and fallen stocks that have stopped falling."""
import html
import traceback

import streamlit as st

from stockmonitor import config
from ui import data
from ui import render

MARKETS = {"US": "US", "India": "IN"}
MARKET_NAME = {"US": "US", "IN": "India"}
ALL = "All"
TILES = [
    ("pth", "Near 52w high", "PTH · within 5%"),
    ("ath", "All-time high", "ATH · within 5%"),
    ("fallen", "Fallen, stabilising", "down 80–90%"),
]

PAGE_CSS = """<style>
.stApp{background:#f7f8fa}
[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
#MainMenu,footer{display:none !important}
.block-container,[data-testid="stMainBlockContainer"]{padding-top:1.5rem;padding-bottom:3rem;max-width:760px}
html,body,.stApp{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#0e1726}
.sm-head{display:flex;justify-content:space-between;align-items:center;font-family:Inter,system-ui,sans-serif}
.sm-title{font-weight:800;font-size:22px;color:#0e1726;letter-spacing:-.01em}
.sm-pill{font-size:12px;color:#00a86b;background:#e7f7ef;padding:4px 10px;border-radius:999px;white-space:nowrap}
.sm-pill.sm-off{color:#8994a7;background:#eceff3}
.st-key-controls [data-testid="stHorizontalBlock"]{flex-wrap:nowrap;align-items:center;gap:8px}
.st-key-controls [data-testid="stColumn"]{min-width:0 !important;width:auto !important;flex:1 1 0 !important}
.st-key-controls [data-testid="stColumn"]:last-child{display:flex;justify-content:flex-end}
.st-key-controls [data-testid="stColumn"]:last-child>div{max-width:170px;width:100%}
.st-key-market [role="radiogroup"]{background:#eceff3;border-radius:10px;padding:3px;gap:0;width:fit-content}
.st-key-market button{background:transparent !important;border:none !important;border-radius:8px !important;
  color:#8994a7 !important;min-height:0;padding:4px 14px;box-shadow:none !important}
.st-key-market button:hover{color:#0e1726 !important}
.st-key-market button[aria-checked="true"]{background:#fff !important;color:#0e1726 !important;
  font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.08) !important}
.st-key-market button *{color:inherit !important}
.st-key-market button p{font-size:14px}
.st-key-controls [data-testid="stSelectbox"] [role="group"]{background:#fff !important;
  border:1px solid #e3e7ed !important;border-radius:10px !important}
.st-key-controls [data-testid="stSelectbox"] input{background:transparent !important}
.st-key-tiles [data-testid="stHorizontalBlock"]{flex-wrap:nowrap;gap:8px}
.st-key-tiles [data-testid="stColumn"]{min-width:0 !important;width:auto !important;flex:1 1 0 !important}
[class*="st-key-tile_"] button{width:100%;height:auto;min-height:0;display:block;text-align:left;
  background:#fff;color:#0e1726;border:1px solid #e3e7ed;border-radius:14px;padding:10px 12px;box-shadow:none}
[class*="st-key-tile_"] button:hover{border-color:#00a86b;color:#0e1726;background:#fff}
[class*="st-key-tile_"] button:focus:not(:active){border-color:#e3e7ed;color:#0e1726;box-shadow:none}
[class*="st-key-tile_"] button>div,[class*="st-key-tile_"] button>div>span{justify-content:flex-start;width:100%}
[class*="st-key-tile_"] button [data-testid="stMarkdownContainer"]{text-align:left;width:100%}
[class*="st-key-tile_"] button p{margin:0;font-size:12px;color:#8994a7;line-height:1.3;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[class*="st-key-tile_"] button p strong{display:block;font-size:28px;font-weight:800;line-height:1.15;color:#0e1726}
@media (max-width:480px){
.block-container,[data-testid="stMainBlockContainer"]{padding-left:12px;padding-right:12px;padding-top:1rem}
[class*="st-key-tile_"] button{padding:8px 9px}
[class*="st-key-tile_"] button p{font-size:10px}
[class*="st-key-tile_"] button p strong{font-size:22px}
}
</style>"""


def _selected_css(view: str) -> str:
    sel = f".st-key-tile_{view} button"
    return (f"<style>{sel},{sel}:hover,{sel}:focus:not(:active){{background:#00a86b;"
            f"border-color:#00a86b;color:#fff}}{sel} p,{sel} p strong{{color:#fff;opacity:.9}}"
            f"{sel} p strong{{opacity:1}}</style>")


def _keep_market():
    """A segmented control can be cleared; put the last choice back."""
    if st.session_state["market"] is None:
        st.session_state["market"] = st.session_state["_market_last"]
    st.session_state["_market_last"] = st.session_state["market"]


def _set_view(view: str):
    st.session_state["view"] = view


def _pill(md) -> str:
    if md is None:
        return '<span class="sm-pill sm-off">No data</span>'
    if md.session is not None:
        text = f"Close · {md.session.strftime('%b')} {md.session.day}"
    else:
        text = md.price_label
    return f'<span class="sm-pill">● {html.escape(text)}</span>'


st.set_page_config(page_title="Stock Monitor", page_icon="📈", layout="centered")
st.session_state.setdefault("view", "pth")
st.session_state.setdefault("market", next(iter(MARKETS)))
st.session_state.setdefault("_market_last", st.session_state["market"])

header = st.empty()

with st.container(key="controls"):
    left, right = st.columns(2)
    with left:
        choice = st.segmented_control("Market", list(MARKETS), key="market",
                                      on_change=_keep_market, label_visibility="collapsed")
market = MARKETS[choice or st.session_state["_market_last"]]

try:
    md = data.load_market(market)
except Exception:
    traceback.print_exc()
    md = None
# A tab whose label or counts can't be read is unavailable, not a quiet market.
usable = (md is not None and md.session is not None and md.universe > 0 and md.counts_ok)

with right:
    index_name = render.INDEX_LABEL[market]
    options = [ALL, index_name] if md is not None and md.index_ok else [ALL]
    index_choice = st.selectbox("Index", options, key=f"index_{market}",
                                label_visibility="collapsed")
index_only = index_choice != ALL

view = st.session_state["view"]
st.html(render.STYLES + PAGE_CSS + _selected_css(view))
header.html(f'<div class="sm-head"><div class="sm-title">Highs &amp; Lows</div>{_pill(md)}</div>')

if md is not None and not md.index_ok:
    st.caption(f"The {index_name} list is unavailable right now, so all stocks are shown.")

counts = data.view_counts(md, index_only) if usable else {v: 0 for v, _, _ in TILES}

with st.container(key="tiles"):
    for col, (key, title, caption) in zip(st.columns(3), TILES):
        with col, st.container(key=f"tile_{key}"):
            st.button(f"{title}\n\n**{counts[key]}**\n\n{caption}", key=f"btn_{key}",
                      on_click=_set_view, args=(key,), width="stretch")

if md is None:
    st.info(f"Data for {MARKET_NAME[market]} isn't available yet.")
elif not usable:
    st.warning(f"Data for {MARKET_NAME[market]} isn't available yet.")
else:
    expected = max(md.expected, md.universe)
    if md.priced / expected < config.COVERAGE_WARN:
        pct = round(100 * md.priced / expected)
        st.warning(f"Only {pct}% of {MARKET_NAME[market]} stocks could be priced in the last "
                   "update — lists may be incomplete.")
    st.html(render.rows_html(data.view_rows(md, view, index_only), view, market, md.session))
