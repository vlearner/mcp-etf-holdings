"""
Reusable prompt templates exposed over MCP.

Clients surface these as slash-commands (Claude Code, Claude Desktop), giving
users a starting point for the questions this server is good at without having
to know which tool does what.

Registration takes the FastMCP instance as an argument rather than importing it
from `server`, which would be circular.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

DISCLAIMER = (
    "Close with a one-line reminder that this is data, not financial advice."
)


def register_prompts(mcp: FastMCP) -> None:
    """Attach every prompt template to `mcp`."""

    @mcp.prompt()
    def etf_deep_dive(ticker: str) -> str:
        """Full workup on a single ETF: costs, size, returns, and concentration."""
        return (
            f"Give me a deep dive on the ETF {ticker}.\n\n"
            f"1. Call etf_info('{ticker}') for costs, size, and trailing returns.\n"
            f"2. Call etf_holdings('{ticker}') for the top positions.\n"
            "3. Summarise: what the fund tracks, what it costs relative to "
            "typical funds in its category, and how concentrated it is — call "
            "out the combined weight of the top 5 holdings and whether any "
            "single position dominates.\n"
            f"4. Note that only the top ~10-15 positions are disclosed, so the "
            "concentration figure is a floor, not the full portfolio.\n\n"
            f"{DISCLAIMER}"
        )

    @mcp.prompt()
    def compare_funds(tickers: str) -> str:
        """Side-by-side comparison of several ETFs on cost, size, and returns."""
        return (
            f"Compare these ETFs: {tickers}.\n\n"
            "1. Call compare_etfs once with all the tickers — do not call "
            "etf_info repeatedly.\n"
            "2. Present the table as returned.\n"
            "3. Below it, explain in a few lines: which is cheapest, which is "
            "largest, and whether the returns differ enough to matter given the "
            "fee gap. If two funds track the same thing, say so plainly.\n"
            "4. If any ticker returned no data, flag it rather than silently "
            "dropping it.\n\n"
            f"{DISCLAIMER}"
        )

    @mcp.prompt()
    def stock_exposure(stock: str) -> str:
        """Find the ETFs that give exposure to a stock, ranked by cost and weight."""
        return (
            f"I want ETF exposure to {stock}.\n\n"
            f"1. If '{stock}' is a company name rather than a ticker, call "
            "lookup_symbol first to resolve it.\n"
            "2. Call stock_exposure_summary with the ticker.\n"
            "3. Present the table, then point out the trade-off: the highest-"
            "weight fund gives the most concentrated exposure, the lowest-"
            "expense fund the cheapest, and these are rarely the same fund.\n"
            "4. Mention that only disclosed top holdings are searched, so funds "
            "holding the stock in a smaller position will not appear.\n\n"
            f"{DISCLAIMER}"
        )

    @mcp.prompt()
    def portfolio_checkup(tickers: str) -> str:
        """Check a set of ETFs for overlapping positions and duplicated exposure."""
        return (
            f"I hold these ETFs: {tickers}. Check whether I am doubling up.\n\n"
            "1. Call etf_holdings for each ticker.\n"
            "2. Call compare_etfs with all of them for costs and categories.\n"
            "3. Build a table of holdings that appear in more than one fund, "
            "with each fund's weight in that holding and the combined weight "
            "across the portfolio (assume equal weighting between funds unless "
            "I said otherwise).\n"
            "4. Say plainly whether these funds are largely redundant, "
            "complementary, or somewhere in between.\n"
            "5. Note the limitation: only the top ~10-15 positions per fund are "
            "disclosed, so real overlap is at least what you found, likely more.\n\n"
            f"{DISCLAIMER}"
        )

    @mcp.prompt()
    def theme_explorer(theme: str) -> str:
        """Discover ETFs for a theme or sector and compare the leading options."""
        return (
            f"Find me ETFs for the '{theme}' theme.\n\n"
            f"1. Call search_etfs('{theme}') to discover candidates.\n"
            "2. Call compare_etfs with the most relevant 3-5 tickers from those "
            "results.\n"
            "3. For the top candidate, call etf_holdings so I can see what I "
            "would actually own — themed funds often hold less of the theme "
            "than the name suggests.\n"
            "4. Summarise which fund is the most direct expression of the theme "
            "and which is the cheapest.\n\n"
            f"{DISCLAIMER}"
        )
