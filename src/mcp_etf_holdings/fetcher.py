"""
Data-fetching layer for ETF holdings with security hardening.

All network I/O is synchronous (yfinance) but wrapped so callers can
await it from async context via run_in_executor.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import yfinance as yf

from .top_etfs import TOP_ETFS

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=8)

# Validate and load cache TTL from environment
def _get_cache_ttl() -> float:
    raw = os.environ.get("ETF_CACHE_TTL_SECONDS", str(24 * 60 * 60))
    try:
        ttl = float(raw)
    except ValueError:
        raise ValueError(f"ETF_CACHE_TTL_SECONDS must be a number, got {raw!r}") from None

    if ttl < 0:
        raise ValueError("ETF_CACHE_TTL_SECONDS must be >= 0")

    # Warn if cache is disabled or unreasonably large
    if ttl == 0:
        logger.warning("Cache disabled: ETF_CACHE_TTL_SECONDS=0")
    elif ttl > 7 * 24 * 60 * 60:  # 7 days
        logger.warning("Very long cache TTL: %d seconds (%.1f days)", ttl, ttl / (24 * 60 * 60))

    return ttl

CACHE_TTL_SECONDS = _get_cache_ttl()

# Semaphore to limit concurrent yfinance requests.
# Created lazily per event loop: an asyncio.Semaphore binds to the first loop
# that touches it, so a module-level instance breaks when the loop is replaced
# (e.g. one loop per test). Keep one semaphore per running loop instead.
_semaphores: "dict[asyncio.AbstractEventLoop, asyncio.Semaphore]" = {}


def _get_fetch_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(8)
        _semaphores[loop] = sem
    return sem

# Regex for valid ticker format
_TICKER_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")

def _is_valid_ticker(ticker: str) -> bool:
    return isinstance(ticker, str) and _TICKER_PATTERN.match(ticker.upper()) is not None


class _TTLCache:
    """Thread-safe in-memory cache with per-entry expiry and bounded size."""

    def __init__(self, ttl_seconds: float, max_size: int = 1000) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._data: OrderedDict[str, tuple[Any, float]] = OrderedDict()
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
            # Mark as recently used (move to end for LRU)
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self._max_size:
                # Evict oldest (least recently used)
                oldest_key = next(iter(self._data))
                del self._data[oldest_key]

            self._data[key] = (value, time.monotonic() + self._ttl)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._data)


_info_cache = _TTLCache(CACHE_TTL_SECONDS, max_size=5000)
_holdings_cache = _TTLCache(CACHE_TTL_SECONDS, max_size=5000)

# Transient error cache: cache errors with short TTL to avoid thundering herd
_error_cache = _TTLCache(60.0, max_size=1000)  # 60 second negative cache


# ---------------------------------------------------------------------------
# Internal sync helpers
# ---------------------------------------------------------------------------


# Expense-ratio fields Yahoo may return, in preference order, tagged with the unit
# each one uses. Net comes before gross because net is what an investor actually pays
# after fee waivers.
#
# The unit MUST come from the field name, never from the value's magnitude. Unlike
# trailing returns (see fmt_ret in server.py), an expense ratio of 0.03 is genuinely
# ambiguous — it is 0.03% as netExpenseRatio but 3% as annualReportExpenseRatio, and
# both are plausible fees. Guessing here silently misreports costs by 100x.
_EXPENSE_RATIO_FIELDS: tuple[tuple[str, bool], ...] = (
    ("netExpenseRatio", True),           # percent, e.g. 0.0945 -> 0.0945%
    ("grossExpenseRatio", True),         # percent
    ("annualReportExpenseRatio", False),  # already a fraction, e.g. 0.000945
    ("expenseRatio", False),             # already a fraction
)


def _expense_ratio_fraction(info: dict[str, Any]) -> float | None:
    """Return the expense ratio as a fraction (0.000945 == 0.0945%), or None.

    As of yfinance 1.5.x only `netExpenseRatio` is populated for ETFs; the others are
    kept as fallbacks for older payloads and mutual funds.
    """
    for field, is_percent in _EXPENSE_RATIO_FIELDS:
        value = info.get(field)
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            logger.debug("Non-numeric %s: %r", field, value)
            continue
        if value < 0:
            continue
        return value / 100.0 if is_percent else value
    return None


def _etf_info_sync(ticker: str) -> dict[str, Any]:
    if not _is_valid_ticker(ticker):
        logger.warning("Invalid ticker format: %s", ticker)
        raise ValueError(f"Invalid ticker format: {ticker}")

    ticker = ticker.upper()
    cached = _info_cache.get(ticker)
    if cached is not None:
        return cached

    # Check error cache to avoid retrying transient failures too soon
    error_cached = _error_cache.get(f"error:info:{ticker}")
    if error_cached is not None:
        return {
            "ticker": ticker,
            "name": "",
            "category": "",
            "total_assets": None,
            "expense_ratio": None,
            "yield": None,
            "ytd_return": None,
            "three_year_return": None,
            "five_year_return": None,
            "nav_price": None,
            "currency": "USD",
        }

    try:
        t = yf.Ticker(ticker, session=None)
        info = t.info or {}
        result = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName", ""),
            "category": info.get("category", ""),
            "total_assets": info.get("totalAssets"),
            "expense_ratio": _expense_ratio_fraction(info),
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
    except Exception:
        logger.exception("Failed to fetch info for ticker %s", ticker)
        _error_cache.set(f"error:info:{ticker}", True)
        return {
            "ticker": ticker,
            "name": "",
            "category": "",
            "total_assets": None,
            "expense_ratio": None,
            "yield": None,
            "ytd_return": None,
            "three_year_return": None,
            "five_year_return": None,
            "nav_price": None,
            "currency": "USD",
        }


def _etf_holdings_sync(ticker: str) -> list[dict[str, Any]]:
    if not _is_valid_ticker(ticker):
        logger.warning("Invalid ticker format: %s", ticker)
        raise ValueError(f"Invalid ticker format: {ticker}")

    ticker = ticker.upper()
    cached = _holdings_cache.get(ticker)
    if cached is not None:
        return cached

    # Check error cache to avoid retrying transient failures too soon
    error_cached = _error_cache.get(f"error:{ticker}")
    if error_cached is not None:
        return []

    try:
        t = yf.Ticker(ticker, session=None)
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
                    try:
                        weight = float(row[key])
                        break
                    except (TypeError, ValueError):
                        logger.debug("Could not convert weight for %s: %s", ticker, row[key])
                        continue

            # Normalize percentage: if <= 1, treat as fraction
            if weight <= 1:
                weight *= 100

            # Sanity clamp to [0, 100]
            weight = max(0.0, min(weight, 100.0))

            records.append(
                {
                    "symbol": str(row.get("Symbol", row.get("symbol", ""))).upper(),
                    "name": str(row.get("Name", row.get("holdingName", ""))),
                    "weight_pct": weight,
                }
            )

        _holdings_cache.set(ticker, records)
        return records
    except Exception as e:
        logger.exception("Failed to fetch holdings for ticker %s", ticker)
        # Cache the error transiently to avoid thundering herd on repeated failures
        _error_cache.set(f"error:{ticker}", True)
        return []


def _search_symbols_sync(
    query: str, limit: int, quote_types: tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
    """Search Yahoo for symbols, optionally restricted to given quote types.

    `quote_types=None` returns everything Yahoo matched (equities, ETFs,
    futures, indices…); pass e.g. ("ETF",) or ("EQUITY", "ETF") to filter.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string")
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError("Limit must be an integer between 1 and 500")

    wanted = {t.upper() for t in quote_types} if quote_types else None

    try:
        # Request extra results since unwanted quote types get filtered out.
        search = yf.Search(query, max_results=min(limit * 3, 50))
        quotes = search.quotes or []
    except Exception:
        logger.exception("Search failed for query %s", query)
        return []

    results: list[dict[str, Any]] = []
    for q in quotes:
        quote_type = str(q.get("quoteType", "")).upper()
        if wanted is not None and quote_type not in wanted:
            continue
        results.append(
            {
                "symbol": q.get("symbol", ""),
                "name": q.get("longname") or q.get("shortname", ""),
                "exchange": q.get("exchDisp") or q.get("exchange", ""),
                "type": quote_type,
            }
        )
        if len(results) >= limit:
            break
    return results


def _search_etfs_sync(query: str, limit: int) -> list[dict[str, Any]]:
    """ETF-only search — the original behaviour, now a thin filter."""
    return _search_symbols_sync(query, limit, quote_types=("ETF",))


def _find_etfs_holding_stock_sync(
    stock_ticker: str, etf_universe: list[str], limit: int
) -> list[dict[str, Any]]:
    if not _is_valid_ticker(stock_ticker):
        raise ValueError(f"Invalid stock ticker: {stock_ticker}")

    stock = stock_ticker.upper()
    matches: list[dict[str, Any]] = []

    for etf in etf_universe:
        try:
            holdings = _etf_holdings_sync(etf)
            for rank, h in enumerate(holdings, 1):
                if h["symbol"] == stock:
                    matches.append(
                        {
                            "etf": etf,
                            "stock": stock,
                            "weight_pct": h["weight_pct"],
                            "rank_in_etf": rank,
                        }
                    )
                    break
        except Exception as e:
            logger.debug("Failed to fetch holdings for %s: %s", etf, e)
            continue

    matches.sort(key=lambda x: x["weight_pct"], reverse=True)
    return matches[:limit]


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def get_etf_info(ticker: str) -> dict[str, Any]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    async with _get_fetch_semaphore():
        return await loop.run_in_executor(_executor, _etf_info_sync, ticker)


async def get_etf_holdings(ticker: str) -> list[dict[str, Any]]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    async with _get_fetch_semaphore():
        return await loop.run_in_executor(_executor, _etf_holdings_sync, ticker)


async def get_etf_infos(tickers: list[str]) -> list[dict[str, Any]]:
    """Fetch metadata for several tickers at once, preserving input order.

    Concurrency is already bounded to 8 by the per-loop semaphore inside
    `get_etf_info`; callers should still cap the list length.
    """
    if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
        raise ValueError("tickers must be a list of strings")

    return list(await asyncio.gather(*(get_etf_info(t) for t in tickers)))


async def search_symbols(
    query: str,
    *,
    limit: int = 10,
    quote_types: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError("Limit must be between 1 and 500")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    async with _get_fetch_semaphore():
        return await loop.run_in_executor(
            _executor, _search_symbols_sync, query, limit, quote_types
        )


async def resolve_stock_symbol(query: str) -> dict[str, Any] | None:
    """Resolve a company or fund name to its best-matching symbol.

    Backs the fallback for users who type "Nvidia" where a ticker is expected.
    Returns the top equity/ETF match, or None if nothing matched.
    """
    if not isinstance(query, str) or not query.strip():
        return None

    try:
        results = await search_symbols(
            query, limit=5, quote_types=("EQUITY", "ETF")
        )
    except ValueError:
        return None

    for r in results:
        if r.get("symbol"):
            return r
    return None


async def search_etfs(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    return await search_symbols(query, limit=limit, quote_types=("ETF",))


async def find_etfs_holding_stock(
    stock_ticker: str,
    *,
    etf_universe: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    # Input validation
    if not isinstance(stock_ticker, str) or not stock_ticker.strip():
        raise ValueError("stock_ticker must be a non-empty string")

    if not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise ValueError("Limit must be between 1 and 1000")

    universe = etf_universe if etf_universe is not None else TOP_ETFS

    if not isinstance(universe, list):
        raise ValueError("etf_universe must be a list of ticker strings")

    # Validate all universe elements are strings
    if not all(isinstance(t, str) for t in universe):
        raise ValueError("All elements in etf_universe must be strings")

    MAX_UNIVERSE = 500
    if len(universe) > MAX_UNIVERSE:
        raise ValueError(f"etf_universe too large (max {MAX_UNIVERSE}, got {len(universe)})")

    # De-duplicate while preserving order
    seen = set()
    universe_dedup = [t for t in universe if not (t in seen or seen.add(t))]

    stock = stock_ticker.upper()
    matches: list[dict[str, Any]] = []

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    # Fetch all holdings in parallel with bounded concurrency, then scan results.
    # This preserves the performance benefit of parallel I/O while bounding memory/requests.
    all_holdings = await asyncio.gather(
        *(get_etf_holdings(etf) for etf in universe_dedup)
    )

    for etf, holdings in zip(universe_dedup, all_holdings):
        for rank, h in enumerate(holdings, 1):
            if h["symbol"] == stock:
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
