"""Which stocks the job prices, and which are in the S&P 500 / NIFTY 500."""
import io
import os
import pickle
import time
from dataclasses import dataclass

import pandas as pd
import requests
import yfinance as yf

from stockmonitor import config


@dataclass
class Stock:
    symbol: str   # yfinance form, e.g. RELIANCE.NS
    ticker: str   # display form, e.g. RELIANCE
    name: str
    mcap: float


# ── Cache ─────────────────────────────────────────────────────

def _cache_path(name):
    return os.path.join(config.CACHE_DIR, f"{name}.pkl")


def _load_cache(name, max_age_h):
    """Cached object, or None if missing/unreadable/older than max_age_h (None = any age)."""
    path = _cache_path(name)
    try:
        if max_age_h is not None and time.time() - os.path.getmtime(path) > max_age_h * 3600:
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_cache(name, obj):
    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(_cache_path(name), "wb") as f:
            pickle.dump(obj, f)
    except Exception as e:
        print(f"  [WARN] could not save cache {name}: {e}")


def _cached_fetch(name, ttl_h, fetch, shrink_label=None):
    """Fresh cache, else fetch(); a stale cache is used only if the fetch fails.

    With shrink_label set, a fetch that comes back below UNIVERSE_SHRINK_LIMIT
    of the previous cached result also counts as failed: a partial fetch must
    not quietly drop stocks.
    """
    fresh = _load_cache(name, ttl_h)
    if fresh:
        return fresh
    try:
        result = fetch()
        if not result:
            raise RuntimeError(f"{name}: empty result")
    except Exception as e:
        print(f"  [ERROR] {name} fetch failed: {e}")
        return _load_cache(name, None)
    if shrink_label:
        previous = _load_cache(name, None)
        if previous and len(result) < config.UNIVERSE_SHRINK_LIMIT * len(previous):
            print(f"  [LOW COVERAGE] {shrink_label} universe {len(result)} vs previous "
                  f"{len(previous)} — using cached universe")
            return previous
    _save_cache(name, result)
    return result


# ── Screener ──────────────────────────────────────────────────

def _screen_all(query):
    """Every quote the screener matches. Raises if fewer come back than its total."""
    quotes, offset, total = [], 0, None
    while True:
        resp = yf.screen(query, offset=offset, size=config.US_SCREEN_PAGE_SIZE,
                         sortField="intradaymarketcap", sortAsc=False)
        page = resp.get("quotes", []) or []
        quotes.extend(page)
        total = resp.get("total", total)
        if len(page) < config.US_SCREEN_PAGE_SIZE or (total is not None and len(quotes) >= total):
            break
        offset += config.US_SCREEN_PAGE_SIZE
    if total is not None and len(quotes) < total:
        raise RuntimeError(f"screener returned {len(quotes)} of {total} quotes")
    return quotes


def _is_derivative(base, name):
    """Warrants and rights: 5+ letter tickers ending W/WW/WS, or named as such."""
    low = name.lower()
    return (len(base) >= 5 and base.endswith(("W", "WS"))) or "warrant" in low or " rights" in low


# ── US ────────────────────────────────────────────────────────

def _fetch_us():
    query = yf.EquityQuery("and", [
        yf.EquityQuery("eq", ["region", "us"]),
        yf.EquityQuery("is-in", ["exchange", *config.US_EXCHANGES]),
        yf.EquityQuery("gte", ["intradaymarketcap", config.US_MCAP_FLOOR]),
    ])
    stocks, seen = [], set()
    for qt in _screen_all(query):
        t = str(qt.get("symbol", "")).strip().upper()
        if qt.get("quoteType") != "EQUITY" or not t or t in seen:
            continue
        # Common stock and ADRs only: a class suffix must be a single letter
        # (BRK-B); preferreds like JPM-PC carry a longer one.
        base, _, cls = t.partition("-")
        if not base.isalpha() or (cls and not (len(cls) == 1 and cls.isalpha())):
            continue
        name = str(qt.get("longName") or qt.get("shortName") or t).strip()
        mcap = qt.get("marketCap") or 0
        if _is_derivative(base, name) or mcap < config.US_MCAP_FLOOR:
            continue
        seen.add(t)
        stocks.append(Stock(t, t, name.title(), float(mcap)))
    return stocks


def us_universe() -> list[Stock]:
    return _cached_fetch("us_universe", config.UNIVERSE_TTL_H, _fetch_us, "US") or []


# ── India ─────────────────────────────────────────────────────

def _nse_csv(url):
    headers = {"User-Agent": config.BROWSER_UA, "Referer": "https://www.nseindia.com/"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = df.columns.str.strip()
    return df


def _fetch_india():
    df = _nse_csv(config.NIFTY_TOTAL_MARKET_URL)
    if "Series" in df.columns:
        df = df[df["Series"].astype(str).str.strip() == "EQ"]
    df = df.dropna(subset=["Symbol"])
    names = dict(zip(df["Symbol"].astype(str).str.strip().str.upper(),
                     df["Company Name"].astype(str).str.strip()))
    for sym, name in config.IN_MANUAL_ADDITIONS.items():
        names.setdefault(sym, name)

    query = yf.EquityQuery("and", [
        yf.EquityQuery("eq", ["region", "in"]),
        yf.EquityQuery("eq", ["exchange", "NSI"]),
        yf.EquityQuery("gte", ["intradaymarketcap",
                               config.IN_SCREEN_MARGIN * config.IN_MCAP_FLOOR]),
    ])
    caps = {str(qt.get("symbol", "")).upper(): qt.get("marketCap")
            for qt in _screen_all(query)}
    if not caps:
        # Never fall back to a per-stock fast_info sweep of the whole market.
        raise RuntimeError("India screener returned no quotes")

    stocks, asked, failed = [], 0, 0
    for ticker, name in names.items():
        if ticker.startswith("DUMMY"):  # NSE placeholder rows, not listed stocks
            continue
        sym = f"{ticker}.NS"
        mcap = caps.get(sym)
        if not mcap:
            asked += 1
            try:
                mcap = yf.Ticker(sym).fast_info.market_cap
            except Exception:
                mcap = None
            if not mcap:
                failed += 1
            time.sleep(config.FAST_INFO_PAUSE_S)
        if mcap and mcap >= config.IN_MCAP_FLOOR:
            stocks.append(Stock(sym, ticker, name, float(mcap)))
    if asked:
        print(f"  fast_info fallback: {failed} of {asked} failed")
    return stocks


def india_universe() -> list[Stock]:
    return _cached_fetch("in_universe", config.UNIVERSE_TTL_H, _fetch_india, "India") or []


# ── Index membership ──────────────────────────────────────────

def _fetch_sp500():
    r = requests.get(config.SP500_URL, headers={"User-Agent": config.BROWSER_UA}, timeout=20)
    r.raise_for_status()
    for table in pd.read_html(io.StringIO(r.text)):
        if "Symbol" in table.columns:
            return {str(s).strip().upper().replace(".", "-") for s in table["Symbol"].dropna()}
    raise RuntimeError("no Symbol table on the S&P 500 page")


def _fetch_nifty500():
    df = _nse_csv(config.NIFTY_500_URL)
    return {f"{str(s).strip().upper()}.NS" for s in df["Symbol"].dropna()}


def index_members(market: str) -> set[str] | None:
    """yfinance symbols in the S&P 500 (US) or NIFTY 500 (IN); None if unavailable."""
    fetch = {"US": _fetch_sp500, "IN": _fetch_nifty500}[market]
    return _cached_fetch(f"index_{market}", config.INDEX_TTL_H, fetch)
