"""Unit tests for the shared display formatters and the markdown table."""

import pytest

from mcp_etf_holdings.formatting import (
    EMPTY,
    fmt_aum,
    fmt_pct,
    fmt_return,
    fmt_weight,
    markdown_table,
)


class TestFmtAum:
    def test_billions(self):
        assert fmt_aum(500_000_000_000) == "$500.00B"

    def test_millions(self):
        assert fmt_aum(250_000_000) == "$250.0M"

    def test_missing(self):
        assert fmt_aum(None) == "N/A"
        assert fmt_aum(0) == "N/A"


class TestFmtPct:
    def test_fraction_becomes_percent(self):
        assert fmt_pct(0.0003) == "0.03%"

    def test_zero_is_data_not_missing(self):
        """A zero-fee fund pays 0.00%, which is not the same as unknown."""
        assert fmt_pct(0.0) == "0.00%"

    def test_none_is_missing(self):
        assert fmt_pct(None) == "N/A"


class TestFmtReturn:
    def test_fraction_is_scaled(self):
        assert fmt_return(0.12) == "12.00%"

    def test_already_percent_is_left_alone(self):
        assert fmt_return(12.4) == "12.40%"

    def test_boundary_of_one_is_treated_as_a_fraction(self):
        assert fmt_return(1.0) == "100.00%"

    def test_negative_fraction(self):
        assert fmt_return(-0.05) == "-5.00%"

    def test_none_is_missing(self):
        assert fmt_return(None) == "N/A"


class TestFmtWeight:
    def test_percent_passthrough(self):
        assert fmt_weight(7.0) == "7.00%"

    def test_none_is_missing(self):
        assert fmt_weight(None) == "N/A"


class TestMarkdownTable:
    def test_basic_shape(self):
        out = markdown_table(["A", "B"], [[1, 2], [3, 4]])
        assert out.splitlines() == [
            "| A | B |",
            "| --- | --- |",
            "| 1 | 2 |",
            "| 3 | 4 |",
        ]

    def test_alignment_row(self):
        out = markdown_table(
            ["A", "B", "C"], [[1, 2, 3]], align=["left", "right", "center"]
        )
        assert out.splitlines()[1] == "| --- | ---: | :---: |"

    def test_alignment_defaults_to_left_when_short(self):
        out = markdown_table(["A", "B"], [[1, 2]], align=["right"])
        assert out.splitlines()[1] == "| ---: | --- |"

    def test_pipes_in_values_are_escaped(self):
        """An unescaped pipe would split the row and corrupt every later cell."""
        out = markdown_table(["Name"], [["Microsoft | Corp"]])
        assert "| Microsoft \\| Corp |" in out

    def test_blank_and_none_cells_become_em_dash(self):
        out = markdown_table(["A", "B"], [[None, "   "]])
        assert out.splitlines()[-1] == f"| {EMPTY} | {EMPTY} |"

    def test_short_rows_are_padded(self):
        out = markdown_table(["A", "B", "C"], [["x"]])
        assert out.splitlines()[-1] == f"| x | {EMPTY} | {EMPTY} |"

    def test_long_rows_are_truncated(self):
        out = markdown_table(["A"], [["x", "y", "z"]])
        assert out.splitlines()[-1] == "| x |"

    def test_no_rows_still_renders_a_header(self):
        out = markdown_table(["A", "B"], [])
        assert out.splitlines() == ["| A | B |", "| --- | --- |"]

    def test_headers_are_required(self):
        with pytest.raises(ValueError, match="at least one header"):
            markdown_table([], [["x"]])
