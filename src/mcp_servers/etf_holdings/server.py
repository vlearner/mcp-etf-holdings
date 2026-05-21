"""
ETF Holdings MCP Server

Exposes three tools to Claude (or any MCP client):

  get_etf_info           – metadata for an ETF (AUM, expense ratio, returns …)
  get_etf_holdings       – top holdings of an ETF with weights
  find_etfs_holding_stock – reverse lookup: which ETFs hold a given stock?

Run directly:
    python -m src.mcp_servers.etf_holdings.server

Or via the installed script:
    etf-holdings-server
"""

from __future__ import annotations

import json
from typing import Annotated

from mcp.server.fastmcp import FastMCP

from .fetcher import find_etfs_holding_stock as _find_etfs_holding_stock, get_etf_holdings, get_etf_info
from .top_etfs import TOP_ETFS

mcp = FastMCP(
    "ETF Holdings",
    instructions=(
        "Use these tools to look up ETF holdings data and perform reverse "
        "lookups (which ETFs hold a given stock). All data is sourced live "
        "from Yahoo Finance via yfinance."
    ),
)


# ---------------------------------------------------------------------------
# Tool: get_etf_info
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_info(
    ticker: Annotated[str, "ETF ticker symbol, e.g. 'SPY' or 'QQQ'"],
) -> str:
    """Return metadata for an ETF: name, category, AUM, expense ratio, NAV, and trailing returns."""
    data = await get_etf_info(ticker)
    if not data.get("name"):
        return f"No data found for ticker '{ticker}'. Verify it is a valid ETF symbol."

    aum = data["total_assets"]
    aum_str = f"${aum / 1e9:.2f}B" if aum and aum >= 1e9 else (f"${aum / 1e6:.1f}M" if aum else "N/A")
    er = data["expense_ratio"]
    er_str = f"{er * 100:.2f}%" if er else "N/A"
    yld = data["yield"]
    yld_str = f"{yld * 100:.2f}%" if yld else "N/A"

    def fmt_ret(v: float | None) -> str:
        return f"{v * 100:.2f}%" if v else "N/A"

    lines = [
        f"**{data['ticker']}** – {data['name']}",
        f"Category    : {data['category'] or 'N/A'}",
        f"AUM         : {aum_str}",
        f"Expense ratio: {er_str}",
        f"Dividend yield: {yld_str}",
        f"NAV/price   : {data['nav_price'] or 'N/A'} {data['currency']}",
        f"YTD return  : {fmt_ret(data['ytd_return'])}",
        f"3-yr return : {fmt_ret(data['three_year_return'])}",
        f"5-yr return : {fmt_ret(data['five_year_return'])}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: get_etf_holdings
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_holdings(
    ticker: Annotated[str, "ETF ticker symbol, e.g. 'SPY'"],
) -> str:
    """Return the top holdings of an ETF with their portfolio weight percentages."""
    holdings = await get_etf_holdings(ticker)
    if not holdings:
        return (
            f"No holdings data found for '{ticker}'. "
            "The ticker may not be an ETF, or holdings data may be unavailable."
        )

    lines = [f"Top holdings of **{ticker.upper()}**:\n"]
    for i, h in enumerate(holdings, 1):
        weight = h["weight_pct"]
        lines.append(f"  {i:2d}. {h['symbol']:<8s}  {weight:5.2f}%  {h['name']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: find_etfs_holding_stock
# ---------------------------------------------------------------------------


@mcp.tool()
async def find_etfs_holding_stock(
    stock_ticker: Annotated[str, "Stock ticker to search for, e.g. 'AAPL' or 'NVDA'"],
    limit: Annotated[int, "Maximum number of ETFs to return (1-50, default 20)"] = 20,
    custom_etf_universe: Annotated[
        str,
        "Optional JSON array of ETF tickers to search instead of the default universe. "
        "Example: '[\"SPY\",\"QQQ\",\"XLK\"]'",
    ] = "",
) -> str:
    """
    Reverse-lookup: find ETFs (from the top-~100 universe or a custom list)
    that hold a given stock in their disclosed top holdings.

    Results are sorted by the stock's weight in each ETF, highest first.
    """
    limit = max(1, min(limit, 50))
    universe: list[str] | None = None
    if custom_etf_universe.strip():
        try:
            universe = json.loads(custom_etf_universe)
            if not isinstance(universe, list):
                return "custom_etf_universe must be a JSON array of ticker strings."
        except json.JSONDecodeError as e:
            return f"Invalid JSON for custom_etf_universe: {e}"

    results = await _find_etfs_holding_stock(
        stock_ticker,
        etf_universe=universe,
        limit=limit,
    )

    if not results:
        searched = len(universe) if universe else len(TOP_ETFS)
        return (
            f"'{stock_ticker.upper()}' was not found in the top holdings of any ETF "
            f"among the {searched} ETFs searched. "
            "Try a custom_etf_universe or note that only top holdings (~10-15 positions) are checked."
        )

    searched = len(universe) if universe else len(TOP_ETFS)
    lines = [
        f"**{stock_ticker.upper()}** appears in the top holdings of "
        f"{len(results)} ETF(s) (searched {searched}):\n"
    ]
    for r in results:
        lines.append(
            f"  {r['etf']:<8s}  weight {r['weight_pct']:5.2f}%  "
            f"(rank #{r['rank_in_etf']} in that ETF)"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
