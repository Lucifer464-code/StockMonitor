"""Throttle-safe price history download and pricing-session resolution.

Ported from Data Bot's stocks_data.py, behaviour unchanged.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

from stockmonitor import config

MARKET_TZ = {"US": "America/New_York", "IN": "Asia/Kolkata"}


def _now(tz: str) -> datetime:
    return datetime.now(ZoneInfo(tz))


def is_market_open(market: str) -> bool:
    """Return True if the given market is currently in its regular session."""
    if market == "US":
        now = _now(MARKET_TZ["US"])
        open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    else:  # IN
        now = _now(MARKET_TZ["IN"])
        open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
        close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return now.weekday() < 5 and open_t <= now <= close_t


def settled_upper(market: str) -> pd.Timestamp:
    """The newest date whose close can be settled, in the market's own timezone.

    While the market is trading, today's prices are still moving, so the cap
    is yesterday; at any other time it is today (before the open nothing for
    today exists yet, after the close today's close is final). The consensus
    session then picks the newest date at or before this that nearly every
    stock has. Asking a few reference tickers for their newest close is not
    enough: Yahoo's daily history often carries the latest session's row
    with a blank close until hours later, for the references too.
    """
    today = pd.Timestamp(_now(MARKET_TZ[market])).tz_localize(None).normalize()
    return today - pd.Timedelta(days=1) if is_market_open(market) else today


def fill_from_quote(close: pd.Series, quote, upper: pd.Timestamp) -> pd.Series:
    """Add a quote's price as its session's close when the history lags it.

    `quote` is (price, session date) from universe.latest_quotes. It only ever
    appends a session newer than the history's last close and no later than
    `upper`, so it never overwrites a real close or brings in a live price.
    """
    if close.empty or not quote:
        return close
    price, day = quote
    if not price or price <= 0 or day > upper or day <= close.index[-1].normalize():
        return close
    return pd.concat([close, pd.Series([float(price)], index=[day])])


def download_batch(symbols: list, period: str = "max"):
    """yf.download for a batch, retrying and then splitting on throttle.

    yfinance signals rate limiting by returning all-NaN columns rather
    than raising, so "did this work?" has to be answered by inspecting the
    data. Coverage is measured as the share of symbols with a usable close
    series; anything well below full is treated as throttled.
    """
    batch = symbols

    def _coverage(df, syms):
        if df is None or df.empty:
            return 0.0
        ok = 0
        for s in syms:
            try:
                col = df[s]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
                if col.dropna().shape[0] >= 6:
                    ok += 1
            except Exception:
                pass
        return ok / max(len(syms), 1)

    def _fetch(syms):
        return yf.download(syms, period=period, auto_adjust=False,
                           group_by="ticker", threads=True, progress=False)

    data = None
    for attempt in range(3):
        try:
            data = _fetch(batch)
        except Exception as e:
            print(f"\n  [WARN] batch download error: {type(e).__name__}: {e}")
            data = None
        cov = _coverage(data, batch)
        if cov >= 0.9:
            return data
        if attempt < 2:
            wait = 5 * (attempt + 1)
            print(f"\n  [RETRY] batch coverage {cov:.0%} — likely rate "
                  f"limited; waiting {wait}s (attempt {attempt + 1}/3)")
            time.sleep(wait)

    # Still short: split into smaller chunks, which the limiter tolerates
    # far better than one large request.
    if len(batch) > 50:
        print(f"\n  [SPLIT] retrying {len(batch)} tickers in chunks of 50")
        merged = {}
        for i in range(0, len(batch), 50):
            chunk = batch[i:i + 50]
            for chunk_attempt in range(2):
                try:
                    sub = _fetch(chunk)
                except Exception:
                    sub = None
                if _coverage(sub, chunk) >= 0.5:
                    break
                time.sleep(3)
            if sub is not None and not sub.empty:
                for s in chunk:
                    try:
                        # Even a one-symbol chunk may come back ticker-grouped;
                        # store the symbol's own frame so every entry matches.
                        merged[s] = sub[s] if isinstance(sub.columns, pd.MultiIndex) else sub
                    except Exception:
                        pass
            time.sleep(1)
        if merged:
            return pd.concat(merged, axis=1)

    return data


def extract_close(data: pd.DataFrame, symbol: str, n_symbols: int) -> pd.Series:
    """One symbol's close series: tz-naive, sorted, NaN Close filled from
    Adj Close, then dropped. Empty Series if the symbol is missing."""
    try:
        sym_df = data if n_symbols == 1 else data[symbol]
        close = sym_df["Close"]
    except Exception:
        return pd.Series(dtype=float)

    # yfinance sometimes returns the most recent trading day with Close=NaN
    # while High/Low/Open are already populated (the close has not settled).
    # Only "Adj Close" is an acceptable stand-in; Open or High would invent a
    # close that never happened.
    if close.isna().any() and "Adj Close" in sym_df.columns:
        close = close.fillna(sym_df["Adj Close"])

    close = close.dropna().sort_index()
    idx = close.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    return pd.Series(close.values, index=idx)


def consensus_session(closes: dict, upper=None, min_share: float = config.CONSENSUS_SHARE):
    """Latest date (<= upper) on which at least min_share of the non-empty
    close series have a bar, or None.

    Reference tickers can carry a bar that much of the market lacks (a feed
    lag or a partial session); pricing to that date would mark the rest stale.
    Only the last CONSENSUS_WINDOW_DAYS up to upper (or up to the newest bar,
    if upper is None) are considered.
    """
    series = [s for s in closes.values() if len(s)]
    if not series:
        return None
    end = (max(s.index.max() for s in series) if upper is None else pd.Timestamp(upper)).normalize()
    cutoff = end - pd.Timedelta(days=config.CONSENSUS_WINDOW_DAYS)
    days = [s.index[s.index >= cutoff].normalize().unique() for s in series]
    counts = pd.Series(np.concatenate([d.values for d in days])).value_counts()
    counts = counts[(counts.index <= end) & (counts >= min_share * len(series))]
    return pd.Timestamp(counts.index.max()) if len(counts) else None
