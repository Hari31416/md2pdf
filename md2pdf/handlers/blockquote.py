"""BlockQuoteHandler — renders Markdown block quotes with a left accent bar."""

from __future__ import annotations

from reportlab.platypus import Flowable, Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render

# Width of the left accent bar in points
_BAR_WIDTH: float = 3.0
# Space between the bar and the text (points)
_BAR_GAP: float = 6.0


class _BlockQuoteBar(Flowable):
    """A thin coloured vertical rule drawn alongside blockquote content.

    ReportLab doesn't natively support a left border on ``Paragraph``,
    so we draw a filled rectangle on the canvas as a custom ``Flowable``.
    """

    def __init__(self, height: float, color) -> None:
        super().__init__()
        self._bq_height = height
        self._color = color
        self.width = _BAR_WIDTH + _BAR_GAP
        self.height = height

    def draw(self) -> None:
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 0, _BAR_WIDTH, self._bq_height, fill=1, stroke=0)


class BlockQuoteHandler(ElementHandler):
    """Render ``BlockQuote`` tokens as indented paragraphs with a left bar.

    Each child paragraph is preceded by a coloured vertical bar (drawn via
    a custom :class:`_BlockQuoteBar` flowable) that spans the full height of
    the paragraph block.
    """

    token_type = "BlockQuote"

    def render(self, token: dict, styles: dict) -> list:
        bar_color = styles.get("color_blockquote_bar")
        bq_style = styles.get("blockquote", styles.get("body"))
        flowables: list = []

        for child in token.get("children", []):
            child_type = child.get("type", "")

            if child_type == "Paragraph":
                text = inline_render(child.get("children", []), styles)
            else:
                # Non-paragraph children: render raw text as a fallback
                text = inline_render(child.get("children", []), styles) or child.get("raw", "")

            if not text:
                continue

            para = Paragraph(text, bq_style)
            # Estimate paragraph height for the bar.  We use a fixed
            # conservative estimate; Phase 6 (LayoutComposer) may refine this.
            estimated_height: float = (bq_style.leading or 14) * max(1, text.count("<br/>") + 1)

            if bar_color is not None:
                flowables.append(_BlockQuoteBar(estimated_height, bar_color))
            flowables.append(para)

        return flowables
