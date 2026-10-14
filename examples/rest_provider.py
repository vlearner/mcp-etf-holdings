"""Example data provider backed by an internal REST API.

Copy this file, adjust the URLs and field names to your API, and run the server with:

    ETF_DATA_PROVIDER=rest_provider:RestProvider \
    ETF_REST_BASE_URL=https://marketdata.internal.example.com \
    ETF_REST_TOKEN=... \
    PYTHONPATH=examples uvx mcp-etf-holdings

The provider only fetches and reshapes data. The server adds ticker validation,
caching, concurrency limits and error handling around it.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class RestProvider:
    name = "Internal market data"

    # Optional: the ETFs reverse lookup scans. Omit to use the built-in US list.
    default_universe = ["SPY", "QQQ", "VTI"]

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=os.environ["ETF_REST_BASE_URL"],
            headers={"Authorization": f"Bearer {os.environ['ETF_REST_TOKEN']}"},
            timeout=15.0,
        )

    def get_info(self, ticker: str) -> dict[str, Any]:
        r = self._client.get(f"/etfs/{ticker}")
        r.raise_for_status()
        d = r.json()
        return {
            "name": d["fundName"],
            "category": d.get("assetClass", ""),
            "total_assets": d.get("aum"),
            "expense_ratio": d.get("expenseRatioPct", 0) / 100,  # a FRACTION: 0.0003 == 0.03%
            "yield": d.get("distributionYield"),
            "currency": d.get("currency", "USD"),
        }

    def get_holdings(self, ticker: str) -> list[dict[str, Any]]:
        r = self._client.get(f"/etfs/{ticker}/holdings")
        r.raise_for_status()
        return [
            {"symbol": h["ticker"], "name": h["name"], "weight_pct": h["weightPct"]}  # PERCENT
            for h in r.json()["holdings"]
        ]

    def search(
        self, query: str, limit: int, quote_types: tuple[str, ...] | None
    ) -> list[dict[str, Any]]:
        r = self._client.get("/search", params={"q": query, "limit": limit})
        r.raise_for_status()
        return [
            {"symbol": s["ticker"], "name": s["name"], "exchange": s.get("mic", ""),
             "type": s.get("kind", "").upper()}  # "EQUITY" or "ETF"
            for s in r.json()["results"]
        ]
