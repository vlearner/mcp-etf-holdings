# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

_No unreleased changes yet._

---

## [0.2.0] — 2026-07-18

### Added
- `search_etfs(query)` tool — search ETFs by name, theme, or category via Yahoo Finance
- TTL cache for holdings and info (default ~24 h) with bounded LRU eviction to cut
  Yahoo Finance round trips
- Negative (transient-error) caching with a short TTL to avoid retry storms on failures
- Expanded default ETF universe to 364 funds for broader reverse-lookup coverage
- Test suite (`pytest` + `pytest-asyncio`) with mocked yfinance responses
- GitHub Actions workflow running the test suite on pushes and PRs to `main`

### Changed
- Security hardening: ticker/input validation, bounded concurrent fetches, de-duplicated
  universe, structured logging, and weight normalization/clamping

### Fixed
- Concurrency semaphore is now created per event loop, fixing a
  "bound to a different event loop" error under repeated event loops
- `_etf_info_sync` error path now returns a consistent shape (includes `nav_price`)

---

## [0.1.0] — 2026-05-20

### Added
- `etf_info(ticker)` — fund metadata (AUM, expense ratio, yield, returns)
- `etf_holdings(ticker)` — top holdings with weight percentages
- `find_etfs_holding_stock(stock_ticker, limit, custom_etf_universe)` — reverse lookup across ~100 ETFs
- Default ETF universe of ~100 funds across broad market, sectors, factors, international, fixed income, and commodities
- MCP client agent (`src/agents/data_fetcher.py`) for scripted access over stdio
- `etf-holdings-server` entry point installed via `pip install -e .`