"""
Data-fetching layer for ETF holdings.

All network I/O is synchronous (yfinance) but wrapped so callers can
await it from async context via run_in_executor.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import yfinance as yf

from .top_etfs import TOP_ETFS

_executor = ThreadPoolExecutor(max_workers=8)

CACHE_TTL_SECONDS = float(os.environ.get("ETF_CACHE_TTL_SECONDS", 24 * 60 * 60))


class _TTLCache:
    """Thread-safe in-memory cache with per-entry expiry."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[Any, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_info_cache = _TTLCache(CACHE_TTL_SECONDS)
_holdings_cache = _TTLCache(CACHE_TTL_SECONDS)


# ---------------------------------------------------------------------------
# Internal sync helpers
# ---------------------------------------------------------------------------


def _etf_info_sync(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper()
    cached = _info_cache.get(ticker)
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    info = t.info or {}
    result = {
        "ticker": ticker,
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
    if result["name"]:
        _info_cache.set(ticker, result)
    return result


def _etf_holdings_sync(ticker: str) -> list[dict[str, Any]]:
    ticker = ticker.upper()
    cached = _holdings_cache.get(ticker)
    if cached is not None:
        return cached
    t = yf.Ticker(ticker)
    try:
        fd = t.funds_data
        if fd is None:
            # Legit empty (e.g. bond/commodity funds): cache so universe
            # scans don't re-fetch it every time. Exceptions are NOT cached.
            _holdings_cache.set(ticker, [])
            return []
        df = fd.top_holdings
        if df is None or df.empty:
            _holdings_cache.set(ticker, [])
            return []
        df = df.reset_index()
        records = []
        for _, row in df.iterrows():
            weight = 0.0
            # Column name varies across yfinance versions
            for key in ("Holding Percent", "% Assets", "holdingPercent"):
                if key in row and row[key] == row[key]:  # skip missing/NaN
                    weight = float(row[key])
                    break
            if weight <= 1:
                weight *= 100  # fraction -> percent
            records.append(
                {
                    "symbol": str(row.get("Symbol", row.get("symbol", ""))),
                    "name": str(row.get("Name", row.get("holdingName", ""))),
                    "weight_pct": weight,
                }
            )
        _holdings_cache.set(ticker, records)
        return records
    except Exception:
        return []


def _search_etfs_sync(query: str, limit: int) -> list[dict[str, Any]]:
    try:
        # Request extra results since non-ETF quotes get filtered out.
        search = yf.Search(query, max_results=min(limit * 3, 50))
        quotes = search.quotes or []
    except Exception:
        return []

    results: list[dict[str, Any]] = []
    for q in quotes:
        if str(q.get("quoteType", "")).upper() != "ETF":
            continue
        results.append(
            {
                "symbol": q.get("symbol", ""),
                "name": q.get("longname") or q.get("shortname", ""),
                "exchange": q.get("exchDisp") or q.get("exchange", ""),
            }
        )
        if len(results) >= limit:
            break
    return results


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def get_etf_info(ticker: str) -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _etf_info_sync, ticker)


async def get_etf_holdings(ticker: str) -> list[dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _etf_holdings_sync, ticker)


async def search_etfs(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _search_etfs_sync, query, limit)


async def find_etfs_holding_stock(
    stock_ticker: str,
    *,
    etf_universe: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    universe = etf_universe if etf_universe is not None else TOP_ETFS
    stock = stock_ticker.upper()

    # Fetch all holdings in parallel (bounded by the executor's worker pool);
    # scanning the full universe before sorting yields the true top-N by weight.
    all_holdings = await asyncio.gather(*(get_etf_holdings(etf) for etf in universe))

    matches: list[dict[str, Any]] = []
    for etf, holdings in zip(universe, all_holdings):
        for rank, h in enumerate(holdings, 1):
            if h["symbol"].upper() == stock:
                matches.append(
                    {
                        "etf": etf,
                        "stock": stock,
                        "weight_pct": h["weight_pct"],
                        "rank_in_etf": rank,
                    }
                )
                break

    matches.sort(key=lambda x: x["weight_pct"], reverse=True)
    return matches[:limit]
