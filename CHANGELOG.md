# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

### Planned
- Cache holdings data (TTL ~24 h) to reduce Yahoo Finance round trips
- `search_etfs(query)` tool for name/category search
- Expand ETF universe beyond top-100 for broader reverse-lookup coverage
- Integration tests using `pytest-asyncio` with mocked yfinance responses

---

## [0.1.0] — 2026-05-20

### Added
- `etf_info(ticker)` — fund metadata (AUM, expense ratio, yield, returns)
- `etf_holdings(ticker)` — top holdings with weight percentages
- `find_etfs_holding_stock(stock_ticker, limit, custom_etf_universe)` — reverse lookup across ~100 ETFs
- Default ETF universe of ~100 funds across broad market, sectors, factors, international, fixed income, and commodities
- MCP client agent (`src/agents/data_fetcher.py`) for scripted access over stdio
- `etf-holdings-server` entry point installed via `pip install -e .`