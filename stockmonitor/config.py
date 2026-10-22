"""Constants shared by the data job and the app."""

SHEET_ID = "1uJoD2JRvzRpn2KHJa80aZADQ2DfRwm2qbZKMuv0PKBM"
TABS = {"US": "H&L US", "IN": "H&L India"}

US_MCAP_FLOOR = 1_000_000_000      # USD
IN_MCAP_FLOOR = 5_000_000_000      # INR (500 Cr)

NEAR_HIGH_PCT = 5.0
FALLEN_MIN_PCT = 80.0
FALLEN_MAX_PCT = 90.0
NO_NEW_LOW_SESSIONS = 10
GAP_SCREEN_PCT = 50.0

SPARK_POINTS = 63
SPARK_SHORT = 22
PRICE_BATCH_SIZE = 100
COVERAGE_WARN = 0.90
CACHE_DIR = "cache"
CONSENSUS_SHARE = 0.95             # share of series that must have a bar on the pricing session (>= COVERAGE_WARN)
CONSENSUS_WINDOW_DAYS = 30         # calendar days before the reference session searched for it

US_EXCHANGES = ["NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS"]

COLUMNS = [
    "Ticker", "Name", "MarketCap", "Price", "High52", "Low52", "Low52Date",
    "ATH", "FromHigh52", "FromATH", "OffLow52", "R1D", "R1W", "R1M", "R3M",
    "R6M", "R1Y", "R3Y", "InIndex", "IsPTH", "IsATH", "IsFallen", "Spark",
    "ListedDate",
]

# Universe sources and caching.
US_SCREEN_PAGE_SIZE = 250          # yfinance's per-request maximum
IN_SCREEN_MARGIN = 0.8             # screen at 0.8 x floor, apply the exact floor later
UNIVERSE_TTL_H = 24
UNIVERSE_SHRINK_LIMIT = 0.9        # a fresh universe below this share of the cached one is a failed fetch
INDEX_TTL_H = 168
FAST_INFO_PAUSE_S = 0.15
NIFTY_TOTAL_MARKET_URL = (
    "https://nsearchives.nseindia.com/content/indices/ind_niftytotalmarket_list.csv"
)
NIFTY_500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
# Recently listed stocks not yet in NSE's constituent CSV: {SYMBOL: Company Name}.
IN_MANUAL_ADDITIONS = {"SEDEMAC": "SEDEMAC Mechatronics Ltd."}
