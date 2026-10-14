"""Pluggable data providers: loading, validation, and how the shared layer treats them."""

import sys
import types

import pytest

from mcp_etf_holdings import fetcher, providers
from mcp_etf_holdings.providers import ProviderError, YFinanceProvider, load_provider


class FakeProvider:
    name = "Acme Data"

    def __init__(self):
        self.calls = []

    def get_info(self, ticker):
        self.calls.append(("info", ticker))
        return {
            "name": f"{ticker} Fund",
            "category": "Large Blend",
            "total_assets": 5e9,
            "expense_ratio": 0.0005,
            "unexpected_field": "dropped",
        }

    def get_holdings(self, ticker):
        self.calls.append(("holdings", ticker))
        return [
            {"symbol": "nvda", "name": "NVIDIA", "weight_pct": 7.5},
            {"symbol": "AAPL", "name": "Apple", "weight_pct": 250},  # clamped
            {"symbol": "BAD", "weight_pct": "n/a"},                    # -> 0
            "garbage",                                                 # skipped
        ]

    def search(self, query, limit, quote_types):
        self.calls.append(("search", query, limit, quote_types))
        return [
            {"symbol": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ", "type": "EQUITY"},
            {"symbol": "NQ=F", "name": "Futures", "exchange": "CME", "type": "FUTURE"},
        ]


class MinimalProvider:
    """Only the required methods, no name, async."""

    name = "Minimal"

    async def get_info(self, ticker):
        return {"name": "Async Fund"}

    async def get_holdings(self, ticker):
        return [{"symbol": "MSFT", "name": "Microsoft", "weight_pct": 5}]


@pytest.fixture
def plugin_module(monkeypatch):
    mod = types.ModuleType("acme_plugin")
    mod.FakeProvider = FakeProvider
    mod.instance = FakeProvider()
    mod.factory = lambda: FakeProvider()
    mod.NotAProvider = object
    monkeypatch.setitem(sys.modules, "acme_plugin", mod)
    return mod


class TestLoading:
    def test_default_is_yfinance(self):
        assert isinstance(load_provider(), YFinanceProvider)
        assert isinstance(load_provider("yfinance"), YFinanceProvider)
        assert isinstance(load_provider("  YFinance "), YFinanceProvider)

    def test_loads_class(self, plugin_module):
        assert isinstance(load_provider("acme_plugin:FakeProvider"), FakeProvider)

    def test_loads_instance_and_factory(self, plugin_module):
        assert load_provider("acme_plugin:instance") is plugin_module.instance
        assert isinstance(load_provider("acme_plugin:factory"), FakeProvider)

    def test_reads_env_var(self, plugin_module, monkeypatch):
        monkeypatch.setenv("ETF_DATA_PROVIDER", "acme_plugin:FakeProvider")
        assert isinstance(load_provider(), FakeProvider)

    def test_missing_module(self):
        with pytest.raises(ProviderError, match="cannot import module"):
            load_provider("no_such_pkg_xyz:Thing")

    def test_missing_attribute(self, plugin_module):
        with pytest.raises(ProviderError, match="no attribute"):
            load_provider("acme_plugin:Nope")

    def test_bad_form(self):
        with pytest.raises(ProviderError, match="package.module:Name"):
            load_provider("acme_plugin:")

    def test_unknown_plain_name_lists_choices(self):
        with pytest.raises(ProviderError, match="yfinance"):
            load_provider("bloomberg")

    def test_entry_point_name(self, monkeypatch):
        ep = types.SimpleNamespace(name="acme", load=lambda: FakeProvider)
        monkeypatch.setattr(providers, "entry_points", lambda group: [ep])
        assert isinstance(load_provider("acme"), FakeProvider)

    def test_missing_required_methods(self, plugin_module):
        with pytest.raises(ProviderError, match="get_info, get_holdings"):
            load_provider("acme_plugin:NotAProvider")

    def test_constructor_failure_is_wrapped(self, monkeypatch):
        class Boom:
            def __init__(self):
                raise RuntimeError("no credentials")

        mod = types.ModuleType("boom_plugin")
        mod.Boom = Boom
        monkeypatch.setitem(sys.modules, "boom_plugin", mod)
        with pytest.raises(ProviderError, match="no credentials"):
            load_provider("boom_plugin:Boom")

    def test_missing_name_defaults_to_spec(self, monkeypatch):
        class Nameless:
            def get_info(self, t):
                return {}

            def get_holdings(self, t):
                return []

        mod = types.ModuleType("nameless_plugin")
        mod.P = Nameless
        monkeypatch.setitem(sys.modules, "nameless_plugin", mod)
        assert load_provider("nameless_plugin:P").name == "nameless_plugin:P"


class TestSharedLayerWithCustomProvider:
    def test_info_is_normalized_and_cached(self):
        p = FakeProvider()
        providers.set_provider(p)
        info = fetcher._etf_info_sync("spy")
        assert info["ticker"] == "SPY"
        assert info["name"] == "SPY Fund"
        assert info["currency"] == "USD"            # default filled in
        assert info["yield"] is None                # missing field filled in
        assert "unexpected_field" not in info
        fetcher._etf_info_sync("SPY")
        assert [c for c in p.calls if c[0] == "info"] == [("info", "SPY")]  # cached

    def test_holdings_are_normalized(self):
        providers.set_provider(FakeProvider())
        h = fetcher._etf_holdings_sync("SPY")
        assert [x["symbol"] for x in h] == ["NVDA", "AAPL", "BAD"]
        assert [x["weight_pct"] for x in h] == [7.5, 100.0, 0.0]

    def test_custom_weights_are_percent_not_fractions(self):
        """A provider returning 0.5 means 0.5%, not 50% (the Yahoo heuristic is Yahoo-only)."""

        class P:
            name = "p"

            def get_info(self, t):
                return {"name": "x"}

            def get_holdings(self, t):
                return [{"symbol": "A", "weight_pct": 0.5}]

        providers.set_provider(P())
        assert fetcher._etf_holdings_sync("SPY")[0]["weight_pct"] == 0.5

    def test_provider_exception_degrades_and_is_negative_cached(self):
        class Failing(FakeProvider):
            def get_holdings(self, ticker):
                self.calls.append(("holdings", ticker))
                raise ConnectionError("upstream down")

        p = Failing()
        providers.set_provider(p)
        assert fetcher._etf_holdings_sync("SPY") == []
        assert fetcher._etf_holdings_sync("SPY") == []
        assert len([c for c in p.calls if c[0] == "holdings"]) == 1

    def test_bad_return_type_degrades(self):
        class Bad(FakeProvider):
            def get_info(self, ticker):
                return "not a dict"

        providers.set_provider(Bad())
        assert fetcher._etf_info_sync("SPY")["name"] == ""

    @pytest.mark.asyncio
    async def test_async_provider_methods(self):
        providers.set_provider(MinimalProvider())
        assert (await fetcher.get_etf_info("SPY"))["name"] == "Async Fund"
        assert (await fetcher.get_etf_holdings("SPY"))[0]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_reverse_lookup_uses_provider_universe(self):
        class P(FakeProvider):
            default_universe = ["AAA", "BBB"]

        p = P()
        providers.set_provider(p)
        out = await fetcher.find_etfs_holding_stock("NVDA")
        assert sorted(c[1] for c in p.calls if c[0] == "holdings") == ["AAA", "BBB"]
        assert [m["etf"] for m in out] == ["AAA", "BBB"]

    def test_default_universe_falls_back_to_builtin(self):
        providers.set_provider(FakeProvider())
        assert fetcher.default_universe() is fetcher.TOP_ETFS

    @pytest.mark.asyncio
    async def test_search_is_filtered_and_normalized(self):
        providers.set_provider(FakeProvider())
        out = await fetcher.search_symbols("nvidia", limit=5, quote_types=("EQUITY",))
        assert [r["symbol"] for r in out] == ["NVDA"]

    @pytest.mark.asyncio
    async def test_search_unsupported(self):
        providers.set_provider(MinimalProvider())
        assert fetcher.supports_search() is False
        assert await fetcher.search_symbols("nvidia") == []
        assert await fetcher.resolve_stock_symbol("nvidia") is None


class TestExampleProvider:
    def test_rest_example_works_end_to_end(self):
        import importlib.util
        from pathlib import Path

        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["authorization"] == "Bearer tok"
            if request.url.path == "/etfs/SPY":
                return httpx.Response(200, json={"fundName": "S&P 500 Fund", "expenseRatioPct": 0.03})
            if request.url.path == "/etfs/SPY/holdings":
                return httpx.Response(
                    200, json={"holdings": [{"ticker": "NVDA", "name": "NVIDIA", "weightPct": 7.5}]}
                )
            return httpx.Response(404)

        path = Path(__file__).parent.parent / "examples" / "rest_provider.py"
        spec = importlib.util.spec_from_file_location("rest_provider_example", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = httpx.Client(
            base_url="https://data.test",
            headers={"Authorization": "Bearer tok"},
            transport=httpx.MockTransport(handler),
        )
        providers.set_provider(mod.RestProvider(client))

        info = fetcher._etf_info_sync("SPY")
        assert info["name"] == "S&P 500 Fund"
        assert info["expense_ratio"] == pytest.approx(0.0003)
        assert fetcher._etf_holdings_sync("SPY")[0]["weight_pct"] == 7.5
        assert fetcher._etf_holdings_sync("QQQ") == []  # 404 degrades, doesn't raise
