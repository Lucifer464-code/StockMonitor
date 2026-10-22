"""The nightly job: price each universe and write the H&L tabs."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import gspread
import pandas as pd

from stockmonitor import config, history, metrics, sheets, universe
from stockmonitor.universe import Stock

_FLAGS = ("IsPTH", "IsATH", "IsFallen")


def _would_be_fallen(m: dict) -> bool:
    """Fallen on depth alone, ignoring the corporate-action screen."""
    return config.FALLEN_MIN_PCT < -m["FromHigh52"] <= config.FALLEN_MAX_PCT


def build_rows(stocks: list[Stock], members: set[str] | None,
               upper: pd.Timestamp | None, quotes: dict | None = None) -> tuple[list[dict], dict]:
    """Download every batch, settle on a consensus session, then compute metrics.

    `quotes` ({symbol: (price, session date)}) fills a session close that
    Yahoo's history still shows blank; see history.fill_from_quote.
    stats["session"] is the pricing session actually used (None if no date
    reaches consensus, in which case nothing is priced).
    """
    quotes = quotes or {}
    closes: dict[str, pd.Series] = {}
    filled = 0
    n_batches = math.ceil(len(stocks) / config.PRICE_BATCH_SIZE)
    for i in range(n_batches):
        batch = stocks[i * config.PRICE_BATCH_SIZE:(i + 1) * config.PRICE_BATCH_SIZE]
        syms = [s.symbol for s in batch]
        data = history.download_batch(syms)
        got = 0
        # A one-symbol download may still come back ticker-grouped.
        n_syms = 2 if data is not None and isinstance(data.columns, pd.MultiIndex) else len(syms)
        for stock in batch if data is not None else []:
            try:
                close = history.extract_close(data, stock.symbol, n_syms)
            except Exception as e:
                print(f"  [WARN] {stock.symbol}: {type(e).__name__}: {e}")
                continue
            if not close.empty:
                if upper is not None:
                    n = len(close)
                    close = history.fill_from_quote(close, quotes.get(stock.symbol), upper)
                    filled += len(close) > n
                closes[stock.symbol] = close
                got += 1
        flag = "" if got >= len(batch) * 0.8 else "  [LOW YIELD]"
        print(f"  Batch {i + 1}/{n_batches}... {got}/{len(batch)}{flag}")

    session = history.consensus_session(closes, upper=upper)
    rows, screened, priced = [], [], 0
    for stock in stocks if session is not None else []:
        close = closes.get(stock.symbol)
        if close is None:
            continue
        try:
            m = metrics.compute_metrics(close, session)
            if m is None:
                continue
            priced += 1
            if m["GapScreened"] and _would_be_fallen(m):
                screened.append(stock.ticker)
            if not any(m[f] for f in _FLAGS):
                continue
            row = {k: v for k, v in m.items() if k != "GapScreened"}
            row.update(
                Ticker=stock.ticker, Name=stock.name, MarketCap=stock.mcap,
                InIndex="" if members is None else stock.symbol in members,
            )
            rows.append({c: row[c] for c in config.COLUMNS})
        except Exception as e:
            print(f"  [WARN] {stock.symbol}: {type(e).__name__}: {e}")
    stats = {"universe": len(stocks), "priced": priced, "stale": len(stocks) - priced,
             "screened": screened, "session": session, "filled": filled}
    return rows, stats


def _cell(v):
    if isinstance(v, (bool, str)):
        return v
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float):
        return round(v, 2)
    if hasattr(v, "item"):  # numpy scalars
        return _cell(v.item())
    return v


def write_tab(ws, rows: list[dict], price_label: str, updated_label: str,
              stats: dict, index_ok: bool) -> None:
    """Write the new block from A1, then clear only what lies below it.

    The sheet is never cleared first: if the write fails, yesterday's data
    stays whole instead of the tab reading as a market with nothing in it.
    """
    values = [
        [price_label, "", "Universe", stats["universe"], "IndexList", "OK" if index_ok else "MISSING"],
        [updated_label, "", "Priced", stats["priced"], "Expected", stats["expected"]],
        list(config.COLUMNS),
    ]
    for r in rows:
        values.append([_cell("" if (c == "InIndex" and not index_ok) else r[c])
                       for c in config.COLUMNS])
    if ws.row_count < len(values):
        ws.resize(rows=len(values))
    ws.update(values=values, range_name="A1", value_input_option="RAW")
    last = len(values)
    if ws.row_count > last:
        corner = gspread.utils.rowcol_to_a1(ws.row_count, max(ws.col_count, len(config.COLUMNS)))
        ws.batch_clear([f"A{last + 1}:{corner}"])


def _previous_universe(ws) -> int:
    """The universe size the tab's last run recorded in D1; 0 if absent or unparseable."""
    try:
        return int(float(ws.acell("D1").value))
    except (TypeError, ValueError):
        return 0


def _labels(session: pd.Timestamp) -> tuple[str, str]:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    price = f"Price as on {session.strftime('%b')} {session.day}, {session.year}  (Close)"
    updated = (f"Updated {now.strftime('%b')} {now.day}, {now.year}"
               f"  ·  {int(now.strftime('%I'))}:{now.strftime('%M %p')} IST")
    return price, updated


def run(markets: list[str]) -> int:
    sh = sheets.open_sheet()
    code = 0
    for market in markets:
        print(f"\n=== {market} ===")
        try:
            code = max(code, _run_market(sh, market))
        except Exception as e:
            print(f"  [ERROR] {market} failed: {type(e).__name__}: {e}; skipping, nothing written")
            code = 1
    return code


def _run_market(sh, market: str) -> int:
    """Price one market and write its tab. Returns 0, or 1 if nothing was written."""
    upper = history.settled_upper(market)
    stocks = universe.us_universe() if market == "US" else universe.india_universe()
    print(f"  Universe: {len(stocks)}")
    if not stocks:
        print(f"  [ERROR] empty universe for {market}; nothing written")
        return 1
    members = universe.index_members(market)
    quotes = universe.latest_quotes(market)
    print(f"  Quotes: {len(quotes)}")
    rows, stats = build_rows(stocks, members, upper, quotes=quotes)
    session = stats["session"]
    if session is None:
        print(f"  [ERROR] no consensus session for {market}; nothing written")
        return 1
    ws = sheets.get_or_create_ws(sh, config.TABS[market])
    # Measure coverage against something a bad run cannot shrink.
    previous = _previous_universe(ws)
    stats["expected"] = expected = max(stats["universe"], previous)
    print(f"  Settled up to: {upper.date()}  Consensus session: {session.date()}  "
          f"(closes filled from quotes: {stats.get('filled', 0)})")
    print(f"  Expected: {expected} (previous universe {previous})")
    print(f"  Stale: {stats['stale']}")
    print(f"  Screened out of Fallen ({len(stats['screened'])}): "
          f"{', '.join(stats['screened']) or '-'}")
    if stats["priced"] / expected < config.COVERAGE_WARN:
        print(f"  [LOW COVERAGE] {stats['priced']}/{expected} = "
              f"{stats['priced'] / expected:.0%}")
    price_label, updated_label = _labels(session)
    write_tab(ws, rows, price_label, updated_label, stats, members is not None)
    print(f"  Wrote {len(rows)} rows to '{config.TABS[market]}' ({price_label})")
    return 0
