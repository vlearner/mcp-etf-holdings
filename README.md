# mcp-etf-holdings

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

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/your-org/mcp-etf-holdings.git
cd mcp-etf-holdings
pip install -e .
```

---

## Usage

### Run the MCP server (stdio transport)

```bash
python -m src.mcp_servers.etf_holdings.server
# or after pip install -e .:
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

Or using the installed entry point:

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "etf-holdings-server"
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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md)