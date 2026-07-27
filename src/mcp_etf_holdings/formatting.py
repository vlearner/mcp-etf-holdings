"""
Shared output formatting for the MCP tools.

Two concerns live here: turning Yahoo's raw numbers into display strings, and
rendering rows as a GitHub-flavored markdown table. Tools that return more than
one row should use `markdown_table` — MCP clients render it, and a table of four
funds is far easier to read than four label/value blocks.
"""

from __future__ import annotations

# Stand-in for a missing value inside a table cell. An empty cell renders as a
# visual gap that reads like a rendering bug; an em dash reads as "no data".
EMPTY = "—"

NA = "N/A"


def fmt_aum(value: float | None) -> str:
    """Format assets under management as $X.XXB / $X.XM."""
    if not value:
        return NA
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    return f"${value / 1e6:.1f}M"


def fmt_pct(value: float | None) -> str:
    """Format a fraction (0.0003) as a percent string (0.03%).

    `is None` rather than a falsy check: a genuine 0.0 (a zero-fee fund, a
    non-distributing fund) is real data and must not read as "N/A".
    """
    if value is None:
        return NA
    return f"{value * 100:.2f}%"


def fmt_return(value: float | None) -> str:
    """Format a trailing return, which Yahoo reports in two different units."""
    if value is None:
        return NA
    # Yahoo returns some funds' returns as fractions (0.12) and others
    # already in percent (12.4); treat |v| > 1 as already-percent.
    return f"{value * 100:.2f}%" if abs(value) <= 1 else f"{value:.2f}%"


def fmt_weight(value: float | None) -> str:
    """Format a portfolio weight that is already expressed in percent."""
    if value is None:
        return NA
    return f"{value:.2f}%"


def _cell(value: object) -> str:
    """Render one cell: stringify, escape pipes, collapse blanks to EMPTY."""
    text = "" if value is None else str(value).strip()
    if not text:
        return EMPTY
    # An unescaped pipe inside a fund name would split the row into extra
    # columns and corrupt every cell after it.
    return text.replace("|", "\\|")


def markdown_table(
    headers: list[str],
    rows: list[list[object]],
    align: list[str] | None = None,
) -> str:
    """Render `rows` as a markdown table.

    `align` takes one of "left", "right", "center" per column and defaults to
    left. Rows shorter than `headers` are padded; longer rows are truncated, so
    a malformed row degrades to a readable line instead of breaking the table.
    """
    if not headers:
        raise ValueError("markdown_table requires at least one header")

    separators = []
    for i in range(len(headers)):
        kind = align[i] if align and i < len(align) else "left"
        if kind == "right":
            separators.append("---:")
        elif kind == "center":
            separators.append(":---:")
        else:
            separators.append("---")

    lines = [
        "| " + " | ".join(_cell(h) for h in headers) + " |",
        "| " + " | ".join(separators) + " |",
    ]
    for row in rows:
        cells = [_cell(c) for c in row[: len(headers)]]
        cells += [EMPTY] * (len(headers) - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
