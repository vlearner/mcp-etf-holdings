# mcp-etf-holdings

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An MCP server for ETF data. Ask which funds hold a stock, compare fees, or pull top
holdings. Data comes live from Yahoo Finance. No API key.

<!-- PYPI-PENDING-BANNER: delete this block in the release commit once 0.3.0 is on PyPI -->
> ⏳ **Pending first PyPI release.** The `uvx` / `pip install` commands below are the
> intended install path but won't resolve until 0.3.0 is published. Until then, use
> [From source](#from-source).

---

## What you can ask

| Ask Claude | Tool it calls |
|---|---|
| "Which ETFs hold NVDA?" | `find_etfs_holding_stock` |
| "What's the cheapest ETF for Nvidia exposure?" | `stock_exposure_summary` |
| "Compare SPY, VOO, QQQ and SCHD" | `compare_etfs` |
| "What are SPY's top holdings?" | `etf_holdings` |
| "What is QQQ's expense ratio and AUM?" | `etf_info` |
| "Find me semiconductor ETFs" | `search_etfs` |
| "What's the ticker for Berkshire Hathaway?" | `lookup_symbol` |

Search by company name or ticker symbol. "Which ETFs hold Nvidia?" works the same as
"Which ETFs hold NVDA?". Ask about several funds at once and you get one comparison table.

---

## Requirements

- Python 3.11+
- An MCP client: Claude Code, Claude Desktop, VS Code, or Cursor
- [uv](https://docs.astral.sh/uv/), which runs the server without a manual install

Install uv:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Setup

You don't need to install the server first. Every config below launches it on demand with
`uvx`, in its own isolated environment.

To put it on your `PATH` instead, run `pip install mcp-etf-holdings`, then swap
`uvx mcp-etf-holdings` for a plain `mcp-etf-holdings` in any config below.

### Claude Code

```bash
claude mcp add etf-holdings -- uvx mcp-etf-holdings
```

### Claude Desktop

1. Open your config file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. Add the server:

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

3. Quit Claude Desktop and reopen it. Closing the window is not enough.

### VS Code

1. Create `.vscode/mcp.json` in your workspace. For a global config, run
   **MCP: Open User Configuration** instead.
2. Add the server. VS Code uses the key `servers`, not `mcpServers`:

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

3. Restart VS Code.

### Cursor

Use the same JSON as Claude Desktop. Put it in `.cursor/mcp.json` for one project, or
`~/.cursor/mcp.json` for all of them. Restart Cursor.

### Verify it works

Ask your client each of these:

- **"Which ETFs hold NVDA?"** — calls `find_etfs_holding_stock`
- **"Compare SPY, QQQ and VTI"** — calls `compare_etfs`, returns one table
- **"Which ETFs hold Nvidia?"** — resolves the name to `NVDA` and says so

If you get real numbers back, you're done.

---

## Example prompts

Copy any of these into a client that has the server connected.

**Compare funds**

> Compare SPY, VOO, IVV and SPLG — they all track the S&P 500, so which is cheapest?

> Compare QQQ, VGT, XLK and SMH on expense ratio and 5-year return.

**Search by name or ticker**

> Which ETFs hold Nvidia?

> What's the ticker for Berkshire Hathaway?

> Find me the Vanguard total stock market fund and show its top holdings.

**Find the cheapest exposure to a stock**

> What's the cheapest ETF to get exposure to Nvidia?

> I want AMD exposure without buying the stock directly. What are my options, and what do
> they cost?

**Check a portfolio for overlap**

> I own VOO, QQQ and VGT. Am I doubling up?

> Show me every holding that appears in more than one of SPY, SCHD and DGRO.

**Discover funds by theme**

> Find semiconductor ETFs and compare the three biggest.

> What dividend ETFs exist, and which has the highest yield?

**Research one fund**

> Give me a deep dive on SCHD.

> How concentrated is QQQ? What share of it is the top 5 positions?

### Prompt templates

The server registers five prompt templates. Claude Desktop and Claude Code show them as
slash-commands, so you don't have to write the prompt yourself.

| Template | Argument | What it does |
|---|---|---|
| `etf_deep_dive` | `ticker` | Costs, size, returns, and a concentration read on one fund |
| `compare_funds` | `tickers` | Side-by-side table plus a cost and return comparison |
| `stock_exposure` | `stock` | Ranks the ETFs holding a stock by weight and cost |
| `portfolio_checkup` | `tickers` | Finds positions duplicated across the funds you hold |
| `theme_explorer` | `theme` | Finds funds for a theme and compares the leaders |

---

## Tool reference

Tools that return more than one row format the result as a markdown table.

### `etf_info(ticker)`

Metadata for one ETF. For two or more funds, use `compare_etfs`.

- `ticker` (string) — ETF symbol, e.g. `"SPY"`

Returns name, category, AUM, expense ratio, dividend yield, NAV/price, and YTD / 3-yr /
5-yr returns.

### `compare_etfs(tickers)`

Compares several ETFs in one table.

- `tickers` (array of strings) — e.g. `["SPY", "QQQ", "VTI", "SCHD"]`. Case-insensitive
  and de-duplicated. Capped at 10 funds per call.

Returns Ticker, Name, Category, AUM, Expense, Yield, YTD, 3-Yr, 5-Yr. A ticker with no
data still gets a row, plus a note naming it, so one typo doesn't discard the rest.

### `etf_holdings(ticker)`

Top holdings of an ETF with portfolio weights.

- `ticker` (string) — ETF symbol, e.g. `"QQQ"`

Returns a ranked table of symbol, name, and weight %.

### `find_etfs_holding_stock(stock_ticker, limit, custom_etf_universe)`

Reverse lookup. Finds which ETFs hold a given stock in their disclosed top positions.

- `stock_ticker` (string) — a ticker like `"NVDA"` or a company name like `"Nvidia"`.
  Names are resolved to a ticker, and the output says which one it used.
- `limit` (int, default 20) — capped at 50
- `custom_etf_universe` (JSON string, optional) — search a specific list instead of the
  default universe, e.g. `'["SPY","QQQ","XLK"]'`

Returns matching ETFs sorted by the stock's weight, highest first.

> Only top holdings are checked, roughly 10–15 positions per ETF. A stock held outside
> those positions will not appear.

### `stock_exposure_summary(stock, limit)`

The same reverse lookup, joined with each fund's cost and size. Use it for "what's the
cheapest or largest way to hold this stock?".

- `stock` (string) — ticker or company name, e.g. `"NVDA"` or `"Nvidia"`
- `limit` (int, default 10) — capped at 25

Returns ETF, Name, Weight, Rank, Expense, AUM, sorted by weight in the stock.

### `lookup_symbol(query, limit, asset_type)`

Resolves a company or fund name to its ticker symbol.

- `query` (string) — e.g. `"Nvidia"` or `"Vanguard total stock market"`
- `limit` (int, default 10) — capped at 25
- `asset_type` (string, default `"any"`) — `"any"`, `"stock"`, or `"etf"`

Returns Symbol, Name, Type, Exchange.

### `search_etfs(query, limit)`

Finds ETFs by name, theme, or category.

- `query` (string) — e.g. `"semiconductor"` or `"dividend"`
- `limit` (int, default 10) — capped at 25

Returns matching ETF tickers with names and exchanges. To resolve a *stock* name instead
of finding funds, use `lookup_symbol`.

---

## From source

For development, or to run without waiting on a release:

```bash
git clone https://github.com/vlearner/mcp-etf-holdings.git
cd mcp-etf-holdings
uv sync
```

Without uv:

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

The repo ships a `.vscode/mcp.json` pointed at your working tree, so VS Code picks up
local changes with no extra setup. Point other clients at:

```json
{
  "command": "uv",
  "args": ["run", "--directory", "/absolute/path/to/mcp-etf-holdings", "mcp-etf-holdings"]
}
```

Check that the server starts:

```bash
uv run mcp-etf-holdings
```

It will sit silent, waiting for JSON-RPC on stdin. That is correct for a stdio MCP server.

To poke at the protocol by hand:

```bash
npx @modelcontextprotocol/inspector uv run mcp-etf-holdings
```

### Tests

```bash
uv run pytest -q
```

The suite is fully offline. Both `yf.Ticker` and `yf.Search` are mocked, the latter by an
autouse fixture, so no test can reach Yahoo by accident.

For coverage:

```bash
uv run pytest -q --cov=mcp_etf_holdings --cov-report=term-missing
```

### Layout

```
src/mcp_etf_holdings/
  server.py       ← FastMCP entry point, 7 tools
  prompts.py      ← prompt templates, exposed as client slash-commands
  fetcher.py      ← async wrappers around yfinance + 24h TTL cache
  formatting.py   ← markdown tables and shared number formatting
  top_etfs.py     ← ~365 ETF tickers scanned for reverse lookups
  __main__.py     ← enables `python -m mcp_etf_holdings`
tests/            ← pytest suite, fully offline
.vscode/mcp.json  ← VS Code config pointing at the working tree
pyproject.toml
```

Dependencies: `mcp` (protocol SDK), `yfinance` (data), `pandas` (holdings frames),
`httpx` (transport).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `command not found: uvx` | Install uv, then restart your editor so it picks up the new `PATH`. |
| Server missing from the client | Editors read MCP config only at startup. Fully quit and reopen. Check the client's MCP logs for the launch error. |
| Works in a terminal, not in the editor | GUI apps often don't inherit your shell `PATH`. Use an absolute path to `uvx` — run `which uvx` to get it. |
| Tool calls return "No data found" | Check the symbol is real. Yahoo rate-limits sometimes, so wait and retry. |
| Python version error on install | Needs 3.11+. Check with `python3 --version`. |

---

## Limits

Worth knowing before you trust a number:

- Only the top ~10–15 positions per ETF are published. Anything derived from holdings —
  reverse lookups, exposure summaries, overlap checks — is a floor, not the full picture.
- The default universe is ~365 funds. A stock held only in small or niche ETFs may not
  turn up.
- Responses are cached in memory for 24h. Override with `ETF_CACHE_TTL_SECONDS`.
- Data is fetched live from Yahoo Finance. No API key, but Yahoo's
  [terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and rate limits
  apply. See [NOTICE](NOTICE) for attribution.

---

## Contributing

PRs welcome. The most useful contribution is expanding the ETF universe in `top_etfs.py`.
Wider coverage means better reverse-lookup results in niche sectors and international
markets.

Open an issue first for larger changes.

---

## Disclaimer

Not affiliated with Yahoo Finance, yfinance, or any financial institution. Data is
retrieved from Yahoo Finance at runtime and is subject to availability and their terms of
service. This is not financial advice.
