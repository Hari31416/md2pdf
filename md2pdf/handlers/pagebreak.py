"""PageBreakHandler — renders Markdown pagebreaks (<!-- pagebreak --> or \\pagebreak) to PageBreak."""

from __future__ import annotations

from reportlab.platypus import PageBreak

from md2pdf.core.registry import ElementHandler


class PageBreakHandler(ElementHandler):
    """Render ``PageBreak`` tokens as a ReportLab PageBreak."""

    token_type = "PageBreak"

    def render(self, token: dict, styles: dict) -> list[PageBreak]:
        return [PageBreak()]
