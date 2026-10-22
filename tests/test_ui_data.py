import math

import pandas as pd

from stockmonitor import config
from ui.data import parse_tab, view_counts, view_rows


def _row(**kw):
    base = {c: "" for c in config.COLUMNS}
    base.update(IsPTH="FALSE", IsATH="FALSE", IsFallen="FALSE", InIndex="FALSE")
    base.update(kw)
    return [base[c] for c in config.COLUMNS]


def _values(rows):
    return [
        ["Price as on Oct 16, 2026  (Close)", "", "Universe", "10", "IndexList", "OK"],
        ["Updated Oct 22, 2026  ·  10:16 AM IST", "", "Priced", "9"],
        list(config.COLUMNS),
        *rows,
    ]


def _md():
    return parse_tab(_values([
        _row(Ticker="A", IsPTH="TRUE", FromHigh52="-1.2", R1W="3", InIndex="TRUE"),
        _row(Ticker="B", IsPTH="TRUE", FromHigh52="-0.4", R1W="9"),
        _row(Ticker="C", IsPTH="TRUE", IsATH="TRUE", FromHigh52="-4.1", R1W="5"),
        _row(Ticker="D", IsFallen="TRUE", FromHigh52="-15", R1W="-2", R1M="4", InIndex="TRUE"),
        _row(Ticker="E", IsFallen="TRUE", FromHigh52="-12", R1W="", R1M="-1"),
    ]))


def test_parse_tab_meta():
    md = parse_tab(_values([]))
    assert md.price_label == "Price as on Oct 16, 2026  (Close)"
    assert md.session == pd.Timestamp("2026-10-16")
    assert (md.universe, md.priced, md.index_ok) == (10, 9, True)


def test_parse_tab_types():
    v = _values([_row(Ticker="X", Price="12.5", MarketCap="", IsPTH="TRUE",
                      Spark="1,2,3", Low52Date="2026-01-05", InIndex="")])
    v[3] = v[3][:-1]  # short row: ListedDate missing, must be padded
    row = parse_tab(v).df.iloc[0]
    assert row["Price"] == 12.5
    assert math.isnan(row["MarketCap"])
    assert row["IsPTH"] is True or row["IsPTH"] == True  # noqa: E712
    assert row["IsATH"] == False  # noqa: E712
    assert row["Spark"] == [1.0, 2.0, 3.0]
    assert row["Low52Date"] == pd.Timestamp("2026-01-05")
    assert pd.isna(row["ListedDate"])
    assert pd.isna(row["InIndex"])


def test_parse_tab_bad_label_and_index_missing():
    v = _values([])
    v[0][0] = "garbage"
    v[0][5] = "MISSING"
    md = parse_tab(v)
    assert md.session is None and md.index_ok is False


def test_parse_tab_empty_body():
    md = parse_tab(_values([]))
    assert md.df.empty
    assert list(md.df.columns) == config.COLUMNS


def test_view_rows_sort_and_filter():
    md = _md()
    assert list(view_rows(md, "pth", False)["Ticker"]) == ["B", "A", "C"]
    assert list(view_rows(md, "ath", False)["Ticker"]) == ["C"]
    assert list(view_rows(md, "fallen", False)["Ticker"]) == ["E", "D"]


def test_view_rows_custom_sort():
    md = _md()
    assert list(view_rows(md, "pth", False, sort="R1W")["Ticker"]) == ["B", "C", "A"]
    assert list(view_rows(md, "pth", False, sort="R1W", ascending=True)["Ticker"]) == ["A", "C", "B"]
    assert list(view_rows(md, "pth", False, sort="Ticker", ascending=True)["Ticker"]) == ["A", "B", "C"]
    assert list(view_rows(md, "fallen", False, sort="R1M")["Ticker"]) == ["D", "E"]


def test_view_rows_blank_values_sort_last_both_ways():
    md = _md()
    assert list(view_rows(md, "fallen", False, sort="R1W")["Ticker"]) == ["D", "E"]
    assert list(view_rows(md, "fallen", False, sort="R1W", ascending=True)["Ticker"]) == ["D", "E"]


def test_view_rows_index_only():
    md = _md()
    assert list(view_rows(md, "pth", True)["Ticker"]) == ["A"]
    assert list(view_rows(md, "fallen", True)["Ticker"]) == ["D"]


def test_view_counts():
    assert view_counts(_md(), False) == {"pth": 3, "ath": 1, "fallen": 2}
    assert view_counts(_md(), True) == {"pth": 1, "ath": 0, "fallen": 1}


def test_parse_tab_expected_from_f2():
    v = _values([])
    v[1] += ["Expected", "12"]
    md = parse_tab(v)
    assert md.expected == 12 and md.counts_ok


def test_parse_tab_expected_falls_back_to_universe():
    md = parse_tab(_values([]))  # an older tab with no E2/F2
    assert md.expected == 10 and md.counts_ok


def test_parse_tab_blank_or_garbled_counts_flagged():
    for d1, d2 in [("", "9"), ("10", "n/a")]:
        v = _values([])
        v[0][3], v[1][3] = d1, d2
        md = parse_tab(v)
        assert md.counts_ok is False
        assert (md.universe, md.priced) == ((0, 9) if d1 == "" else (10, 0))


def test_view_rows_ties_break_by_market_cap():
    md = parse_tab(_values([
        _row(Ticker="S", IsPTH="TRUE", IsATH="TRUE", IsFallen="TRUE", FromHigh52="-1", R1W="2",
             OffLow52="5", MarketCap="1e9"),
        _row(Ticker="L", IsPTH="TRUE", IsATH="TRUE", IsFallen="TRUE", FromHigh52="-1", R1W="2",
             OffLow52="5", MarketCap="9e9"),
        _row(Ticker="M", IsPTH="TRUE", IsATH="TRUE", IsFallen="TRUE", FromHigh52="-1", R1W="2",
             OffLow52="5", MarketCap="5e9"),
    ]))
    for view in ("pth", "ath", "fallen"):
        assert list(view_rows(md, view, False)["Ticker"]) == ["L", "M", "S"], view
