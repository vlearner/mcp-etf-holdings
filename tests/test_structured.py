"""Tool results carry markdown text AND structured JSON, via the real FastMCP call path."""

import json
from unittest.mock import patch

import pytest

from mcp_etf_holdings import providers, server
from tests.test_providers import FakeProvider, MinimalProvider


async def call(name, args):
    """Call a tool the way an MCP client would; returns (content, structured)."""
    result = await server.mcp.call_tool(name, args)
    return result.content, result.structuredContent


class UniverseProvider(FakeProvider):
    default_universe = ["AAA"]


@pytest.mark.asyncio
class TestStructuredOutput:
    async def test_etf_info_has_text_and_structure(self):
        providers.set_provider(FakeProvider())
        content, data = await call("etf_info", {"ticker": "SPY"})
        assert "SPY Fund" in content[0].text
        assert data["source"] == "Acme Data"
        assert data["found"] is True
        assert data["etf"]["ticker"] == "SPY"
        assert data["etf"]["expense_ratio"] == 0.0005
        json.dumps(data)  # serialisable

    async def test_etf_info_not_found(self):
        class Empty(FakeProvider):
            def get_info(self, ticker):
                return {}

        providers.set_provider(Empty())
        content, data = await call("etf_info", {"ticker": "ZZZZ"})
        assert "No data found" in content[0].text
        assert data["found"] is False and data["etf"] is None
        assert data["message"] == content[0].text

    async def test_etf_holdings(self):
        providers.set_provider(FakeProvider())
        _, data = await call("etf_holdings", {"ticker": "spy"})
        assert data["ticker"] == "SPY"
        assert data["holdings"][0] == {
            "rank": 1, "symbol": "NVDA", "name": "NVIDIA", "weight_pct": 7.5
        }

    async def test_compare_etfs_reports_missing(self):
        providers.set_provider(FakeProvider())
        _, data = await call("compare_etfs", {"tickers": ["SPY", "not a ticker"]})
        assert [e["ticker"] for e in data["etfs"]] == ["SPY"]
        assert data["missing"] == ["NOT A TICKER"]
        assert data["omitted"] == []

    async def test_find_etfs_holding_stock(self):
        providers.set_provider(UniverseProvider())
        _, data = await call("find_etfs_holding_stock", {"stock_ticker": "nvda"})
        assert data["stock"] == "NVDA"
        assert data["interpreted_from"] is None
        assert data["searched"] == 1
        assert data["matches"] == [{"etf": "AAA", "weight_pct": 7.5, "rank_in_etf": 1}]

    async def test_stock_exposure_summary_has_cost_fields(self):
        providers.set_provider(UniverseProvider())
        _, data = await call("stock_exposure_summary", {"stock": "NVDA"})
        m = data["matches"][0]
        assert m["etf"] == "AAA"
        assert m["expense_ratio"] == 0.0005
        assert m["total_assets"] == 5e9

    async def test_name_fallback_is_disclosed_in_structure(self):
        providers.set_provider(UniverseProvider())
        _, data = await call("find_etfs_holding_stock", {"stock_ticker": "Nvidia"})
        assert data["stock"] == "NVDA"
        assert data["interpreted_from"] == "Nvidia"

    async def test_lookup_symbol(self):
        providers.set_provider(FakeProvider())
        _, data = await call("lookup_symbol", {"query": "nvidia", "asset_type": "stock"})
        assert data["results"][0]["symbol"] == "NVDA"
        assert data["source"] == "Acme Data"

    async def test_unsupported_search_is_explained(self):
        providers.set_provider(MinimalProvider())
        for tool, args in (
            ("lookup_symbol", {"query": "nvidia"}),
            ("search_etfs", {"query": "semiconductor"}),
        ):
            content, data = await call(tool, args)
            assert "not available" in content[0].text
            assert data["results"] == []

    async def test_default_provider_names_yahoo(self):
        with patch("mcp_etf_holdings.providers.yf.Ticker") as t:
            t.return_value.info = {"longName": "SPDR S&P 500 ETF Trust"}
            _, data = await call("etf_info", {"ticker": "SPY"})
        assert data["source"] == "Yahoo Finance"


@pytest.mark.asyncio
async def test_end_to_end_through_a_real_client_session():
    """What a connected client actually receives over the protocol."""
    from mcp.shared.memory import create_connected_server_and_client_session

    providers.set_provider(FakeProvider())
    async with create_connected_server_and_client_session(server.mcp._mcp_server) as client:
        result = await client.call_tool("etf_holdings", {"ticker": "SPY"})
    assert result.isError is False
    assert "Top holdings of **SPY**" in result.content[0].text
    assert result.structuredContent["source"] == "Acme Data"
    assert result.structuredContent["holdings"][0]["symbol"] == "NVDA"


class TestStartup:
    def test_bad_provider_fails_fast(self, monkeypatch):
        monkeypatch.setenv("ETF_DATA_PROVIDER", "no_such_pkg_xyz:Thing")
        with pytest.raises(SystemExit) as exc:
            server.main(["--transport", "stdio"])
        assert "cannot import module" in str(exc.value)
