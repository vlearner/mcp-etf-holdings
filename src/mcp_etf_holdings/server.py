"""
ETF Holdings MCP Server

Exposes seven tools to Claude (or any MCP client):

  etf_info               – metadata for a single ETF (AUM, expense ratio, returns …)
  compare_etfs           – several ETFs side by side in one table
  etf_holdings           – top holdings of an ETF with weights
  find_etfs_holding_stock – reverse lookup: which ETFs hold a given stock?
  stock_exposure_summary – ETFs holding a stock, with cost and size for each
  search_etfs            – search ETFs by name, theme, or category
  lookup_symbol          – resolve a company or fund name to its ticker

Run directly:
    python -m mcp_etf_holdings

Or via the installed script:
    mcp-etf-holdings
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .fetcher import (
    find_etfs_holding_stock as _find_etfs_holding_stock,
    get_etf_holdings,
    get_etf_info,
    get_etf_infos,
    resolve_stock_symbol,
    search_etfs as _search_etfs,
    search_symbols as _search_symbols,
)
from .formatting import (
    EMPTY,
    fmt_aum,
    fmt_pct,
    fmt_return,
    fmt_weight,
    markdown_table,
)
from .prompts import register_prompts
from .top_etfs import TOP_ETFS

# Comparing more funds than this makes the table unreadable and fans out a lot
# of Yahoo requests for a single tool call.
MAX_COMPARE = 10

mcp = FastMCP(
    "ETF Holdings",
    instructions=(
        "Use these tools to look up ETF holdings data and perform reverse "
        "lookups (which ETFs hold a given stock). All data is sourced live "
        "from Yahoo Finance via yfinance.\n\n"
        "Guidelines:\n"
        "- When the user asks about more than one ETF, call compare_etfs once "
        "with all the tickers instead of calling etf_info repeatedly — it "
        "returns a single side-by-side table.\n"
        "- When the user names a company or fund instead of giving a ticker "
        "('Nvidia', 'Vanguard total market'), call lookup_symbol first to "
        "resolve it, then pass the resolved symbol to the other tools.\n"
        "- stock_exposure_summary answers 'what is the cheapest/largest ETF "
        "for exposure to X'; find_etfs_holding_stock is the plain reverse "
        "lookup without cost data.\n"
        "- Tools return markdown; present tables as tables, do not re-flow "
        "them into prose lists."
    ),
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _normalize_tickers(tickers: list[str]) -> list[str]:
    """Upper-case, strip, drop blanks, de-duplicate preserving order."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in tickers:
        if not isinstance(raw, str):
            continue
        t = raw.strip().upper()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


async def _lookup_with_name_fallback(
    stock: str,
    *,
    limit: int,
    universe: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    """Reverse-lookup a stock, falling back to name resolution when it misses.

    Users type "Nvidia" where a ticker is expected, and the ticker pattern
    happily accepts it — so the failure would otherwise be a silent empty
    result. Only runs on a miss, so the happy path costs nothing.

    Returns (results, symbol_used, disclosure_note). The note is non-empty
    whenever the symbol searched is not the one the user typed; the guess is
    never silent.
    """
    symbol = stock.strip().upper()

    try:
        results = await _find_etfs_holding_stock(
            stock, etf_universe=universe, limit=limit
        )
    except ValueError:
        # Malformed input (e.g. "Berkshire Hathaway") — go straight to the
        # resolver rather than surfacing a validation error.
        results = []

    if results:
        return results, symbol, ""

    # Yahoo writes share classes with a dash (BRK-B, BF-B); people type the dot
    # form they see everywhere else. Retry that before the name search: left to
    # the resolver, "BRK.B" fuzzy-matches an unrelated fund (BRKC) and the
    # answer comes back confident and wrong.
    dashed = symbol.replace(".", "-")
    if dashed != symbol:
        try:
            results = await _find_etfs_holding_stock(
                dashed, etf_universe=universe, limit=limit
            )
        except ValueError:
            results = []
        if results:
            note = (
                f'> Interpreted "{stock.strip()}" as **{dashed}** '
                "(Yahoo writes share classes with a dash).\n"
            )
            return results, dashed, note

    match = await resolve_stock_symbol(stock)
    if not match:
        return [], symbol, ""

    resolved = str(match.get("symbol", "")).strip().upper()
    if not resolved or resolved == symbol:
        return [], symbol, ""

    try:
        results = await _find_etfs_holding_stock(
            resolved, etf_universe=universe, limit=limit
        )
    except ValueError:
        results = []

    name = match.get("name") or resolved
    note = f'> Interpreted "{stock.strip()}" as **{resolved}** ({name}).\n'
    return results, resolved, note


# ---------------------------------------------------------------------------
# Tool: etf_info
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_info(
    ticker: Annotated[
        str, Field(description="ETF ticker symbol, e.g. 'SPY' or 'QQQ'")
    ],
) -> str:
    """Return metadata for a single ETF: name, category, AUM, expense ratio, NAV, and trailing returns.

    For two or more ETFs, use compare_etfs instead — it returns one table.
    """
    data = await get_etf_info(ticker)
    if not data.get("name"):
        return f"No data found for ticker '{ticker}'. Verify it is a valid ETF symbol."

    lines = [
        f"**{data['ticker']}** – {data['name']}",
        f"Category      : {data['category'] or 'N/A'}",
        f"AUM           : {fmt_aum(data['total_assets'])}",
        f"Expense ratio : {fmt_pct(data['expense_ratio'])}",
        f"Dividend yield: {fmt_pct(data['yield'])}",
        f"NAV/price     : {data['nav_price'] or 'N/A'} {data['currency']}",
        f"YTD return    : {fmt_return(data['ytd_return'])}",
        f"3-yr return   : {fmt_return(data['three_year_return'])}",
        f"5-yr return   : {fmt_return(data['five_year_return'])}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool: compare_etfs
# ---------------------------------------------------------------------------


@mcp.tool()
async def compare_etfs(
    tickers: Annotated[
        list[str],
        Field(
            description=(
                "ETF tickers to compare side by side, "
                "e.g. ['SPY', 'QQQ', 'VTI', 'SCHD']"
            )
        ),
    ],
) -> str:
    """
    Compare several ETFs side by side in a single table: name, category, AUM,
    expense ratio, dividend yield, and YTD / 3-yr / 5-yr returns.

    Use this whenever the user mentions more than one ETF — it is one call
    instead of several etf_info calls, and the result is already tabular.
    """
    if not isinstance(tickers, list) or not tickers:
        return "Provide a list of ETF tickers, e.g. ['SPY', 'QQQ', 'VTI']."

    symbols = _normalize_tickers(tickers)
    if not symbols:
        return "Provide a list of ETF tickers, e.g. ['SPY', 'QQQ', 'VTI']."

    dropped = symbols[MAX_COMPARE:]
    symbols = symbols[:MAX_COMPARE]

    infos = await get_etf_infos(symbols)

    rows: list[list[object]] = []
    missing: list[str] = []
    for symbol, data in zip(symbols, infos):
        if not data.get("name"):
            missing.append(symbol)
            rows.append([symbol] + [EMPTY] * 8)
            continue
        rows.append(
            [
                symbol,
                data["name"],
                data["category"] or EMPTY,
                fmt_aum(data["total_assets"]),
                fmt_pct(data["expense_ratio"]),
                fmt_pct(data["yield"]),
                fmt_return(data["ytd_return"]),
                fmt_return(data["three_year_return"]),
                fmt_return(data["five_year_return"]),
            ]
        )

    table = markdown_table(
        ["Ticker", "Name", "Category", "AUM", "Expense", "Yield", "YTD", "3-Yr", "5-Yr"],
        rows,
        align=["left", "left", "left", "right", "right", "right", "right", "right", "right"],
    )

    out = [f"Comparing {len(symbols)} ETF(s):\n", table]
    if missing:
        out.append(
            f"\nNo data returned for: {', '.join(missing)}. "
            "Verify these are valid ETF symbols."
        )
    if dropped:
        out.append(
            f"\nOnly the first {MAX_COMPARE} tickers were compared; "
            f"omitted: {', '.join(dropped)}."
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Tool: etf_holdings
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_holdings(
    ticker: Annotated[str, Field(description="ETF ticker symbol, e.g. 'SPY'")],
) -> str:
    """Return the top holdings of an ETF with their portfolio weight percentages."""
    holdings = await get_etf_holdings(ticker)
    if not holdings:
        return (
            f"No holdings data found for '{ticker}'. "
            "The ticker may not be an ETF, or holdings data may be unavailable."
        )

    rows = [
        [i, h["symbol"], h["name"], fmt_weight(h["weight_pct"])]
        for i, h in enumerate(holdings, 1)
    ]
    table = markdown_table(
        ["#", "Symbol", "Name", "Weight"],
        rows,
        align=["right", "left", "left", "right"],
    )
    return f"Top holdings of **{ticker.strip().upper()}**:\n\n{table}"


# ---------------------------------------------------------------------------
# Tool: find_etfs_holding_stock
# ---------------------------------------------------------------------------


@mcp.tool()
async def find_etfs_holding_stock(
    stock_ticker: Annotated[
        str,
        Field(
            description=(
                "Stock ticker or company name to search for, "
                "e.g. 'NVDA' or 'Nvidia'"
            )
        ),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of ETFs to return (1-50, default 20)"),
    ] = 20,
    custom_etf_universe: Annotated[
        str,
        Field(
            description=(
                "Optional JSON array of ETF tickers to search instead of the "
                'default universe. Example: \'["SPY","QQQ","XLK"]\''
            )
        ),
    ] = "",
) -> str:
    """
    Reverse-lookup: find ETFs (from a ~365-ETF universe or a custom list)
    that hold a given stock in their disclosed top holdings.

    Results are sorted by the stock's weight in each ETF, highest first.
    For a version that also reports each ETF's expense ratio and size, use
    stock_exposure_summary.
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

    results, symbol, note = await _lookup_with_name_fallback(
        stock_ticker, limit=limit, universe=universe
    )
    searched = len(universe) if universe else len(TOP_ETFS)

    if not results:
        return (
            f"{note}'{symbol}' was not found in the top holdings of any ETF "
            f"among the {searched} ETFs searched. "
            "Try a custom_etf_universe or note that only top holdings (~10-15 positions) are checked."
        )

    rows = [
        [r["etf"], fmt_weight(r["weight_pct"]), f"#{r['rank_in_etf']}"]
        for r in results
    ]
    table = markdown_table(
        ["ETF", "Weight", "Rank in ETF"],
        rows,
        align=["left", "right", "right"],
    )
    header = (
        f"**{symbol}** appears in the top holdings of "
        f"{len(results)} ETF(s) (searched {searched}):"
    )
    return f"{note}{header}\n\n{table}"


# ---------------------------------------------------------------------------
# Tool: stock_exposure_summary
# ---------------------------------------------------------------------------


@mcp.tool()
async def stock_exposure_summary(
    stock: Annotated[
        str,
        Field(
            description=(
                "Stock ticker or company name to find ETF exposure for, "
                "e.g. 'NVDA' or 'Nvidia'"
            )
        ),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of ETFs to return (1-25, default 10)"),
    ] = 10,
) -> str:
    """
    Find the ETFs that give exposure to a stock, with each fund's weight in that
    stock alongside its expense ratio and AUM.

    Answers "what is the cheapest / largest ETF for exposure to X?" — the weight
    column shows how much exposure you get, expense ratio what it costs.
    """
    limit = max(1, min(limit, 25))

    results, symbol, note = await _lookup_with_name_fallback(stock, limit=limit)
    if not results:
        return (
            f"{note}'{symbol}' was not found in the top holdings of any of the "
            f"{len(TOP_ETFS)} ETFs searched. Only top holdings (~10-15 positions) "
            "are checked, so a small position will not appear."
        )

    etfs = [r["etf"] for r in results]
    infos = await get_etf_infos(etfs)
    info_by_ticker = {i["ticker"]: i for i in infos}

    rows: list[list[object]] = []
    for r in results:
        info = info_by_ticker.get(r["etf"].upper(), {})
        rows.append(
            [
                r["etf"],
                info.get("name") or EMPTY,
                fmt_weight(r["weight_pct"]),
                f"#{r['rank_in_etf']}",
                fmt_pct(info.get("expense_ratio")),
                fmt_aum(info.get("total_assets")),
            ]
        )

    table = markdown_table(
        ["ETF", "Name", "Weight", "Rank", "Expense", "AUM"],
        rows,
        align=["left", "left", "right", "right", "right", "right"],
    )
    header = (
        f"ETF exposure to **{symbol}** — {len(results)} fund(s), "
        "sorted by weight in the stock:"
    )
    return f"{note}{header}\n\n{table}"


# ---------------------------------------------------------------------------
# Tool: search_etfs
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_etfs(
    query: Annotated[
        str,
        Field(
            description=(
                "Search term: fund name, theme, or category, "
                "e.g. 'semiconductor' or 'dividend'"
            )
        ),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of ETFs to return (1-25, default 10)"),
    ] = 10,
) -> str:
    """
    Search for ETFs by name, theme, or category.

    Yahoo Finance search is the primary source; its hits are topped up from a
    curated index over the built-in ETF universe, which covers themes Yahoo's
    search answers poorly ("S&P 500", "bitcoin"). Live matches rank first.

    Returns matching ETF tickers with their full names and exchanges.
    Useful for discovering ETFs to pass to etf_info, compare_etfs,
    etf_holdings, or find_etfs_holding_stock.

    To resolve a stock or company name rather than find ETFs, use lookup_symbol.
    """
    if not query.strip():
        return "Provide a non-empty search query, e.g. 'semiconductor' or 'emerging markets'."
    limit = max(1, min(limit, 25))

    results = await _search_etfs(query, limit=limit)
    if not results:
        return f"No ETFs found matching '{query}'. Try a broader or different search term."

    rows = [[r["symbol"], r["name"], r["exchange"]] for r in results]
    table = markdown_table(["Symbol", "Name", "Exchange"], rows)
    return f"ETFs matching **'{query}'** ({len(results)} result(s)):\n\n{table}"


# ---------------------------------------------------------------------------
# Tool: lookup_symbol
# ---------------------------------------------------------------------------


_ASSET_TYPE_FILTERS: dict[str, tuple[str, ...] | None] = {
    "any": None,
    "stock": ("EQUITY",),
    "etf": ("ETF",),
}


@mcp.tool()
async def lookup_symbol(
    query: Annotated[
        str,
        Field(
            description=(
                "Company or fund name to resolve, e.g. 'Nvidia' or "
                "'Vanguard total stock market'"
            )
        ),
    ],
    limit: Annotated[
        int, Field(description="Maximum number of results (1-25, default 10)")
    ] = 10,
    asset_type: Annotated[
        str,
        Field(description="Filter results: 'any' (default), 'stock', or 'etf'"),
    ] = "any",
) -> str:
    """
    Resolve a company or fund name to its ticker symbol.

    Call this first whenever the user names a company instead of giving a
    ticker — "Which ETFs hold Nvidia?" needs NVDA. Covers stocks and ETFs;
    use asset_type='stock' to exclude funds from the results.
    """
    if not query.strip():
        return "Provide a non-empty name to look up, e.g. 'Nvidia' or 'Berkshire Hathaway'."
    limit = max(1, min(limit, 25))

    key = asset_type.strip().lower() if isinstance(asset_type, str) else "any"
    if key not in _ASSET_TYPE_FILTERS:
        return (
            f"Unknown asset_type '{asset_type}'. "
            f"Use one of: {', '.join(sorted(_ASSET_TYPE_FILTERS))}."
        )

    results = await _search_symbols(
        query, limit=limit, quote_types=_ASSET_TYPE_FILTERS[key]
    )
    if not results:
        return (
            f"No symbols found matching '{query}'"
            + (f" with asset_type '{key}'" if key != "any" else "")
            + ". Try a different or shorter name."
        )

    rows = [[r["symbol"], r["name"], r["type"], r["exchange"]] for r in results]
    table = markdown_table(["Symbol", "Name", "Type", "Exchange"], rows)
    return f"Symbols matching **'{query}'** ({len(results)} result(s)):\n\n{table}"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

register_prompts(mcp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
