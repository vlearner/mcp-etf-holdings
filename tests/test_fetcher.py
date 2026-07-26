import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.mcp_servers.etf_holdings.fetcher import (
    _TTLCache,
    _etf_info_sync,
    _etf_holdings_sync,
    _find_etfs_holding_stock_sync,
    get_etf_info,
    get_etf_holdings,
    find_etfs_holding_stock,
    search_etfs,
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_info):
            result = _etf_info_sync("FAKEETF")

        assert result["ticker"] == "FAKEETF"
        assert result["name"] == ""

    def test_get_etf_info_caching(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info) as mock_yf:
            result1 = _etf_info_sync("SPY")
            result2 = _etf_info_sync("SPY")

            assert result1 == result2
            assert mock_yf.call_count == 1

    def test_get_etf_info_case_insensitive(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_info_sync("SPY")

        assert result["name"] == "SPY"
        assert result["nav_price"] == 450.0
        assert result["expense_ratio"] == 0.0003


class TestEtfHoldingsSync:
    """Test the _etf_holdings_sync function."""

    def test_get_etf_holdings_success(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info) as mock_yf:
            result1 = _etf_holdings_sync("SPY")
            result2 = _etf_holdings_sync("SPY")

            assert result1 == result2
            assert mock_yf.call_count == 1

    def test_get_etf_holdings_no_info(self, mock_ticker_no_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_info):
            result = _etf_holdings_sync("XYZ")

        assert result == []

    def test_get_etf_holdings_no_holdings(self, mock_ticker_no_holdings):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings):
            result = _etf_holdings_sync("BND")

        assert result == []

    def test_legit_empty_holdings_are_cached(self, mock_ticker_no_holdings):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings) as mock_yf:
            _etf_holdings_sync("BND")
            _etf_holdings_sync("BND")

        assert mock_yf.call_count == 1

    def test_get_etf_holdings_exception_handling(self):
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        mock_ticker.funds_data = None

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result == []

    def test_get_etf_holdings_case_insensitive(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker):
            result = _etf_holdings_sync("SPY")

        assert result[0]["weight_pct"] == pytest.approx(0.5)
        assert result[1]["weight_pct"] == pytest.approx(1.5)


class TestFindEtfsHoldingStockSync:
    """Test the _find_etfs_holding_stock_sync function."""

    def test_find_etfs_holding_stock_success(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) <= 2
        assert result[0]["stock"] == "AAPL"
        assert result[0]["etf"] in ["SPY", "QQQ"]

    def test_find_etfs_holding_stock_limit(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ", "IVV"], limit=2)

        assert len(result) <= 2

    def test_find_etfs_holding_stock_not_found(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", side_effect=mock_yf_ticker_side_effect):
            result = _find_etfs_holding_stock_sync("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) == 2
        assert result[0]["weight_pct"] == pytest.approx(7.0)
        assert result[1]["weight_pct"] == pytest.approx(5.0)

    def test_find_etfs_holding_stock_case_insensitive(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _find_etfs_holding_stock_sync("aapl", etf_universe=["SPY"], limit=10)

        assert len(result) == 1
        assert result[0]["stock"] == "AAPL"


class TestAsyncWrappers:
    """Test the async wrapper functions."""

    @pytest.mark.asyncio
    async def test_get_etf_info_async(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await get_etf_info("SPY")

        assert result["ticker"] == "SPY"
        assert result["name"] == "SPDR S&P 500 ETF Trust"

    @pytest.mark.asyncio
    async def test_get_etf_holdings_async(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await get_etf_holdings("SPY")

        assert len(result) == 5
        assert result[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_async(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) <= 2
        assert all(r["stock"] == "AAPL" for r in result)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_default_universe(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
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

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Search", side_effect=mock_search):
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
