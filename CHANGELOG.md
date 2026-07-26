# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

### Changed
- **Breaking:** the import path is now `mcp_etf_holdings`, was
  `src.mcp_servers.etf_holdings`. The distribution previously installed a top-level
  package literally named `src`, which would collide in site-packages; fixed before the
  first PyPI release since import paths are public API.
- **Breaking:** removed `src/agents/data_fetcher.py`. Nothing imported it, its docstring
  was stale, and an MCP client covers the same ground. Import `mcp_etf_holdings.fetcher`
  directly for programmatic access.
- Primary console script is now `mcp-etf-holdings`, so bare `uvx mcp-etf-holdings`
  resolves without `--from`. `etf-holdings-server` remains as an alias.
- Consolidated to a single PyPI publish workflow using trusted publishing (OIDC); the
  competing token-based tag workflow is gone. The build now fails if the wheel ever
  ships a top-level `src/` again.

### Added
- `python -m mcp_etf_holdings` entry point and `__version__` on the package.
- `.vscode/mcp.json` for VS Code, pointing at the working tree.
- Python 3.13 to the test matrix.

### Removed
- `run_server.sh`, which hardcoded an absolute interpreter path valid on one machine.

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