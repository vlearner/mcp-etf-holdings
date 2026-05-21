#!/bin/bash
cd "$(dirname "$0")"
exec /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m src.mcp_servers.etf_holdings.server
