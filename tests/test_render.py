import pandas as pd

from stockmonitor import config
from ui.render import STYLES, fmt_mcap, fmt_pct, rows_html, sparkline_svg

SESSION = pd.Timestamp("2026-10-16")


def _df(**kw):
    base = dict(
        Ticker="AAA", Name="Alpha Corp", MarketCap=130e9, Price=125.0, High52=150.0,
        Low52=50.0, Low52Date=pd.Timestamp("2026-09-28"), ATH=160.0, FromHigh52=-85.0,
        FromATH=-3.0, OffLow52=25.0, R1D=0.7, R1W=1.1, R1M=-7.9, R3M=7.6, R6M=30.7,
        R1Y=34.0, R3Y=90.2, InIndex=True, IsPTH=True, IsATH=True, IsFallen=True,
        Spark=[float(i) for i in range(63)], ListedDate=pd.NaT,
    )
    base.update(kw)
    return pd.DataFrame([base], columns=config.COLUMNS)


def test_empty_state():
    out = rows_html(_df().iloc[0:0], "fallen", "US", SESSION)
    assert "No stocks match right now." in out


def test_names_escaped():
    out = rows_html(_df(Name="AT&T <Inc>"), "pth", "US", SESSION)
    assert "AT&amp;T &lt;Inc&gt;" in out
    assert "<Inc>" not in out


def test_listed_note_rendered():
    out = rows_html(_df(ListedDate=pd.Timestamp("2026-03-02")), "pth", "US", SESSION)
    assert "Listed Mar 2, 2026" in out
    assert "Listed" not in rows_html(_df(), "pth", "US", SESSION)


def test_range_bar_position():
    assert "left:75.0%" in rows_html(_df(), "pth", "US", SESSION)
    assert "left:100.0%" in rows_html(_df(Price=999.0), "pth", "US", SESSION)
    assert "left:0.0%" in rows_html(_df(Price=1.0), "pth", "US", SESSION)


def test_returns_strip_has_seven():
    assert rows_html(_df(), "pth", "US", SESSION).count('class="sm-ret"') == 7


def test_fallen_key_columns():
    out = rows_html(_df(), "fallen", "US", SESSION)
    assert "−85.0%" in out and "+25.0%" in out
    assert "low 18 days ago" in out
    assert "low 18 days ago" not in rows_html(_df(), "fallen", "US", None)


def test_fmt_mcap():
    assert fmt_mcap(4.97e12, "US") == "$4.97T"
    assert fmt_mcap(130e9, "US") == "$130B"
    assert fmt_mcap(950e6, "US") == "$950M"
    assert fmt_mcap(1.23456e12, "IN") == "₹1,23,456 Cr"


def test_fmt_pct():
    assert fmt_pct(1.14) == "+1.1%"
    assert fmt_pct(-0.4) == "−0.4%"
    assert fmt_pct(float("nan")) == "—"
    assert fmt_pct(3.0, signed=False) == "3.0%"


def test_sparkline_colour():
    assert "#00a86b" in sparkline_svg([1, 2, 3])
    assert "#e5484d" in sparkline_svg([3, 2, 1])
    assert sparkline_svg([]) == ""


def test_index_label_and_prices():
    assert "In <b>S&amp;P 500</b>" in rows_html(_df(), "pth", "US", SESSION)
    assert "In <b>NIFTY 500</b>" in rows_html(_df(), "pth", "IN", SESSION)
    assert "S&amp;P 500" not in rows_html(_df(InIndex=False), "pth", "US", SESSION)
    out = rows_html(_df(Price=123456.7), "pth", "IN", SESSION)
    assert "₹1,23,456.70" in out
    assert "$125.00" in rows_html(_df(), "pth", "US", SESSION)


def test_no_script():
    assert "<script" not in rows_html(_df(), "pth", "US", SESSION) + STYLES


def test_rows_embed_sparkline_as_image():
    # st.html sanitises with DOMPurify's HTML profile, which strips inline <svg>.
    out = rows_html(_df(), "pth", "US", SESSION)
    assert "<svg" not in out
    assert '<img class="sm-spark" src="data:image/svg+xml;base64,' in out
