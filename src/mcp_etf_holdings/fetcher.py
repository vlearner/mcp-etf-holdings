"""
Data-fetching layer: validation, caching and concurrency around a data provider.

Providers (see providers.py) do the actual I/O and may be sync or async. They run
in a thread pool, so callers can await them from async context.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .providers import _expense_ratio_fraction, get_provider  # noqa: F401
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

def is_valid_ticker(ticker: str) -> bool:
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


_INFO_DEFAULTS: dict[str, Any] = {
    "ticker": "",
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


def _empty_info(ticker: str) -> dict[str, Any]:
    return {**_INFO_DEFAULTS, "ticker": ticker}


def _call_provider(method: Any, *args: Any) -> Any:
    """Call a provider method from a worker thread; await it if it is async."""
    result = method(*args)
    if inspect.isawaitable(result):
        async def _await() -> Any:
            return await result

        return asyncio.run(_await())
    return result


def _normalize_info(raw: Any, ticker: str) -> dict[str, Any]:
    """Coerce a provider's info payload to the shape the tools expect."""
    if not isinstance(raw, dict):
        raise TypeError(f"get_info must return a dict, got {type(raw).__name__}")
    info = {**_INFO_DEFAULTS, **{k: v for k, v in raw.items() if k in _INFO_DEFAULTS}}
    info["ticker"] = ticker
    info["name"] = str(info["name"] or "")
    info["category"] = str(info["category"] or "")
    info["currency"] = str(info["currency"] or "USD")
    return info


def _normalize_holdings(raw: Any) -> list[dict[str, Any]]:
    """Coerce a provider's holdings to [{symbol, name, weight_pct}], weight in percent."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise TypeError(f"get_holdings must return a list, got {type(raw).__name__}")
    records: list[dict[str, Any]] = []
    for h in raw:
        if not isinstance(h, dict):
            continue
        try:
            weight = float(h.get("weight_pct", 0.0))
        except (TypeError, ValueError):
            weight = 0.0
        if weight != weight:  # NaN
            weight = 0.0
        records.append(
            {
                "symbol": str(h.get("symbol", "")).strip().upper(),
                "name": str(h.get("name", "") or ""),
                # Sanity clamp to [0, 100]
                "weight_pct": max(0.0, min(weight, 100.0)),
            }
        )
    return records


def _etf_info_sync(ticker: str) -> dict[str, Any]:
    if not is_valid_ticker(ticker):
        logger.warning("Invalid ticker format: %s", ticker)
        raise ValueError(f"Invalid ticker format: {ticker}")

    ticker = ticker.upper()
    cached = _info_cache.get(ticker)
    if cached is not None:
        return cached

    # Check error cache to avoid retrying transient failures too soon
    error_cached = _error_cache.get(f"error:info:{ticker}")
    if error_cached is not None:
        return _empty_info(ticker)

    try:
        result = _normalize_info(_call_provider(get_provider().get_info, ticker), ticker)
        if result["name"]:
            _info_cache.set(ticker, result)
        return result
    except Exception:
        logger.exception("Failed to fetch info for ticker %s", ticker)
        _error_cache.set(f"error:info:{ticker}", True)
        return _empty_info(ticker)


def _etf_holdings_sync(ticker: str) -> list[dict[str, Any]]:
    if not is_valid_ticker(ticker):
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
        records = _normalize_holdings(_call_provider(get_provider().get_holdings, ticker))
        # An empty list is legit (e.g. bond/commodity funds): cache it so universe
        # scans don't re-fetch every time. Exceptions are NOT cached here.
        _holdings_cache.set(ticker, records)
        return records
    except Exception:
        logger.exception("Failed to fetch holdings for ticker %s", ticker)
        # Cache the error transiently to avoid thundering herd on repeated failures
        _error_cache.set(f"error:{ticker}", True)
        return []


def supports_search() -> bool:
    """Whether the active provider can resolve names and search for ETFs."""
    return callable(getattr(get_provider(), "search", None))


def default_universe() -> list[str]:
    """ETFs scanned by reverse lookup: the provider's own list, else the built-in one."""
    custom = getattr(get_provider(), "default_universe", None)
    if isinstance(custom, (list, tuple)) and custom:
        return [str(t) for t in custom]
    return TOP_ETFS


def _search_symbols_sync(
    query: str, limit: int, quote_types: tuple[str, ...] | None = None
) -> list[dict[str, Any]]:
    """Search the provider for symbols, optionally restricted to given quote types."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string")
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError("Limit must be an integer between 1 and 500")

    search = getattr(get_provider(), "search", None)
    if not callable(search):
        return []

    try:
        raw = _call_provider(search, query, limit, quote_types)
    except Exception:
        logger.exception("Search failed for query %s", query)
        return []

    wanted = {t.upper() for t in quote_types} if quote_types else None
    results: list[dict[str, Any]] = []
    for q in raw or []:
        if not isinstance(q, dict):
            continue
        quote_type = str(q.get("type", "")).upper()
        # Providers are asked to filter, but re-check so a lax one cannot leak
        # futures/indices into an ETF search. Untyped rows are kept.
        if wanted is not None and quote_type and quote_type not in wanted:
            continue
        results.append(
            {
                "symbol": str(q.get("symbol", "")),
                "name": str(q.get("name", "") or ""),
                "exchange": str(q.get("exchange", "") or ""),
                "type": quote_type,
            }
        )
        if len(results) >= limit:
            break
    return results


def _find_etfs_holding_stock_sync(
    stock_ticker: str, etf_universe: list[str], limit: int
) -> list[dict[str, Any]]:
    if not is_valid_ticker(stock_ticker):
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

    universe = etf_universe if etf_universe is not None else default_universe()

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


# Back-compat alias for the previous private name.
_is_valid_ticker = is_valid_ticker
