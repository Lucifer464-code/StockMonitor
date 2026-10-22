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
        _row(Ticker="D", IsFallen="TRUE", OffLow52="12", InIndex="TRUE"),
        _row(Ticker="E", IsFallen="TRUE", OffLow52="30"),
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


def test_view_rows_index_only():
    md = _md()
    assert list(view_rows(md, "pth", True)["Ticker"]) == ["A"]
    assert list(view_rows(md, "fallen", True)["Ticker"]) == ["D"]


def test_view_counts():
    assert view_counts(_md(), False) == {"pth": 3, "ath": 1, "fallen": 2}
    assert view_counts(_md(), True) == {"pth": 1, "ath": 0, "fallen": 1}
