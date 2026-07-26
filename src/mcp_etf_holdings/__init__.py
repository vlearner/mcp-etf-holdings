"""ETF Holdings MCP server — ETF reverse lookup, holdings, and metadata."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-etf-holdings")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
