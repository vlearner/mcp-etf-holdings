# mcp-etf-holdings

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An MCP server that lets Claude (or any MCP client) answer questions about ETF holdings — reverse lookup, top positions, and fund metadata — all sourced live from Yahoo Finance.

> **Not yet on PyPI.** This project hasn't been published to PyPI, so `pip install mcp-etf-holdings` / `uvx mcp-etf-holdings` will **not** work yet. Follow the quickstart below to run it from a clone instead.

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

## Quickstart (5 minutes)

Requires **Python 3.11+**. Check your version with `python3 --version`.

```bash
# 1. Clone the repo
git clone https://github.com/vlearner/mcp-etf-holdings.git
cd mcp-etf-holdings

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install the project (installs deps + the `etf-holdings-server` command)
pip install -e .

# 4. Run it
etf-holdings-server
```

If it's working, the process will sit there waiting silently — that's expected, it's an MCP server talking over stdio, not a normal CLI program. Press `Ctrl+C` to stop it.

That confirms the server runs. To actually *use* it, wire it into Claude Desktop or Claude Code (next section) rather than running it standalone.

---

## Connect it to Claude Desktop or Claude Code

You need the **absolute path** to your clone and the **absolute path** to the Python interpreter inside the `.venv` you just created.

```bash
# from inside the mcp-etf-holdings directory, with .venv activated
pwd                             # → absolute path to the repo
which python                    # → absolute path to the venv's python
```

### Claude Desktop

Open your config file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an entry under `mcpServers` (create the file/section if it doesn't exist), using the two paths from above:

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "/absolute/path/to/mcp-etf-holdings/.venv/bin/python",
      "args": ["-m", "src.mcp_servers.etf_holdings.server"],
      "cwd": "/absolute/path/to/mcp-etf-holdings"
    }
  }
}
```

Then **fully quit and reopen** Claude Desktop (not just close the window). You should see "etf-holdings" listed under the 🔌 / MCP tools icon in a new chat.

### Claude Code

Same idea, in `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "etf-holdings": {
      "command": "/absolute/path/to/mcp-etf-holdings/.venv/bin/python",
      "args": ["-m", "src.mcp_servers.etf_holdings.server"],
      "cwd": "/absolute/path/to/mcp-etf-holdings"
    }
  }
}
```

Restart your Claude Code session afterward.

> Using the venv's `python` directly (instead of the `etf-holdings-server` command) avoids relying on your shell `PATH`, which is the most common reason MCP servers "don't show up" in Claude Desktop.

### Verify it worked

Ask Claude: **"Which ETFs hold NVDA?"** or **"What are QQQ's top holdings?"** — if it calls the `find_etfs_holding_stock` or `etf_holdings` tool and returns real data, you're set.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pip install mcp-etf-holdings` fails / not found | It's not on PyPI yet — clone the repo and use `pip install -e .` instead (see Quickstart). |
| Server tool not showing up in Claude Desktop | Use the venv's full `python` path in the config (not just `python` or `etf-holdings-server`), and make sure `cwd` is the absolute repo path. Fully restart Claude Desktop after editing the config. |
| `ModuleNotFoundError` when running | You likely activated the wrong environment, or skipped `pip install -e .`. Re-run the Quickstart steps in order. |
| `command not found: etf-holdings-server` | Your venv isn't activated. Run `source .venv/bin/activate` first, or use the full path `/path/to/.venv/bin/etf-holdings-server`. |
| Tool calls return "No data found" | Double-check the ticker is a real ETF/stock symbol. Yahoo Finance occasionally rate-limits — wait a bit and retry. |
| Python version error during install | You need Python 3.11+. Check with `python3 --version`; install a newer one from [python.org](https://www.python.org/downloads/) if needed. |

---

## Use from a script or agent (without Claude Desktop)

```python
import asyncio
from src.agents.data_fetcher import fetch_etf_info, fetch_etf_holdings, fetch_etfs_holding_stock

async def main():
    print(await fetch_etf_info("QQQ"))
    print(await fetch_etf_holdings("SPY"))
    print(await fetch_etfs_holding_stock("AAPL", limit=10))

asyncio.run(main())
```

Run with `python your_script.py` from the repo root (with the venv activated).

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
src/
  mcp_servers/
    etf_holdings/
      server.py      ← FastMCP server entry point (4 tools)
      fetcher.py     ← Async wrappers around yfinance (sync) calls + 24h TTL cache
      top_etfs.py    ← ~360 ETF tickers used for reverse-lookup scans
  agents/
    data_fetcher.py  ← MCP client that spawns the server over stdio
tests/                ← pytest suite, fully offline (yfinance is mocked)
pyproject.toml
```

Run the tests with:

```bash
pip install -e ".[dev]"
pytest tests/
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
