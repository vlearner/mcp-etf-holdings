"""
Data-fetching layer for ETF holdings.

All network I/O is synchronous (yfinance) but wrapped so callers can
await it from async context via run_in_executor.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import yfinance as yf

from .top_etfs import TOP_ETFS

_executor = ThreadPoolExecutor(max_workers=8)


# ---------------------------------------------------------------------------
# Internal sync helpers
# ---------------------------------------------------------------------------


def _etf_info_sync(ticker: str) -> dict[str, Any]:
    t = yf.Ticker(ticker.upper())
    info = t.info or {}
    return {
        "ticker": ticker.upper(),
        "name": info.get("longName") or info.get("shortName", ""),
        "category": info.get("category", ""),
        "total_assets": info.get("totalAssets"),
        "expense_ratio": info.get("annualReportExpenseRatio") or info.get("expenseRatio"),
        "yield": info.get("yield"),
        "ytd_return": info.get("ytdReturn"),
        "three_year_return": info.get("threeYearAverageReturn"),
        "five_year_return": info.get("fiveYearAverageReturn"),
        "nav_price": info.get("navPrice") or info.get("regularMarketPrice"),
        "currency": info.get("currency", "USD"),
    }


def _etf_holdings_sync(ticker: str) -> list[dict[str, Any]]:
    t = yf.Ticker(ticker.upper())
    try:
        fd = t.funds_data
        if fd is None:
            return []
        df = fd.top_holdings
        if df is None or df.empty:
            return []
        df = df.reset_index()
        records = []
        for _, row in df.iterrows():
            records.append(
                {
                    "symbol": str(row.get("Symbol", row.get("symbol", ""))),
                    "name": str(row.get("Name", row.get("holdingName", ""))),
                    "weight_pct": float(row.get("% Assets", row.get("holdingPercent", 0))) * 100
                    if float(row.get("% Assets", row.get("holdingPercent", 0))) <= 1
                    else float(row.get("% Assets", row.get("holdingPercent", 0))),
                }
            )
        return records
    except Exception:
        return []


def _find_etfs_holding_stock_sync(
    stock_ticker: str, etf_universe: list[str], limit: int
) -> list[dict[str, Any]]:
    stock_ticker = stock_ticker.upper()
    matches: list[dict[str, Any]] = []

    for etf in etf_universe:
        holdings = _etf_holdings_sync(etf)
        for h in holdings:
            if h["symbol"].upper() == stock_ticker:
                matches.append(
                    {
                        "etf": etf,
                        "stock": stock_ticker,
                        "weight_pct": h["weight_pct"],
                        "rank_in_etf": holdings.index(h) + 1,
                    }
                )
                break
        if len(matches) >= limit:
            break

    matches.sort(key=lambda x: x["weight_pct"], reverse=True)
    return matches


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def get_etf_info(ticker: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _etf_info_sync, ticker)


async def get_etf_holdings(ticker: str) -> list[dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _etf_holdings_sync, ticker)


async def find_etfs_holding_stock(
    stock_ticker: str,
    *,
    etf_universe: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    universe = etf_universe if etf_universe is not None else TOP_ETFS
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        _find_etfs_holding_stock_sync,
        stock_ticker,
        universe,
        limit,
    )
