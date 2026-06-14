"""TableHandler — renders Markdown tables to ReportLab Table flowables.

Key features
------------
- ``repeatRows=1`` ensures the header row reprints on every page break.
- ``splitByRow=True`` allows a table to span multiple pages.
- Cell content is wrapped in ``Paragraph`` flowables so long text wraps.
- Column widths are computed from the available page width divided evenly
  among columns.  Phase 6 may introduce per-column overrides.
"""

from __future__ import annotations

import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render

logger = logging.getLogger(__name__)

# Default page margins (points) — Phase 6 will source these from Config.
_LEFT_MARGIN: float = 25 * mm
_RIGHT_MARGIN: float = 25 * mm
_PAGE_WIDTH: float = A4[0]
_AVAILABLE_WIDTH: float = _PAGE_WIDTH - _LEFT_MARGIN - _RIGHT_MARGIN


class TableHandler(ElementHandler):
    """Render ``Table`` tokens as ``Table`` flowables with repeating headers."""

    token_type = "Table"

    def render(self, token: dict, styles: dict) -> list:
        node = token.get("_node")
        if node is None:
            logger.warning("TableHandler: token has no _node — skipping")
            return []

        header_texts = self._extract_header(node, styles)
        data_rows_texts = self._extract_rows(node, styles)

        if not header_texts:
            logger.warning("TableHandler: table has no header row — skipping")
            return []

        # Table alignment support
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.styles import ParagraphStyle

        column_align = getattr(node, "column_align", [])
        col_count = len(header_texts)
        alignments = []
        for i in range(col_count):
            align_val = column_align[i] if i < len(column_align) else None
            alignments.append(align_val)

        # Create dynamically aligned paragraph styles
        header_styles = {}
        cell_styles = {}
        for align_val in [None, 0, 1]:
            if align_val == 0:
                align_code = TA_CENTER
                suffix = "center"
            elif align_val == 1:
                align_code = TA_RIGHT
                suffix = "right"
            else:
                align_code = TA_LEFT
                suffix = "left"

            header_styles[align_val] = ParagraphStyle(
                f"table_header_{suffix}",
                parent=styles["table_header"],
                alignment=align_code,
            )
            cell_styles[align_val] = ParagraphStyle(
                f"table_cell_{suffix}",
                parent=styles["table_cell"],
                alignment=align_code,
            )

        header_row = []
        for col_idx, cell in enumerate(header_texts):
            align_val = alignments[col_idx]
            header_row.append(Paragraph(cell, header_styles[align_val]))

        data_rows = []
        for row in data_rows_texts:
            data_row = []
            for col_idx, cell in enumerate(row):
                align_val = alignments[col_idx]
                data_row.append(Paragraph(cell, cell_styles[align_val]))
            data_rows.append(data_row)

        all_rows = [header_row] + data_rows
        col_widths = self._compute_col_widths(col_count)

        tbl = Table(
            all_rows,
            colWidths=col_widths,
            repeatRows=1,
            splitByRow=True,
        )
        tbl.spaceBefore = 0
        tbl.spaceAfter = styles.get("spacing_base", 8)

        # Add ALIGN commands to TableStyle
        table_commands = list(styles.get("table_style", []))
        for col_idx, align_val in enumerate(alignments):
            if align_val == 0:
                align_str = "CENTER"
            elif align_val == 1:
                align_str = "RIGHT"
            else:
                align_str = "LEFT"
            table_commands.append(("ALIGN", (col_idx, 0), (col_idx, -1), align_str))

        tbl.setStyle(TableStyle(table_commands))
        return [tbl]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _extract_header(self, node, styles: dict) -> list[str]:
        """Extract plain-text strings from the table's header row."""
        header = getattr(node, "header", None)
        if header is None:
            return []
        children = getattr(header, "children", None) or []
        return [self._cell_text(cell, styles, parent_style="table_header") for cell in children]

    def _extract_rows(self, node, styles: dict) -> list[list[str]]:
        """Extract plain-text strings from all body rows."""
        rows_node = getattr(node, "children", None) or []
        result: list[list[str]] = []
        for row in rows_node:
            cells = getattr(row, "children", None) or []
            result.append(
                [self._cell_text(cell, styles, parent_style="table_cell") for cell in cells]
            )
        return result

    def _cell_text(
        self, cell_node, styles: dict | None = None, parent_style: str | None = None
    ) -> str:
        """Render a table cell node to an inline markup string."""
        children = getattr(cell_node, "children", None) or []
        if not children:
            return ""
        # Normalise children to token-dict format for inline_render
        from md2pdf.core.parser import MarkdownParser  # noqa: PLC0415

        parser = MarkdownParser()
        child_tokens = [parser._normalize(c) for c in children]
        return inline_render(child_tokens, styles, parent_style)

    def _compute_col_widths(self, col_count: int) -> list[float]:
        """Distribute available page width evenly across *col_count* columns."""
        if col_count <= 0:
            return []
        width = _AVAILABLE_WIDTH / col_count
        return [width] * col_count
