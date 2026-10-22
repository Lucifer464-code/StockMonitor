"""Pure per-stock metrics from a close-price series."""
import math

import pandas as pd

from stockmonitor import config

NAN = float("nan")


def _pct(a: float, b: float) -> float:
    """(a / b - 1) * 100, rounded so exact thresholds survive float error."""
    return round((a / b - 1.0) * 100.0, 9)


def _return_since(close: pd.Series, session: pd.Timestamp, offset: pd.DateOffset) -> float:
    target = session - offset
    if close.index[0] > target:
        return NAN
    pos = close.index.searchsorted(target, side="right") - 1
    return _pct(float(close.iloc[-1]), float(close.iloc[pos]))


def compute_metrics(close: pd.Series, session: pd.Timestamp) -> dict | None:
    """Metrics for one stock as of `session`, or None if it has no bar then."""
    c = close[close.index <= session]
    if len(c) < 2 or c.index[-1] != session:
        return None

    price = float(c.iloc[-1])
    window = c[c.index >= session - pd.DateOffset(years=1)]
    high52 = float(window.max())
    low52 = float(window.min())
    low52_date = window.index[window.to_numpy() == low52][-1]
    ath = float(c.max())

    from_high = _pct(price, high52)
    from_ath = _pct(price, ath)
    off_low = _pct(price, low52)

    ratios = window.to_numpy()[1:] / window.to_numpy()[:-1]
    gap = bool((ratios < 1.0 - config.GAP_SCREEN_PCT / 100.0).any())

    # Strictly more than FALLEN_MIN below the high, so a stock exactly 10%
    # down is PTH and never in both tabs.
    is_fallen = config.FALLEN_MIN_PCT < -from_high <= config.FALLEN_MAX_PCT and not gap

    first = c.index[0]
    listed = first if (session - first) < pd.Timedelta(days=365) else None

    return {
        "Price": price,
        "High52": high52,
        "Low52": low52,
        "Low52Date": low52_date,
        "ATH": ath,
        "FromHigh52": from_high,
        "FromATH": from_ath,
        "OffLow52": off_low,
        "R1D": _pct(price, float(c.iloc[-2])),
        "R1W": _pct(price, float(c.iloc[-6])) if len(c) >= 6 else NAN,
        "R1M": _return_since(c, session, pd.DateOffset(months=1)),
        "R3M": _return_since(c, session, pd.DateOffset(months=3)),
        "R6M": _return_since(c, session, pd.DateOffset(months=6)),
        "R1Y": _return_since(c, session, pd.DateOffset(years=1)),
        "R3Y": _return_since(c, session, pd.DateOffset(years=3)),
        "IsPTH": from_high >= -config.PTH_PCT,
        "IsATH": from_ath >= -config.ATH_PCT,
        "IsFallen": bool(is_fallen),
        "Spark": ",".join(f"{v:.2f}" for v in c.iloc[-config.SPARK_POINTS:]),
        "ListedDate": listed,
        "GapScreened": gap,
    }
