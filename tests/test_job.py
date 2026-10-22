import numpy as np
import pandas as pd

from conftest import make_series
from stockmonitor import job
from stockmonitor.config import COLUMNS
from stockmonitor.job import build_rows, write_tab
from stockmonitor.universe import Stock

SESSION = pd.Timestamp("2026-10-16")


class FakeWS:
    row_count = 1000

    def __init__(self):
        self.cleared = False
        self.updates = []

    def clear(self):
        self.cleared = True

    def update(self, values, range_name, value_input_option):
        self.updates.append(type("U", (), {"range": range_name, "values": values,
                                           "opt": value_input_option})())

    def resize(self, rows):
        self.row_count = rows


def make_row(**kw):
    row = {c: "" for c in COLUMNS}
    row.update(Ticker="AAA", Price=1.0, InIndex=True)
    row.update(kw)
    return row


STATS = {"universe": 10, "priced": 9, "stale": 1, "screened": []}


def test_write_tab_layout():
    ws = FakeWS()
    write_tab(ws, [make_row()], "Price as on Oct 16, 2026  (Close)", "Updated ...", STATS, True)
    assert ws.cleared
    v = ws.updates[0].values
    assert v[0][0].startswith("Price as on") and v[0][2:6] == ["Universe", 10, "IndexList", "OK"]
    assert v[1][2:4] == ["Priced", 9]
    assert v[2] == COLUMNS
    assert ws.updates[0].opt == "RAW"
    assert len(v) == 4


def test_write_tab_cell_values():
    ws = FakeWS()
    row = make_row(Price=1.23456, R1D=float("nan"), IsPTH=True,
                   Low52Date=pd.Timestamp("2026-09-01"), ListedDate=None)
    write_tab(ws, [row], "p", "u", STATS, True)
    out = dict(zip(COLUMNS, ws.updates[0].values[3]))
    assert out["Price"] == 1.23 and out["R1D"] == "" and out["IsPTH"] is True
    assert out["Low52Date"] == "2026-09-01" and out["ListedDate"] == ""


def test_write_tab_index_missing():
    ws = FakeWS()
    write_tab(ws, [make_row()], "p", "u", STATS, False)
    v = ws.updates[0].values
    assert v[0][5] == "MISSING"
    assert dict(zip(COLUMNS, v[3]))["InIndex"] == ""


def frame(series_by_sym):
    """yfinance-style multi-symbol frame (group_by=ticker)."""
    idx = sorted(set().union(*[s.index for s in series_by_sym.values()]))
    parts = {}
    for sym, s in series_by_sym.items():
        s = s.reindex(idx)
        parts[sym] = pd.DataFrame({"Close": s, "Adj Close": s})
    return pd.concat(parts, axis=1)


def patch(monkeypatch, series_by_sym):
    monkeypatch.setattr(job.history, "download_batch",
                        lambda syms, period="max": frame({s: series_by_sym[s] for s in syms}))


def stocks(*syms):
    return [Stock(s, s.split(".")[0], s, 1e9) for s in syms]


PTH = make_series([50.0] * 299 + [100.0])
FLAT = make_series([100.0] * 150 + [150.0] * 50 + [100.0] * 100)  # high 150, price 100


def fallen_series():
    # Peak 100, decline to 12 early, flat since: down 88%, low not recent.
    vals = [100.0] * 50 + list(np.linspace(100, 12, 50)) + [12.0] * 5 + [12.5] * 195
    return make_series(vals)


def test_build_rows_keeps_flagged_only(monkeypatch):
    patch(monkeypatch, {"AAA": PTH, "BBB": FLAT, "CCC": fallen_series()})
    rows, stats = build_rows(stocks("AAA", "BBB", "CCC"), None, SESSION)
    assert sorted(r["Ticker"] for r in rows) == ["AAA", "CCC"]
    assert stats["universe"] == 3 and stats["priced"] == 3 and stats["stale"] == 0


def test_build_rows_counts_stale(monkeypatch):
    short = make_series([10.0] * 50, end="2026-10-14")
    patch(monkeypatch, {"AAA": PTH, "BBB": short})
    rows, stats = build_rows(stocks("AAA", "BBB"), None, SESSION)
    assert stats["stale"] == 1 and stats["priced"] == 1


def test_build_rows_survives_none_download_and_bad_series(monkeypatch):
    monkeypatch.setattr(job.history, "download_batch", lambda syms, period="max": None)
    rows, stats = build_rows(stocks("AAA", "BBB"), None, SESSION)
    assert rows == [] and stats["stale"] == 2
    patch(monkeypatch, {"AAA": PTH, "BBB": make_series([0.0] * 20)})
    rows, stats = build_rows(stocks("AAA", "BBB"), None, SESSION)
    assert [r["Ticker"] for r in rows] == ["AAA"] and stats["stale"] == 1


def test_build_rows_logs_screened(monkeypatch):
    vals = [100.0] * 50 + [20.0] * 10 + [12.0] * 5 + [12.5] * 235  # 80% one-day gap
    patch(monkeypatch, {"AAA": make_series(vals)})
    rows, stats = build_rows(stocks("AAA"), None, SESSION)
    assert rows == [] and stats["screened"] == ["AAA"]


def test_build_rows_in_index(monkeypatch):
    patch(monkeypatch, {"AAA.NS": PTH, "BBB.NS": PTH})
    sts = stocks("AAA.NS", "BBB.NS")
    rows, _ = build_rows(sts, {"AAA.NS"}, SESSION)
    assert {r["Ticker"]: r["InIndex"] for r in rows} == {"AAA": True, "BBB": False}
    rows, _ = build_rows(sts, None, SESSION)
    assert all(r["InIndex"] == "" for r in rows)
