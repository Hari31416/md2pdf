from __future__ import annotations

import pytest
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import Table

from md2pdf.core.parser import MarkdownParser
from md2pdf.handlers.table import TableHandler
from md2pdf.styles.default import build_default_stylesheet


@pytest.fixture
def styles() -> dict:
    from md2pdf.assets._font_registry import register_fonts

    register_fonts()
    return build_default_stylesheet()


def test_table_column_alignment_parsing_and_style(styles):
    md = "| Left | Center | Right | Default |\n" "|:---|:---:|---:|---|\n" "| a | b | c | d |\n"
    parser = MarkdownParser()
    tokens = parser.parse(md)
    table_token = next(t for t in tokens if t["type"] == "Table")

    # Verify column_align parsed by mistletoe
    node = table_token["_node"]
    assert node.column_align == [None, 0, 1, None]

    # Render table
    flowables = TableHandler().render(table_token, styles)
    assert len(flowables) == 1
    tbl = flowables[0]
    assert isinstance(tbl, Table)

    # Inspect the cell ParagraphStyles and alignments
    # tbl._cellvalues is a 2D list of cells. Row 0 is header, Row 1 is data row.
    header_row = tbl._cellvalues[0]
    data_row = tbl._cellvalues[1]

    # Verify column 0 (left aligned)
    assert header_row[0].style.alignment == TA_LEFT
    assert data_row[0].style.alignment == TA_LEFT

    # Verify column 1 (center aligned)
    assert header_row[1].style.alignment == TA_CENTER
    assert data_row[1].style.alignment == TA_CENTER

    # Verify column 2 (right aligned)
    assert header_row[2].style.alignment == TA_RIGHT
    assert data_row[2].style.alignment == TA_RIGHT

    # Verify column 3 (default aligned -> left)
    assert header_row[3].style.alignment == TA_LEFT
    assert data_row[3].style.alignment == TA_LEFT

    # Inspect the Table's internal CellStyles and alignments
    # tbl._cellStyles is a 2D list of CellStyle objects matching the cell layout.
    header_cell_styles = tbl._cellStyles[0]
    data_cell_styles = tbl._cellStyles[1]

    # Verify column 0 (left aligned)
    assert header_cell_styles[0].alignment == "LEFT"
    assert data_cell_styles[0].alignment == "LEFT"

    # Verify column 1 (center aligned)
    assert header_cell_styles[1].alignment == "CENTER"
    assert data_cell_styles[1].alignment == "CENTER"

    # Verify column 2 (right aligned)
    assert header_cell_styles[2].alignment == "RIGHT"
    assert data_cell_styles[2].alignment == "RIGHT"

    # Verify column 3 (default aligned -> left)
    assert header_cell_styles[3].alignment == "LEFT"
    assert data_cell_styles[3].alignment == "LEFT"


def test_table_dynamic_margins(styles):
    """Verify that TableHandler calculates column widths dynamically from styles."""
    md = "| Header 1 | Header 2 |\n|---|---|\n| cell 1 | cell 2 |"
    parser = MarkdownParser()
    tokens = parser.parse(md)
    table_token = next(t for t in tokens if t["type"] == "Table")

    # Override margins and page width in styles
    styles["_page_width"] = 500.0
    styles["_left_margin"] = 50.0
    styles["_right_margin"] = 50.0
    # Expected available width: 500.0 - 50.0 - 50.0 = 400.0
    # Expected column width for 2 columns: 200.0 each

    flowables = TableHandler().render(table_token, styles)
    assert len(flowables) == 1
    tbl = flowables[0]
    assert isinstance(tbl, Table)
    # Check that column widths are correct
    assert tbl._colWidths == [200.0, 200.0]
