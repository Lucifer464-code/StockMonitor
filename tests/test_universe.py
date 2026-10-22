import os
import pickle
import time

import pytest

from stockmonitor import config, universe
from stockmonitor.universe import Stock, index_members, india_universe, us_universe


@pytest.fixture(autouse=True)
def cache_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(universe.time, "sleep", lambda s: None)
    return tmp_path


def q(sym, mcap=5e9, name="Some Co", qtype="EQUITY"):
    return {"symbol": sym, "marketCap": mcap, "longName": name, "quoteType": qtype}


def age_file(path, hours):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def test_us_universe_filters(monkeypatch):
    page1 = [q("AAPL", 3e12, "apple inc.")] * 2 + [q(f"X{chr(65 + i % 26)}{chr(65 + i // 26)}")
                                                   for i in range(248)]
    page1 = page1[:250]
    page2 = [q("BRK-B", 1e12), q("JPM-PC"), q("DJTWW"), q("SPY", qtype="ETF"),
             q("TINY", 5e8)] + [q(f"Y{chr(65 + i % 26)}{chr(65 + i // 26)}") for i in range(55)]
    pages = {0: page1, 250: page2}
    monkeypatch.setattr(universe.yf, "screen", lambda query, offset=0, size=250, **k:
                        {"quotes": pages[offset]})
    stocks = us_universe()
    tickers = [s.ticker for s in stocks]
    assert "BRK-B" in tickers and "JPM-PC" not in tickers and "DJTWW" not in tickers
    assert "SPY" not in tickers and "TINY" not in tickers
    assert tickers.count("AAPL") == 1 and all(s.mcap >= 1e9 for s in stocks)
    assert next(s for s in stocks if s.ticker == "AAPL").name == "Apple Inc."
    assert all(s.symbol == s.ticker for s in stocks)


def test_us_universe_pages(monkeypatch):
    offsets = []

    def fake(query, offset=0, size=250, **k):
        offsets.append(offset)
        return {"quotes": [q(f"A{i}".replace("0", "Z")) for i in range(250 if offset == 0 else 60)]}

    monkeypatch.setattr(universe.yf, "screen", fake)
    us_universe()
    assert offsets == [0, 250]


def test_us_universe_stale_cache_on_failure(monkeypatch, cache_dir):
    path = cache_dir / "us_universe.pkl"
    path.write_bytes(pickle.dumps([Stock("AAPL", "AAPL", "Apple", 3e12)]))
    age_file(path, 48)

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(universe.yf, "screen", boom)
    assert [s.ticker for s in us_universe()] == ["AAPL"]


def test_us_universe_fresh_cache_skips_fetch(monkeypatch, cache_dir):
    (cache_dir / "us_universe.pkl").write_bytes(pickle.dumps([Stock("AAPL", "AAPL", "Apple", 3e12)]))

    def boom(*a, **k):
        raise AssertionError("should not fetch")

    monkeypatch.setattr(universe.yf, "screen", boom)
    assert [s.ticker for s in us_universe()] == ["AAPL"]


class Resp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


NSE_CSV = ("Company Name,Industry,Symbol,Series,ISIN Code\n"
           "Aaa Ltd.,X,AAA,EQ,1\nBbb Ltd.,X,BBB,EQ,2\nCcc Ltd.,X,CCC,BE,3\n")


def patch_india(monkeypatch, screener, fast):
    monkeypatch.setattr(universe.requests, "get", lambda *a, **k: Resp(NSE_CSV))
    monkeypatch.setattr(universe.yf, "screen",
                        lambda query, offset=0, size=250, **k: {"quotes": screener if offset == 0 else []})

    class T:
        def __init__(self, sym):
            self.sym = sym

        @property
        def fast_info(self):
            if self.sym not in fast:
                raise KeyError(self.sym)
            return type("FI", (), {"market_cap": fast[self.sym]})()

    monkeypatch.setattr(universe.yf, "Ticker", T)


def test_india_universe_merges_csv_and_screener(monkeypatch):
    patch_india(monkeypatch, [q("AAA.NS", 6e9, "Screener Name")],
                {"BBB.NS": 7e9, "SEDEMAC.NS": 8e9})
    stocks = {s.ticker: s for s in india_universe()}
    assert set(stocks) >= {"AAA", "BBB", "SEDEMAC"} and "CCC" not in stocks
    assert stocks["AAA"].name == "Aaa Ltd." and stocks["AAA"].symbol == "AAA.NS"
    assert stocks["BBB"].mcap == 7e9
    assert stocks["SEDEMAC"].name == "SEDEMAC Mechatronics Ltd."


def test_india_floor(monkeypatch):
    patch_india(monkeypatch, [q("AAA.NS", 4e9)], {"BBB.NS": 7e9})
    assert {s.ticker for s in india_universe()} == {"BBB"}


def test_india_stale_cache_on_failure(monkeypatch, cache_dir):
    path = cache_dir / "in_universe.pkl"
    path.write_bytes(pickle.dumps([Stock("AAA.NS", "AAA", "Aaa", 6e9)]))
    age_file(path, 48)

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(universe.requests, "get", boom)
    assert [s.ticker for s in india_universe()] == ["AAA"]


WIKI = ("<html><body><table><tr><th>Other</th></tr><tr><td>x</td></tr></table>"
        "<table><tr><th>Symbol</th><th>Security</th></tr>"
        "<tr><td>BRK.B</td><td>Berkshire</td></tr><tr><td>MSFT</td><td>Microsoft</td></tr>"
        "</table></body></html>")


def test_index_members_sp500(monkeypatch):
    monkeypatch.setattr(universe.requests, "get", lambda *a, **k: Resp(WIKI))
    assert index_members("US") == {"BRK-B", "MSFT"}


def test_index_members_nifty(monkeypatch):
    monkeypatch.setattr(universe.requests, "get",
                        lambda *a, **k: Resp("Company Name,Symbol\nAaa,AAA\n"))
    assert index_members("IN") == {"AAA.NS"}


def test_index_members_none_without_cache(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(universe.requests, "get", boom)
    assert index_members("US") is None
    assert index_members("IN") is None


def test_index_members_stale_cache(monkeypatch, cache_dir):
    path = cache_dir / "index_US.pkl"
    path.write_bytes(pickle.dumps({"MSFT"}))
    age_file(path, 500)

    def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(universe.requests, "get", boom)
    assert index_members("US") == {"MSFT"}


# ── Coverage guards: a bad fetch must not shrink the universe unseen ──

def _us_pages(n, total=None):
    """Fake yf.screen serving n distinct valid quotes, reporting `total` (default n)."""
    quotes = [q("Q" + "".join(chr(65 + (i // 26 ** k) % 26) for k in range(3))) for i in range(n)]

    def fake(query, offset=0, size=250, **k):
        return {"quotes": quotes[offset:offset + size], "total": n if total is None else total}

    return fake


def _write_cache(cache_dir, name, n, hours=48):
    path = cache_dir / f"{name}.pkl"
    path.write_bytes(pickle.dumps([Stock(f"C{i}", f"C{i}", "Cached", 5e9) for i in range(n)]))
    age_file(path, hours)
    return path


def test_us_screen_short_of_total_uses_stale_cache(monkeypatch, cache_dir, capsys):
    path = _write_cache(cache_dir, "us_universe", 3)
    before = path.read_bytes()
    monkeypatch.setattr(universe.yf, "screen", _us_pages(260, total=600))
    assert [s.ticker for s in us_universe()] == ["C0", "C1", "C2"]
    assert path.read_bytes() == before
    assert "260 of 600" in capsys.readouterr().out


def test_us_screen_reaching_total_is_fresh(monkeypatch, cache_dir):
    monkeypatch.setattr(universe.yf, "screen", _us_pages(260))
    assert len(us_universe()) == 260


def test_universe_shrink_keeps_previous_cache(monkeypatch, cache_dir, capsys):
    path = _write_cache(cache_dir, "us_universe", 300)
    before = path.read_bytes()
    monkeypatch.setattr(universe.yf, "screen", _us_pages(260))
    got = us_universe()
    assert len(got) == 300 and got[0].ticker == "C0"
    assert path.read_bytes() == before
    out = capsys.readouterr().out
    assert "[LOW COVERAGE] US universe 260 vs previous 300" in out
    assert "using cached universe" in out


def test_universe_small_shrink_accepted(monkeypatch, cache_dir):
    _write_cache(cache_dir, "us_universe", 280)
    monkeypatch.setattr(universe.yf, "screen", _us_pages(260))
    assert len(us_universe()) == 260
    assert len(pickle.loads((cache_dir / "us_universe.pkl").read_bytes())) == 260


def test_india_empty_screener_uses_stale_cache(monkeypatch, cache_dir):
    _write_cache(cache_dir, "in_universe", 2)
    patch_india(monkeypatch, [], {})

    swept = []
    monkeypatch.setattr(universe.yf, "Ticker", lambda sym: swept.append(sym))
    assert [s.ticker for s in india_universe()] == ["C0", "C1"]
    assert swept == []


def test_india_fast_info_failures_logged(monkeypatch, capsys):
    # AAA from the screener; BBB and SEDEMAC fall back, and SEDEMAC fails.
    patch_india(monkeypatch, [q("AAA.NS", 6e9)], {"BBB.NS": 7e9})
    india_universe()
    assert "fast_info fallback: 1 of 2 failed" in capsys.readouterr().out


def test_india_skips_dummy_symbols(monkeypatch):
    csv = NSE_CSV + "Dummy Ltd.,X,DUMMYXYZ,EQ,4\n"
    patch_india(monkeypatch, [q("AAA.NS", 6e9)], {"BBB.NS": 7e9, "SEDEMAC.NS": 8e9})
    monkeypatch.setattr(universe.requests, "get", lambda *a, **k: Resp(csv))
    asked = []
    real = universe.yf.Ticker

    def spy(sym):
        asked.append(sym)
        return real(sym)

    monkeypatch.setattr(universe.yf, "Ticker", spy)
    tickers = {s.ticker for s in india_universe()}
    assert "DUMMYXYZ" not in tickers and "DUMMYXYZ.NS" not in asked
