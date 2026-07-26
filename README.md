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
| "What are SPY's top holdings?" | `etf_holdings` |
| "What is QQQ's expense ratio and AUM?" | `etf_info` |
| "Find me semiconductor ETFs" | `search_etfs` |

The reverse-lookup tool scans a universe of ~360 major ETFs (broad market, sectors, factors, international, fixed income, commodities).

No API key needed — data comes live from Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance).

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

Ask: **"Which ETFs hold NVDA?"** or **"What are QQQ's top holdings?"** If it calls
`find_etfs_holding_stock` or `etf_holdings` and returns real data, you're set.

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

### `etf_info(ticker)`

Returns fund metadata for a given ETF ticker.

**Parameters**

- `ticker` (string) — ETF symbol, e.g. `"SPY"`

**Returns** — name, category, AUM, expense ratio, dividend yield, NAV/price, YTD / 3-yr / 5-yr returns.

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

- `stock_ticker` (string) — stock to search for, e.g. `"NVDA"`
- `limit` (int, default 20) — max results, capped at 50
- `custom_etf_universe` (JSON string, optional) — restrict search to a specific list, e.g. `'["SPY","QQQ","XLK"]'`

**Returns** — list of matching ETFs sorted by the stock's weight, highest first.

> Note: only top holdings (~10–15 positions per ETF) are checked. A stock held outside the top positions will not appear in results.

---

### `search_etfs(query, limit)`

Search for ETFs by name, theme, or category using Yahoo Finance search.

**Parameters**

- `query` (string) — search term, e.g. `"semiconductor"` or `"dividend"`
- `limit` (int, default 10) — max results, capped at 25

**Returns** — matching ETF tickers with full names and exchanges. Useful for discovering tickers to feed into the other tools.

---

## Project layout

```
src/mcp_etf_holdings/
  server.py       ← FastMCP server entry point (4 tools)
  fetcher.py      ← Async wrappers around yfinance (sync) calls + 24h TTL cache
  top_etfs.py     ← ~360 ETF tickers used for reverse-lookup scans
  __main__.py     ← enables `python -m mcp_etf_holdings`
tests/            ← pytest suite, fully offline (yfinance is mocked)
.vscode/mcp.json  ← VS Code MCP config pointing at the working tree
pyproject.toml
```

Run the tests with:

```bash
uv run pytest -q     # or: pip install -e ".[dev]" && pytest -q
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
- Only top holdings (~10–15 positions) are exposed per ETF; full portfolio data isn't available via this API.
- The default ETF universe covers ~360 funds. Stocks held only in niche or very small ETFs may not be found.
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
