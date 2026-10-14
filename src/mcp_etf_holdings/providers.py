"""
Pluggable data providers.

The server gets all of its ETF data from one *provider*. The default is Yahoo
Finance via yfinance. Point ``ETF_DATA_PROVIDER`` at your own class to serve the
same tools from an internal or licensed data source instead.

A provider is any object with these members (sync or ``async`` methods both work):

    name: str                                          # shown in tool output
    get_info(ticker) -> dict                           # required
    get_holdings(ticker) -> list[dict]                 # required
    search(query, limit, quote_types) -> list[dict]    # optional
    default_universe: list[str]                        # optional

Provider methods should raise on failure and return empty results for "no data".
Validation, caching, concurrency limits and error caching are applied by the
server, so a provider does not need to implement them.

See the "Custom data providers" section of the README for the exact shapes.
"""

from __future__ import annotations

import importlib
import logging
import os
from importlib.metadata import entry_points
from typing import Any, Protocol, runtime_checkable

import yfinance as yf

logger = logging.getLogger(__name__)

PROVIDER_ENV = "ETF_DATA_PROVIDER"
ENTRY_POINT_GROUP = "mcp_etf_holdings.providers"
DEFAULT_PROVIDER = "yfinance"


@runtime_checkable
class ETFDataProvider(Protocol):
    """The required surface of a data provider. ``search`` is optional."""

    name: str

    def get_info(self, ticker: str) -> dict[str, Any]: ...

    def get_holdings(self, ticker: str) -> list[dict[str, Any]]: ...


class ProviderError(RuntimeError):
    """The configured data provider could not be loaded or is malformed."""


# ---------------------------------------------------------------------------
# Default provider: Yahoo Finance
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


class YFinanceProvider:
    """Live data from Yahoo Finance through yfinance. No API key."""

    name = "Yahoo Finance"

    def get_info(self, ticker: str) -> dict[str, Any]:
        info = yf.Ticker(ticker, session=None).info or {}
        return {
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

    def get_holdings(self, ticker: str) -> list[dict[str, Any]]:
        fd = yf.Ticker(ticker, session=None).funds_data
        if fd is None:
            return []

        df = fd.top_holdings
        if df is None or df.empty:
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

            # Yahoo reports a fraction (0.07 == 7%). Other providers must already
            # return percent, so this heuristic stays here, not in the shared layer.
            if weight <= 1:
                weight *= 100

            records.append(
                {
                    "symbol": str(row.get("Symbol", row.get("symbol", ""))).upper(),
                    "name": str(row.get("Name", row.get("holdingName", ""))),
                    "weight_pct": weight,
                }
            )
        return records

    def search(
        self, query: str, limit: int, quote_types: tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Search Yahoo for symbols, optionally restricted to given quote types.

        `quote_types=None` returns everything Yahoo matched (equities, ETFs,
        futures, indices…); pass e.g. ("ETF",) or ("EQUITY", "ETF") to filter.
        """
        wanted = {t.upper() for t in quote_types} if quote_types else None

        try:
            # Request extra results since unwanted quote types get filtered out.
            quotes = yf.Search(query, max_results=min(limit * 3, 50)).quotes or []
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


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _import_target(spec: str) -> Any:
    module_name, _, attr = spec.partition(":")
    if not module_name or not attr:
        raise ProviderError(
            f"{PROVIDER_ENV}={spec!r} is not in 'package.module:Name' form."
        )
    try:
        obj: Any = importlib.import_module(module_name)
    except ImportError as e:
        raise ProviderError(
            f"{PROVIDER_ENV}={spec!r}: cannot import module {module_name!r} ({e}). "
            "Is the package installed in the same environment as mcp-etf-holdings?"
        ) from e
    for part in attr.split("."):
        try:
            obj = getattr(obj, part)
        except AttributeError as e:
            raise ProviderError(
                f"{PROVIDER_ENV}={spec!r}: {module_name!r} has no attribute {attr!r}."
            ) from e
    return obj


def _instantiate(obj: Any) -> Any:
    """Accept a class, a zero-argument factory, or a ready-made instance."""
    if isinstance(obj, type):
        return obj()
    if hasattr(obj, "get_info"):
        return obj
    if callable(obj):
        return obj()
    return obj


def _validate(provider: Any, spec: str) -> ETFDataProvider:
    missing = [
        m for m in ("get_info", "get_holdings") if not callable(getattr(provider, m, None))
    ]
    if missing:
        raise ProviderError(
            f"Data provider {spec!r} is missing required method(s): {', '.join(missing)}."
        )
    if not isinstance(getattr(provider, "name", None), str) or not provider.name:
        try:
            provider.name = spec
        except Exception:  # read-only attribute on a frozen object
            raise ProviderError(
                f"Data provider {spec!r} needs a non-empty string 'name' attribute."
            ) from None
    return provider  # type: ignore[return-value]


def load_provider(spec: str | None = None) -> ETFDataProvider:
    """Build the provider named by `spec` (default: the ETF_DATA_PROVIDER env var).

    `spec` is ``yfinance``, a name registered under the ``mcp_etf_holdings.providers``
    entry-point group, or ``package.module:Name`` (a class, factory, or instance).
    """
    spec = (spec if spec is not None else os.environ.get(PROVIDER_ENV, "")).strip()
    if not spec or spec.lower() == DEFAULT_PROVIDER:
        return YFinanceProvider()

    if ":" in spec:
        target = _import_target(spec)
    else:
        registered = {ep.name: ep for ep in entry_points(group=ENTRY_POINT_GROUP)}
        if spec not in registered:
            known = ", ".join([DEFAULT_PROVIDER, *sorted(registered)])
            raise ProviderError(
                f"Unknown data provider {spec!r}. Use one of: {known}, "
                "or 'package.module:Name'."
            )
        target = registered[spec].load()

    try:
        provider = _instantiate(target)
    except Exception as e:
        raise ProviderError(f"Data provider {spec!r} failed to initialise: {e}") from e
    return _validate(provider, spec)


_provider: ETFDataProvider | None = None


def get_provider() -> ETFDataProvider:
    """Return the active provider, loading it on first use."""
    global _provider
    if _provider is None:
        _provider = load_provider()
        logger.info("Using data provider: %s", _provider.name)
    return _provider


def set_provider(provider: ETFDataProvider | None) -> None:
    """Install a provider programmatically (embedding, tests). None resets to env."""
    global _provider
    _provider = _validate(provider, type(provider).__name__) if provider is not None else None
