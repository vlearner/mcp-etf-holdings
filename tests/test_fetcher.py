import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.mcp_servers.etf_holdings.fetcher import (
    _TTLCache,
    _etf_info_sync,
    _etf_holdings_sync,
    get_etf_info,
    get_etf_holdings,
    find_etfs_holding_stock,
    _info_cache,
    _holdings_cache,
)


class TestTTLCache:
    """Test the _TTLCache class."""

    def test_set_and_get(self):
        cache = _TTLCache(ttl_seconds=10)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        cache = _TTLCache(ttl_seconds=10)
        assert cache.get("nonexistent") is None

    def test_cache_expiry(self):
        cache = _TTLCache(ttl_seconds=0.1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.2)
        assert cache.get("key1") is None

    def test_clear(self):
        cache = _TTLCache(ttl_seconds=10)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cache_with_different_types(self):
        cache = _TTLCache(ttl_seconds=10)
        cache.set("str_key", "string_value")
        cache.set("dict_key", {"nested": "dict"})
        cache.set("list_key", [1, 2, 3])

        assert cache.get("str_key") == "string_value"
        assert cache.get("dict_key") == {"nested": "dict"}
        assert cache.get("list_key") == [1, 2, 3]

    def test_cache_thread_safety(self):
        import threading

        cache = _TTLCache(ttl_seconds=10)
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

    def test_get_etf_info_no_info(self, mock_ticker_no_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_info):
            result = _etf_info_sync("INVALID")

        assert result["ticker"] == "INVALID"
        assert result["name"] == ""

    def test_get_etf_info_caching(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info) as mock_yf:
            result1 = _etf_info_sync("SPY")
            result2 = _etf_info_sync("SPY")

            assert result1 == result2
            assert mock_yf.call_count == 1  # Only called once due to caching

    def test_get_etf_info_case_insensitive(self, mock_ticker_with_info):
        _info_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = _etf_info_sync("spy")

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
            result = _etf_holdings_sync("INVALID")

        assert result == []

    def test_get_etf_holdings_no_holdings(self, mock_ticker_no_holdings):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings):
            result = _etf_holdings_sync("XYZ")

        assert result == []

    def test_legit_empty_holdings_are_cached(self, mock_ticker_no_holdings):
        # Bond/commodity funds legitimately have no equity holdings; cache
        # the empty result so universe scans don't re-fetch them every time.
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_no_holdings) as mock_yf:
            _etf_holdings_sync("BND")
            _etf_holdings_sync("BND")

        assert mock_yf.call_count == 1

    def test_exception_results_are_not_cached(self):
        _holdings_cache.clear()

        mock_ticker = MagicMock()
        type(mock_ticker).funds_data = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker) as mock_yf:
            assert _etf_holdings_sync("SPY") == []
            assert _etf_holdings_sync("SPY") == []

        assert mock_yf.call_count == 2  # transient failures retried, not cached

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
            result = _etf_holdings_sync("spy")

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


class TestFindEtfsHoldingStock:
    """Test the find_etfs_holding_stock parallel scan."""

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_success(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) <= 2
        assert result[0]["stock"] == "AAPL"
        assert result[0]["etf"] in ["SPY", "QQQ"]

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_limit(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ", "IVV"], limit=2)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_not_found(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("NOTFOUND", etf_universe=["SPY", "QQQ"], limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_sorts_by_weight(self):
        _holdings_cache.clear()

        def mock_yf_ticker_side_effect(ticker):
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
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ"], limit=10)

        assert len(result) == 2
        assert result[0]["weight_pct"] == pytest.approx(7.0)
        assert result[1]["weight_pct"] == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_case_insensitive(self, mock_ticker_with_info):
        _holdings_cache.clear()

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker_with_info):
            result = await find_etfs_holding_stock("aapl", etf_universe=["SPY"], limit=10)

        assert len(result) == 1
        assert result[0]["stock"] == "AAPL"

    @pytest.mark.asyncio
    async def test_limit_returns_true_top_n_by_weight(self):
        _holdings_cache.clear()

        def mock_yf_ticker_side_effect(ticker):
            weights = {"SPY": 0.02, "QQQ": 0.09, "IVV": 0.05}
            mock_ticker = MagicMock()
            holdings_df = pd.DataFrame({
                "Symbol": ["AAPL"],
                "Name": ["Apple"],
                "% Assets": [weights[ticker]],
            })
            mock_funds_data = MagicMock()
            mock_funds_data.top_holdings = holdings_df
            mock_ticker.funds_data = mock_funds_data
            return mock_ticker

        with patch("src.mcp_servers.etf_holdings.fetcher.yf.Ticker", side_effect=mock_yf_ticker_side_effect):
            result = await find_etfs_holding_stock("AAPL", etf_universe=["SPY", "QQQ", "IVV"], limit=2)

        # The two highest-weight ETFs win, regardless of universe order
        assert [r["etf"] for r in result] == ["QQQ", "IVV"]


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
