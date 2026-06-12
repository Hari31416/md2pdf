"""HeadingHandler — renders Markdown headings (H1–H6) to ReportLab Paragraphs."""

from __future__ import annotations

from reportlab.platypus import Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render


class HeadingHandler(ElementHandler):
    """Render ``Heading`` tokens as styled ``Paragraph`` flowables.

    Heading levels above 4 fall back to the ``h4`` style since ReportLab's
    default stylesheet does not define H5/H6.
    """

    token_type = "Heading"

    def render(self, token: dict, styles: dict) -> list:
        level: int = token.get("attrs", {}).get("level", 1)
        style_key = f"h{min(level, 4)}"
        text = inline_render(token.get("children", []), styles)
        return [Paragraph(text, styles[style_key])]
