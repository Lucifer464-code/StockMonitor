import math

import numpy as np
import pandas as pd
import pytest

from stockmonitor.metrics import compute_metrics
from tests.conftest import make_series

SESSION = pd.Timestamp("2026-10-16")


def rising(n, top=100.0, last=None):
    """n closes rising to `top` on the second-to-last bar, then `last`."""
    v = list(np.linspace(50, top, n - 1))
    v.append(top if last is None else last)
    return v


def test_pth_within_5pct():
    s = make_series(rising(300, last=96))
    m = compute_metrics(s, SESSION)
    assert m["FromHigh52"] == pytest.approx(-4.0)
    assert m["IsPTH"]


def test_pth_boundary():
    assert compute_metrics(make_series(rising(300, last=95.0)), SESSION)["IsPTH"]
    assert not compute_metrics(make_series(rising(300, last=94.9)), SESSION)["IsPTH"]


def test_ath_uses_full_history():
    # 200 about three years back, then a 52w high of 100, last 99.
    v = [200.0] + [60.0] * 499 + [100.0] * 300
    v[-1] = 99.0
    m = compute_metrics(make_series(v), SESSION)
    assert m["IsPTH"] and not m["IsATH"]
    assert m["FromATH"] == pytest.approx(-50.5)


def fallen_series(low_ago, last):
    v = [100.0] * 100 + list(np.linspace(100, 20, 180))   # 280 closes, no gaps
    v += [20.0] * 20                                      # 300 closes
    v[-1 - low_ago] = 12.0
    v[-1] = last
    return make_series(v)


def test_fallen_true():
    m = compute_metrics(fallen_series(20, 15.0), SESSION)
    assert m["FromHigh52"] == pytest.approx(-85.0)
    assert m["IsFallen"]
    assert m["OffLow52"] == pytest.approx(25.0)


def test_fallen_recent_low_excluded():
    m = compute_metrics(fallen_series(5, 15.0), SESSION)
    assert m["FromHigh52"] == pytest.approx(-85.0)
    assert not m["IsFallen"]


def test_fallen_band_edges():
    assert not compute_metrics(fallen_series(20, 25.0), SESSION)["IsFallen"]
    assert not compute_metrics(fallen_series(20, 9.0), SESSION)["IsFallen"]
    assert compute_metrics(fallen_series(20, 20.0), SESSION)["IsFallen"]


def test_gap_screened():
    v = [100.0] * 100 + [40.0] * 200   # 100 -> 40 is ratio 0.4
    v[-1] = 15.0
    v[-30] = 12.0
    m = compute_metrics(make_series(v), SESSION)
    assert m["GapScreened"] and not m["IsFallen"]


def test_short_history_listed_date():
    s = make_series(rising(100))
    m = compute_metrics(s, SESSION)
    assert m["ListedDate"] == s.index[0]
    assert math.isnan(m["R1Y"]) and math.isnan(m["R6M"])
    assert not math.isnan(m["R3M"])


def test_full_history_no_listed_date():
    assert compute_metrics(make_series(rising(400)), SESSION)["ListedDate"] is None


def test_no_bar_on_session_returns_none():
    s = make_series(rising(300), end="2026-10-15")
    assert compute_metrics(s, SESSION) is None


def test_ignores_closes_after_session():
    s = make_series(rising(300, last=96))
    s.loc[pd.Timestamp("2026-10-19")] = 500.0
    m = compute_metrics(s, SESSION)
    assert m["Price"] == pytest.approx(96.0)


def test_returns_1d_1w():
    v = rising(300)
    v[-6:] = [100, 101, 102, 103, 104, 110]
    m = compute_metrics(make_series(v), SESSION)
    assert m["R1D"] == pytest.approx(5.769, abs=1e-3)
    assert m["R1W"] == pytest.approx(10.0)


def test_spark():
    m = compute_metrics(make_series(rising(300)), SESSION)
    parts = m["Spark"].split(",")
    assert len(parts) == 63
    assert parts[-1] == f"{m['Price']:.2f}"
