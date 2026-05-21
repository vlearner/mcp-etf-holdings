"""
ETF Holdings data-fetcher agent.

High-level async functions that spin up the ETF Holdings MCP server as a
subprocess and call its tools over stdio. Intended for use from scripts,
notebooks, or other agents that need ETF data without running the server
as a persistent process.

Usage example:
    import asyncio
    from src.agents.data_fetcher import (
        fetch_etf_info,
        fetch_etf_holdings,
        fetch_etfs_holding_stock,
    )

    async def main():
        info = await fetch_etf_info("SPY")
        print(info)

        holders = await fetch_etfs_holding_stock("NVDA", limit=10)
        print(holders)

    asyncio.run(main())
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_servers.etf_holdings.server"],
    )


@asynccontextmanager
async def _session() -> AsyncGenerator[ClientSession, None]:
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    async with _session() as session:
        result = await session.call_tool(tool_name, arguments=arguments)
        parts = [block.text for block in result.content if hasattr(block, "text")]
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_etf_info(ticker: str) -> str:
    """Return formatted metadata for an ETF."""
    return await _call_tool("etf_info", {"ticker": ticker})


async def fetch_etf_holdings(ticker: str) -> str:
    """Return the top holdings of an ETF as a formatted string."""
    return await _call_tool("etf_holdings", {"ticker": ticker})


async def fetch_etfs_holding_stock(
    stock_ticker: str,
    *,
    limit: int = 20,
    custom_etf_universe: list[str] | None = None,
) -> str:
    """
    Return a formatted list of ETFs that hold *stock_ticker* in their top holdings.

    Args:
        stock_ticker: The stock ticker to search for (e.g. "AAPL").
        limit: Maximum number of ETFs to return (1-50).
        custom_etf_universe: If provided, search only these ETF tickers instead
            of the default ~100-ETF universe.
    """
    args: dict[str, Any] = {"stock_ticker": stock_ticker, "limit": limit}
    if custom_etf_universe:
        args["custom_etf_universe"] = json.dumps(custom_etf_universe)
    return await _call_tool("find_etfs_holding_stock", args)


# ---------------------------------------------------------------------------
# CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        tickers_to_demo = ["SPY", "QQQ"]
        stock_to_find = "NVDA"

        for etf in tickers_to_demo:
            print(f"\n{'='*60}")
            print(await fetch_etf_info(etf))
            print()
            print(await fetch_etf_holdings(etf))

        print(f"\n{'='*60}")
        print(await fetch_etfs_holding_stock(stock_to_find, limit=15))

    asyncio.run(_demo())
