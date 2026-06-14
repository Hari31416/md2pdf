"""BlockQuoteHandler — renders Markdown block quotes with a left accent bar."""

from __future__ import annotations

from reportlab.platypus import Paragraph

from md2pdf.core.flowables import BlockQuoteBar
from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render


class BlockQuoteHandler(ElementHandler):
    """Render ``BlockQuote`` tokens as indented paragraphs with a left bar.

    Each child paragraph is wrapped with a left accent bar using the
    custom :class:`BlockQuoteBar` flowable.
    """

    token_type = "BlockQuote"

    def render(self, token: dict, styles: dict) -> list:
        bar_color = styles.get("color_blockquote_bar")
        bq_style = styles.get("blockquote", styles.get("body"))
        flowables: list = []

        for child in token.get("children", []):
            child_type = child.get("type", "")

            if child_type == "Paragraph":
                text = inline_render(child.get("children", []), styles, parent_style=bq_style)
            else:
                # Non-paragraph children: render raw text as a fallback
                text = inline_render(
                    child.get("children", []), styles, parent_style=bq_style
                ) or child.get("raw", "")

            if not text:
                continue

            para = Paragraph(text, bq_style)

            if bar_color is not None:
                flowables.append(BlockQuoteBar(para, bar_color=bar_color))
            else:
                flowables.append(para)

        return flowables
