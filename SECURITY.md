# Security Policy

## Supported versions

> **Pre-release.** `mcp-etf-holdings` is not on PyPI yet, so `pip install mcp-etf-holdings`
> will not resolve. The supported version is whatever is currently on `main`.

| Version | Supported | Notes |
| ------- | --------- | ----- |
| `main` (0.3.0-dev) | ✅ | Install from source — see the README |
| GitHub Release `0.1.0` | ❌ | May 2026, superseded. Packaging was broken (installed a top-level `src` package). Do not use. |

Once 0.3.0 is published this becomes: latest minor release supported, fixes shipped as
new patch releases rather than backports.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub Security Advisories:
**[Report a vulnerability](https://github.com/vlearner/mcp-etf-holdings/security/advisories/new)**

Please include:

- The commit SHA you are on (or release version, once releases exist) and your Python version
- Which MCP tool is involved, and the exact tool arguments that trigger it
- What an attacker gains — the impact, not just the mechanism
- A minimal reproduction if you have one

**Response targets:** acknowledgement within 5 days, an initial assessment within
14 days, and regular updates until it's resolved. This is a small volunteer-run
project, so please allow reasonable time before public disclosure. Credit in the
advisory and release notes unless you'd rather stay anonymous.

## Threat model

Understanding how this runs matters for judging what counts as a vulnerability.

`mcp-etf-holdings` is a **stdio MCP server**. It is launched as a local subprocess by
an MCP client (VS Code, Claude Desktop, Cursor) and speaks JSON-RPC over stdin/stdout.
It does **not** open a network listener, does **not** accept remote connections, and
does **not** handle credentials, API keys, or user accounts. It reads no secrets and
writes no files.

Its only outbound traffic is to Yahoo Finance via `yfinance`.

### In scope

- Argument handling in the four tools (`etf_info`, `etf_holdings`,
  `find_etfs_holding_stock`, `search_etfs`) — injection, path traversal, or any way
  tool arguments reach a shell, filesystem, or interpreter
- Anything letting a crafted Yahoo Finance response cause code execution, crashes, or
  unbounded resource use. **Upstream responses are untrusted input**
- Resource exhaustion: unbounded memory or connection growth, cache growth, or ways to
  defeat the concurrency limit on the ~360-ETF reverse-lookup scan
- Dependency vulnerabilities that are actually reachable from this code
- Anything causing the server to write to stdout outside the JSON-RPC stream, which
  corrupts the MCP transport

### Out of scope

- **Data accuracy.** Wrong, stale, or missing figures from Yahoo Finance are data-quality
  bugs — please file those as normal issues. This project is not affiliated with Yahoo
  and does not validate their numbers, and its output is not financial advice.
- Yahoo Finance rate limiting, outages, or terms-of-service matters
- Vulnerabilities in `yfinance`, `pandas`, `httpx`, or the `mcp` SDK themselves — report
  those upstream. We do want to know if this project uses them in an unsafe way.
- Anything requiring an attacker to already have local code execution as your user. At
  that point they can edit the code directly; the server holds nothing they don't have.
- An MCP client choosing to call a tool. Deciding which tools to expose and trust is the
  client's job.

## Notes for operators

- **No API key is required, so there is no key to leak.** If a config asks you for a
  credential for this server, something is wrong.
- The server trusts the client that launched it. Only add it to MCP clients you control.
- Responses are cached in memory for 24 h (`ETF_CACHE_TTL_SECONDS` overrides) with a
  bounded LRU. Nothing is written to disk and the cache dies with the process.
- Ticker arguments are validated against `^[A-Z0-9.\-]{1,10}$` before reaching yfinance.
- Once published, install from PyPI or this repository only. Verify the package name is
  exactly `mcp-etf-holdings` — typosquats on popular MCP server names are a real risk.
