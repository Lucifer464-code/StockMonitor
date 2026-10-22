"""Throttle-safe price history download and pricing-session resolution.

Ported from Data Bot's stocks_data.py, behaviour unchanged.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from stockmonitor import config


def is_market_open(market: str) -> bool:
    """Return True if the given market is currently in its regular session."""
    if market == "US":
        tz = ZoneInfo("America/New_York")
        now = datetime.now(tz)
        open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    else:  # IN
        tz = ZoneInfo("Asia/Kolkata")
        now = datetime.now(tz)
        open_t = now.replace(hour=9, minute=15, second=0, microsecond=0)
        close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return now.weekday() < 5 and open_t <= now <= close_t


def latest_settled_session(market: str = "US"):
    """The most recent SETTLED session for a market, as a normalised date.

    Individual tickers cannot be trusted to answer this: a thinly traded
    name may simply have no bar for a session, so letting each row use its
    own newest bar mixes sessions within one table. Resolve it once from
    liquid references and hold every row to it.

    A session counts as settled only once its close exists. Mid-session the
    provider already carries today's bar with a live, still-moving close,
    so today is excluded unless the market has closed.
    """
    refs = config.SESSION_REFERENCE.get(market, config.SESSION_REFERENCE["US"])
    today = pd.Timestamp.now().normalize()
    market_open = is_market_open(market)

    best = None
    for sym in refs:
        try:
            hist = yf.download(sym, period="1mo", auto_adjust=False,
                               progress=False)
            col = hist["Close"]
            if hasattr(col, "columns"):
                col = col.iloc[:, 0]
            col = col.dropna()
            if col.empty:
                continue
            idx = col.index
            idx = idx.tz_localize(None) if getattr(idx, "tz", None) is not None else idx
            dates = [d.normalize() for d in idx]
            # Drop today while the session is still running: its close has
            # not settled yet.
            if market_open:
                dates = [d for d in dates if d < today]
            if not dates:
                continue
            cand = max(dates)
            if best is None or cand > best:
                best = cand
        except Exception:
            continue

    if best is not None:
        print(f"  Pricing session: {best.date()} "
              f"({'market open, today excluded' if market_open else 'market closed'})")
    else:
        print("  [WARN] could not resolve a pricing session from reference "
              "tickers; falling back to each ticker's newest settled bar.")
    return best


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
                col = df[s]["Close"] if len(syms) > 1 else df["Close"]
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
                        merged[s] = sub[s] if len(chunk) > 1 else sub
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
    """
    series = [s for s in closes.values() if len(s)]
    if not series:
        return None
    counts = pd.Series([d.normalize() for s in series for d in s.index.unique()]).value_counts()
    need = min_share * len(series)
    ok = [d for d, n in counts.items() if n >= need and (upper is None or d <= upper)]
    return max(ok) if ok else None
