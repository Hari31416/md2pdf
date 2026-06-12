"""Custom ReportLab flowables for md2pdf typesetting safeguards."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.platypus import Flowable

if TYPE_CHECKING:
    from reportlab.lib.colors import Color


class BlockQuoteBar(Flowable):
    """A custom Flowable wrapping an inner flowable with a left vertical accent bar.

    This ensures that the accent bar spans the exact height of the nested content,
    and cleanly delegates wrapping, drawing, and splitting so the blockquote
    can break across page boundaries without formatting errors.
    """

    def __init__(
        self,
        inner_flowable: Flowable,
        bar_color: Color | None = None,
        bar_width: float = 3.0,
        padding: float = 8.0,
    ) -> None:
        super().__init__()
        self.inner = inner_flowable
        self.bar_color = bar_color or colors.HexColor("#cccccc")
        self.bar_width = bar_width
        self.padding = padding
        self.width = 0.0
        self.height = 0.0

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        inner_avail_width = max(0.0, availWidth - (self.bar_width + self.padding))
        w_inner, h_inner = self.inner.wrap(inner_avail_width, availHeight)
        self.width = w_inner + self.bar_width + self.padding
        self.height = h_inner
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.saveState()
        c.setFillColor(self.bar_color)
        c.rect(0, 0, self.bar_width, self.height, fill=1, stroke=0)
        c.restoreState()
        self.inner.drawOn(c, self.bar_width + self.padding, 0)

    def split(self, availWidth: float, availHeight: float) -> list[Flowable]:
        inner_avail_width = max(0.0, availWidth - (self.bar_width + self.padding))
        splits = self.inner.split(inner_avail_width, availHeight)
        if not splits:
            return []
        return [
            BlockQuoteBar(
                s,
                bar_color=self.bar_color,
                bar_width=self.bar_width,
                padding=self.padding,
            )
            for s in splits
        ]


class BookmarkFlowable(Flowable):
    """A custom flowable that registers a PDF bookmark anchor on the current page.

    This is an invisible, zero-size flowable inserted just before heading flowables
    to serve as anchor destinations for Table of Contents links.
    """

    def __init__(self, key: str) -> None:
        super().__init__()
        self.key = key

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return 0.0, 0.0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
