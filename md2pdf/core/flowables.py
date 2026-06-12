"""Custom ReportLab flowables for md2pdf typesetting safeguards."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.platypus import Flowable, Image

logger = logging.getLogger(__name__)

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


class ResizableImage(Image):
    """An Image subclass that dynamically fits itself into available page space.

    If the image does not fit within the remaining vertical space on the current page,
    and we are not yet on a fresh page (i.e., we have room to defer), it triggers a
    deferral by returning its original dimensions. ReportLab will then push it to
    the next page.

    On a fresh page, or if we have already deferred once, it scales down proportionally
    to fit the remaining page height/width (down to a minimum scale if needed to
    prevent layout overflows).
    """

    # Track the maximum available height seen in the current rendering pass.
    # Updated dynamically on each wrap call to learn the printable page frame height.
    max_avail_height: float = 0.0

    # Minimum scale factor before deferring rendering to the next page.
    min_scale: float = 0.8

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._deferred: bool = False
        # Capture the initial target width and height to serve as our scaling baseline.
        # ReportLab's Image stores these in self.drawWidth and self.drawHeight.
        self.orig_width: float = float(self.drawWidth)
        self.orig_height: float = float(self.drawHeight)

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        # Update the class-level maximum seen height
        ResizableImage.max_avail_height = max(ResizableImage.max_avail_height, availHeight)

        # Calculate the scale factor required to fit the remaining space
        s = max(0.01, min(1.0, availWidth / self.orig_width, availHeight / self.orig_height))

        # We are on a fresh page (or as close to it as possible with preceding block elements
        # in KeepTogether like heading/bookmark) if the available height is close to the max.
        # We allow a margin of 120 points for preceding titles/headings.
        is_fresh_page = availHeight >= ResizableImage.max_avail_height - 120.0

        # Scale limit check using min_scale setting
        if s >= ResizableImage.min_scale or is_fresh_page or self._deferred:
            # We scale the image to fit
            self.drawWidth = self.orig_width * s
            self.drawHeight = self.orig_height * s
            logger.debug(
                "ResizableImage.wrap: fit. original=(%.2fx%.2f), scale=%.2f, new=(%.2fx%.2f), is_fresh=%s",
                self.orig_width,
                self.orig_height,
                s,
                self.drawWidth,
                self.drawHeight,
                is_fresh_page,
            )
            return self.drawWidth, self.drawHeight
        else:
            # Defer to the next page by returning original dimensions
            # ReportLab will find this too large for the current page and push it to the next
            self._deferred = True
            logger.debug(
                "ResizableImage.wrap: defer. original=(%.2fx%.2f), availHeight=%.2f, scale=%.2f, max_avail=%.2f",
                self.orig_width,
                self.orig_height,
                availHeight,
                s,
                ResizableImage.max_avail_height,
            )
            return self.orig_width, self.orig_height
