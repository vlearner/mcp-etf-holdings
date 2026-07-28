# Changelog

All notable changes to this project are recorded here.

## [Unreleased]

### Added
- `compare_etfs(tickers)` — compares any number of ETFs (up to 10) in a single table
  instead of requiring one `etf_info` call per fund. Takes a real array parameter, so
  clients pass `["SPY","QQQ","VTI"]` rather than a JSON string.
- `lookup_symbol(query, limit, asset_type)` — resolves a company or fund name to its
  ticker. Yahoo's search already returned equities; the ETF-only filter had been
  discarding them, so there was no way to go from "Nvidia" to `NVDA`.
- `stock_exposure_summary(stock, limit)` — the reverse lookup joined with each fund's
  expense ratio and AUM, for "what is the cheapest way to hold this stock?".
- Company names are now accepted wherever a stock ticker is. `find_etfs_holding_stock`
  and `stock_exposure_summary` resolve a name when the direct lookup returns nothing, and
  disclose the substitution (`> Interpreted "Nvidia" as **NVDA**`) rather than guessing
  silently. The ticker pattern accepts `NVIDIA` as well-formed, so this previously failed
  as an empty result with no explanation.
- Five prompt templates (`etf_deep_dive`, `compare_funds`, `stock_exposure`,
  `portfolio_checkup`, `theme_explorer`), surfaced as slash-commands by MCP clients.
- README "Use cases & prompt cookbook" section with copy-paste prompts by intent.
- `python -m mcp_etf_holdings` entry point and `__version__` on the package.
- `.vscode/mcp.json` for VS Code, pointing at the working tree.
- Python 3.13 to the test matrix.

### Fixed
- `find_etfs_holding_stock("BRK.B")` answered about BRKC, an unrelated YieldMax fund.
  Yahoo writes share classes with a dash (`BRK-B`), so the dot form matched nothing and
  fell through to the company-name resolver, which fuzzy-matched a different fund and
  reported it with full confidence — a silently wrong answer, not an error. The dot form
  is now retried as a dash before any name search, and the substitution is disclosed.
  `BRK.B` returns XLF at the top, as `BRK-B` already did.
- `compare_etfs(["VOO", "Vanguard S&P 500"])` raised and discarded the whole batch,
  including VOO's valid row. A batch entry that fails ticker validation now degrades to
  the same empty placeholder row an unknown-but-well-formed symbol (`ZZZZZ`) has always
  produced. A single-ticker lookup still raises — only the batch is forgiving.
- `etf_info(" voo ")` raised a `ValueError` on surrounding whitespace. Tickers are now
  trimmed before validation, so a padded symbol resolves like a bare one and shares its
  cache entry. Interior whitespace (`SP Y`) is still rejected.
- `search_etfs` consulted only Yahoo's search API, which answers "S&P 500" with indices
  and futures that the ETF filter drops, and "bitcoin" with GBTC alone while IBIT and
  FBTC sit in `TOP_ETFS`. Yahoo's hits are now topped up from a curated keyword index
  over the local universe, ranked after the live matches. A search that *failed* is not
  topped up: an outage is indistinguishable from a query nothing matched, and a static
  list served under those conditions would read as a live result.
- Tool parameter descriptions never reached the JSON schema. They were written as
  `Annotated[str, "..."]`, and pydantic ignores bare strings in `Annotated` — so every
  parameter on all four original tools was exposed to clients with no description. They
  now use `Field(description=...)`, with a test asserting no parameter is left undescribed.
- `etf_info`'s label column was misaligned: `Expense ratio:` and `Dividend yield:` were
  not padded to the width used by the other rows.
- A newline inside a table cell ended the row early and left the remainder as a stray
  line, garbling the table. Cell values now have their internal whitespace collapsed.
- `etf_info` reported `Expense ratio: N/A` for every fund. Yahoo moved the value to
  `netExpenseRatio`; the code only read `annualReportExpenseRatio`/`expenseRatio`, which
  are now `None` for all ETFs checked. The two field families use different units
  (`netExpenseRatio` is a percent, the legacy fields are fractions), so the conversion is
  driven by which field supplied the value — never by its magnitude, since `0.03` is
  genuinely ambiguous between 0.03% and 3%.
- A genuine `0.0` expense ratio, dividend yield, or trailing return rendered as `N/A`
  because of falsy checks. Zero-fee funds now display `0.00%`.

### Changed
- Tools returning more than one row now emit markdown tables rather than fixed-width
  text lists: `etf_holdings`, `find_etfs_holding_stock`, `search_etfs`, and all new tools.
  `etf_info` keeps its label/value block, since a one-row table reads worse.
- Shared display formatting moved to a new `formatting.py` (`fmt_aum`, `fmt_pct`,
  `fmt_return`, `fmt_weight`, `markdown_table`); it had been duplicated across tools.
  `markdown_table` escapes pipes in values — fund names contain them.
- The ETF universe was documented as "~300" in `top_etfs.py` and "~360" in the README
  while actually holding 364 tickers; all three now say ~365.
- Test suite expanded from 73 to 226 tests (96% line coverage), adding units for the
  cache-TTL environment validation, negative/error caching, holdings weight
  normalization, every prompt body, and the name-resolution fallback. `pytest-cov` is
  now a dev dependency.

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

### Removed
- `_search_etfs_sync`, which became unreachable once `search_etfs` began delegating to
  `search_symbols`.
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