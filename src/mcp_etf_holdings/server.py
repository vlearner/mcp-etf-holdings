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

import argparse
import json
import os
import sys
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult
from pydantic import Field

from .fetcher import (
    default_universe,
    find_etfs_holding_stock as _find_etfs_holding_stock,
    get_etf_holdings,
    get_etf_info,
    get_etf_infos,
    is_valid_ticker,
    resolve_stock_symbol,
    search_etfs as _search_etfs,
    search_symbols as _search_symbols,
    supports_search,
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
from .providers import ProviderError, get_provider
from .results import notice, reply

# Comparing more funds than this makes the table unreadable and fans out a lot
# of upstream requests for a single tool call.
MAX_COMPARE = 10

mcp = FastMCP(
    "ETF Holdings",
    instructions=(
        "Use these tools to look up ETF holdings data and perform reverse "
        "lookups (which ETFs hold a given stock). Data comes from the "
        "configured data provider (Yahoo Finance by default); each result's "
        "structured content names it in `source`.\n\n"
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
        "- Tools return markdown text plus structured JSON; present tables as "
        "tables, do not re-flow them into prose lists."
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
    whenever a name was interpreted as a ticker; the guess is never silent.
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


_NO_SEARCH = (
    "Name and theme search is not available with the '{source}' data provider. "
    "Use exact ticker symbols."
)


def _no_search() -> CallToolResult:
    return notice(_NO_SEARCH.format(source=get_provider().name), {"results": []})


# ---------------------------------------------------------------------------
# Tool: etf_info
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_info(
    ticker: Annotated[
        str, Field(description="ETF ticker symbol, e.g. 'SPY' or 'QQQ'")
    ],
) -> CallToolResult:
    """Return metadata for a single ETF: name, category, AUM, expense ratio, NAV, and trailing returns.

    For two or more ETFs, use compare_etfs instead — it returns one table.
    """
    ticker = ticker.strip()
    data = await get_etf_info(ticker)
    if not data.get("name"):
        return notice(
            f"No data found for ticker '{ticker}'. Verify it is a valid ETF symbol.",
            {"found": False, "etf": None},
        )

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
    return reply("\n".join(lines), {"found": True, "etf": data})


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
) -> CallToolResult:
    """
    Compare several ETFs side by side in a single table: name, category, AUM,
    expense ratio, dividend yield, and YTD / 3-yr / 5-yr returns.

    Use this whenever the user mentions more than one ETF — it is one call
    instead of several etf_info calls, and the result is already tabular.
    """
    empty = {"etfs": [], "missing": [], "omitted": []}
    if not isinstance(tickers, list) or not tickers:
        return notice("Provide a list of ETF tickers, e.g. ['SPY', 'QQQ', 'VTI'].", empty)

    symbols = _normalize_tickers(tickers)
    if not symbols:
        return notice("Provide a list of ETF tickers, e.g. ['SPY', 'QQQ', 'VTI'].", empty)

    dropped = symbols[MAX_COMPARE:]
    symbols = symbols[:MAX_COMPARE]

    # Entries that aren't even ticker-shaped (a pasted fund name) are reported as
    # missing rather than raising and discarding the rest of the comparison.
    valid = [s for s in symbols if is_valid_ticker(s)]
    info_by_symbol = dict(zip(valid, await get_etf_infos(valid)))

    rows: list[list[object]] = []
    missing: list[str] = []
    found: list[dict[str, Any]] = []
    for symbol in symbols:
        data = info_by_symbol.get(symbol, {})
        if not data.get("name"):
            missing.append(symbol)
            rows.append([symbol] + [EMPTY] * 8)
            continue
        found.append(data)
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
    return reply(
        "\n".join(out), {"etfs": found, "missing": missing, "omitted": dropped}
    )


# ---------------------------------------------------------------------------
# Tool: etf_holdings
# ---------------------------------------------------------------------------


@mcp.tool()
async def etf_holdings(
    ticker: Annotated[str, Field(description="ETF ticker symbol, e.g. 'SPY'")],
) -> CallToolResult:
    """Return the top holdings of an ETF with their portfolio weight percentages."""
    ticker = ticker.strip()
    holdings = await get_etf_holdings(ticker)
    if not holdings:
        return notice(
            f"No holdings data found for '{ticker}'. "
            "The ticker may not be an ETF, or holdings data may be unavailable.",
            {"ticker": ticker.upper(), "holdings": []},
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
    return reply(
        f"Top holdings of **{ticker.upper()}**:\n\n{table}",
        {
            "ticker": ticker.upper(),
            "holdings": [{"rank": i, **h} for i, h in enumerate(holdings, 1)],
        },
    )


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
) -> CallToolResult:
    """
    Reverse-lookup: find ETFs (from the default universe, ~365 ETFs, or a custom list)
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
                return notice(
                    "custom_etf_universe must be a JSON array of ticker strings.",
                    {"matches": []},
                )
        except json.JSONDecodeError as e:
            return notice(f"Invalid JSON for custom_etf_universe: {e}", {"matches": []})

    results, symbol, note = await _lookup_with_name_fallback(
        stock_ticker, limit=limit, universe=universe
    )
    searched = len(universe) if universe else len(default_universe())
    base = {
        "stock": symbol,
        "interpreted_from": stock_ticker.strip() if note else None,
        "searched": searched,
    }

    if not results:
        return notice(
            f"{note}'{symbol}' was not found in the top holdings of any ETF "
            f"among the {searched} ETFs searched. "
            "Try a custom_etf_universe or note that only top holdings (~10-15 positions) are checked.",
            {**base, "matches": []},
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
    matches = [
        {"etf": r["etf"], "weight_pct": r["weight_pct"], "rank_in_etf": r["rank_in_etf"]}
        for r in results
    ]
    return reply(f"{note}{header}\n\n{table}", {**base, "matches": matches})


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
) -> CallToolResult:
    """
    Find the ETFs that give exposure to a stock, with each fund's weight in that
    stock alongside its expense ratio and AUM.

    Answers "what is the cheapest / largest ETF for exposure to X?" — the weight
    column shows how much exposure you get, expense ratio what it costs.
    """
    limit = max(1, min(limit, 25))

    results, symbol, note = await _lookup_with_name_fallback(stock, limit=limit)
    searched = len(default_universe())
    base = {
        "stock": symbol,
        "interpreted_from": stock.strip() if note else None,
        "searched": searched,
    }
    if not results:
        return notice(
            f"{note}'{symbol}' was not found in the top holdings of any of the "
            f"{searched} ETFs searched. Only top holdings (~10-15 positions) "
            "are checked, so a small position will not appear.",
            {**base, "matches": []},
        )

    etfs = [r["etf"] for r in results]
    infos = await get_etf_infos(etfs)
    info_by_ticker = {i["ticker"]: i for i in infos}

    rows: list[list[object]] = []
    matches: list[dict[str, Any]] = []
    for r in results:
        info = info_by_ticker.get(r["etf"].upper(), {})
        matches.append(
            {
                "etf": r["etf"],
                "name": info.get("name") or None,
                "weight_pct": r["weight_pct"],
                "rank_in_etf": r["rank_in_etf"],
                "expense_ratio": info.get("expense_ratio"),
                "total_assets": info.get("total_assets"),
            }
        )
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
    return reply(f"{note}{header}\n\n{table}", {**base, "matches": matches})


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
) -> CallToolResult:
    """
    Search for ETFs by name, theme, or category.

    Returns matching ETF tickers with their full names and exchanges.
    Useful for discovering ETFs to pass to etf_info, compare_etfs,
    etf_holdings, or find_etfs_holding_stock.

    To resolve a stock or company name rather than find ETFs, use lookup_symbol.
    """
    if not query.strip():
        return notice(
            "Provide a non-empty search query, e.g. 'semiconductor' or 'emerging markets'.",
            {"query": query, "results": []},
        )
    if not supports_search():
        return _no_search()
    limit = max(1, min(limit, 25))

    results = await _search_etfs(query, limit=limit)
    if not results:
        return notice(
            f"No ETFs found matching '{query}'. Try a broader or different search term.",
            {"query": query, "results": []},
        )

    rows = [[r["symbol"], r["name"], r["exchange"]] for r in results]
    table = markdown_table(["Symbol", "Name", "Exchange"], rows)
    return reply(
        f"ETFs matching **'{query}'** ({len(results)} result(s)):\n\n{table}",
        {
            "query": query,
            "results": [
                {"symbol": r["symbol"], "name": r["name"], "exchange": r["exchange"]}
                for r in results
            ],
        },
    )


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
) -> CallToolResult:
    """
    Resolve a company or fund name to its ticker symbol.

    Call this first whenever the user names a company instead of giving a
    ticker — "Which ETFs hold Nvidia?" needs NVDA. Covers stocks and ETFs;
    use asset_type='stock' to exclude funds from the results.
    """
    empty = {"query": query, "results": []}
    if not query.strip():
        return notice(
            "Provide a non-empty name to look up, e.g. 'Nvidia' or 'Berkshire Hathaway'.",
            empty,
        )
    if not supports_search():
        return _no_search()
    limit = max(1, min(limit, 25))

    key = asset_type.strip().lower() if isinstance(asset_type, str) else "any"
    if key not in _ASSET_TYPE_FILTERS:
        return notice(
            f"Unknown asset_type '{asset_type}'. "
            f"Use one of: {', '.join(sorted(_ASSET_TYPE_FILTERS))}.",
            empty,
        )

    results = await _search_symbols(
        query, limit=limit, quote_types=_ASSET_TYPE_FILTERS[key]
    )
    if not results:
        return notice(
            f"No symbols found matching '{query}'"
            + (f" with asset_type '{key}'" if key != "any" else "")
            + ". Try a different or shorter name.",
            empty,
        )

    rows = [[r["symbol"], r["name"], r["type"], r["exchange"]] for r in results]
    table = markdown_table(["Symbol", "Name", "Type", "Exchange"], rows)
    return reply(
        f"Symbols matching **'{query}'** ({len(results)} result(s)):\n\n{table}",
        {
            "query": query,
            "results": [
                {
                    "symbol": r["symbol"],
                    "name": r["name"],
                    "type": r["type"],
                    "exchange": r["exchange"],
                }
                for r in results
            ],
        },
    )


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

register_prompts(mcp)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mcp-etf-holdings",
        description="ETF holdings MCP server. Speaks stdio unless told otherwise.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="stdio (default) or http (streamable HTTP at /mcp)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "127.0.0.1"),
        help="HTTP bind address (default 127.0.0.1; there is no authentication)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=os.environ.get("MCP_PORT", "8000"),  # argparse applies type=int
        help="HTTP port (default 8000)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        # Load now so a misconfigured ETF_DATA_PROVIDER fails at startup with a
        # clear message, not on the first tool call.
        provider = get_provider()
    except ProviderError as e:
        sys.exit(f"mcp-etf-holdings: {e}")
    print(f"mcp-etf-holdings: data provider: {provider.name}", file=sys.stderr)
    if args.transport == "http":
        # The server has no authentication, so anything but loopback exposes
        # data tools to the network. Allow it, but say so loudly.
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print(
                f"WARNING: binding to {args.host} with no authentication; "
                "put an authenticating proxy in front of this.",
                file=sys.stderr,
            )
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
