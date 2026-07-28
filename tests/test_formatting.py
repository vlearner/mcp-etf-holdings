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

    def test_newlines_in_values_are_flattened(self):
        """A newline would end the row early and leave a stray line behind."""
        out = markdown_table(["Name", "W"], [["Fund\nName", "1%"]])
        assert out.splitlines() == [
            "| Name | W |",
            "| --- | --- |",
            "| Fund Name | 1% |",
        ]

    def test_internal_whitespace_is_collapsed(self):
        out = markdown_table(["Name"], [["Fund\t \tName"]])
        assert out.splitlines()[-1] == "| Fund Name |"

    def test_whitespace_only_cell_is_empty(self):
        out = markdown_table(["A"], [["\n\t  "]])
        assert out.splitlines()[-1] == f"| {EMPTY} |"

    def test_zero_is_rendered_not_treated_as_blank(self):
        """0 is falsy but is real data — it must not collapse to an em dash."""
        out = markdown_table(["A"], [[0]])
        assert out.splitlines()[-1] == "| 0 |"

    def test_multiple_pipes_all_escaped(self):
        out = markdown_table(["A"], [["a|b|c"]])
        assert out.splitlines()[-1] == "| a\\|b\\|c |"

    def test_unknown_align_value_falls_back_to_left(self):
        out = markdown_table(["A"], [["x"]], align=["sideways"])
        assert out.splitlines()[1] == "| --- |"

    def test_header_cells_are_escaped_too(self):
        out = markdown_table(["A|B"], [["x"]])
        assert out.splitlines()[0] == "| A\\|B |"
