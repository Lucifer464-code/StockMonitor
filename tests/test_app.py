from pathlib import Path

from streamlit.testing.v1 import AppTest

import ui.data
from stockmonitor import config
from ui.data import parse_tab

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _row(**kw):
    base = {c: "" for c in config.COLUMNS}
    base.update(IsPTH="FALSE", IsATH="FALSE", IsFallen="FALSE", InIndex="TRUE",
                Name="Co", Price="10", Spark="1,2,3")
    base.update(kw)
    return [base[c] for c in config.COLUMNS]


def _md(universe=100, priced=100, index="OK", label="Price as on Oct 16, 2026  (Close)",
        expected=None):
    """In the index: 48 PTH (31 of them also ATH) and 3 Fallen. Plus 5 PTH outside it."""
    rows = [_row(Ticker=f"P{i}", IsPTH="TRUE", IsATH="TRUE" if i < 31 else "FALSE",
                 FromHigh52=str(-i / 10), R1W=str(i)) for i in range(48)]
    rows += [_row(Ticker=f"F{i}", IsFallen="TRUE") for i in range(3)]
    rows += [_row(Ticker=f"X{i}", IsPTH="TRUE", InIndex="FALSE") for i in range(5)]
    values = [
        [label, "", "Universe", str(universe), "IndexList", index],
        ["Updated Oct 22, 2026", "", "Priced", str(priced), "Expected",
         "" if expected is None else str(expected)],
        list(config.COLUMNS),
        *rows,
    ]
    return parse_tab(values)


def _run(monkeypatch, md=None, fail=False):
    calls = []

    def fake(market):
        calls.append(market)
        if fail:
            raise RuntimeError("tab missing")
        return md if md is not None else _md()

    monkeypatch.setattr(ui.data, "load_market", fake)
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    at.calls = calls
    return at


def _tile(at, view):
    return at.button(key=f"btn_{view}")


def _page_html(at):
    return " ".join(h.value for h in at.html)


def test_index_defaults_to_all(monkeypatch):
    at = _run(monkeypatch)
    assert at.selectbox(key="index_US").value == "All"
    assert "53" in _tile(at, "pth").label


def test_tiles_show_counts(monkeypatch):
    at = _run(monkeypatch)
    at.selectbox(key="index_US").select("S&P 500").run()
    assert "48" in _tile(at, "pth").label
    assert "31" in _tile(at, "ath").label
    assert "3" in _tile(at, "fallen").label
    assert at.session_state["view"] == "pth"


def test_tile_click_switches_view(monkeypatch):
    at = _run(monkeypatch)
    _tile(at, "fallen").click().run()
    assert at.session_state["view"] == "fallen"


def test_index_filter_changes_counts(monkeypatch):
    at = _run(monkeypatch)
    at.selectbox(key="index_US").select("S&P 500").run()
    assert "48" in _tile(at, "pth").label
    at.selectbox(key="index_US").select("All").run()
    assert "53" in _tile(at, "pth").label


def test_market_switch_changes_index_options(monkeypatch):
    at = _run(monkeypatch)
    assert at.segmented_control(key="market").options == ["US", "India"]
    at.segmented_control(key="market").set_value("India").run()
    assert at.selectbox(key="index_IN").options == ["All", "NIFTY 500"]
    assert at.selectbox(key="index_IN").value == "All"
    assert at.calls[-1] == "IN"


def test_index_missing_offers_only_all(monkeypatch):
    at = _run(monkeypatch, md=_md(index="MISSING"))
    assert at.selectbox(key="index_US").options == ["All"]
    assert any("unavailable" in c.value for c in at.caption)


def test_low_coverage_warning(monkeypatch):
    at = _run(monkeypatch, md=_md(universe=100, priced=60))
    assert any("60%" in w.value for w in at.warning)


def test_no_warning_at_full_coverage(monkeypatch):
    at = _run(monkeypatch)
    assert len(at.warning) == 0


def test_header_shows_session(monkeypatch):
    at = _run(monkeypatch)
    assert "Close · Oct 16" in _page_html(at)


def test_header_falls_back_to_raw_label(monkeypatch):
    at = _run(monkeypatch, md=_md(label="weird label"))
    assert "weird label" in _page_html(at)


def test_list_rendered_with_html(monkeypatch):
    at = _run(monkeypatch)
    assert "P0" in _page_html(at)


def test_load_failure_shows_message(monkeypatch):
    at = _run(monkeypatch, fail=True)
    assert any("Data for US isn't available yet." in i.value for i in at.info)
    assert "0" in _tile(at, "pth").label
    at.segmented_control(key="market").set_value("India").run()
    assert not at.exception
    assert any("Data for India isn't available yet." in i.value for i in at.info)


def test_low_coverage_measured_against_expected(monkeypatch):
    # The run's own universe shrank to 100, but the previous run had 200.
    at = _run(monkeypatch, md=_md(universe=100, priced=100, expected=200))
    assert any("50%" in w.value for w in at.warning)


def _unavailable(at, name="US"):
    return any(f"Data for {name} isn't available yet." in w.value for w in at.warning)


def test_unparseable_label_is_unavailable_not_empty(monkeypatch):
    at = _run(monkeypatch, md=_md(label="weird label"))
    assert _unavailable(at)
    assert "P0" not in _page_html(at) and "No stocks match" not in _page_html(at)


def test_blank_universe_is_unavailable_not_empty(monkeypatch):
    at = _run(monkeypatch, md=_md(universe=""))
    assert _unavailable(at)
    assert "P0" not in _page_html(at) and "No stocks match" not in _page_html(at)


def test_garbled_priced_is_unavailable(monkeypatch):
    at = _run(monkeypatch, md=_md(priced="#REF!"))
    assert _unavailable(at)


def test_load_failure_logged_with_traceback(monkeypatch, capsys):
    _run(monkeypatch, fail=True)
    err = capsys.readouterr().err
    assert "Traceback" in err and "RuntimeError: tab missing" in err


def test_tiles_in_order_with_current_rules(monkeypatch):
    at = _run(monkeypatch)
    labels = [b.label for b in at.button if (b.key or "").startswith("btn_")]
    assert [l.split("\n")[0] for l in labels] == ["Near 52w high", "Fallen from PTH", "All-time high"]
    assert "within 10%" in labels[0] and "down 10–20%" in labels[1] and "within 5%" in labels[2]


# ── Sortable headers ─────────────────────────────────────────

def _order(at, *tickers):
    page = _page_html(at)
    return [page.index(f"<b>{t}</b>") for t in tickers]


def test_header_buttons_per_view(monkeypatch):
    at = _run(monkeypatch)
    keys = {b.key for b in at.button}
    assert {"sort_pth_Ticker", "sort_pth_FromHigh52", "sort_pth_R1W"} <= keys
    assert not any(k.startswith("sort_pth_") and "trend" in k.lower() for k in keys)
    _tile(at, "fallen").click().run()
    keys = {b.key for b in at.button}
    assert {"sort_fallen_Ticker", "sort_fallen_FromHigh52", "sort_fallen_R1W",
            "sort_fallen_R1M"} <= keys
    assert at.button(key="sort_fallen_R1W").label.startswith("5D")
    assert at.button(key="sort_fallen_R1M").label.startswith("1M")


def test_default_sort_marked_and_applied(monkeypatch):
    at = _run(monkeypatch)
    assert at.button(key="sort_pth_FromHigh52").label.endswith("▼")
    a, b = _order(at, "P0", "P47")
    assert a < b  # closest to the high first


def test_click_header_sorts_then_flips(monkeypatch):
    at = _run(monkeypatch)
    at.button(key="sort_pth_R1W").click().run()
    assert at.button(key="sort_pth_R1W").label.endswith("▼")
    assert not at.button(key="sort_pth_FromHigh52").label.endswith(("▼", "▲"))
    a, b = _order(at, "P47", "P0")
    assert a < b  # biggest 1W first
    at.button(key="sort_pth_R1W").click().run()
    assert at.button(key="sort_pth_R1W").label.endswith("▲")
    a, b = _order(at, "P0", "P47")
    assert a < b


def test_stock_header_sorts_a_to_z_first(monkeypatch):
    at = _run(monkeypatch)
    at.button(key="sort_pth_Ticker").click().run()
    assert at.button(key="sort_pth_Ticker").label.endswith("▲")
    a, b = _order(at, "P0", "X0")
    assert a < b


def test_sort_is_kept_per_tab(monkeypatch):
    at = _run(monkeypatch)
    at.button(key="sort_pth_R1W").click().run()
    _tile(at, "fallen").click().run()
    assert at.button(key="sort_fallen_FromHigh52").label.endswith("▼")
    _tile(at, "pth").click().run()
    assert at.button(key="sort_pth_R1W").label.endswith("▼")
