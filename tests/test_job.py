import numpy as np
import pandas as pd
import pytest

from conftest import make_series
from stockmonitor import job
from stockmonitor.config import COLUMNS
from stockmonitor.job import build_rows, write_tab
from stockmonitor.universe import Stock

SESSION = pd.Timestamp("2026-10-16")


class FakeWS:
    row_count = 1000
    col_count = 26

    def __init__(self, d1=None, fail_update=False):
        self.calls = []
        self.updates = []
        self.d1 = d1
        self.fail_update = fail_update

    def clear(self):
        self.calls.append("clear")

    def update(self, values, range_name, value_input_option):
        if self.fail_update:
            raise RuntimeError("quota exceeded")
        self.calls.append("update")
        self.updates.append(type("U", (), {"range": range_name, "values": values,
                                           "opt": value_input_option})())

    def batch_clear(self, ranges):
        self.calls.append(("batch_clear", ranges))

    def resize(self, rows):
        self.calls.append(("resize", rows))
        self.row_count = rows

    def acell(self, label):
        assert label == "D1"
        return type("C", (), {"value": self.d1})()


def make_row(**kw):
    row = {c: "" for c in COLUMNS}
    row.update(Ticker="AAA", Price=1.0, InIndex=True)
    row.update(kw)
    return row


STATS = {"universe": 10, "priced": 9, "stale": 1, "screened": [], "expected": 12}


def test_write_tab_layout():
    ws = FakeWS()
    write_tab(ws, [make_row()], "Price as on Oct 16, 2026  (Close)", "Updated ...", STATS, True)
    v = ws.updates[0].values
    assert v[0][0].startswith("Price as on") and v[0][2:6] == ["Universe", 10, "IndexList", "OK"]
    assert v[1][2:6] == ["Priced", 9, "Expected", 12]
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
    # 19 of 20 (95%) have the session's bar, so it stands and BBB is stale.
    short = make_series([10.0] * 50, end="2026-10-14")
    syms = ["BBB"] + [f"S{i}" for i in range(19)]
    patch(monkeypatch, {s: (short if s == "BBB" else PTH) for s in syms})
    rows, stats = build_rows(stocks(*syms), None, SESSION)
    assert stats["stale"] == 1 and stats["priced"] == 19
    assert stats["session"] == SESSION


def test_build_rows_consensus_falls_back_a_day(monkeypatch):
    lag = make_series([10.0] * 50, end="2026-10-15")
    syms = [f"S{i}" for i in range(10)]
    patch(monkeypatch, {s: (PTH if i < 7 else lag) for i, s in enumerate(syms)})
    _, stats = build_rows(stocks(*syms), None, SESSION)
    assert stats["session"] == pd.Timestamp("2026-10-15")
    assert stats["stale"] == 0 and stats["priced"] == 10


def test_build_rows_fills_lagging_session_from_quotes(monkeypatch):
    # The history carries Oct 15 as its newest close for everyone (Yahoo has
    # not filled Oct 16 yet); the quotes hold Oct 16's close.
    lag = make_series([50.0] * 299 + [100.0], end="2026-10-15")
    syms = [f"S{i}" for i in range(10)]
    patch(monkeypatch, {s: lag for s in syms})
    quotes = {s: (101.0, SESSION) for s in syms}
    _, without = build_rows(stocks(*syms), None, SESSION)
    rows, stats = build_rows(stocks(*syms), None, SESSION, quotes=quotes)
    assert without["session"] == pd.Timestamp("2026-10-15")
    assert stats["session"] == SESSION and stats["priced"] == 10
    assert all(r["Price"] == 101.0 for r in rows)


def test_run_passes_quotes_and_settled_upper(monkeypatch):
    us = FakeWS()
    patch_run(monkeypatch, {"H&L US": us})
    seen = {}
    monkeypatch.setattr(job.universe, "latest_quotes", lambda m: {"U0": (1.0, SESSION)})

    def spy(sts, members, upper, quotes=None):
        seen.update(upper=upper, quotes=quotes)
        return [], {"universe": len(sts), "priced": len(sts), "stale": 0,
                    "screened": [], "session": SESSION}

    monkeypatch.setattr(job, "build_rows", spy)
    assert job.run(["US"]) == 0
    assert seen == {"upper": SESSION, "quotes": {"U0": (1.0, SESSION)}}


def test_build_rows_survives_none_download_and_bad_series(monkeypatch):
    monkeypatch.setattr(job.history, "download_batch", lambda syms, period="max": None)
    rows, stats = build_rows(stocks("AAA", "BBB"), None, SESSION)
    assert rows == [] and stats["stale"] == 2
    patch(monkeypatch, {"AAA": PTH, "BBB": make_series([0.0] * 20), "CCC": PTH,
                        "DDD": PTH, "EEE": PTH})
    rows, stats = build_rows(stocks("AAA", "BBB", "CCC", "DDD", "EEE"), None, SESSION)
    assert "BBB" not in [r["Ticker"] for r in rows] and stats["stale"] == 1


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


def test_write_tab_writes_before_clearing_below():
    ws = FakeWS()
    write_tab(ws, [make_row(), make_row()], "p", "u", STATS, True)
    assert "clear" not in ws.calls
    assert ws.calls == ["update", ("batch_clear", ["A6:Z1000"])]


def test_write_tab_grows_sheet_first():
    ws = FakeWS()
    ws.row_count = 3
    write_tab(ws, [make_row(), make_row()], "p", "u", STATS, True)
    assert ws.calls == [("resize", 5), "update"]


def test_write_tab_failed_update_keeps_old_data():
    ws = FakeWS(fail_update=True)
    with pytest.raises(RuntimeError):
        write_tab(ws, [make_row()], "p", "u", STATS, True)
    assert ws.calls == []  # nothing was cleared


# ── run(): expected count and per-market isolation ───────────

def patch_run(monkeypatch, tabs, priced=None, boom=()):
    """Fake everything run() touches. tabs: {tab title: FakeWS}."""
    monkeypatch.setattr(job.sheets, "open_sheet", lambda: object())
    monkeypatch.setattr(job.sheets, "get_or_create_ws", lambda sh, title: tabs[title])
    monkeypatch.setattr(job.history, "settled_upper", lambda m: SESSION)
    monkeypatch.setattr(job.universe, "latest_quotes", lambda m: {})
    monkeypatch.setattr(job.universe, "us_universe", lambda: stocks(*[f"U{i}" for i in range(10)]))
    monkeypatch.setattr(job.universe, "india_universe", lambda: stocks(*[f"I{i}.NS" for i in range(10)]))
    monkeypatch.setattr(job.universe, "index_members", lambda m: set())

    def fake_build(sts, members, ref, quotes=None):
        if sts[0].symbol.startswith(boom):
            raise MemoryError("consensus blew up")
        n = len(sts) if priced is None else priced
        return [], {"universe": len(sts), "priced": n, "stale": len(sts) - n,
                    "screened": [], "session": SESSION}

    monkeypatch.setattr(job, "build_rows", fake_build)


def test_run_expected_is_max_of_universe_and_previous(monkeypatch, capsys):
    us, india = FakeWS(d1="20"), FakeWS(d1="")
    patch_run(monkeypatch, {"H&L US": us, "H&L India": india}, priced=10)
    assert job.run(["US", "IN"]) == 0
    assert us.updates[0].values[1][4:6] == ["Expected", 20]
    assert us.updates[0].values[0][3] == 10
    assert india.updates[0].values[1][4:6] == ["Expected", 10]
    out = capsys.readouterr().out
    assert "[LOW COVERAGE] 10/20 = 50%" in out


def test_run_unparseable_previous_counts_as_zero(monkeypatch):
    us = FakeWS(d1="Universe?")
    patch_run(monkeypatch, {"H&L US": us})
    job.run(["US"])
    assert us.updates[0].values[1][5] == 10


def test_run_market_failure_does_not_stop_the_other(monkeypatch, capsys):
    us, india = FakeWS(), FakeWS()
    patch_run(monkeypatch, {"H&L US": us, "H&L India": india}, boom="U")
    assert job.run(["US", "IN"]) == 1
    assert us.updates == [] and len(india.updates) == 1
    assert "[ERROR] US failed: MemoryError: consensus blew up" in capsys.readouterr().out
