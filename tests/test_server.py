"""
Integration tests for the MCP server layer.

Exercises the seven registered tools end-to-end (argument handling,
fetcher calls, output formatting) with yfinance mocked out.
"""

import pandas as pd
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


class TestShareClassDotForm:
    """Yahoo holds BRK-B; users type BRK.B. The dot form must find the fund.

    Before the dot->dash retry this fell through to the company-name resolver,
    which matched BRK.B to BRKC — an unrelated YieldMax fund — and answered
    about it. A wrong-fund answer reads exactly like a right one, so these
    cases guard the retry, not just the happy path.
    """

    @staticmethod
    def _patch_universe_holding(symbol: str, weight: float):
        """Every ETF in the universe holds exactly `symbol`, at `weight` percent."""
        df = pd.DataFrame(
            {"Symbol": [symbol], "Name": [f"{symbol} Inc."], "% Assets": [weight]}
        )

        def factory(ticker, session=None):
            mock = MagicMock()
            mock.info = {"longName": f"Fund {ticker}", "shortName": ticker}
            funds = MagicMock()
            funds.top_holdings = df
            mock.funds_data = funds
            return mock

        return patch("mcp_etf_holdings.fetcher.yf.Ticker", side_effect=factory)

    @pytest.mark.asyncio
    async def test_dot_form_finds_the_dash_form_and_discloses_it(self):
        with self._patch_universe_holding("BRK-B", 12.07):
            out = await server.find_etfs_holding_stock(
                "BRK.B", custom_etf_universe='["XLF"]'
            )

        assert '> Interpreted "BRK.B" as **BRK-B**' in out
        assert "**BRK-B** appears in the top holdings" in out
        assert "| XLF | 12.07% | #1 |" in out

    @pytest.mark.asyncio
    async def test_dash_retry_happens_before_the_name_resolver(self):
        """The resolver is what returned BRKC — the retry must beat it to the answer."""
        with self._patch_universe_holding("BRK-B", 12.07):
            with patch("mcp_etf_holdings.server.resolve_stock_symbol") as resolver:
                out = await server.find_etfs_holding_stock(
                    "BRK.B", custom_etf_universe='["XLF"]'
                )

        resolver.assert_not_called()
        assert "**BRK-B** appears in the top holdings" in out

    @pytest.mark.asyncio
    async def test_stock_exposure_summary_gets_the_same_retry(self):
        with self._patch_universe_holding("BRK-B", 12.07):
            out = await server.stock_exposure_summary("BRK.B", limit=1)

        assert '> Interpreted "BRK.B" as **BRK-B**' in out
        assert "ETF exposure to **BRK-B**" in out

    @pytest.mark.asyncio
    async def test_padded_dot_form_is_handled(self):
        with self._patch_universe_holding("BRK-B", 12.07):
            out = await server.find_etfs_holding_stock(
                "  brk.b  ", custom_etf_universe='["XLF"]'
            )

        assert "**BRK-B** appears in the top holdings" in out

    @pytest.mark.asyncio
    async def test_dot_free_ticker_never_pays_for_a_retry(self):
        """A plain symbol must not trigger a second universe scan."""
        with self._patch_universe_holding("AAPL", 7.0):
            with patch(
                "mcp_etf_holdings.server._find_etfs_holding_stock",
                wraps=server._find_etfs_holding_stock,
            ) as lookup:
                out = await server.find_etfs_holding_stock(
                    "AAPL", custom_etf_universe='["SPY"]'
                )

        assert lookup.call_count == 1
        assert "Interpreted" not in out

    @pytest.mark.asyncio
    async def test_name_resolver_still_runs_when_the_dash_form_misses(self):
        """The retry is an extra step, not a replacement for name resolution."""
        quotes = [{"quoteType": "EQUITY", "symbol": "AAPL", "longname": "Apple Inc."}]
        with self._patch_universe_holding("AAPL", 7.0), _patch_search(quotes):
            out = await server.find_etfs_holding_stock(
                "APPLE.INC", custom_etf_universe='["SPY"]'
            )

        assert '> Interpreted "APPLE.INC" as **AAPL** (Apple Inc.)' in out
        assert "**AAPL** appears in the top holdings" in out


class TestCompareEtfsUnusableEntry:
    """A fund name among the tickers must not discard the funds that resolved."""

    @staticmethod
    def _patch_named_funds(mock_ticker_info):
        def factory(symbol, session=None):
            mock = MagicMock()
            mock.info = dict(mock_ticker_info, longName=f"Fund {symbol}")
            mock.funds_data = None
            return mock

        return patch("mcp_etf_holdings.fetcher.yf.Ticker", side_effect=factory)

    @pytest.mark.asyncio
    async def test_fund_name_does_not_kill_the_batch(self, mock_ticker_info):
        with self._patch_named_funds(mock_ticker_info):
            out = await server.compare_etfs(["VOO", "Vanguard S&P 500"])

        assert "Comparing 2 ETF(s)" in out
        assert "| VOO | Fund VOO |" in out
        assert "| VANGUARD S&P 500 | — |" in out
        assert "No data returned for: VANGUARD S&P 500" in out

    @pytest.mark.asyncio
    async def test_valid_rows_keep_their_order_around_a_bad_entry(self, mock_ticker_info):
        with self._patch_named_funds(mock_ticker_info):
            out = await server.compare_etfs(["VOO", "Vanguard S&P 500", "QQQ"])

        tickers = [
            line.split("|")[1].strip()
            for line in out.splitlines()
            if line.startswith("| ") and "---" not in line
        ]
        assert tickers == ["Ticker", "VOO", "VANGUARD S&P 500", "QQQ"]

    @pytest.mark.asyncio
    async def test_every_entry_unusable_still_renders_a_table(self, mock_ticker_info):
        with self._patch_named_funds(mock_ticker_info):
            out = await server.compare_etfs(["Vanguard S&P 500", "iShares Core"])

        assert "| Ticker | Name |" in out
        assert "No data returned for: VANGUARD S&P 500, ISHARES CORE" in out


class TestPaddedTickerInput:
    """Surrounding whitespace is a typo, not a malformed ticker."""

    @pytest.mark.asyncio
    async def test_etf_info_accepts_a_padded_ticker(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.etf_info(" voo ")

        assert out.startswith("**VOO** – SPDR S&P 500 ETF Trust")

    @pytest.mark.asyncio
    async def test_etf_holdings_accepts_a_padded_ticker(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.etf_holdings(" voo ")

        assert "Top holdings of **VOO**" in out
        assert "AAPL" in out

    @pytest.mark.asyncio
    async def test_compare_etfs_accepts_padded_tickers(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.compare_etfs([" voo ", "\tqqq\n"])

        assert "| VOO |" in out and "| QQQ |" in out
        assert "No data returned" not in out

    @pytest.mark.asyncio
    async def test_find_etfs_holding_stock_accepts_a_padded_stock(
        self, mock_ticker_with_info
    ):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.find_etfs_holding_stock(
                " aapl ", custom_etf_universe='["SPY"]'
            )

        assert "**AAPL** appears in the top holdings" in out


class TestSearchEtfsLocalUniverse:
    """Yahoo's search misses funds that are sitting in TOP_ETFS."""

    @pytest.mark.asyncio
    async def test_sp500_query_answers_from_the_local_universe(self):
        """Yahoo answers "S&P 500" with indices and futures; the ETF filter drops them all."""
        index_quotes = [
            {"quoteType": "INDEX", "symbol": "^GSPC", "shortname": "S&P 500"},
            {"quoteType": "FUTURE", "symbol": "ES=F", "shortname": "E-Mini S&P 500"},
        ]
        with _patch_search(index_quotes):
            out = await server.search_etfs("S&P 500")

        assert "| VOO | Vanguard S&P 500 ETF |" in out
        assert "SPY" in out and "IVV" in out
        assert "^GSPC" not in out and "ES=F" not in out

    @pytest.mark.asyncio
    async def test_bitcoin_query_adds_the_funds_yahoo_omits(self):
        with _patch_search(
            [{"quoteType": "ETF", "symbol": "GBTC", "longname": "Grayscale Bitcoin Trust ETF"}]
        ):
            out = await server.search_etfs("bitcoin")

        assert "IBIT" in out and "FBTC" in out
        assert out.count("| GBTC |") == 1  # Yahoo's hit, not duplicated locally

    @pytest.mark.asyncio
    async def test_yahoo_matches_are_listed_before_local_ones(self):
        with _patch_search(
            [{"quoteType": "ETF", "symbol": "BITO", "longname": "ProShares Bitcoin Strategy ETF"}]
        ):
            out = await server.search_etfs("bitcoin")

        rows = [ln for ln in out.splitlines() if ln.startswith("| ") and "---" not in ln]
        assert rows[1].startswith("| BITO |")


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


class TestNormalizeTickers:
    """Direct tests for the helper behind compare_etfs' input handling."""

    def test_uppercases_and_strips(self):
        assert server._normalize_tickers([" spy ", "qqq"]) == ["SPY", "QQQ"]

    def test_preserves_first_occurrence_order(self):
        assert server._normalize_tickers(["VTI", "SPY", "vti"]) == ["VTI", "SPY"]

    def test_drops_blanks(self):
        assert server._normalize_tickers(["", "   ", "SPY"]) == ["SPY"]

    def test_skips_non_string_elements(self):
        assert server._normalize_tickers(["SPY", 42, None, "QQQ"]) == ["SPY", "QQQ"]

    def test_empty_input(self):
        assert server._normalize_tickers([]) == []


class TestLookupWithNameFallback:
    """Direct tests for the resolution helper shared by two tools."""

    @pytest.mark.asyncio
    async def test_no_note_when_direct_lookup_succeeds(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            results, symbol, note = await server._lookup_with_name_fallback(
                "aapl", limit=5, universe=["SPY"]
            )

        assert symbol == "AAPL"
        assert note == ""
        assert results

    @pytest.mark.asyncio
    async def test_resolution_to_the_same_symbol_adds_no_note(
        self, mock_ticker_no_holdings
    ):
        """Resolving AAPL -> AAPL is not a substitution worth announcing."""
        quotes = [{"quoteType": "EQUITY", "symbol": "AAPL", "longname": "Apple Inc."}]
        with _patch_ticker(mock_ticker_no_holdings), _patch_search(quotes):
            results, symbol, note = await server._lookup_with_name_fallback(
                "AAPL", limit=5, universe=["SPY"]
            )

        assert symbol == "AAPL"
        assert note == ""
        assert results == []

    @pytest.mark.asyncio
    async def test_note_survives_a_resolution_that_still_finds_nothing(
        self, mock_ticker_no_holdings
    ):
        """The user still needs to know their name was reinterpreted."""
        quotes = [{"quoteType": "EQUITY", "symbol": "NVDA", "longname": "NVIDIA Corporation"}]
        with _patch_ticker(mock_ticker_no_holdings), _patch_search(quotes):
            results, symbol, note = await server._lookup_with_name_fallback(
                "Nvidia", limit=5, universe=["SPY"]
            )

        assert results == []
        assert symbol == "NVDA"
        assert 'Interpreted "Nvidia" as **NVDA**' in note

    @pytest.mark.asyncio
    async def test_malformed_input_routes_to_the_resolver(self, mock_ticker_with_info):
        """'Berkshire Hathaway' fails the ticker regex — resolve, don't raise."""
        quotes = [{"quoteType": "EQUITY", "symbol": "NVDA", "longname": "NVIDIA Corporation"}]
        with _patch_ticker(mock_ticker_with_info), _patch_search(quotes):
            results, symbol, note = await server._lookup_with_name_fallback(
                "Berkshire Hathaway Inc!", limit=5, universe=["SPY"]
            )

        assert symbol == "NVDA"
        assert "Interpreted" in note

    @pytest.mark.asyncio
    async def test_resolver_result_without_a_symbol_is_ignored(
        self, mock_ticker_no_holdings
    ):
        with _patch_ticker(mock_ticker_no_holdings), _patch_search(
            [{"quoteType": "EQUITY", "symbol": "", "longname": "Nameless"}]
        ):
            results, symbol, note = await server._lookup_with_name_fallback(
                "whatever", limit=5, universe=["SPY"]
            )

        assert note == ""
        assert symbol == "WHATEVER"


class TestLimitClamping:
    """Every limit is clamped rather than rejected, so a bad value still answers."""

    @pytest.mark.asyncio
    async def test_stock_exposure_summary_clamps_high(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.stock_exposure_summary("AAPL", limit=999)

        assert "25 fund(s)" in out

    @pytest.mark.asyncio
    async def test_stock_exposure_summary_clamps_low(self, mock_ticker_with_info):
        with _patch_ticker(mock_ticker_with_info):
            out = await server.stock_exposure_summary("AAPL", limit=0)

        assert "1 fund(s)" in out

    @pytest.mark.asyncio
    async def test_lookup_symbol_clamps_high(self, equity_quotes):
        with _patch_search(equity_quotes * 20):
            out = await server.lookup_symbol("nvidia", limit=999)

        assert "(25 result(s))" in out

    @pytest.mark.asyncio
    async def test_search_etfs_clamps_high(self):
        quotes = [
            {"quoteType": "ETF", "symbol": f"E{i}", "longname": f"Fund {i}"}
            for i in range(60)
        ]
        with _patch_search(quotes):
            out = await server.search_etfs("fund", limit=999)

        assert "(25 result(s))" in out


class TestPromptContent:
    """Every prompt body must render and name the tools it is meant to drive."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name,args,expected_substring,expected_tool",
        [
            ("etf_deep_dive", {"ticker": "SCHD"}, "SCHD", "etf_holdings"),
            ("compare_funds", {"tickers": "SPY, QQQ"}, "SPY, QQQ", "compare_etfs"),
            ("stock_exposure", {"stock": "Nvidia"}, "Nvidia", "stock_exposure_summary"),
            ("portfolio_checkup", {"tickers": "VOO, VGT"}, "VOO, VGT", "etf_holdings"),
            ("theme_explorer", {"theme": "clean energy"}, "clean energy", "search_etfs"),
        ],
    )
    async def test_prompt_renders(self, name, args, expected_substring, expected_tool):
        result = await server.mcp.get_prompt(name, args)
        text = result.messages[0].content.text

        assert expected_substring in text
        assert expected_tool in text
        assert "not financial advice" in text

    @pytest.mark.asyncio
    async def test_every_prompt_declares_its_arguments(self):
        prompts = await server.mcp.list_prompts()
        for prompt in prompts:
            assert prompt.arguments, f"{prompt.name} declares no arguments"


class TestDefensiveValidationPaths:
    @pytest.mark.asyncio
    async def test_blank_stock_is_handled_not_raised(self):
        """The fetcher raises on a blank ticker; the tool must still answer."""
        with _patch_search([]):
            out = await server.find_etfs_holding_stock(
                "   ", custom_etf_universe='["SPY"]'
            )

        assert "was not found" in out

    @pytest.mark.asyncio
    async def test_failure_after_resolution_degrades_to_not_found(self):
        """If the re-run raises, report not-found — never surface a traceback."""
        quotes = [{"quoteType": "EQUITY", "symbol": "NVDA", "longname": "NVIDIA Corporation"}]
        with _patch_search(quotes), patch(
            "mcp_etf_holdings.server._find_etfs_holding_stock",
            side_effect=ValueError("boom"),
        ):
            out = await server.find_etfs_holding_stock(
                "Nvidia", custom_etf_universe='["SPY"]'
            )

        assert 'Interpreted "Nvidia" as **NVDA**' in out
        assert "was not found" in out

    @pytest.mark.asyncio
    async def test_failed_dash_retry_degrades_to_not_found(self):
        """A raising dash retry must fall through, not surface a traceback."""
        with _patch_search([]), patch(
            "mcp_etf_holdings.server._find_etfs_holding_stock",
            side_effect=ValueError("boom"),
        ):
            out = await server.find_etfs_holding_stock(
                "BRK.B", custom_etf_universe='["XLF"]'
            )

        assert "'BRK.B' was not found" in out
        assert "Interpreted" not in out


class TestEntryPoint:
    def test_main_runs_the_server_over_stdio(self):
        with patch.object(server.mcp, "run") as run:
            server.main()

        run.assert_called_once_with(transport="stdio")

    def test_version_is_exposed(self):
        from mcp_etf_holdings import __version__

        assert isinstance(__version__, str) and __version__

    def test_version_falls_back_outside_an_install(self):
        import importlib

        import mcp_etf_holdings

        with patch(
            "importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError,
        ):
            reloaded = importlib.reload(mcp_etf_holdings)
            assert reloaded.__version__ == "0.0.0.dev0"

        importlib.reload(mcp_etf_holdings)
