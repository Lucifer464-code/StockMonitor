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


def _md(universe=100, priced=100, index="OK", label="Price as on Oct 16, 2026  (Close)"):
    """In the index: 48 PTH (31 of them also ATH) and 3 Fallen. Plus 5 PTH outside it."""
    rows = [_row(Ticker=f"P{i}", IsPTH="TRUE", IsATH="TRUE" if i < 31 else "FALSE")
            for i in range(48)]
    rows += [_row(Ticker=f"F{i}", IsFallen="TRUE") for i in range(3)]
    rows += [_row(Ticker=f"X{i}", IsPTH="TRUE", InIndex="FALSE") for i in range(5)]
    values = [
        [label, "", "Universe", str(universe), "IndexList", index],
        ["Updated Oct 22, 2026", "", "Priced", str(priced)],
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


def test_tiles_show_counts(monkeypatch):
    at = _run(monkeypatch)
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
    at.selectbox(key="index_US").select("All").run()
    assert "53" in _tile(at, "pth").label


def test_market_switch_changes_index_options(monkeypatch):
    at = _run(monkeypatch)
    at.segmented_control(key="market").set_value("🇮🇳 India").run()
    assert at.selectbox(key="index_IN").options == ["NIFTY 500", "All"]
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
    at.segmented_control(key="market").set_value("🇮🇳 India").run()
    assert not at.exception
    assert any("Data for India isn't available yet." in i.value for i in at.info)
