"""Tool results: markdown for people, structured JSON for programs.

Every tool returns both in one MCP result. Clients that only read text keep getting
the same markdown as before; clients that read ``structuredContent`` get typed data
without scraping tables.
"""

from __future__ import annotations

from typing import Any

from mcp.types import CallToolResult, TextContent

from .providers import get_provider


def reply(text: str, data: dict[str, Any] | None = None) -> CallToolResult:
    """Bundle `text` with a structured payload.

    The payload always carries ``source`` (the data provider's name) so a consumer can
    tell where numbers came from. When a tool has nothing to report, `text` explains
    why and is repeated as ``message`` so programmatic callers need not parse prose.
    """
    payload: dict[str, Any] = {"source": get_provider().name, **(data or {})}
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=payload,
    )


def notice(text: str, data: dict[str, Any] | None = None) -> CallToolResult:
    """A reply that explains why there is no result (bad input, no data, unsupported)."""
    return reply(text, {**(data or {}), "message": text})
