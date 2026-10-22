"""App data layer: read an H&L tab into a typed MarketData, filter and sort per view."""
import re
from dataclasses import dataclass

import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

from stockmonitor import config
from stockmonitor.sheets import SCOPES

DATE_COLUMNS = ["Low52Date", "ListedDate"]
BOOL_COLUMNS = ["IsPTH", "IsATH", "IsFallen"]
TEXT_COLUMNS = ["Ticker", "Name"]
NUMBER_COLUMNS = [c for c in config.COLUMNS
                  if c not in DATE_COLUMNS + BOOL_COLUMNS + TEXT_COLUMNS + ["InIndex", "Spark"]]

# view -> (flag column, sort column); every view sorts descending.
VIEWS = {
    "pth": ("IsPTH", "FromHigh52"),
    "ath": ("IsATH", "R1W"),
    "fallen": ("IsFallen", "OffLow52"),
}

_LABEL_DATE = re.compile(r"Price as on (\w{3}) (\d{1,2}), (\d{4})")


@dataclass
class MarketData:
    df: pd.DataFrame
    price_label: str
    session: pd.Timestamp | None
    universe: int
    priced: int
    index_ok: bool


def _cell(row: list[str], i: int) -> str:
    return row[i].strip() if i < len(row) else ""


def _int(text: str) -> int:
    try:
        return int(float(text))
    except ValueError:
        return 0


def _session(label: str) -> pd.Timestamp | None:
    m = _LABEL_DATE.search(label)
    if not m:
        return None
    ts = pd.to_datetime(f"{m.group(1)} {m.group(2)} {m.group(3)}", format="%b %d %Y", errors="coerce")
    return None if pd.isna(ts) else ts


def _bool(text: str) -> bool:
    return text.upper() == "TRUE"


def _in_index(text: str):
    if text == "":
        return float("nan")
    return _bool(text)


def _spark(text: str) -> list[float]:
    out = []
    for part in text.split(","):
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out


def parse_tab(values: list[list[str]]) -> MarketData:
    """Pure: turn `get_all_values()` output into a MarketData."""
    r1 = values[0] if len(values) > 0 else []
    r2 = values[1] if len(values) > 1 else []
    label = _cell(r1, 0)
    body = values[3:]
    n = len(config.COLUMNS)
    padded = [(list(r) + [""] * n)[:n] for r in body]
    df = pd.DataFrame(padded, columns=config.COLUMNS, dtype=object)
    df = df.astype({c: object for c in config.COLUMNS})
    for c in NUMBER_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    for c in DATE_COLUMNS:
        df[c] = pd.to_datetime(df[c].replace("", None), errors="coerce")
    for c in BOOL_COLUMNS:
        df[c] = pd.Series([_bool(str(v).strip()) for v in df[c]], index=df.index, dtype=bool)
    df["InIndex"] = pd.Series([_in_index(str(v).strip()) for v in df["InIndex"]],
                              index=df.index, dtype=object)
    df["Spark"] = pd.Series([_spark(str(v)) for v in df["Spark"]], index=df.index, dtype=object)
    return MarketData(
        df=df,
        price_label=label,
        session=_session(label),
        universe=_int(_cell(r1, 3)),
        priced=_int(_cell(r2, 3)),
        index_ok=_cell(r1, 5).upper() == "OK",
    )


@st.cache_resource
def _client():
    info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_data(ttl=1800)
def load_market(market: str) -> MarketData:
    """Read one market's tab ("US" or "IN"). Raises if the tab is missing or unreadable."""
    ws = _client().open_by_key(config.SHEET_ID).worksheet(config.TABS[market])
    return parse_tab(ws.get_all_values())


def view_rows(md: MarketData, view: str, index_only: bool) -> pd.DataFrame:
    flag, sort_col = VIEWS[view]
    df = md.df
    mask = df[flag].astype(bool)
    if index_only:
        mask &= df["InIndex"].eq(True)
    return df[mask].sort_values(sort_col, ascending=False, na_position="last")


def view_counts(md: MarketData, index_only: bool) -> dict[str, int]:
    return {v: len(view_rows(md, v, index_only)) for v in VIEWS}
