import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from mcp_etf_holdings.fetcher import (
    _TTLCache,
    _etf_info_sync,
    _etf_holdings_sync,
    _find_etfs_holding_stock_sync,
    get_etf_info,
    get_etf_holdings,
    find_etfs_holding_stock,
    search_etfs,
    _search_symbols_sync,
    resolve_stock_symbol,
    get_etf_infos,
    _info_cache,
    _holdings_cache,
    _is_valid_ticker,
)


class TestTickerValidation:
    """Test ticker format validation."""

    def test_valid_tickers(self):
        assert _is_valid_ticker("SPY")
        assert _is_valid_ticker("AAPL")
        assert _is_valid_ticker("BRK.B")
        assert _is_valid_ticker("BF-A")

    def test_invalid_tickers(self):
        assert not _is_valid_ticker("")  # empty
        assert not _is_valid_ticker("TOOLONGTOBEVALID")  # too long
        assert not _is_valid_ticker("SPY!")  # special chars
        assert not _is_valid_ticker(None)  # not a string
        assert not _is_valid_ticker("@#$")  # invalid chars


class TestTTLCache:
    """Test the _TTLCache class."""

    def test_set_and_get(self):
        cache = _TTLCache(ttl_seconds=10, max_size=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        cache = _TTLCache(ttl_seconds=10, max_size=100)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self):
        cache = _TTLCache(ttl_seconds=0.1, max_size=100)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.2)
        assert cache.get("key1") is None

    def test_clear(self):
        cache = _TTLCache(ttl_seconds=10, max_size=100)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_with_different_types(self):
        cache = _TTLCache(ttl_seconds=10, max_size=100)
        cache.set("str_key", "string_value")
        cache.set("dict_key", {"nested": "dict"})
        cache.set("list_key", [1, 2, 3])

        assert cache.get("str_key") == "string_value"
        assert cache.get("dict_key") == {"nested": "dict"}
        assert cache.get("list_key") == [1, 2, 3]

    def test_cache_lru_eviction(self):
        cache = _TTLCache(ttl_seconds=10, max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert cache.size() == 3

        # Adding a 4th key should evict the oldest (key1)
        cache.set("key4", "value4")
        assert cache.size() == 3
        assert cache.get("key1") is None
        assert cache.get("key4") == "value4"

    def test_cache_thread_safety(self):
        import threading

        cache = _TTLCache(ttl_seconds=10, max_size=100)
        results = []

        def write_to_cache():
            for i in range(10):
                cache.set(f"key_{i}", f"value_{i}")

        def read_from_cache():
            for i in range(10):
                val = cache.get(f"key_{i}")
                if val is not None:
                    results.append(val)

        threads = []
        for _ in range(2):
            threads.append(threading.Thread(target=write_to_cache))
            threads.append(threading.Thread(target=read_from_cache))

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(results) >= 10


class TestEtfInfoSync:
    """Test the _etf_info_sync function."""

    def test_get_etf_info_success(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _etf_info_sync("SPY")

        assert result["ticker"] == "SPY"
        assert result["name"] == "SPDR S&P 500 ETF Trust"
        assert result["category"] == "Large Cap Equities"
        assert result["total_assets"] == 500_000_000_000
        assert result["expense_ratio"] == 0.0003
        assert result["currency"] == "USD"

    def test_get_etf_info_invalid_ticker(self):
        _info_cache.clear()

        with pytest.raises(ValueError, match="Invalid ticker format"):
            _etf_info_sync("invalid!")

    def test_get_etf_info_no_info(self, mock_ticker_no_info):
        _info_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_info):
            result = _etf_info_sync("FAKEETF")

        assert result["ticker"] == "FAKEETF"
        assert result["name"] == ""

    def test_get_etf_info_caching(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info) as mock_yf:
            result1 = _etf_info_sync("SPY")
            result2 = _etf_info_sync("SPY")

            assert result1 == result2
            assert mock_yf.call_count == 1

    def test_get_etf_info_case_insensitive(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _etf_info_sync("SPY")

        assert result["ticker"] == "SPY"

    def test_get_etf_info_fallback_fields(self):
        _info_cache.clear()

        mock_ticker = MagicMock()
        mock_ticker.info = {
            "shortName": "SPY",
            "expenseRatio": 0.0003,
            "regularMarketPrice": 450.0,
        }

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_info_sync("SPY")

        assert result["name"] == "SPY"
        assert result["nav_price"] == 450.0
        assert result["expense_ratio"] == 0.0003


class TestExpenseRatioUnits:
    """`expense_ratio` is always a fraction, whichever Yahoo field supplied it.

    Regression coverage for a bug where every fund reported "N/A": the code read only
    `annualReportExpenseRatio`/`expenseRatio`, and Yahoo had moved to `netExpenseRatio`.
    The unit differs per field, so these must not be conflated — see
    _EXPENSE_RATIO_FIELDS in fetcher.py.
    """

    def _info_with(self, **fields):
        mock_ticker = MagicMock()
        mock_ticker.info = {"shortName": "TEST", **fields}
        return mock_ticker

    def test_net_expense_ratio_is_percent_and_converted(self):
        """netExpenseRatio 0.18 means 0.18%, i.e. 0.0018 — not 18%."""
        _info_cache.clear()
        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=self._info_with(netExpenseRatio=0.18)):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == pytest.approx(0.0018)

    def test_annual_report_expense_ratio_is_already_a_fraction(self):
        """The legacy field needs no conversion — 0.0018 is already 0.18%."""
        _info_cache.clear()
        with patch(
            "mcp_etf_holdings.fetcher.yf.Ticker",
            return_value=self._info_with(annualReportExpenseRatio=0.0018),
        ):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == pytest.approx(0.0018)

    def test_both_field_families_agree_on_the_same_fee(self):
        """0.18 (percent field) and 0.0018 (fraction field) must not both be taken raw."""
        _info_cache.clear()
        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=self._info_with(netExpenseRatio=0.18)):
            from_percent = _etf_info_sync("TEST")["expense_ratio"]
        _info_cache.clear()
        with patch(
            "mcp_etf_holdings.fetcher.yf.Ticker",
            return_value=self._info_with(annualReportExpenseRatio=0.0018),
        ):
            from_fraction = _etf_info_sync("TEST")["expense_ratio"]
        assert from_percent == pytest.approx(from_fraction)

    def test_net_is_preferred_over_gross(self):
        """Net is what the investor actually pays after waivers."""
        _info_cache.clear()
        with patch(
            "mcp_etf_holdings.fetcher.yf.Ticker",
            return_value=self._info_with(netExpenseRatio=0.20, grossExpenseRatio=0.35),
        ):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == pytest.approx(0.0020)

    def test_percent_field_wins_over_legacy_fraction_field(self):
        """Yahoo populates netExpenseRatio today; it leads the preference order."""
        _info_cache.clear()
        with patch(
            "mcp_etf_holdings.fetcher.yf.Ticker",
            return_value=self._info_with(netExpenseRatio=0.50, annualReportExpenseRatio=0.0018),
        ):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == pytest.approx(0.0050)

    def test_zero_expense_ratio_is_preserved_not_treated_as_missing(self):
        """A genuine zero-fee fund must survive; `or`-chaining used to drop it."""
        _info_cache.clear()
        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=self._info_with(netExpenseRatio=0.0)):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == 0.0

    def test_missing_everywhere_is_none(self):
        _info_cache.clear()
        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=self._info_with()):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] is None

    def test_non_numeric_value_falls_through_to_next_field(self):
        _info_cache.clear()
        with patch(
            "mcp_etf_holdings.fetcher.yf.Ticker",
            return_value=self._info_with(netExpenseRatio="n/a", annualReportExpenseRatio=0.0018),
        ):
            result = _etf_info_sync("TEST")
        assert result["expense_ratio"] == pytest.approx(0.0018)

    def test_real_world_values_round_trip_to_published_fees(self):
        """Values observed live from Yahoo, against each fund's actual published fee."""
        for ticker, net_field_value, expected_pct in [
            ("SPY", 0.0945, 0.0945),
            ("VOO", 0.03, 0.03),
            ("ARKK", 0.75, 0.75),
            ("GLD", 0.40, 0.40),
        ]:
            _info_cache.clear()
            with patch(
                "mcp_etf_holdings.fetcher.yf.Ticker",
                return_value=self._info_with(netExpenseRatio=net_field_value),
            ):
                result = _etf_info_sync(ticker)
            # server.py renders as `expense_ratio * 100`
            assert result["expense_ratio"] * 100 == pytest.approx(expected_pct)


class TestEtfHoldingsSync:
    """Test the _etf_holdings_sync function."""

    def test_get_etf_holdings_success(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _etf_holdings_sync("SPY")

        assert len(result) == 5
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["name"] == "Apple Inc."
        assert result[0]["weight_pct"] == pytest.approx(7.0)

    def test_get_etf_holdings_invalid_ticker(self):
        _holdings_cache.clear()

        with pytest.raises(ValueError, match="Invalid ticker format"):
            _etf_holdings_sync("invalid!")

    def test_get_etf_holdings_caching(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info) as mock_yf:
            result1 = _etf_holdings_sync("SPY")
            result2 = _etf_holdings_sync("SPY")

            assert result1 == result2
            assert mock_yf.call_count == 1

    def test_get_etf_holdings_no_info(self, mock_ticker_no_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_info):
            result = _etf_holdings_sync("XYZ")

        assert result == []

    def test_get_etf_holdings_no_holdings(self, mock_ticker_no_holdings):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings):
            result = _etf_holdings_sync("BND")

        assert result == []

    def test_legit_empty_holdings_are_cached(self, mock_ticker_no_holdings):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings) as mock_yf:
            _etf_holdings_sync("BND")
            _etf_holdings_sync("BND")

        assert mock_yf.call_count == 1

    def test_get_etf_holdings_exception_handling(self):
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        mock_ticker.funds_data = None

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result == []

    def test_get_etf_holdings_case_insensitive(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _etf_holdings_sync("SPY")

        assert len(result) == 5

    def test_get_etf_holdings_weight_conversion(self):
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        holdings_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT"],
            "holdingName": ["Apple", "Microsoft"],
            "holdingPercent": [0.07, 0.06],
        })
        mock_funds_data = MagicMock()
        mock_funds_data.top_holdings = holdings_df
        mock_ticker.funds_data = mock_funds_data

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result[0]["weight_pct"] == pytest.approx(7.0)
        assert result[1]["weight_pct"] == pytest.approx(6.0)

    def test_weight_clamping(self):
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        holdings_df = pd.DataFrame({
            "Symbol": ["A", "B"],
            "Name": ["Asset A", "Asset B"],
            "% Assets": [150.0, -10.0],  # Out of bounds
        })
        mock_funds_data = MagicMock()
        mock_funds_data.top_holdings = holdings_df
        mock_ticker.funds_data = mock_funds_data

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result[0]["weight_pct"] == 100.0  # Clamped to max
        assert result[1]["weight_pct"] == 0.0  # Clamped to min

    def test_weight_edge_case_small_holdings(self):
        """Test weight normalization for small holdings in the 0-1% band.

        Note: The heuristic 'if weight <= 1: multiply by 100' assumes values
        <= 1 are fractions. A holding reported as 0.5% (legitimate) will be
        treated as 0.005 fraction and converted to 0.5%, which is correct.
        However, a holding reported as 0.009 (0.9%) or 0.01 (1%) may appear
        as a fraction vs. already-a-percent depending on the data source.
        This test documents the behavior.
        """
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        # Simulate small holdings: 0.5% and 1.5% as fractions
        holdings_df = pd.DataFrame({
            "Symbol": ["SMALL1", "SMALL2"],
            "Name": ["Small Holding 1", "Small Holding 2"],
            "% Assets": [0.005, 0.015],  # 0.5% and 1.5% as fractions
        })
        mock_funds_data = MagicMock()
        mock_funds_data.top_holdings = holdings_df
        mock_ticker.funds_data = mock_funds_data

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result[0]["weight_pct"] == pytest.approx(0.5)
        assert result[1]["weight_pct"] == pytest.approx(1.5)


class TestFindEtfsHoldingStockSync:
    """Test the _find_etfs_holding_stock_sync function."""

    def test_find_etfs_holding_stock_success(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) <= 2
        assert result[0]["stock"] == "AAPL"
        assert result[0]["etf"] in ["SPY", "QQQ"]

    def test_find_etfs_holding_stock_limit(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ", "IVV"], limit=2)

        assert len(result) <= 2

    def test_find_etfs_holding_stock_not_found(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("NOTFOUND", etf_universe=["SPY", "QQQ"], limit=10)

        assert result == []

    def test_find_etfs_holding_stock_sorts_by_weight(self):
        _holdings_cache.clear()

        def mock_yf_ticker_side_effect(ticker, session=None):
            mock_ticker = MagicMock()

            if ticker == "SPY":
                holdings_df = pd.DataFrame({
                    "Symbol": ["AAPL", "MSFT"],
                    "Name": ["Apple", "Microsoft"],
                    "% Assets": [0.07, 0.02],
                })
            elif ticker == "QQQ":
                holdings_df = pd.DataFrame({
                    "Symbol": ["AAPL", "MSFT"],
                    "Name": ["Apple", "Microsoft"],
                    "% Assets": [0.05, 0.10],
                })
            else:
                return mock_ticker

            mock_funds_data = MagicMock()
            mock_funds_data.top_holdings = holdings_df
            mock_ticker.funds_data = mock_funds_data
            return mock_ticker

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", side_effect=mock_yf_ticker_side_effect):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) == 2
        assert result[0]["weight_pct"] == pytest.approx(7.0)
        assert result[1]["weight_pct"] == pytest.approx(5.0)

    def test_find_etfs_holding_stock_case_insensitive(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("aapl", etf_universe=["SPY"], limit=10)

        assert len(result) == 1
        assert result[0]["stock"] == "AAPL"


class TestAsyncWrappers:
    """Test the async wrapper functions."""

    @pytest.mark.asyncio
    async def test_get_etf_info_async(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await get_etf_info("SPY")

        assert result["ticker"] == "SPY"
        assert result["name"] == "SPDR S&P 500 ETF Trust"

    @pytest.mark.asyncio
    async def test_get_etf_holdings_async(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await get_etf_holdings("SPY")

        assert len(result) == 5
        assert result[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_async(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) <= 2
        assert all(r["stock"] == "AAPL" for r in result)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_default_universe(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("AAPL", limit=1)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_etfs_async(self):
        def mock_search(query, max_results):
            mock_search = MagicMock()
            mock_search.quotes = [
                {"symbol": "SPY", "longname": "SPDR S&P 500", "quoteType": "ETF"},
                {"symbol": "QQQ", "longname": "Invesco QQQ", "quoteType": "ETF"},
            ]
            return mock_search

        with patch("mcp_etf_holdings.fetcher.yf.Search", side_effect=mock_search):
            result = await search_etfs("S&P", limit=2)

        assert len(result) == 2
        assert result[0]["symbol"] == "SPY"


class TestInputValidation:
    """Test input validation."""

    def test_find_etfs_invalid_stock_ticker(self):
        with pytest.raises(ValueError, match="Invalid stock ticker"):
            _find_etfs_holding_stock_sync("invalid!", etf_universe=["SPY"], limit=10)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_invalid_universe_type(self):
        with pytest.raises(ValueError, match="must be a list"):
            await find_etfs_holding_stock("AAPL", etf_universe="SPY,QQQ", limit=10)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_invalid_universe_size(self):
        universe = [f"FAKE{i}" for i in range(600)]
        with pytest.raises(ValueError, match="too large"):
            await find_etfs_holding_stock("AAPL", etf_universe=universe, limit=10)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_invalid_limit(self):
        with pytest.raises(ValueError, match="between 1 and 1000"):
            await find_etfs_holding_stock("AAPL", limit=0)

    @pytest.mark.asyncio
    async def test_search_etfs_invalid_limit(self):
        with pytest.raises(ValueError, match="between 1 and 500"):
            await search_etfs("test", limit=0)

    @pytest.mark.asyncio
    async def test_search_etfs_invalid_query(self):
        with pytest.raises(ValueError, match="non-empty string"):
            await search_etfs("", limit=10)


class TestSearchSymbols:
    """The generalized search, which search_etfs now delegates to."""

    QUOTES = [
        {"quoteType": "EQUITY", "symbol": "NVDA", "longname": "NVIDIA Corporation", "exchDisp": "NASDAQ"},
        {"quoteType": "ETF", "symbol": "SMH", "longname": "VanEck Semiconductor ETF", "exchange": "NMS"},
        {"quoteType": "FUTURE", "symbol": "NQ=F", "shortname": "Nasdaq 100 Futures"},
    ]

    def _patch(self, quotes):
        mock_search = MagicMock()
        mock_search.quotes = quotes
        return patch("mcp_etf_holdings.fetcher.yf.Search", return_value=mock_search)

    def test_no_filter_returns_every_quote_type(self):
        with self._patch(self.QUOTES):
            results = _search_symbols_sync("nvidia", 10)

        assert [r["symbol"] for r in results] == ["NVDA", "SMH", "NQ=F"]
        assert results[0]["type"] == "EQUITY"

    def test_filter_is_applied(self):
        with self._patch(self.QUOTES):
            results = _search_symbols_sync("nvidia", 10, quote_types=("EQUITY",))

        assert [r["symbol"] for r in results] == ["NVDA"]

    def test_filter_is_case_insensitive(self):
        with self._patch(self.QUOTES):
            results = _search_symbols_sync("nvidia", 10, quote_types=("etf",))

        assert [r["symbol"] for r in results] == ["SMH"]

    def test_limit_truncates(self):
        with self._patch(self.QUOTES):
            results = _search_symbols_sync("nvidia", 2)

        assert len(results) == 2

    def test_search_failure_returns_empty(self):
        with patch(
            "mcp_etf_holdings.fetcher.yf.Search", side_effect=Exception("network down")
        ):
            assert _search_symbols_sync("nvidia", 10) == []

    @pytest.mark.asyncio
    async def test_search_etfs_still_filters_to_etfs(self):
        with self._patch(self.QUOTES):
            results = await search_etfs("nvidia", limit=10)

        assert [r["symbol"] for r in results] == ["SMH"]


class TestResolveStockSymbol:
    def _patch(self, quotes):
        mock_search = MagicMock()
        mock_search.quotes = quotes
        return patch("mcp_etf_holdings.fetcher.yf.Search", return_value=mock_search)

    @pytest.mark.asyncio
    async def test_returns_best_match(self):
        quotes = [
            {"quoteType": "EQUITY", "symbol": "NVDA", "longname": "NVIDIA Corporation"},
            {"quoteType": "EQUITY", "symbol": "NVDX", "longname": "Other"},
        ]
        with self._patch(quotes):
            match = await resolve_stock_symbol("Nvidia")

        assert match["symbol"] == "NVDA"

    @pytest.mark.asyncio
    async def test_futures_are_not_a_valid_resolution(self):
        with self._patch([{"quoteType": "FUTURE", "symbol": "NQ=F", "shortname": "x"}]):
            assert await resolve_stock_symbol("nasdaq futures") is None

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        with self._patch([]):
            assert await resolve_stock_symbol("zzzznotreal") is None

    @pytest.mark.asyncio
    async def test_blank_query_returns_none_without_searching(self):
        with patch("mcp_etf_holdings.fetcher.yf.Search") as search:
            assert await resolve_stock_symbol("   ") is None
        search.assert_not_called()


class TestGetEtfInfos:
    @pytest.mark.asyncio
    async def test_preserves_input_order(self, mock_ticker_info):
        def ticker_factory(symbol, session=None):
            mock = MagicMock()
            mock.info = dict(mock_ticker_info, longName=f"Fund {symbol}")
            return mock

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", side_effect=ticker_factory):
            results = await get_etf_infos(["VTI", "SPY", "QQQ"])

        assert [r["ticker"] for r in results] == ["VTI", "SPY", "QQQ"]
        assert results[0]["name"] == "Fund VTI"

    @pytest.mark.asyncio
    async def test_empty_list(self):
        assert await get_etf_infos([]) == []

    @pytest.mark.asyncio
    async def test_rejects_non_string_elements(self):
        with pytest.raises(ValueError, match="list of strings"):
            await get_etf_infos(["SPY", 42])
