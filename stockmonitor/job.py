"""The nightly job: price each universe and write the H&L tabs."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from stockmonitor import config, history, metrics, sheets, universe
from stockmonitor.universe import Stock

_FLAGS = ("IsPTH", "IsATH", "IsFallen")


def _would_be_fallen(m: dict, close: pd.Series, session: pd.Timestamp) -> bool:
    """Fallen on depth and recency alone, ignoring the corporate-action screen."""
    c = close[close.index <= session]
    recent_start = c.index[-min(config.NO_NEW_LOW_SESSIONS, len(c))]
    return (config.FALLEN_MIN_PCT <= -m["FromHigh52"] <= config.FALLEN_MAX_PCT
            and m["Low52Date"] < recent_start)


def build_rows(stocks: list[Stock], members: set[str] | None,
               reference_session: pd.Timestamp | None) -> tuple[list[dict], dict]:
    """Download every batch, settle on a consensus session, then compute metrics.

    stats["session"] is the pricing session actually used (None if no date
    reaches consensus, in which case nothing is priced).
    """
    closes: dict[str, pd.Series] = {}
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
                closes[stock.symbol] = close
                got += 1
        flag = "" if got >= len(batch) * 0.8 else "  [LOW YIELD]"
        print(f"  Batch {i + 1}/{n_batches}... {got}/{len(batch)}{flag}")

    session = history.consensus_session(closes, upper=reference_session)
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
            if m["GapScreened"] and _would_be_fallen(m, close, session):
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
             "screened": screened, "session": session}
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
    values = [
        [price_label, "", "Universe", stats["universe"], "IndexList", "OK" if index_ok else "MISSING"],
        [updated_label, "", "Priced", stats["priced"]],
        list(config.COLUMNS),
    ]
    for r in rows:
        values.append([_cell("" if (c == "InIndex" and not index_ok) else r[c])
                       for c in config.COLUMNS])
    if ws.row_count < len(values):
        ws.resize(rows=len(values))
    ws.clear()
    ws.update(values=values, range_name="A1", value_input_option="RAW")


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
        reference = history.latest_settled_session(market)
        if reference is None:
            print(f"  [ERROR] no settled session for {market}; skipping, nothing written")
            code = 1
            continue
        stocks = universe.us_universe() if market == "US" else universe.india_universe()
        print(f"  Universe: {len(stocks)}")
        if not stocks:
            print(f"  [ERROR] empty universe for {market}; nothing written")
            code = 1
            continue
        members = universe.index_members(market)
        rows, stats = build_rows(stocks, members, reference)
        session = stats["session"]
        if session is None:
            print(f"  [ERROR] no consensus session for {market}; nothing written")
            code = 1
            continue
        print(f"  Reference session: {reference.date()}  Consensus session: {session.date()}")
        print(f"  Stale: {stats['stale']}")
        print(f"  Screened out of Fallen ({len(stats['screened'])}): "
              f"{', '.join(stats['screened']) or '-'}")
        if stats["priced"] / len(stocks) < config.COVERAGE_WARN:
            print(f"  [LOW COVERAGE] {stats['priced']}/{len(stocks)} = "
                  f"{stats['priced'] / len(stocks):.0%}")
        price_label, updated_label = _labels(session)
        ws = sheets.get_or_create_ws(sh, config.TABS[market])
        write_tab(ws, rows, price_label, updated_label, stats, members is not None)
        print(f"  Wrote {len(rows)} rows to '{config.TABS[market]}' ({price_label})")
    return code
