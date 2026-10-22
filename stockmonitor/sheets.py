"""Google Sheets access for the data job."""
import gspread
from google.oauth2.service_account import Credentials

from stockmonitor import config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def open_sheet(service_file: str = "service_account.json") -> gspread.Spreadsheet:
    creds = Credentials.from_service_account_file(service_file, scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(config.SHEET_ID)


def get_or_create_ws(sh, title: str) -> gspread.Worksheet:
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=1000, cols=len(config.COLUMNS))
