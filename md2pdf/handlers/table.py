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

        col_count = len(header_texts)

        import re

        # Check for column width overrides in the header texts
        width_overrides: list[tuple[str, float] | None] = [None] * col_count
        clean_header_texts = []
        for col_idx, cell_text in enumerate(header_texts):
            match = re.search(r"\s*(?:\{width=([^}]+)\}|<!--\s*width=([^-]+)\s*-->)\s*$", cell_text)
            if match:
                width_str = match.group(1) or match.group(2)
                width_str = width_str.strip()
                clean_text = cell_text[: match.start()]
                clean_header_texts.append(clean_text)

                try:
                    if "%" in width_str:
                        pct = float(width_str.replace("%", "").strip()) / 100.0
                        width_overrides[col_idx] = ("pct", pct)
                    else:
                        val = float(re.sub(r"[a-zA-Z]", "", width_str).strip())
                        width_overrides[col_idx] = ("abs", val)
                except ValueError:
                    width_overrides[col_idx] = None
            else:
                clean_header_texts.append(cell_text)

        # Table alignment support
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.styles import ParagraphStyle

        column_align = getattr(node, "column_align", [])
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
        for col_idx, cell in enumerate(clean_header_texts):
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
        col_widths = self._compute_col_widths(
            col_count,
            styles,
            width_overrides,
            clean_header_texts,
            data_rows_texts,
        )

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

    def _compute_col_widths(
        self,
        col_count: int,
        styles: dict | None = None,
        width_overrides: list[tuple[str, float] | None] | None = None,
        clean_header_texts: list[str] | None = None,
        data_rows_texts: list[list[str]] | None = None,
    ) -> list[float]:
        """Compute column widths supporting overrides and content-based heuristics."""
        if col_count <= 0:
            return []

        page_width = A4[0]
        left_margin = 20 * mm
        right_margin = 20 * mm
        if styles:
            page_width = styles.get("_page_width", page_width)
            left_margin = styles.get("_left_margin", left_margin)
            right_margin = styles.get("_right_margin", right_margin)
        available_width = page_width - left_margin - right_margin

        # Initialize widths
        widths = [0.0] * col_count
        remaining_width = available_width
        unassigned_indices = []

        if width_overrides:
            for idx in range(col_count):
                override = width_overrides[idx] if idx < len(width_overrides) else None
                if override:
                    type_, val = override
                    if type_ == "abs":
                        widths[idx] = val
                        remaining_width -= val
                    elif type_ == "pct":
                        w = available_width * val
                        widths[idx] = w
                        remaining_width -= w
                else:
                    unassigned_indices.append(idx)
        else:
            unassigned_indices = list(range(col_count))

        if unassigned_indices:
            import math
            import re

            def strip_tags(text: str) -> str:
                return re.sub(r"<[^>]+>", "", text)

            max_lens = []
            for idx in unassigned_indices:
                h_text = (
                    clean_header_texts[idx]
                    if clean_header_texts and idx < len(clean_header_texts)
                    else ""
                )
                max_len = len(strip_tags(h_text))
                if data_rows_texts:
                    for row in data_rows_texts:
                        if idx < len(row):
                            max_len = max(max_len, len(strip_tags(row[idx])))
                max_lens.append(max(max_len, 3))

            weights = [math.sqrt(length) for length in max_lens]
            total_weight = sum(weights)

            # Safeguard if overallocated
            if remaining_width < 20.0 * len(unassigned_indices):
                remaining_width = 20.0 * len(unassigned_indices)

            for i, idx in enumerate(unassigned_indices):
                if total_weight > 0:
                    widths[idx] = remaining_width * (weights[i] / total_weight)
                else:
                    widths[idx] = remaining_width / len(unassigned_indices)

        # Enforce minimum column width of 20 points
        min_width = 20.0
        for idx in range(col_count):
            if widths[idx] < min_width:
                widths[idx] = min_width

        return widths
