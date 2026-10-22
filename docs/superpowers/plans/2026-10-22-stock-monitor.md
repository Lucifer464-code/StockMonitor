# Stock Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Streamlit app plus a nightly data job showing US and India stocks near their 52-week high (PTH), near their all-time high (ATH), and down 80–90% but no longer making new lows (Fallen), each filterable to S&P 500 / NIFTY 500.

**Architecture:** `highs_data.py` builds each market's universe from the yfinance screener (with the NSE list for India), downloads full price history in throttle-safe batches, computes every metric in a pure `metrics` module, and writes one Google Sheet tab per market. The Streamlit app reads those tabs, filters and sorts in pandas, and renders the list as HTML `<details>` rows, so expanding a row needs no rerun.

**Tech Stack:** Python 3.14, Streamlit ≥ 1.40, pandas, yfinance 1.2.x, gspread, google-auth, requests, lxml, pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-highs-lows-dashboard-design.md`

**Repos:**
- New repo `D:\Projects\StockMonitor` (`Lucifer464-code/StockMonitor`, branch `main`): all tasks except Task 8.
- Existing repo `D:\Projects\Data Bot` (`master`): Task 8 only, and **only `run_all.py`**. Never edit `stocks_data.py`.

## Global Constraints

- Google Sheet ID `1uJoD2JRvzRpn2KHJa80aZADQ2DfRwm2qbZKMuv0PKBM`. New tabs `H&L US` and `H&L India`. Never touch any other tab.
- US floor `1_000_000_000` USD. India floor `5_000_000_000` INR (₹500 Cr).
- PTH: `FromHigh52 >= -5.0`. ATH: `FromATH >= -5.0`, full history (`period="max"`).
- Fallen: `80.0 <= -FromHigh52 <= 90.0`, the 52-week low not within the last 10 sessions, and not gap-screened.
- US universe: all US-listed common stock **including ADRs**. Exchanges `NMS, NGM, NCM, NYQ, ASE, PCX, BTS`. `quoteType == "EQUITY"`. A ticker passes if its base is alphabetic, with an optional single-letter class suffix (`BRK-B` passes; `JPM-PC` and `DJTWW` fail).
- India universe: NSE NIFTY Total Market CSV (`https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv`, `Series == "EQ"`), plus manual addition `SEDEMAC: "SEDEMAC Mechatronics Ltd."`.
- India market caps come from the yfinance screener (checked 2026-10-22: median gap 0.9% vs fast_info, 5 of 739 missing), with per-stock `fast_info` only for the missing few. This replaces the spec's "India keeps its existing path".
- Index lists: S&P 500 from Wikipedia "List of S&P 500 companies" (`.` → `-`). NIFTY 500 from `https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv`.
- Price batch size 100, with the same retry and split behaviour as `stocks_data.py` (copied, not imported).
- Every row is priced from one settled session, resolved from the reference tickers `US: SPY, AAPL, MSFT` and `IN: RELIANCE.NS, TCS.NS, HDFCBANK.NS`. A row with no bar on that session is dropped and counted as stale.
- Look: light only, no dark mode. Surfaces `#ffffff` / `#f7f8fa`, accent `#00a86b`, down `#e5484d`, muted text `#8994a7`, borders `#e3e7ed`, Inter/system sans, card radius 14px. The reference mockups are `blend-eg.html` and `row-expand.html` in `D:\Projects\Data Bot\.superpowers\brainstorm\1359-1792652255\content\`.
- Open app, no login. The app reads credentials from `st.secrets["GOOGLE_SERVICE_ACCOUNT"]`; the job reads them from `service_account.json` in the repo root. Both are git-ignored and never committed.
- Commit after each task and push (`git push`). The user's standing rule is to always push after committing.

## Review Focus

1. **Recent listing (< 1 year of history):** it is still classified, `ListedDate` is set, its "52-week" high and low come from the history it has, and returns past its history are blank. The app shows "Listed <date>" in small text. Tests: Task 1 `test_short_history_listed_date`, Task 6 `test_listed_note_rendered`.
2. **Ticker with no bar on the pricing session:** dropped, counted in `stale`, never shown with an older price. Tests: Task 1 `test_no_bar_on_session_returns_none`, Task 4 `test_build_rows_counts_stale`.
3. **A view with zero stocks (Fallen will often be empty):** a friendly empty state, not a blank card or an error. Test: Task 6 `test_empty_state`.
4. **Index list unavailable and no cache:** `InIndex` blank, the meta flag set to `MISSING`, and the app offers only "All", with a note. Tests: Task 3 `test_index_members_none_without_cache`, Task 7 `test_index_missing_offers_only_all`.
5. **Company names with HTML characters** (`Chefs' Warehouse`, `AT&T`, `<`): escaped in the rendered rows. Test: Task 6 `test_names_escaped`.

---

## File Structure (StockMonitor)

```
StockMonitor/
  app.py                    Streamlit entry: controls, tiles, list, warnings
  highs_data.py             CLI entry for the data job: [--us-only | --india-only]
  stockmonitor/
    __init__.py
    config.py               every constant above, plus the column order
    metrics.py              pure: one price series -> one row dict
    history.py              session resolution, batched download, close extraction
    universe.py             US/India universes, index membership, file caches
    sheets.py               gspread open + get-or-create worksheet
    job.py                  build rows, write tab, coverage log
  ui/
    __init__.py
    data.py                 read a tab -> MarketData; filter/sort per view
    render.py               formatting, sparkline SVG, row HTML, CSS
  tests/
    conftest.py             synthetic series helpers
    test_metrics.py  test_history.py  test_universe.py
    test_job.py      test_ui_data.py  test_render.py  test_app.py
  requirements.txt          runtime (also used by Streamlit Cloud)
  requirements-dev.txt      -r requirements.txt + pytest
  .streamlit/config.toml    light theme, primaryColor #00a86b
  README.md                 run + deploy steps
  cache/                    git-ignored
```

Sheet tab layout (both tabs):

| Cell / row | Content |
|---|---|
| A1 | `Price as on Oct 16, 2026  (Close)` (same format as `stocks_data.py`) |
| A2 | `Updated Oct 22, 2026  ·  10:16 AM IST` |
| C1 / D1 | `Universe` / count of stocks in the universe |
| C2 / D2 | `Priced` / count of stocks priced from the session |
| E1 / F1 | `IndexList` / `OK` or `MISSING` |
| Row 3 | header = `config.COLUMNS` |
| Row 4+ | one row per stock flagged PTH, ATH or Fallen |

`config.COLUMNS` (exact order):
`Ticker, Name, MarketCap, Price, High52, Low52, Low52Date, ATH, FromHigh52, FromATH, OffLow52, R1D, R1W, R1M, R3M, R6M, R1Y, R3Y, InIndex, IsPTH, IsATH, IsFallen, Spark, ListedDate`

Cell values: floats rounded to 2 dp, NaN → `""`, bools → `TRUE`/`FALSE` (written with `value_input_option="RAW"`), dates → `YYYY-MM-DD`, `InIndex` → `""` when the list is missing. `Spark` holds the last 63 closes up to the session, comma-joined at 2 dp.

---

### Task 1: Scaffold + metrics core

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.streamlit/config.toml`, `stockmonitor/__init__.py`, `stockmonitor/config.py`, `stockmonitor/metrics.py`, `tests/conftest.py`, `tests/test_metrics.py`
- Modify: `.gitignore` (add `cache/`)

**Interfaces:**
- Produces: `config.*` constants as named in Global Constraints:
  - `SHEET_ID`, `TABS = {"US": "H&L US", "IN": "H&L India"}`, `US_MCAP_FLOOR`, `IN_MCAP_FLOOR`
  - `NEAR_HIGH_PCT = 5.0`, `FALLEN_MIN_PCT = 80.0`, `FALLEN_MAX_PCT = 90.0`, `NO_NEW_LOW_SESSIONS = 10`, `GAP_SCREEN_PCT = 50.0`
  - `SPARK_POINTS = 63`, `SPARK_SHORT = 22`, `PRICE_BATCH_SIZE = 100`, `US_EXCHANGES`, `SESSION_REFERENCE`, `COLUMNS`, `COVERAGE_WARN = 0.90`, `CACHE_DIR = "cache"`
- Produces: `metrics.compute_metrics(close: pd.Series, session: pd.Timestamp) -> dict | None`
  - `close`: tz-naive `DatetimeIndex`, sorted, NaNs removed. Closes after `session` are ignored.
  - Returns a dict keyed by `COLUMNS[3:]` minus `InIndex`, plus `GapScreened: bool`. `Low52Date` and `ListedDate` are `pd.Timestamp` (or `None` for `ListedDate`). Returns are floats (`nan` when unreachable).

- [ ] **Step 1: Set up the environment.**
  - Create the venv: `"D:/Projects/Data Bot/.venv/Scripts/python.exe" -m venv .venv`.
  - `requirements.txt`: `streamlit>=1.40`, `pandas>=2.0`, `numpy>=1.24`, `yfinance>=1.2`, `gspread>=6.0`, `google-auth>=2.0`, `requests>=2.28`, `lxml>=5.0`.
  - `requirements-dev.txt`: `-r requirements.txt`, then `pytest>=8`.
  - Install with `.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`.
  - Copy `D:\Projects\Data Bot\service_account.json` into the repo root, and `D:\Projects\Data Bot\.streamlit\secrets.toml` to `.streamlit/secrets.toml`. Both are git-ignored, so check `git status` doesn't list them.
  - Write `.streamlit/config.toml` with `[theme] base="light"`, `primaryColor="#00a86b"`, `backgroundColor="#f7f8fa"`, `font="sans serif"`.

- [ ] **Step 2: Write the failing tests in `tests/test_metrics.py`.**
  `conftest.py` provides `make_series(values, end="2026-10-16") -> pd.Series` over `pd.bdate_range(end=end, periods=len(values))`. `SESSION = pd.Timestamp("2026-10-16")`.

```python
def test_pth_within_5pct():          # 300 closes rising to 100, last 96
    m = compute_metrics(s, SESSION); assert m["FromHigh52"] == pytest.approx(-4.0); assert m["IsPTH"]
def test_pth_boundary():             # last 95.0 -> IsPTH True; last 94.9 -> False
def test_ath_uses_full_history():    # 200 three years back, 52w high 100, last 99
    assert m["IsPTH"] and not m["IsATH"]; assert m["FromATH"] == pytest.approx(-50.5)
def test_fallen_true():              # 52w high 100, low 12 set 20 sessions ago, last 15
    assert m["FromHigh52"] == pytest.approx(-85.0); assert m["IsFallen"]
    assert m["OffLow52"] == pytest.approx(25.0)
def test_fallen_recent_low_excluded():   # same, but the low was 5 sessions ago -> not IsFallen
def test_fallen_band_edges():        # last 25 (-75%) -> False; last 9 (-91%) -> False; last 20 (-80%) -> True
def test_gap_screened():             # one session close/prev = 0.4 inside the 52w window
    assert m["GapScreened"] and not m["IsFallen"]
def test_short_history_listed_date():    # 100 sessions only
    assert m["ListedDate"] == s.index[0]; assert math.isnan(m["R1Y"]) and math.isnan(m["R6M"])
    assert not math.isnan(m["R3M"])
def test_full_history_no_listed_date():  # 400 sessions -> ListedDate is None
def test_no_bar_on_session_returns_none():   # series ends 2026-10-15 -> None
def test_ignores_closes_after_session(): # extra bar on 2026-10-19 -> Price is the 2026-10-16 close
def test_returns_1d_1w():            # last six closes 100,101,102,103,104,110
    assert m["R1D"] == pytest.approx(5.769, abs=1e-3); assert m["R1W"] == pytest.approx(10.0)
def test_spark():                    # 300 closes -> 63 comma-separated values, last == f"{price:.2f}"
```

- [ ] **Step 3: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -q`. Expected: errors, because `stockmonitor.metrics` doesn't exist yet.

- [ ] **Step 4: Implement `compute_metrics` in `stockmonitor/metrics.py`.** These rules aren't fixed by the signature:
  - Trim to closes ≤ `session`. Return `None` if the last trimmed date isn't `session`, or if there are fewer than 2 closes.
  - 52-week window = closes with date ≥ `session - pd.DateOffset(years=1)`. `Low52Date` is the **last** date the window's minimum occurs.
  - `R1D` uses the previous close. `R1W` uses `iloc[-6]` (`nan` if fewer than 6 closes). `R1M`, `R3M`, `R6M`, `R1Y`, `R3Y` use the last close ≤ `session - DateOffset(...)`, and are `nan` if the series starts after that target.
  - Not a new low = `Low52Date` falls before the date of `trimmed.iloc[-10]`.
  - `GapScreened` = any `close / prev_close < 1 - GAP_SCREEN_PCT/100` inside the 52-week window.
  - `ListedDate` = first date if `session - first < 365 days`, otherwise `None`.

- [ ] **Step 5: Run the tests and confirm they pass.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_metrics.py -q`. Expected: all pass.

- [ ] **Step 6: Commit and push.**
  `git add -A && git commit -m "Add project scaffold and the metrics core" && git push`. Then confirm `git status` doesn't show `service_account.json` or `secrets.toml` as tracked.

### Task 2: History download (copied from `stocks_data.py`)

**Files:**
- Create: `stockmonitor/history.py`, `tests/test_history.py`

**Interfaces:**
- Consumes: `config.SESSION_REFERENCE`
- Produces:
  - `is_market_open(market: str) -> bool` (`"US"` / `"IN"`)
  - `latest_settled_session(market: str) -> pd.Timestamp | None`
  - `download_batch(symbols: list[str], period: str = "max") -> pd.DataFrame | None`
  - `extract_close(data: pd.DataFrame, symbol: str, n_symbols: int) -> pd.Series`: tz-naive, sorted, NaN Close filled from `Adj Close`, then dropped. Returns an empty Series if the symbol is missing.

- [ ] **Step 1: Write the failing tests.**

```python
def test_download_retries_until_coverage(monkeypatch):
    # fake yf.download: 1st call all-NaN frame, 2nd call full frame; time.sleep patched out
    assert download_batch(["A","B"]) is second_frame; assert calls == 2
def test_download_splits_large_batch(monkeypatch):
    # 120 symbols, every full-batch call all-NaN, chunk calls of <=50 return data
    out = download_batch(syms); assert set(out.columns.get_level_values(0)) == set(syms)
def test_extract_close_fills_adj_and_strips_tz():
    # multi-index frame, tz-aware index, last Close NaN but Adj Close 101.0
    s = extract_close(df, "A", 2); assert s.index.tz is None; assert s.iloc[-1] == 101.0
def test_extract_close_missing_symbol_empty():
    assert extract_close(df, "ZZZ", 2).empty
def test_latest_settled_session_drops_today_when_open(monkeypatch):
    # is_market_open -> True; reference history includes today's bar -> returns the previous day
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_history.py -q`. Expected: import errors.

- [ ] **Step 3: Implement.**
  - Port `_download_batch_with_retry`, `_latest_settled_session` and `_is_market_open` from `D:\Projects\Data Bot\stocks_data.py` (lines ~552–690) as module functions, keeping behaviour identical.
  - Keep the coverage thresholds: ≥ 0.9 accept, retry waits of 5s and 10s, split into chunks of 50 with ≥ 0.5 accept.
  - Keep `auto_adjust=False` and `group_by="ticker"`.
  - Write `extract_close` from the per-symbol block at lines ~771–810.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_history.py -q`. Expected: all pass.

- [ ] **Step 5: Commit and push.**
  `git commit -m "Add throttle-safe history download and session resolution"`, then push.

### Task 3: Universes and index membership

**Files:**
- Create: `stockmonitor/universe.py`, `tests/test_universe.py`

**Interfaces:**
- Consumes: `config` floors, `US_EXCHANGES`, `CACHE_DIR`
- Produces:
  - `@dataclass Stock: symbol: str, ticker: str, name: str, mcap: float`. `symbol` is the yfinance form (`RELIANCE.NS`); `ticker` is the display form (`RELIANCE`).
  - `us_universe() -> list[Stock]`
  - `india_universe() -> list[Stock]`
  - `index_members(market: str) -> set[str] | None`: a set of yfinance symbols, or `None` if unavailable.
  - Cache helpers `_load_cache(name, max_age_h) / _save_cache(name, obj)` writing pickle files under `CACHE_DIR`. Universe files have a 24h TTL and index files 168h. A stale cache is only used after a failed fetch.

- [ ] **Step 1: Write the failing tests.** `yf.screen`, `requests.get` and `yf.Ticker` are monkeypatched, so there's no network.

```python
def test_us_universe_filters(monkeypatch):
    # fake screen pages (250 + 60 quotes) incl. JPM-PC, DJTWW, an ETF, BRK-B, dup AAPL
    tickers = [s.ticker for s in us_universe()]
    assert "BRK-B" in tickers and "JPM-PC" not in tickers and "DJTWW" not in tickers
    assert tickers.count("AAPL") == 1 and all(s.mcap >= 1e9 for s in us_universe())
def test_us_universe_pages(monkeypatch):     # asserts offsets 0 and 250 were requested
def test_us_universe_stale_cache_on_failure(monkeypatch, tmp_path):
    # screen raises; a cache file older than 24h exists -> its stocks are returned
def test_india_universe_merges_csv_and_screener(monkeypatch):
    # CSV: AAA (EQ), BBB (EQ), CCC (BE -> dropped); screener has AAA.NS 6e9; BBB.NS missing
    # fast_info fallback gives BBB.NS 7e9; SEDEMAC added from manual list via fallback
    stocks = {s.ticker: s for s in india_universe()}
    assert set(stocks) >= {"AAA", "BBB"} and "CCC" not in stocks
    assert stocks["AAA"].name == "Aaa Ltd."   # name taken from the CSV, not the screener
def test_india_floor(monkeypatch):           # a 4e9 INR stock is excluded
def test_index_members_sp500(monkeypatch):   # fake Wikipedia HTML with BRK.B, MSFT
    assert index_members("US") == {"BRK-B", "MSFT"}
def test_index_members_nifty(monkeypatch):   # fake CSV Symbol AAA -> {"AAA.NS"}
def test_index_members_none_without_cache(monkeypatch, tmp_path):
    # requests.get raises, no cache -> None
def test_index_members_stale_cache(monkeypatch, tmp_path):   # raises, old cache -> cached set
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_universe.py -q`. Expected: import errors.

- [ ] **Step 3: Implement `stockmonitor/universe.py`.**
  - **US:** `yf.EquityQuery` with region `us`, `is-in` the exchange list, and `intradaymarketcap` ≥ `US_MCAP_FLOOR`. Page with `size=250`. Use quote `marketCap` for `mcap`, and `longName` (falling back to `shortName`) title-cased for the name.
  - **India:** load the NSE CSV with headers `User-Agent` (browser string from `stocks_data.py`) and `Referer: https://www.nseindia.com/`. Pull screener quotes for region `in` and exchange `NSI` with cap ≥ `0.8 * IN_MCAP_FLOOR`. For symbols in the CSV but missing from the screener, try `yf.Ticker(sym).fast_info.market_cap` one at a time with a 0.15s pause. Then apply the floor.
  - **S&P 500:** `requests.get` with a browser UA, then `pd.read_html(io.StringIO(text))`. Take the first table with a `Symbol` column.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_universe.py -q`. Expected: all pass.

- [ ] **Step 5: Smoke test against the live network.**
  Run `.venv/Scripts/python.exe -c "from stockmonitor.universe import *; print(len(us_universe()), len(india_universe()), len(index_members('US') or []), len(index_members('IN') or []))"`.
  Expected roughly: `2600–2800  730–750  ~503  ~500`.

- [ ] **Step 6: Commit and push.**
  `git commit -m "Add US/India universes and index membership"`, then push.

### Task 4: Data job + sheet writer + CLI

**Files:**
- Create: `stockmonitor/sheets.py`, `stockmonitor/job.py`, `highs_data.py`, `tests/test_job.py`

**Interfaces:**
- Consumes:
  - `universe.us_universe/india_universe/index_members`, `Stock`
  - `history.latest_settled_session/download_batch/extract_close`
  - `metrics.compute_metrics`, `config.*`
- Produces:
  - `sheets.open_sheet(service_file: str = "service_account.json") -> gspread.Spreadsheet`
  - `sheets.get_or_create_ws(sh, title: str) -> gspread.Worksheet`: creates the tab with 1000 rows × `len(COLUMNS)` cols if missing.
  - `job.build_rows(stocks: list[Stock], members: set[str] | None, session: pd.Timestamp) -> tuple[list[dict], dict]`
    - Rows are keyed by `COLUMNS` and only include stocks with any of `IsPTH`, `IsATH`, `IsFallen`.
    - The stats dict has keys `universe: int`, `priced: int`, `stale: int`, `screened: list[str]`.
  - `job.write_tab(ws, rows: list[dict], price_label: str, updated_label: str, stats: dict, index_ok: bool) -> None`
  - `job.run(markets: list[str]) -> int`: returns exit code 0, or 1 if any market wrote nothing.
  - `highs_data.py`: `--us-only` → `["US"]`, `--india-only` → `["IN"]`, default `["US", "IN"]`. Runs `sys.exit(job.run(...))`.

- [ ] **Step 1: Write the failing tests.** Use a fake worksheet that records `clear()` and `update(range, values, value_input_option)`, and monkeypatch `download_batch` to return synthetic frames.

```python
def test_write_tab_layout():
    write_tab(ws, rows, "Price as on Oct 16, 2026  (Close)", "Updated ...", {"universe": 10, "priced": 9, "stale": 1, "screened": []}, True)
    assert ws.cleared; v = ws.updates[0].values
    assert v[0][0].startswith("Price as on") and v[0][2:6] == ["Universe", 10, "IndexList", "OK"]
    assert v[1][2:4] == ["Priced", 9]; assert v[2] == COLUMNS; assert ws.updates[0].opt == "RAW"
def test_write_tab_cell_values():   # nan -> "", True -> True, Timestamp -> "2026-09-01", 1.23456 -> 1.23
def test_write_tab_index_missing():  # index_ok False -> F1 "MISSING" and every InIndex == ""
def test_build_rows_keeps_flagged_only(monkeypatch):
    # three symbols: one PTH-shaped, one flat mid-range, one Fallen-shaped -> 2 rows
def test_build_rows_counts_stale(monkeypatch):   # one symbol's series ends before session -> stats["stale"] == 1
def test_build_rows_logs_screened(monkeypatch):  # gap-screened fallen candidate -> its ticker in stats["screened"]
def test_build_rows_in_index(monkeypatch):       # members={"AAA"} -> AAA InIndex True, BBB False; members=None -> ""
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_job.py -q`. Expected: import errors.

- [ ] **Step 3: Implement.**
  - `build_rows` batches `PRICE_BATCH_SIZE` symbols at a time.
  - `run` prints, for each market: universe size, then per batch `Batch i/n... got/len`, with a `[LOW YIELD]` suffix below 80% (as in `stocks_data.py`).
  - It then prints the stale count and the screened tickers, and `[LOW COVERAGE] priced/universe = xx%` when below `COVERAGE_WARN`.
  - The labels use `stocks_data.py`'s formats: `Price as on {Mon} {d}, {yyyy}  (Close)` and `Updated {Mon} {d}, {yyyy}  ·  {h}:{MM} {AM/PM} IST`.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run `.venv/Scripts/python.exe -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Real run, India first because it's smaller.**
  - Run `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -u highs_data.py --india-only`. Expected: exit 0, coverage ≥ 90%, and an `H&L India` tab with A1 dated to the latest NSE session.
  - Then run `--us-only` and expect the same for `H&L US`.
  - Spot-check 3 rows of each tab against yfinance closes.

- [ ] **Step 6: Commit and push.**
  `git commit -m "Add the highs_data job and sheet writer"`, then push.

### Task 5: App data layer

**Files:**
- Create: `ui/__init__.py`, `ui/data.py`, `tests/test_ui_data.py`

**Interfaces:**
- Consumes: the tab layout above, and `config.TABS` / `COLUMNS`
- Produces:
  - `@dataclass MarketData: df: pd.DataFrame, price_label: str, session: pd.Timestamp | None, universe: int, priced: int, index_ok: bool` (`session` parsed from `price_label`, `None` if unparseable)
  - `parse_tab(values: list[list[str]]) -> MarketData`: pure. Numbers become floats (`""` → NaN). `TRUE`/`FALSE` become bools, and `InIndex` `""` becomes NaN. Date columns become Timestamps or NaT. `Spark` becomes `list[float]`.
  - `load_market(market: str) -> MarketData`: `@st.cache_data(ttl=1800)`. Credentials come from `st.secrets["GOOGLE_SERVICE_ACCOUNT"]`, and it reads `ws.get_all_values()`.
  - `view_rows(md: MarketData, view: str, index_only: bool) -> pd.DataFrame`, where `view` is one of `"pth"`, `"ath"`, `"fallen"`:
    - Filters on the view's flag, plus `InIndex == True` when `index_only`.
    - Sort: pth by `FromHigh52` descending; ath by `R1W` descending; fallen by `OffLow52` descending.
  - `view_counts(md, index_only) -> dict[str, int]` keyed by `pth`, `ath`, `fallen`.

- [ ] **Step 1: Write the failing tests.**

```python
def test_parse_tab_meta():       # A1/A2/D1/D2/F1 -> price_label, session=2026-10-16, universe=10, priced=9, index_ok True
def test_parse_tab_types():      # "12.5"->12.5, ""->nan, "TRUE"->True, Spark "1,2,3"->[1.0,2.0,3.0]
def test_parse_tab_empty_body(): # only rows 1-3 -> empty df with COLUMNS
def test_view_rows_sort_and_filter():   # pth sorted -0.4, -1.2, -4.1; fallen sorted by OffLow52 desc
def test_view_rows_index_only(): # only InIndex True rows
def test_view_counts():          # {"pth": 2, "ath": 1, "fallen": 1}
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_ui_data.py -q`. Expected: import errors.

- [ ] **Step 3: Implement `ui/data.py`.**

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run the same command. Expected: all pass.

- [ ] **Step 5: Commit and push.**
  `git commit -m "Add the app data layer"`, then push.

### Task 6: Row rendering

**Files:**
- Create: `ui/render.py`, `tests/test_render.py`

**Interfaces:**
- Consumes: the rows from `view_rows`
- Produces:
  - `fmt_mcap(v: float, market: str) -> str`: US `$4.97T` / `$130B` / `$950M`; India `₹1,23,456 Cr` (Indian digit grouping).
  - `fmt_pct(v: float, signed: bool = True) -> str`: `+1.1%` / `−0.4%` with a true minus sign; NaN → `—`.
  - `sparkline_svg(points: list[float], width: int = 64, height: int = 20, color: str | None = None) -> str`: green `#00a86b` if last ≥ first, else `#e5484d`, unless `color` is given. Empty input → `""`.
  - `rows_html(df: pd.DataFrame, view: str, market: str, session: pd.Timestamp | None) -> str`: one `<details class="sm-row">` per stock. Empty `df` → `<div class="sm-empty">No stocks match right now.</div>`.
  - `STYLES: str`: one `<style>` block for the whole page.

  What each row shows:
  - **Summary:** ticker, then name · market cap.
  - **Trend line:** the last `SPARK_SHORT` points for pth/ath, all 63 in grey `#8994a7` for fallen.
  - **Key column:** pth `FromHigh52`, ath `FromATH`, fallen `FromHigh52` in red.
  - **Right column:** price with 1W% for pth/ath. For fallen, `OffLow52` in green.
  - **Fallen subtitle:** "low N days ago", in calendar days from `Low52Date` to `session` (omitted when `session` is None).
  - **Panel:**
    - a 7-tile returns strip (1D, 1W, 1M, 3M, 6M, 1Y, 3Y)
    - the 52-week range bar, with the dot at `(Price-Low52)/(High52-Low52)` clamped to 0–100%
    - facts: all-time high, market cap, and "In S&P 500" / "In NIFTY 500" when `InIndex` is True
    - a small `Listed <Mon d, yyyy>` note under the range bar when `ListedDate` is set

- [ ] **Step 1: Write the failing tests.**

```python
def test_empty_state():            assert "No stocks match right now." in rows_html(empty_df, "fallen", "US", SESSION)
def test_names_escaped():          # Name "AT&T <Inc>" -> "AT&amp;T &lt;Inc&gt;" present, raw "<Inc>" absent
def test_listed_note_rendered():   # ListedDate 2026-03-02 -> "Listed Mar 2, 2026"; NaT -> no "Listed"
def test_range_bar_position():     # Low52 50, High52 150, Price 125 -> 'left:75.0%'
def test_returns_strip_has_seven(): # 7 occurrences of class="sm-ret"
def test_fallen_key_columns():     # shows FromHigh52 "−85.0%" and OffLow52 "+25.0%", "low 18 days ago"
def test_fmt_mcap():               # (4.97e12,"US")->"$4.97T"; (1.23456e12,"IN")->"₹1,23,456 Cr"
def test_sparkline_colour():       # rising -> '#00a86b'; falling -> '#e5484d'; [] -> ""
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_render.py -q`. Expected: import errors.

- [ ] **Step 3: Implement `ui/render.py`.**
  - Escape every text field with `html.escape`.
  - Copy the CSS values from `row-expand.html`.
  - Make sure rows work at 360px width: the name truncates with an ellipsis, and the returns strip wraps into 4+3 below 480px.

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run the same command. Expected: all pass.

- [ ] **Step 5: Commit and push.**
  `git commit -m "Add row rendering"`, then push.

### Task 7: The Streamlit app

**Files:**
- Create: `app.py`, `tests/test_app.py`, `README.md`

**Interfaces:**
- Consumes: `ui.data.load_market/view_rows/view_counts/MarketData`, and `ui.render.rows_html/STYLES`
- Session state:
  - `st.session_state["view"]` ∈ `{"pth","ath","fallen"}`, default `"pth"`
  - market control `key="market"`, options `["🇺🇸 US", "🇮🇳 India"]`
  - index control `key=f"index_{market}"`, options `["S&P 500", "All"]` / `["NIFTY 500", "All"]`, defaulting to the index

- [ ] **Step 1: Write the failing tests** using `streamlit.testing.v1.AppTest.from_file("app.py")`, with `ui.data.load_market` monkeypatched to return fixture `MarketData`.

```python
def test_tiles_show_counts():          # rendered tile labels contain "48", "31", "3" for the fixture
def test_tile_click_switches_view():   # click the Fallen tile button -> session_state["view"] == "fallen"
def test_market_switch_changes_index_options():   # India -> selectbox options ["NIFTY 500", "All"]
def test_index_missing_offers_only_all():   # index_ok False -> options ["All"] and caption mentions the list is unavailable
def test_low_coverage_warning():       # priced/universe = 0.6 -> warning text contains "60%"
def test_header_shows_session():       # "Close · Oct 16" rendered from price_label
```

- [ ] **Step 2: Run the tests and confirm they fail.**
  Run `.venv/Scripts/python.exe -m pytest tests/test_app.py -q`. Expected: failures, because `app.py` doesn't exist.

- [ ] **Step 3: Implement `app.py`.**
  - `st.set_page_config(page_title="Stock Monitor", page_icon="📈", layout="centered")`, then inject `STYLES`.
  - **Header:** "Highs & Lows" on the left, and on the right a pill `● Close · <Mon d>` parsed from `price_label`.
  - **Controls row:** `st.segmented_control` for the market, `st.selectbox` for the index.
  - **Tiles:** three `st.columns`. Each holds an `st.container(key=f"tile_{view}")` with an `st.button`, labelled with the tile title and its count. CSS targets `.st-key-tile_*`, and the selected tile gets the green fill (`#00a86b`, white text).
    - Titles: "Near 52w high" / "All-time high" / "Fallen, stabilising".
    - Captions: "PTH · within 5%" / "ATH · within 5%" / "down 80–90%".
  - **Warning:** a coverage warning when `priced/universe < COVERAGE_WARN`: "Only N% of <US|India> stocks could be priced in the last update — lists may be incomplete."
  - **List:** `st.html(rows_html(...))` inside a white rounded card.
  - **Error handling:** if `load_market` raises or the tab is missing, show "Data for <market> isn't available yet." instead of a traceback.
  - **README:** cover local run (`streamlit run app.py`), the job (`python highs_data.py`), and Streamlit Cloud deploy (repo `Lucifer464-code/StockMonitor`, main file `app.py`, paste the `[GOOGLE_SERVICE_ACCOUNT]` block from `.streamlit/secrets.toml` into the app's secrets).

- [ ] **Step 4: Run the tests and confirm they pass.**
  Run `.venv/Scripts/python.exe -m pytest -q`. Expected: all pass.

- [ ] **Step 5: Run it for real.**
  - Run `.venv/Scripts/python.exe -m streamlit run app.py` against the real tabs from Task 4.
  - Check at desktop and 390px widths that:
    - the tiles switch views
    - the index filter changes the counts
    - rows expand without a rerun
    - Fallen shows its empty state or rows
  - Take screenshots for the user.

- [ ] **Step 6: Commit and push.**
  `git commit -m "Add the Stock Monitor app"`, then push.

### Task 8: Hook the job into Data Bot's `run_all.py`

**Files:**
- Modify: `D:\Projects\Data Bot\run_all.py`, and nothing else in Data Bot.

**Interfaces:**
- Produces:
  - `STOCKMONITOR_ROOT = ROOT.parent / "StockMonitor"`
  - `FOLLOW_ON = {"stocks": ("highs", "highs_data.py")}`
  - The interpreter for the follow-on is `STOCKMONITOR_ROOT/.venv/Scripts/python.exe` if it exists, otherwise `sys.executable`.

- [ ] **Step 1: Write a scratch check script** (not committed) in the session scratchpad.
  - It imports `run_all` and points `STOCKMONITOR_ROOT` at a temp dir holding a dummy `highs_data.py` that prints `HIGHS RAN`.
  - It replaces `BATCH_JOBS` with one fake `stocks` job (`python -c "print('STOCKS RAN')"`).
  - It asserts that `run_all.main()` output has `STOCKS RAN` before `HIGHS RAN`, and that the summary lists `highs: ok`.

- [ ] **Step 2: Run the check and confirm it fails.**
  Expected: `HIGHS RAN` is missing.

- [ ] **Step 3: Implement the follow-on.**
  - Each top-level job gets a thread that runs it, streams its output, records its exit code, and then, if it has a `FOLLOW_ON` entry and the root folder exists, runs the follow-on the same way. The follow-on runs even if the parent job failed, because the two write independent data.
  - If the folder is missing, print `[run_all] StockMonitor not found — skipping highs`.
  - The live job keeps its current behaviour.
  - The summary lists the follow-on's exit code.
  - Update the module docstring.

- [ ] **Step 4: Run the check and confirm it passes.**
  Expected: correct order and `highs: ok`. Then run `python run_all.py -- --us-only` once for real and confirm `highs` starts only after `stocks` exits.

- [ ] **Step 5: Commit and push Data Bot, staging only `run_all.py`.**
  `git add run_all.py && git commit -m "run_all: run StockMonitor's highs job after stocks_data" && git push`. The user's other uncommitted changes stay unstaged.
