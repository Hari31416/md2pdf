"""ParagraphHandler — renders Markdown paragraphs to ReportLab Paragraphs."""

from __future__ import annotations

from reportlab.platypus import Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render


class ParagraphHandler(ElementHandler):
    """Render ``Paragraph`` tokens as styled ``Paragraph`` flowables."""

    token_type = "Paragraph"

    def render(self, token: dict, styles: dict) -> list:
        text = inline_render(token.get("children", []), styles)
        return [Paragraph(text, styles["body"])]
