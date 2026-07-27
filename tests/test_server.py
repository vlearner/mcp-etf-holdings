"""
Integration tests for the MCP server layer.

Exercises the seven registered tools end-to-end (argument handling,
fetcher calls, output formatting) with yfinance mocked out.
"""

import pytest
from unittest.mock import MagicMock, patch

from mcp_etf_holdings import server
from mcp_etf_holdings.fetcher import _info_cache, _holdings_cache
from mcp_etf_holdings.top_etfs import TOP_ETFS


@pytest.fixture(autouse=True)
def clear_caches():
    _info_cache.clear()
    _holdings_cache.clear()
    yield
    _info_cache.clear()
    _holdings_cache.clear()


def _patch_ticker(mock_ticker):
    return patch("mcp_etf_holdings.fetcher.yf.Ticker", return_value=mock_ticker)


def _patch_search(quotes):
    mock_search = MagicMock()
    mock_search.quotes = quotes
    return patch("mcp_etf_holdings.fetcher.yf.Search", return_value=mock_search)


class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_all_tools_registered(self):
        tools = await server.mcp.list_tools()
        names = {t.name for t in tools}
        assert names == {
            "etf_info",
            "compare_etfs",
            "etf_holdings",
            "find_etfs_holding_stock",
            "stock_exposure_summary",
            "search_etfs",
            "lookup_symbol",
        }

    @pytest.mark.asyncio
    async def test_every_parameter_has_a_description(self):
        """A bare string in Annotated[...] is silently dropped by pydantic.

        Descriptions must be wrapped in Field(description=...) or the model
        sees an untyped, unexplained parameter.
        """
        tools = await server.mcp.list_tools()
        for tool in tools:
            for name, schema in tool.inputSchema["properties"].items():
                assert schema.get("description"), f"{tool.name}.{name} has no description"

    @pytest.mark.asyncio
    async def test_compare_etfs_takes_an_array_not_a_string(self):
        tools = {t.name: t for t in await server.mcp.list_tools()}
        schema = tools["compare_etfs"].inputSchema["properties"]["tickers"]
        assert schema["type"] == "array"
        assert schema["items"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_tools_callable_via_mcp_protocol(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            result = await server.mcp.call_tool("etf_info", {"ticker": "SPY"})
        # FastMCP returns a list of content blocks
        text = result[0].text if isinstance(result, list) else str(result)
        assert "SPY" in text


class TestEtfInfoTool:
    @pytest.mark.asyncio
    async def test_formats_metadata(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.etf_info("SPY")

        assert "**SPY** – SPDR S&P 500 ETF Trust" in out
        assert "$500.00B" in out
        assert "0.03%" in out  # expense ratio
        assert "Large Cap Equities" in out

    @pytest.mark.asyncio
    async def test_invalid_ticker_message(self, mock_ticker_no_info):
        with _patch_ticker(mock_ticker_no_info):
            out = await server.etf_info("NOTREAL")

        assert "No data found for ticker 'NOTREAL'" in out

    @pytest.mark.asyncio
    async def test_renders_net_expense_ratio_without_100x_error(self):
        """Yahoo's netExpenseRatio 0.18 is 0.18%, so the output must not say 18.00%."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Invesco QQQ Trust", "netExpenseRatio": 0.18}
        with _patch_ticker(mock_ticker):
            out = await server.etf_info("QQQ")

        assert "Expense ratio : 0.18%" in out
        assert "18.00%" not in out

    @pytest.mark.asyncio
    async def test_expense_ratio_na_when_absent(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Mystery Fund"}
        with _patch_ticker(mock_ticker):
            out = await server.etf_info("MYST")

        assert "Expense ratio : N/A" in out

    @pytest.mark.asyncio
    async def test_zero_values_render_as_zero_not_na(self):
        """A zero fee, zero yield, or flat year is data — not a missing value."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "longName": "Zero Fee Fund",
            "netExpenseRatio": 0.0,
            "yield": 0.0,
            "ytdReturn": 0.0,
        }
        with _patch_ticker(mock_ticker):
            out = await server.etf_info("ZERO")

        assert "Expense ratio : 0.00%" in out
        assert "Dividend yield: 0.00%" in out
        assert "YTD return    : 0.00%" in out

    @pytest.mark.asyncio
    async def test_millions_aum_formatting(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"longName": "Small ETF", "totalAssets": 250_000_000}
        with _patch_ticker(mock_ticker):
            out = await server.etf_info("SML")

        assert "$250.0M" in out


class TestEtfHoldingsTool:
    @pytest.mark.asyncio
    async def test_formats_holdings_list(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.etf_holdings("spy")

        assert "Top holdings of **SPY**" in out
        assert "AAPL" in out and "Apple Inc." in out
        assert "7.00%" in out

    @pytest.mark.asyncio
    async def test_no_holdings_message(self, mock_ticker_no_holdings):
        with _patch_ticker(mock_ticker_no_holdings):
            out = await server.etf_holdings("XYZ")

        assert "No holdings data found for 'XYZ'" in out


class TestFindEtfsHoldingStockTool:
    @pytest.mark.asyncio
    async def test_finds_stock_in_custom_universe(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.find_etfs_holding_stock(
                "AAPL", custom_etf_universe='["SPY", "QQQ"]'
            )

        assert "**AAPL** appears in the top holdings" in out
        assert "searched 2" in out
        assert "SPY" in out

    @pytest.mark.asyncio
    async def test_not_found_message_mentions_universe_size(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.find_etfs_holding_stock(
                "NOTHELD", custom_etf_universe='["SPY"]'
            )

        assert "'NOTHELD' was not found" in out
        assert "among the 1 ETFs searched" in out

    @pytest.mark.asyncio
    async def test_default_universe_size_in_message(self, mock_ticker_no_holdings):
        with _patch_ticker(mock_ticker_no_holdings):
            out = await server.find_etfs_holding_stock("AAPL")

        assert f"among the {len(TOP_ETFS)} ETFs searched" in out

    @pytest.mark.asyncio
    async def test_invalid_json_universe(self):
        out = await server.find_etfs_holding_stock("AAPL", custom_etf_universe="not json")
        assert "Invalid JSON" in out

    @pytest.mark.asyncio
    async def test_non_array_json_universe(self):
        out = await server.find_etfs_holding_stock("AAPL", custom_etf_universe='{"a": 1}')
        assert "must be a JSON array" in out

    @pytest.mark.asyncio
    async def test_limit_is_clamped(self, mock_ticker_with_info):
        # limit=0 must clamp to 1, not error or return nothing
        with _patch_ticker(mock_ticker_with_info):
            out = await server.find_etfs_holding_stock(
                "AAPL", limit=0, custom_etf_universe='["SPY", "QQQ"]'
            )

        assert "1 ETF(s)" in out


class TestSearchEtfsTool:
    SAMPLE_QUOTES = [
        {"quoteType": "EQUITY", "symbol": "TSM", "shortname": "Taiwan Semi"},
        {"quoteType": "ETF", "symbol": "SOXX", "longname": "iShares Semiconductor ETF", "exchDisp": "NASDAQ"},
        {"quoteType": "ETF", "symbol": "SMH", "longname": "VanEck Semiconductor ETF", "exchange": "NMS"},
        {"quoteType": "FUTURE", "symbol": "SOX=F", "shortname": "PHLX Semi Futures"},
    ]

    @pytest.mark.asyncio
    async def test_returns_only_etfs(self):
        with _patch_search(self.SAMPLE_QUOTES):
            out = await server.search_etfs("semiconductor")

        assert "SOXX" in out and "SMH" in out
        assert "TSM" not in out and "SOX=F" not in out

    @pytest.mark.asyncio
    async def test_formats_name_and_exchange(self):
        with _patch_search(self.SAMPLE_QUOTES):
            out = await server.search_etfs("semiconductor")

        assert "iShares Semiconductor ETF" in out
        assert "NASDAQ" in out

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        with _patch_search(self.SAMPLE_QUOTES):
            out = await server.search_etfs("semiconductor", limit=1)

        assert "SOXX" in out
        assert "SMH" not in out

    @pytest.mark.asyncio
    async def test_no_results_message(self):
        with _patch_search([]):
            out = await server.search_etfs("zzzznotreal")

        assert "No ETFs found matching 'zzzznotreal'" in out

    @pytest.mark.asyncio
    async def test_blank_query_rejected(self):
        out = await server.search_etfs("   ")
        assert "non-empty search query" in out

    @pytest.mark.asyncio
    async def test_search_exception_returns_no_results(self):
        with patch(
            "mcp_etf_holdings.fetcher.yf.Search",
            side_effect=Exception("network down"),
        ):
            out = await server.search_etfs("semiconductor")

        assert "No ETFs found" in out


class TestCompareEtfsTool:
    @pytest.mark.asyncio
    async def test_renders_one_row_per_ticker(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.compare_etfs(["SPY", "QQQ", "VTI"])

        assert "| Ticker | Name | Category | AUM |" in out
        # header + separator + 3 data rows
        assert len([ln for ln in out.splitlines() if ln.startswith("|")]) == 5
        for ticker in ("SPY", "QQQ", "VTI"):
            assert f"| {ticker} |" in out

    @pytest.mark.asyncio
    async def test_deduplicates_and_uppercases(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.compare_etfs(["spy", "SPY", " spy "])

        assert "Comparing 1 ETF(s)" in out
        assert out.count("| SPY |") == 1

    @pytest.mark.asyncio
    async def test_caps_at_max_compare(self, mock_ticker_with_info):
        tickers = [f"ETF{i}" for i in range(server.MAX_COMPARE + 3)]
        with _patch_ticker(mock_ticker_with_info):
            out = await server.compare_etfs(tickers)

        assert f"Comparing {server.MAX_COMPARE} ETF(s)" in out
        assert "omitted: ETF10, ETF11, ETF12" in out

    @pytest.mark.asyncio
    async def test_bad_ticker_keeps_the_good_rows(self, mock_ticker_info):
        """One unknown ticker must not discard the funds that did resolve."""

        def ticker_factory(symbol, session=None):
            mock = MagicMock()
            mock.info = None if symbol == "FAKE" else mock_ticker_info
            mock.funds_data = None
            return mock

        with patch("mcp_etf_holdings.fetcher.yf.Ticker", side_effect=ticker_factory):
            out = await server.compare_etfs(["SPY", "FAKE", "VTI"])

        assert "| SPY |" in out and "| VTI |" in out
        assert "No data returned for: FAKE" in out
        assert "| FAKE | — |" in out

    @pytest.mark.asyncio
    async def test_empty_list_is_rejected(self):
        assert "Provide a list of ETF tickers" in await server.compare_etfs([])
        assert "Provide a list of ETF tickers" in await server.compare_etfs(["", "  "])


class TestLookupSymbolTool:
    @pytest.mark.asyncio
    async def test_any_returns_equities_that_search_etfs_drops(self, equity_quotes):
        with _patch_search(equity_quotes):
            out = await server.lookup_symbol("nvidia")

        assert "| NVDA | NVIDIA Corporation | EQUITY | NASDAQ |" in out
        assert "SMH" in out
        assert "NQ=F" in out  # asset_type 'any' filters nothing

    @pytest.mark.asyncio
    async def test_stock_filter_excludes_funds(self, equity_quotes):
        with _patch_search(equity_quotes):
            out = await server.lookup_symbol("nvidia", asset_type="stock")

        assert "NVDA" in out
        assert "SMH" not in out and "NQ=F" not in out

    @pytest.mark.asyncio
    async def test_etf_filter_excludes_stocks(self, equity_quotes):
        with _patch_search(equity_quotes):
            out = await server.lookup_symbol("semiconductor", asset_type="ETF")

        assert "SMH" in out
        assert "NVDA" not in out

    @pytest.mark.asyncio
    async def test_unknown_asset_type_rejected(self):
        out = await server.lookup_symbol("nvidia", asset_type="crypto")
        assert "Unknown asset_type 'crypto'" in out

    @pytest.mark.asyncio
    async def test_blank_query_rejected(self):
        assert "non-empty name" in await server.lookup_symbol("   ")

    @pytest.mark.asyncio
    async def test_no_results_message(self):
        with _patch_search([]):
            out = await server.lookup_symbol("zzzznotreal")
        assert "No symbols found matching 'zzzznotreal'" in out


class TestStockExposureSummaryTool:
    @pytest.mark.asyncio
    async def test_joins_weight_with_cost_and_size(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.stock_exposure_summary("AAPL", limit=2)

        assert "ETF exposure to **AAPL**" in out
        assert "| ETF | Name | Weight | Rank | Expense | AUM |" in out
        assert "7.00%" in out           # weight in the stock
        assert "$500.00B" in out        # AUM, from the metadata join
        assert "0.03%" in out           # expense ratio, from the metadata join

    @pytest.mark.asyncio
    async def test_not_found_message(self, mock_ticker_no_holdings):
        with _patch_ticker(mock_ticker_no_holdings):
            out = await server.stock_exposure_summary("NOTHELD")

        assert "'NOTHELD' was not found" in out
        assert f"{len(TOP_ETFS)} ETFs searched" in out


class TestCompanyNameFallback:
    """A company name where a ticker is expected must resolve, and say so."""

    @pytest.mark.asyncio
    async def test_find_etfs_resolves_name_and_discloses(
        self, mock_ticker_with_info, equity_quotes
    ):
        with _patch_ticker(mock_ticker_with_info), _patch_search(equity_quotes):
            out = await server.find_etfs_holding_stock(
                "Nvidia", custom_etf_universe='["SPY"]'
            )

        assert '> Interpreted "Nvidia" as **NVDA**' in out
        assert "**NVDA** appears in the top holdings" in out

    @pytest.mark.asyncio
    async def test_stock_exposure_resolves_name(
        self, mock_ticker_with_info, equity_quotes
    ):
        with _patch_ticker(mock_ticker_with_info), _patch_search(equity_quotes):
            out = await server.stock_exposure_summary("Nvidia", limit=1)

        assert '> Interpreted "Nvidia" as **NVDA**' in out
        assert "ETF exposure to **NVDA**" in out

    @pytest.mark.asyncio
    async def test_no_resolver_call_when_ticker_already_matches(
        self, mock_ticker_with_info
    ):
        """The fallback is miss-only — a working ticker must not pay for a search."""
        with _patch_ticker(mock_ticker_with_info):
            with patch(
                "mcp_etf_holdings.server.resolve_stock_symbol"
            ) as resolver:
                out = await server.find_etfs_holding_stock(
                    "AAPL", custom_etf_universe='["SPY"]'
                )

        resolver.assert_not_called()
        assert "Interpreted" not in out

    @pytest.mark.asyncio
    async def test_unresolvable_name_reports_plainly(self, mock_ticker_no_holdings):
        with _patch_ticker(mock_ticker_no_holdings), _patch_search([]):
            out = await server.find_etfs_holding_stock(
                "Not A Real Company", custom_etf_universe='["SPY"]'
            )

        assert "was not found" in out
        assert "Interpreted" not in out


class TestPromptRegistration:
    @pytest.mark.asyncio
    async def test_all_prompts_registered(self):
        prompts = await server.mcp.list_prompts()
        assert {p.name for p in prompts} == {
            "etf_deep_dive",
            "compare_funds",
            "stock_exposure",
            "portfolio_checkup",
            "theme_explorer",
        }

    @pytest.mark.asyncio
    async def test_prompt_renders_with_its_argument(self):
        result = await server.mcp.get_prompt("etf_deep_dive", {"ticker": "SCHD"})
        text = result.messages[0].content.text
        assert "SCHD" in text
        assert "not financial advice" in text
