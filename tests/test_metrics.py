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


def test_pth_within_10pct():
    s = make_series(rising(300, last=91))
    m = compute_metrics(s, SESSION)
    assert m["FromHigh52"] == pytest.approx(-9.0)
    assert m["IsPTH"] and not m["IsFallen"]


def test_pth_boundary():
    assert compute_metrics(make_series(rising(300, last=90.0)), SESSION)["IsPTH"]
    assert not compute_metrics(make_series(rising(300, last=89.9)), SESSION)["IsPTH"]


def test_ath_stays_within_5pct():
    # Here the all-time high is the 52-week high: 94 is PTH (within 10%) but not ATH.
    m = compute_metrics(make_series(rising(300, last=94.0)), SESSION)
    assert m["IsPTH"] and not m["IsATH"]
    assert compute_metrics(make_series(rising(300, last=95.0)), SESSION)["IsATH"]


def test_ath_uses_full_history():
    # 200 about three years back, then a 52w high of 100, last 99.
    v = [200.0] + [60.0] * 499 + [100.0] * 300
    v[-1] = 99.0
    m = compute_metrics(make_series(v), SESSION)
    assert m["IsPTH"] and not m["IsATH"]
    assert m["FromATH"] == pytest.approx(-50.5)


def test_fallen_is_80_to_90pct_of_the_high():
    m = compute_metrics(make_series(rising(300, last=85.0)), SESSION)
    assert m["FromHigh52"] == pytest.approx(-15.0)
    assert m["IsFallen"] and not m["IsPTH"]


def test_fallen_band_edges_never_overlap_pth():
    def flags(last):
        m = compute_metrics(make_series(rising(300, last=last)), SESSION)
        return m["IsPTH"], m["IsFallen"]
    assert flags(90.0) == (True, False)    # exactly 10% down is PTH
    assert flags(89.9) == (False, True)
    assert flags(80.0) == (False, True)    # exactly 20% down is still Fallen
    assert flags(79.9) == (False, False)


def test_fallen_needs_no_recent_low_rule():
    # Fell to 85 and kept sliding to a fresh 52-week low today: still Fallen.
    v = [50.0] * 100 + [100.0] + [99.0] * 150 + list(np.linspace(99, 86, 48)) + [85.0]
    v[:100] = [90.0] * 100  # keep every earlier close above today's 85
    m = compute_metrics(make_series(v), SESSION)
    assert m["Low52"] == pytest.approx(85.0)
    assert m["IsFallen"]


def test_gap_screened():
    # A one-day 60% drop inside the year, then a recovery to 85% of the high.
    v = [100.0] * 100 + [40.0] * 50 + list(np.linspace(40, 85, 150))
    m = compute_metrics(make_series(v), SESSION)
    assert m["FromHigh52"] == pytest.approx(-15.0)
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
