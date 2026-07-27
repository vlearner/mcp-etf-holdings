# mcp-etf-holdings

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An MCP server that lets Claude (or any MCP client) answer questions about ETF holdings — reverse lookup, top positions, and fund metadata — all sourced live from Yahoo Finance.

<!-- PYPI-PENDING-BANNER: delete this block in the release commit once 0.3.0 is on PyPI -->
> ⏳ **Pending first PyPI release.** The `uvx` / `pip install` commands below are the
> intended install path but won't resolve until 0.3.0 is published. Until then, use
> [From source](#from-source).

---

## What it does

| Ask Claude... | Tool it calls |
|----------------|----------------|
| "Which ETFs hold NVDA?" | `find_etfs_holding_stock` |
| "What's the cheapest ETF for Nvidia exposure?" | `stock_exposure_summary` |
| "Compare SPY, VOO, QQQ and SCHD" | `compare_etfs` |
| "What are SPY's top holdings?" | `etf_holdings` |
| "What is QQQ's expense ratio and AUM?" | `etf_info` |
| "Find me semiconductor ETFs" | `search_etfs` |
| "What's the ticker for Berkshire Hathaway?" | `lookup_symbol` |

Search by company name or ticker symbol — "Which ETFs hold Nvidia?" works the same as
"Which ETFs hold NVDA?". Ask about several funds at once and you get one comparison table
back.

The reverse-lookup tools scan a universe of ~365 major ETFs (broad market, sectors, factors, international, fixed income, commodities).

No API key needed — data comes live from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance).

---

## Example prompts

Copy any of these into a client that has the server connected.

### Compare funds side by side

> Compare SPY, VOO, IVV and SPLG — they all track the S&P 500, so which is cheapest?

> Compare QQQ, VGT, XLK and SMH on expense ratio and 5-year return.

> Which of VTI, ITOT and SCHB has the lowest fee?

### Search by company name or ticker

> Which ETFs hold Nvidia?

> What's the ticker for Berkshire Hathaway?

> Find me the Vanguard total stock market fund and show its top holdings.

### Find the cheapest or largest exposure to a stock

> What's the cheapest ETF to get exposure to Nvidia?

> I want AMD exposure without buying the stock directly — what are my options, and what
> do they cost?

> Which ETF gives me the most concentrated Tesla exposure?

### Check a portfolio for overlap

> I own VOO, QQQ and VGT. Am I doubling up?

> Show me every holding that appears in more than one of SPY, SCHD and DGRO.

### Discover funds by theme

> Find semiconductor ETFs and compare the three biggest.

> What dividend ETFs exist, and which has the highest yield?

> Show me clean energy ETFs, then tell me what the top one actually holds.

### Research a single fund

> Give me a deep dive on SCHD.

> How concentrated is QQQ? What share of it is the top 5 positions?

> What does ARKK hold right now?

### Prompt templates (slash-commands)

The server also registers five prompt templates. In Claude Desktop and Claude Code they
show up as slash-commands, so you don't have to write the prompt yourself:

| Template | Argument | What it does |
|---|---|---|
| `etf_deep_dive` | `ticker` | Costs, size, returns, and a concentration read on one fund |
| `compare_funds` | `tickers` | Side-by-side table plus a cost/return interpretation |
| `stock_exposure` | `stock` | Ranks the ETFs that hold a stock by weight and cost |
| `portfolio_checkup` | `tickers` | Finds positions duplicated across the funds you hold |
| `theme_explorer` | `theme` | Discovers funds for a theme and compares the leaders |

> **Not financial advice.** Every tool reports what Yahoo Finance publishes. See
> [Data source & limitations](#data-source--limitations) for what the numbers do and
> don't cover.

---

## Install

Requires **Python 3.11+**.

You don't need to install anything ahead of time — every config below launches the
server on demand. If you'd rather have it on your `PATH`:

```bash
pip install mcp-etf-holdings
```

---

## Connect it to your editor

Each client below runs `uvx mcp-etf-holdings`, which downloads and launches the server
in an isolated environment on first use. No clone, no virtualenv, no absolute paths.

> Don't have [uv](https://docs.astral.sh/uv/)? Install it with
> `curl -LsSf https://astral.sh/uv/install.sh | sh`, or swap `uvx mcp-etf-holdings`
> for a plain `mcp-etf-holdings` after `pip install mcp-etf-holdings`.

### VS Code

Create `.vscode/mcp.json` in your workspace (or run **MCP: Open User Configuration**
for a global one). Note VS Code uses the key `servers`:

```json
{
  "servers": {
    "etf-holdings": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-etf-holdings"]
    }
  }
}
```

### Claude Desktop

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Claude Desktop and Cursor use `mcpServers` rather than `servers`:

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "uvx",
      "args": ["mcp-etf-holdings"]
    }
  }
}
```

Then **fully quit and reopen** Claude Desktop — closing the window isn't enough.

### Claude Code

```bash
claude mcp add etf-holdings -- uvx mcp-etf-holdings
```

### Cursor

Same JSON as Claude Desktop, in `.cursor/mcp.json` (project) or `~/.cursor/mcp.json`
(global).

### Verify it worked

Ask: **"Which ETFs hold NVDA?"** or **"Compare SPY, QQQ and VTI"**. If it calls
`find_etfs_holding_stock` or `compare_etfs` and returns real data, you're set. Then try
**"Which ETFs hold Nvidia?"** by name, to check that symbol lookup works too.

---

## From source

For development, or to run without publishing:

```bash
git clone https://github.com/vlearner/mcp-etf-holdings.git
cd mcp-etf-holdings
uv sync                      # or: python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

The repo ships a `.vscode/mcp.json` that points at your working tree, so VS Code picks
up local changes with no extra setup. For other clients, point them at:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/absolute/path/to/mcp-etf-holdings", "mcp-etf-holdings"]
}
```

Run the server standalone to check it starts — it will sit silent, waiting for JSON-RPC
on stdin, which is correct for a stdio MCP server:

```bash
uv run mcp-etf-holdings
```

To exercise the protocol interactively:

```bash
npx @modelcontextprotocol/inspector uv run mcp-etf-holdings
```

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `command not found: uvx` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh`, then restart your editor so it picks up the new `PATH`. |
| Server doesn't appear in the client | Editors only read MCP config at startup — fully restart (quit, don't just close the window). Check the client's MCP logs for the launch error. |
| Works in a terminal but not in the editor | GUI apps often don't inherit your shell `PATH`. Use an absolute path to `uvx` (`which uvx`) in the config. |
| Tool calls return "No data found" | Verify the ticker is a real ETF/stock symbol. Yahoo Finance rate-limits occasionally — wait and retry. |
| Python version error during install | Needs Python 3.11+. Check with `python3 --version`. |

---

## MCP tools reference

Tools that return more than one row format the result as a markdown table.

### `etf_info(ticker)`

Returns fund metadata for a single ETF ticker. For two or more funds use `compare_etfs`.

**Parameters**

- `ticker` (string) — ETF symbol, e.g. `"SPY"`

**Returns** — name, category, AUM, expense ratio, dividend yield, NAV/price, YTD / 3-yr / 5-yr returns.

---

### `compare_etfs(tickers)`

Compares several ETFs in a single table.

**Parameters**

- `tickers` (array of strings) — e.g. `["SPY", "QQQ", "VTI", "SCHD"]`. Case-insensitive
  and de-duplicated; capped at 10 funds per call.

**Returns** — one table with Ticker, Name, Category, AUM, Expense, Yield, YTD, 3-Yr, 5-Yr.
Tickers that return no data still get a row, plus a note naming them — one typo doesn't
discard the rest of the comparison.

---

### `etf_holdings(ticker)`

Returns the top holdings of an ETF with portfolio weight percentages.

**Parameters**

- `ticker` (string) — ETF symbol, e.g. `"QQQ"`

**Returns** — ranked list of holdings with symbol, name, and weight %.

---

### `find_etfs_holding_stock(stock_ticker, limit, custom_etf_universe)`

Reverse lookup: find which ETFs hold a given stock in their disclosed top positions.

**Parameters**

- `stock_ticker` (string) — stock to search for: a ticker like `"NVDA"` or a company name
  like `"Nvidia"`. Names are resolved to a ticker, and the output says which one it used.
- `limit` (int, default 20) — max results, capped at 50
- `custom_etf_universe` (JSON string, optional) — restrict search to a specific list, e.g. `'["SPY","QQQ","XLK"]'`

**Returns** — table of matching ETFs sorted by the stock's weight, highest first.

> Note: only top holdings (~10–15 positions per ETF) are checked. A stock held outside the top positions will not appear in results.

---

### `stock_exposure_summary(stock, limit)`

Same reverse lookup as above, joined with each fund's cost and size — the tool to reach for
when the question is "what's the cheapest / largest way to hold this?".

**Parameters**

- `stock` (string) — ticker or company name, e.g. `"NVDA"` or `"Nvidia"`
- `limit` (int, default 10) — max results, capped at 25

**Returns** — table with ETF, Name, Weight, Rank, Expense, AUM, sorted by weight in the stock.

---

### `lookup_symbol(query, limit, asset_type)`

Resolves a company or fund name to its ticker symbol. Use it whenever you know the name but
not the symbol.

**Parameters**

- `query` (string) — e.g. `"Nvidia"` or `"Vanguard total stock market"`
- `limit` (int, default 10) — max results, capped at 25
- `asset_type` (string, default `"any"`) — `"any"`, `"stock"`, or `"etf"`

**Returns** — table with Symbol, Name, Type, Exchange.

---

### `search_etfs(query, limit)`

Search for ETFs by name, theme, or category using Yahoo Finance search.

**Parameters**

- `query` (string) — search term, e.g. `"semiconductor"` or `"dividend"`
- `limit` (int, default 10) — max results, capped at 25

**Returns** — table of matching ETF tickers with full names and exchanges. Useful for
discovering tickers to feed into `compare_etfs` or the other tools. To resolve a *stock*
name rather than find funds, use `lookup_symbol`.

---

## Project layout

```
src/mcp_etf_holdings/
  server.py       ← FastMCP server entry point (7 tools)
  prompts.py      ← Prompt templates exposed as client slash-commands
  fetcher.py      ← Async wrappers around yfinance (sync) calls + 24h TTL cache
  formatting.py   ← Markdown tables and shared number formatting
  top_etfs.py     ← ~365 ETF tickers used for reverse-lookup scans
  __main__.py     ← enables `python -m mcp_etf_holdings`
tests/            ← pytest suite, fully offline (yfinance is mocked)
.vscode/mcp.json  ← VS Code MCP config pointing at the working tree
pyproject.toml
```

Run the tests with:

```bash
uv run pytest -q     # or: pip install -e ".[dev]" && pytest -q
```

The suite is fully offline — both `yf.Ticker` and `yf.Search` are mocked, the latter by
an autouse fixture so no test can reach Yahoo even by accident. For coverage:

```bash
uv run pytest -q --cov=mcp_etf_holdings --cov-report=term-missing
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `mcp` | MCP server/client SDK |
| `yfinance` | Live ETF data from Yahoo Finance |
| `pandas` | Holdings DataFrame processing |
| `httpx` | Async HTTP (used by MCP transport) |

---

## Data source & limitations

- Data is sourced **live at runtime** from Yahoo Finance via `yfinance` — no API key required, but subject to Yahoo's [terms of service](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and rate limits. See [NOTICE](NOTICE) for full attribution.
- Only top holdings (~10–15 positions) are exposed per ETF; full portfolio data isn't available via this API. Anything derived from holdings — reverse lookups, exposure summaries, overlap checks — is therefore a floor, not a complete picture.
- The default ETF universe covers ~365 funds. Stocks held only in niche or very small ETFs may not be found.
- Holdings/info responses are cached in-memory for 24h (`ETF_CACHE_TTL_SECONDS` env var overrides).

---

## Disclaimer

This tool is not affiliated with Yahoo Finance, yfinance, or any financial institution.
Data is retrieved from Yahoo Finance at runtime and is subject to availability and their
terms of service. This is not financial advice.

---

## Contributing

PRs are welcome! The project is especially looking for contributions that expand the default ETF universe — broader coverage means more accurate reverse-lookup results across niche sectors and international markets.

Please open an issue first for larger changes so we can discuss the approach.
