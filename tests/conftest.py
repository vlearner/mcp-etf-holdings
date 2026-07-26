import pytest
from unittest.mock import MagicMock, patch
import pandas as pd


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Clear all module-level caches before each test to prevent cross-test contamination."""
    from src.mcp_servers.etf_holdings.fetcher import _info_cache, _holdings_cache, _error_cache
    _info_cache.clear()
    _holdings_cache.clear()
    _error_cache.clear()
    yield
    # Optional: clear again after test
    _info_cache.clear()
    _holdings_cache.clear()
    _error_cache.clear()


@pytest.fixture
def mock_ticker_info():
    """Mock yfinance Ticker.info for ETF metadata."""
    return {
        "longName": "SPDR S&P 500 ETF Trust",
        "shortName": "SPY",
        "category": "Large Cap Equities",
        "totalAssets": 500_000_000_000,
        "annualReportExpenseRatio": 0.0003,
        "expenseRatio": 0.0003,
        "yield": 0.015,
        "ytdReturn": 0.12,
        "threeYearAverageReturn": 0.14,
        "fiveYearAverageReturn": 0.12,
        "navPrice": 450.25,
        "regularMarketPrice": 450.25,
        "currency": "USD",
    }


@pytest.fixture
def mock_holdings_data():
    """Mock yfinance Ticker.funds_data.top_holdings DataFrame."""
    return pd.DataFrame({
        "Symbol": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"],
        "Name": ["Apple Inc.", "Microsoft Corporation", "NVIDIA Corporation", "Alphabet Inc.", "Amazon.com Inc."],
        "% Assets": [0.07, 0.06, 0.05, 0.04, 0.03],
    })


@pytest.fixture
def mock_ticker_with_info(mock_ticker_info, mock_holdings_data):
    """Mock yfinance Ticker object with info and holdings."""
    mock_ticker = MagicMock()
    mock_ticker.info = mock_ticker_info

    mock_funds_data = MagicMock()
    mock_funds_data.top_holdings = mock_holdings_data
    mock_ticker.funds_data = mock_funds_data

    return mock_ticker


@pytest.fixture
def mock_ticker_no_info():
    """Mock yfinance Ticker object with no info (invalid ticker)."""
    mock_ticker = MagicMock()
    mock_ticker.info = None
    mock_ticker.funds_data = None

    return mock_ticker


@pytest.fixture
def mock_ticker_no_holdings():
    """Mock yfinance Ticker object with info but no holdings."""
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "longName": "Some ETF",
        "shortName": "XYZ",
    }

    mock_funds_data = MagicMock()
    mock_funds_data.top_holdings = None
    mock_ticker.funds_data = mock_funds_data

    return mock_ticker
