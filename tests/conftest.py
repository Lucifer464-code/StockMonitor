import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_series(values, end="2026-10-16"):
    """Business-day close series ending on `end`."""
    idx = pd.bdate_range(end=end, periods=len(values))
    return pd.Series([float(v) for v in values], index=idx)
