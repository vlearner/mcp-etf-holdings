# mcp-etf-holdings

[![PyPI version](https://img.shields.io/pypi/v/mcp-etf-holdings)](https://pypi.org/project/mcp-etf-holdings/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-etf-holdings)](https://pypi.org/project/mcp-etf-holdings/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An MCP server that lets Claude (or any MCP client) answer questions about ETF holdings — reverse lookup, top positions, and fund metadata — all sourced live from Yahoo Finance.

---

## What it does

| Question | Tool |
|----------|------|
| "Which ETFs hold NVDA?" | `find_etfs_holding_stock` |
| "What are SPY's top holdings?" | `etf_holdings` |
| "What is QQQ's expense ratio and AUM?" | `etf_info` |

The default search universe is ~100 major ETFs covering broad market, sectors, factors, international, fixed income, and commodities.

---

## Data Source

- Data is sourced **live at runtime** from Yahoo Finance via the [yfinance](https://github.com/ranaroussi/yfinance) library.
- **No API key required.**
- Subject to Yahoo Finance's [terms of service](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) and rate limits.
- See [NOTICE](NOTICE) for full third-party attribution.

---

## Installation

Requires Python 3.11+.

**Option 1 — uvx (no install needed, recommended for Claude Desktop users):**

```bash
uvx mcp-etf-holdings
```

**Option 2 — pip:**

```bash
pip install mcp-etf-holdings
```

---

## Usage

### Run the MCP server (stdio transport)

```bash
# uvx (no prior install needed)
uvx mcp-etf-holdings

# or after pip install:
etf-holdings-server
```

### Use from a script or agent

```python
import asyncio
from src.agents.data_fetcher import fetch_etf_info, fetch_etf_holdings, fetch_etfs_holding_stock

async def main():
    print(await fetch_etf_info("QQQ"))
    print(await fetch_etf_holdings("SPY"))
    print(await fetch_etfs_holding_stock("AAPL", limit=10))

asyncio.run(main())
```

### Wire into Claude Desktop / Claude Code

Add to `claude_desktop_config.json` (or `~/.claude/mcp_servers.json`):

**Option 1 — uvx (recommended, no install step):**

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

**Option 2 — pip-installed entry point:**

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "etf-holdings-server"
    }
  }
}
```

**Option 3 — local dev (cloned repo):**

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "python",
      "args": ["-m", "src.mcp_servers.etf_holdings.server"],
      "cwd": "/absolute/path/to/mcp-etf-holdings"
    }
  }
}
```

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

## Project layout

```
src/
  mcp_servers/
    etf_holdings/
      server.py      ← FastMCP server entry point
      fetcher.py     ← Async wrappers around yfinance (sync) calls
      top_etfs.py    ← ~100 ETF tickers used for reverse-lookup scans
  agents/
    data_fetcher.py  ← MCP client that spawns the server over stdio
pyproject.toml
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

## Limitations

- Data is sourced from Yahoo Finance and subject to their availability and rate limits.
- Only top holdings (~10–15 positions) are exposed per ETF; full portfolio data is not available via this API.
- The default ETF universe covers ~100 funds. Stocks held only in niche or smaller ETFs may not be found.

---

## Disclaimer

This tool is not affiliated with Yahoo Finance, yfinance, or any financial institution.
Data is retrieved from Yahoo Finance at runtime and is subject to availability and their
terms of service. This is not financial advice.

---

## Contributing

PRs are welcome! The project is especially looking for contributions that expand the default ETF universe beyond the current ~100 funds — broader coverage means more accurate reverse-lookup results across niche sectors and international markets.

Please open an issue first for larger changes so we can discuss the approach.