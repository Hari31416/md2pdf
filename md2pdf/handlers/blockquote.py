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

        registry = styles.get("_registry")
        for child in token.get("children", []):
            child_type = child.get("type", "")
            child_flowables = []

            if child_type == "Paragraph":
                text = inline_render(child.get("children", []), styles, parent_style=bq_style)
                if text:
                    child_flowables = [Paragraph(text, bq_style)]
            elif registry:
                handler = registry.get(child_type)
                if handler is not None:
                    child_flowables = handler.render(child, styles)

            # Fallback to rendering raw text of the child
            if not child_flowables:
                text = inline_render(
                    child.get("children", []), styles, parent_style=bq_style
                ) or child.get("raw", "")
                if text:
                    child_flowables = [Paragraph(text, bq_style)]

            for f in child_flowables:
                if bar_color is not None:
                    flowables.append(BlockQuoteBar(f, bar_color=bar_color))
                else:
                    flowables.append(f)

        return flowables
