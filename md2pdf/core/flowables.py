"""Custom ReportLab flowables for md2pdf typesetting safeguards."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from reportlab.lib import colors
from reportlab.platypus import Flowable, Image, KeepTogether

logger = logging.getLogger(__name__)


def _absolute_to_local(canvas, x_abs: float, y_abs: float) -> tuple[float, float]:
    """Convert absolute page coordinates to local canvas coordinates by inverting the CTM."""
    matrix = getattr(canvas, "_currentMatrix", (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    a, b, c, d, e, f = matrix
    det = a * d - b * c
    if abs(det) < 1e-7:
        return x_abs - e, y_abs - f

    inv_a = d / det
    inv_c = -c / det
    inv_e = (c * f - d * e) / det
    inv_b = -b / det
    inv_d = a / det
    inv_f = (b * e - a * f) / det

    x_local = inv_a * x_abs + inv_c * y_abs + inv_e
    y_local = inv_b * x_abs + inv_d * y_abs + inv_f
    return x_local, y_local


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

    When *title* and *level* are provided the flowable also calls
    ``canvas.addOutlineEntry`` so that the bookmark appears in the PDF viewer's
    navigation / bookmarks panel.
    """

    page_registry: dict[str, int] = {}

    def __init__(self, key: str, title: str = "", level: int = 0) -> None:
        super().__init__()
        self.key = key
        self.title = title
        # PDF outline levels are 0-indexed; clamp to [0, 5].
        self.level = max(0, min(level, 5))

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        return 0.0, 0.0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
        doc = getattr(self.canv, "_doctemplate", None)
        if doc is not None and hasattr(doc, "_bookmark_page_registry"):
            doc._bookmark_page_registry[self.key] = self.canv.getPageNumber()
        else:
            BookmarkFlowable.page_registry[self.key] = self.canv.getPageNumber()
        if self.title:
            try:
                self.canv.addOutlineEntry(
                    self.title,
                    self.key,
                    level=self.level,
                    closed=False,
                )
            except Exception:
                logger.debug("addOutlineEntry failed for key=%r", self.key, exc_info=True)


def find_bookmarks(items: list) -> list[BookmarkFlowable]:
    """Recursively search for BookmarkFlowables with a title in a list of flowables."""
    res = []
    for item in items:
        if isinstance(item, BookmarkFlowable):
            if item.title:
                res.append(item)
        elif hasattr(item, "_content") and isinstance(item._content, list):
            res.extend(find_bookmarks(item._content))
        elif hasattr(item, "inner") and getattr(item, "inner", None):
            res.extend(find_bookmarks([item.inner]))
    return res


_image_state = threading.local()


class ResizableImageMeta(type):
    """Metaclass to expose thread-local attributes as class-level properties for ResizableImage."""

    @property
    def max_avail_height(cls) -> float:
        return getattr(_image_state, "max_avail_height", 0.0)

    @max_avail_height.setter
    def max_avail_height(cls, value: float) -> None:
        _image_state.max_avail_height = value

    @property
    def min_scale(cls) -> float:
        return getattr(_image_state, "min_scale", 0.8)

    @min_scale.setter
    def min_scale(cls, value: float) -> None:
        _image_state.min_scale = value


class ResizableImage(Image, metaclass=ResizableImageMeta):
    """An Image subclass that dynamically fits itself into available page space.

    If the image does not fit within the remaining vertical space on the current page,
    and we are not yet on a fresh page (i.e., we have room to defer), it triggers a
    deferral by returning its original dimensions. ReportLab will then push it to
    the next page.

    On a fresh page, or if we have already deferred once, it scales down proportionally
    to fit the remaining page height/width (down to a minimum scale if needed to
    prevent layout overflows).
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._deferred: bool = False
        # Capture the initial target width and height to serve as our scaling baseline.
        # ReportLab's Image stores these in self.drawWidth and self.drawHeight.
        self.orig_width: float = float(self.drawWidth)
        self.orig_height: float = float(self.drawHeight)
        self.spaceBefore = 0
        self.spaceAfter = 8

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


class FootnoteFlowable(Flowable):
    """A custom Flowable that renders a footnote at the bottom of the page frame.

    During Pass 1, it records the page number it naturally lands on.
    During Pass 2 (final pass), it draws the separator line (if it is the first
    footnote on the page) and draws the footnote text styled as a Paragraph at the
    absolute bottom of the page frame.
    """

    page_registry: dict[str, int] = {}
    page_footnotes: dict[int, list[FootnoteFlowable]] = {}

    def __init__(self, label: str, text: str, styles: dict) -> None:
        super().__init__()
        self.label = label
        self.text = text
        self.styles = styles

        # Normalize and parse any inline markdown formatting inside the footnote text
        from mistletoe.span_token import tokenize_inner
        from reportlab.platypus import Paragraph

        from md2pdf.core.parser import MarkdownParser
        from md2pdf.handlers.inline import inline_render

        parser = MarkdownParser()
        inline_tokens = [parser._normalize(t) for t in tokenize_inner(text)]
        rendered_text = inline_render(inline_tokens, styles)

        # Style and format the footnote text
        footnote_style = styles.get("footnote")
        self.para_text = f'<sup><a name="fn-{label}"/>{label}</sup> {rendered_text}'
        self.paragraph = Paragraph(self.para_text, footnote_style)
        self.width = 0.0
        self.height = 0.0

    def get_height(self, availWidth: float, availHeight: float) -> float:
        """Eagerly compute and cache the height of the footnote.

        This is necessary because later footnotes on a page may not have been wrapped
        yet when the first footnote is being drawn, meaning their height is otherwise
        recorded as 0.0, leading to overlapping layout.
        """
        # INVARIANT: get_height() must compute the full required height (including padding
        # and separators) and cache it in self.height. This cached height is then used
        # by MD2PDFDocTemplate.handle_pageBegin() to dynamically expand the bottom margin
        # of the page frame, ensuring we allocate exactly enough room for footnotes.
        if self.height > 0.0:
            return self.height

        w, h = self.paragraph.wrap(availWidth, availHeight)
        self.width = w

        doc = getattr(self, "_doc", None)
        if doc is None:
            doc = getattr(self.canv, "_doctemplate", None) if hasattr(self, "canv") else None

        is_first = False
        if (
            doc is not None
            and hasattr(doc, "_footnote_page_registry")
            and hasattr(doc, "_footnote_page_footnotes")
        ):
            page_registry = doc._footnote_page_registry
            page_footnotes = doc._footnote_page_footnotes
        else:
            page_registry = FootnoteFlowable.page_registry
            page_footnotes = FootnoteFlowable.page_footnotes

        page_num = page_registry.get(self.label)
        if page_num is not None:
            fns = page_footnotes.get(page_num, [])
            if fns and fns[0] is self:
                is_first = True

        if is_first:
            self.height = h + 14.0  # 10pt for separator rule space, 4pt padding
        else:
            self.height = h + 4.0  # 4pt padding

        return self.height

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        # INVARIANT: wrap() returns (0.0, 0.0) so ReportLab does not reserve standard flow
        # height for the footnote flowable itself, as footnotes are drawn out-of-flow
        # at the absolute bottom of the page frame. The actual layout height is computed
        # and cached by calling get_height() here.
        self.get_height(availWidth, availHeight)
        return 0.0, 0.0

    def draw(self) -> None:
        page_num = self.canv.getPageNumber()
        # Record the page number where this footnote flowable is drawn
        doc = getattr(self.canv, "_doctemplate", None)
        if doc is not None and hasattr(doc, "_footnote_page_registry"):
            doc._footnote_page_registry[self.label] = page_num
        else:
            FootnoteFlowable.page_registry[self.label] = page_num

        is_final = getattr(self.canv._doctemplate, "_md2pdf_is_final", False)
        if not is_final:
            self.paragraph.drawOn(self.canv, 0, 0)
            return

        # Find all footnotes on this page to align properly
        if doc is not None and hasattr(doc, "_footnote_page_footnotes"):
            fns = doc._footnote_page_footnotes.get(page_num, [])
        else:
            fns = FootnoteFlowable.page_footnotes.get(page_num, [])
        if not fns:
            return

        doc = getattr(self.canv, "_doctemplate", None)
        if doc is None:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm

            # Fallback to standard A4 dimensions with 20mm horizontal margins and 22mm vertical margins
            left_margin = 20 * mm
            bottom_margin = 22 * mm
            width = A4[0] - left_margin * 2
            height = A4[1] - bottom_margin * 2
        else:
            width, height = doc.width, doc.height
            left_margin = doc.leftMargin
            bottom_margin = doc.bottomMargin

        # Total height of all footnotes on this page
        total_H = sum(f.get_height(width, height) for f in fns)

        # Calculate the absolute position of this flowable's origin
        x_abs, y_abs = self.canv.absolutePosition(0, 0)

        # Find our index among the footnotes on this page
        try:
            idx = fns.index(self)
        except ValueError:
            return

        # Calculate the starting y_abs for this footnote.
        # Footnotes are stacked downwards starting from (bottom_margin + total_H).
        y_start_abs = bottom_margin + total_H
        for i in range(idx):
            y_start_abs -= fns[i].get_height(width, height)

        # If this is the first footnote, draw the separator line!
        if idx == 0:
            line_y_abs = y_start_abs - 6.0
            line_x_start = left_margin
            line_x_end = left_margin + 72.0  # 1 inch line

            # Translate to local coordinates using the inverse transform matrix
            local_line_x_start, local_line_y_start = _absolute_to_local(
                self.canv, line_x_start, line_y_abs
            )
            local_line_x_end, local_line_y_end = _absolute_to_local(
                self.canv, line_x_end, line_y_abs
            )

            self.canv.saveState()
            self.canv.setStrokeColor(self.styles.get("color_hr") or colors.HexColor("#cccccc"))
            self.canv.setLineWidth(0.5)
            self.canv.line(
                local_line_x_start, local_line_y_start, local_line_x_end, local_line_y_end
            )
            self.canv.restoreState()

        para_y_abs = y_start_abs - self.get_height(width, height) + 4.0

        # Draw the paragraph at its absolute position
        para_x_local, para_y_local = _absolute_to_local(self.canv, left_margin, para_y_abs)

        self.paragraph.drawOn(self.canv, para_x_local, para_y_local)


class KeepTogetherParts(KeepTogether):
    """A subclass of KeepTogether that checks if a minimum subset of flowables fits.

    Specifically, if the last flowable is a Table, it calculates the height of the preceding
    flowables plus the height of the first row of the Table (or the repeated header rows plus
    the first data row). If this minimum height fits in the available space, it splits and
    allows the components to flow, allowing the table to start on the current page and split
    to the next page, preventing huge empty gaps at the bottom of pages.
    """

    def split(self, aW: float, aH: float) -> list[Flowable]:
        if getattr(self, "_wrapInfo", None) != (aW, aH):
            self.wrap(aW, aH)

        from reportlab.platypus import Table
        from reportlab.platypus.flowables import _listWrapOn

        dims: list[tuple[float, float]] = []
        _listWrapOn(self._content, aW, self.canv, dims=dims)

        h_before = 0.0
        h_table_first_row = 0.0

        for i, child in enumerate(self._content):
            child_w, child_h = dims[i]
            if isinstance(child, Table) and i == len(self._content) - 1:
                row_heights = getattr(child, "_rowHeights", None)
                if row_heights:
                    num_rows_to_keep = max(1, getattr(child, "repeatRows", 0))
                    if len(row_heights) > num_rows_to_keep:
                        num_rows_to_keep += 1
                    # Add 15 points safety margin for grid lines/padding/borders
                    h_table_first_row = sum(row_heights[:num_rows_to_keep]) + 15.0
                else:
                    h_table_first_row = 45.0  # 30 + 15 fallback
            else:
                h_before += child_h

        h_min = h_before + h_table_first_row

        S = self._content[:]
        cf = atTop = getattr(self, "_frame", None)
        if cf:
            atTop = getattr(cf, "_atTop", None)
            cAW = cf._width
            cAH = cf._height

        C0 = h_min > aH
        C1 = C0 and atTop

        if C0 or C1:
            fb = False
            panf = self._doctemplateAttr("_peekNextFrame")
            if cf and panf:
                nf = panf()
                nAW = nf._width
                nAH = nf._height
            if C0 and not atTop:
                fb = not (atTop and cf and nf and cAW >= nAW and cAH >= nAH)
            elif nf and nAW >= cf._width and nAH >= h_min:
                fb = True

            from reportlab.platypus.doctemplate import FrameBreak, NullActionFlowable

            S.insert(0, (FrameBreak() if fb else NullActionFlowable()))

        return S


class AdmonitionBox(Flowable):
    """A custom Flowable wrapping multiple inner flowables with a filled background

    and a left vertical accent bar. Supports splitting across page boundaries.
    """

    def __init__(
        self,
        content: list[Flowable],
        border_color: colors.Color,
        bg_color: colors.Color,
        title_flowable: Flowable | None = None,
        padding: float = 10.0,
        left_bar_width: float = 4.0,
    ) -> None:
        super().__init__()
        self.content = content
        self.title_flowable = title_flowable
        self.border_color = border_color
        self.bg_color = bg_color
        self.padding = padding
        self.left_bar_width = left_bar_width
        self.width = 0.0
        self.height = 0.0
        self.spaceBefore = 0
        self.spaceAfter = 8

    def wrap(self, availWidth: float, availHeight: float) -> tuple[float, float]:
        inner_avail_width = max(0.0, availWidth - (self.left_bar_width + self.padding * 2))
        h_total = self.padding
        if self.title_flowable:
            _, h_title = self.title_flowable.wrap(inner_avail_width, availHeight)
            h_total += h_title + 6.0
        for f in self.content:
            _, h_f = f.wrap(inner_avail_width, availHeight)
            h_total += h_f + 4.0
        h_total += self.padding
        self.width = availWidth
        self.height = h_total
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        assert self.height > 0.0, "AdmonitionBox must be wrapped before drawn."

        c.saveState()
        # 1. Background
        c.setFillColor(self.bg_color)
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        # 2. Left accent bar
        c.setFillColor(self.border_color)
        c.rect(0, 0, self.left_bar_width, self.height, fill=1, stroke=0)
        c.restoreState()

        # 3. Draw content
        inner_avail_width = max(0.0, self.width - (self.left_bar_width + self.padding * 2))
        inner_x = self.left_bar_width + self.padding
        y_cursor = self.height - self.padding
        if self.title_flowable:
            if not hasattr(self.title_flowable, "height") or self.title_flowable.height <= 0.0:
                self.title_flowable.wrap(inner_avail_width, self.height)
            h_title = self.title_flowable.height
            y_cursor -= h_title
            self.title_flowable.drawOn(c, inner_x, y_cursor)
            y_cursor -= 6.0
        for f in self.content:
            if not hasattr(f, "height") or f.height <= 0.0:
                f.wrap(inner_avail_width, self.height)
            h_f = f.height
            y_cursor -= h_f
            f.drawOn(c, inner_x, y_cursor)
            y_cursor -= 4.0

    def split(self, availWidth: float, availHeight: float) -> list[Flowable]:
        inner_avail_width = max(0.0, availWidth - (self.left_bar_width + self.padding * 2))
        title_h = 0.0
        if self.title_flowable:
            _, title_h = self.title_flowable.wrap(inner_avail_width, availHeight)

        h_used = self.padding
        if self.title_flowable:
            h_used += title_h + 6.0

        fit_idx = 0
        for i, f in enumerate(self.content):
            _, h_f = f.wrap(inner_avail_width, availHeight)
            if h_used + h_f + self.padding > availHeight:
                break
            h_used += h_f + 4.0
            fit_idx = i + 1

        if fit_idx == 0 or fit_idx == len(self.content):
            return []

        content_fit = self.content[:fit_idx]
        content_leftover = self.content[fit_idx:]

        part1 = AdmonitionBox(
            content=content_fit,
            border_color=self.border_color,
            bg_color=self.bg_color,
            title_flowable=self.title_flowable,
            padding=self.padding,
            left_bar_width=self.left_bar_width,
        )
        part2 = AdmonitionBox(
            content=content_leftover,
            border_color=self.border_color,
            bg_color=self.bg_color,
            title_flowable=None,
            padding=self.padding,
            left_bar_width=self.left_bar_width,
        )
        return [part1, part2]
