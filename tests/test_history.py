import numpy as np
import pandas as pd

from stockmonitor import history
from stockmonitor.history import download_batch, extract_close, latest_settled_session


def full_frame(syms, n=10):
    idx = pd.bdate_range(end="2026-10-16", periods=n)
    cols = pd.MultiIndex.from_product([syms, ["Close", "Adj Close"]])
    return pd.DataFrame(np.arange(n * len(cols), dtype=float).reshape(n, len(cols)) + 1,
                        index=idx, columns=cols)


def nan_frame(syms, n=10):
    df = full_frame(syms, n)
    df[:] = np.nan
    return df


def test_download_retries_until_coverage(monkeypatch):
    second = full_frame(["A", "B"])
    frames = [nan_frame(["A", "B"]), second]
    calls = []

    def fake_download(*a, **k):
        calls.append(1)
        return frames[len(calls) - 1]

    monkeypatch.setattr(history.yf, "download", fake_download)
    monkeypatch.setattr(history.time, "sleep", lambda s: None)
    assert download_batch(["A", "B"]) is second
    assert len(calls) == 2


def test_download_splits_large_batch(monkeypatch):
    syms = [f"S{i}" for i in range(120)]

    def fake_download(batch, *a, **k):
        if len(batch) > 50:
            return nan_frame(batch)
        return full_frame(batch)

    monkeypatch.setattr(history.yf, "download", fake_download)
    monkeypatch.setattr(history.time, "sleep", lambda s: None)
    out = download_batch(syms)
    assert set(out.columns.get_level_values(0)) == set(syms)


def test_extract_close_fills_adj_and_strips_tz():
    df = full_frame(["A", "B"])
    df.index = df.index.tz_localize("America/New_York")
    df.iloc[-1, df.columns.get_loc(("A", "Close"))] = np.nan
    df.iloc[-1, df.columns.get_loc(("A", "Adj Close"))] = 101.0
    s = extract_close(df, "A", 2)
    assert s.index.tz is None
    assert s.iloc[-1] == 101.0


def test_extract_close_missing_symbol_empty():
    assert extract_close(full_frame(["A", "B"]), "ZZZ", 2).empty


def test_latest_settled_session_drops_today_when_open(monkeypatch):
    today = pd.Timestamp.now().normalize()
    idx = pd.DatetimeIndex([today - pd.Timedelta(days=2), today - pd.Timedelta(days=1), today])
    hist = pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)
    monkeypatch.setattr(history.yf, "download", lambda *a, **k: hist)
    monkeypatch.setattr(history, "is_market_open", lambda m: True)
    assert latest_settled_session("US") == today - pd.Timedelta(days=1)
    monkeypatch.setattr(history, "is_market_open", lambda m: False)
    assert latest_settled_session("US") == today


def _closes(n, with_latest, latest="2026-10-16", prior="2026-10-15"):
    out = {}
    for i in range(n):
        dates = [prior] + ([latest] if i < with_latest else [])
        out[f"S{i}"] = pd.Series([1.0] * len(dates), index=pd.to_datetime(dates))
    return out


def test_consensus_session_skips_minority_date():
    assert history.consensus_session(_closes(10, 7), None) == pd.Timestamp("2026-10-15")


def test_consensus_session_latest_when_majority():
    assert history.consensus_session(_closes(10, 9), None) == pd.Timestamp("2026-10-16")


def test_consensus_session_respects_upper():
    got = history.consensus_session(_closes(10, 10), pd.Timestamp("2026-10-15"))
    assert got == pd.Timestamp("2026-10-15")


def test_consensus_session_none():
    assert history.consensus_session({}, None) is None
