"""Layout composer for applying typesetting safeguards and anti-fail logic."""

from __future__ import annotations

from typing import TYPE_CHECKING

from reportlab.platypus import Flowable, KeepTogether

if TYPE_CHECKING:
    pass


class LayoutComposer:
    """Post-processes the flat list of flowables to apply layout safeguards.

    Prevents:
    - Section headings stranded at the bottom of a page (orphaned headings).
    - Heading-image separation (ghost empty page gaps).
    """

    def compose(self, flowables: list[Flowable]) -> list[Flowable]:
        """Apply all layout safeguard passes in order.

        Args:
            flowables: Flat list of flowables before layout grouping.

        Returns:
            A post-processed list of flowables with safeguards applied.
        """
        flowables = self._bond_headings_to_next(flowables)
        flowables = self._bond_headings_to_images(flowables)
        return flowables

    def _bond_headings_to_next(self, flowables: list[Flowable]) -> list[Flowable]:
        """Wrap each heading with the immediately following flowable in a KeepTogether.

        This ensures headings never appear alone at the bottom of a page.
        Supports preceding BookmarkFlowables by keeping them in the same KeepTogether block.
        """
        result: list[Flowable] = []
        i = 0
        while i < len(flowables):
            current = flowables[i]
            bookmark = None
            heading = None
            idx_next = i + 1

            if (
                self._is_bookmark(current)
                and i + 1 < len(flowables)
                and self._is_heading(flowables[i + 1])
            ):
                bookmark = current
                heading = flowables[i + 1]
                idx_next = i + 2
            elif self._is_heading(current):
                heading = current
                idx_next = i + 1

            assert idx_next > i
            if heading is not None and idx_next < len(flowables):
                nxt = flowables[idx_next]
                # Don't bond heading to another heading or an image block
                if not self._is_heading(nxt) and not self._is_image_block(nxt):
                    elements = [bookmark, heading, nxt] if bookmark else [heading, nxt]
                    from reportlab.platypus import Table

                    from md2pdf.core.flowables import KeepTogetherParts

                    if isinstance(nxt, Table):
                        result.append(KeepTogetherParts(elements))
                    else:
                        result.append(KeepTogether(elements))
                    i = idx_next + 1
                    continue

            result.append(current)
            i += 1
        return result

    def _bond_headings_to_images(self, flowables: list[Flowable]) -> list[Flowable]:
        """Wrap headings followed by image/diagram blocks in KeepTogether.

        Prevents ReportLab from inserting a large empty gap/page break between
        a heading and its corresponding chart/math block.
        """
        result: list[Flowable] = []
        i = 0
        while i < len(flowables):
            current = flowables[i]
            bookmark = None
            heading = None
            idx_next = i + 1

            if (
                self._is_bookmark(current)
                and i + 1 < len(flowables)
                and self._is_heading(flowables[i + 1])
            ):
                bookmark = current
                heading = flowables[i + 1]
                idx_next = i + 2
            elif self._is_heading(current):
                heading = current
                idx_next = i + 1

            assert idx_next > i
            if heading is not None and idx_next < len(flowables):
                nxt = flowables[idx_next]
                if self._is_image_block(nxt):
                    elements = [bookmark, heading, nxt] if bookmark else [heading, nxt]
                    result.append(KeepTogether(elements))
                    i = idx_next + 1
                    continue

            result.append(current)
            i += 1
        return result

    def _is_heading(self, f: Flowable) -> bool:
        from reportlab.platypus import Paragraph

        if not isinstance(f, Paragraph):
            return False
        style_name = getattr(f.style, "name", "")
        return style_name.startswith("h") if style_name else False

    def _is_image_block(self, f: Flowable) -> bool:
        from reportlab.platypus import Image, KeepTogether

        from md2pdf.assets.fallback import PlaceholderBox

        if isinstance(f, KeepTogether):
            return any(self._is_image_block(child) for child in f._content)

        return isinstance(f, Image) or isinstance(f, PlaceholderBox)

    def _is_bookmark(self, f: Flowable) -> bool:
        from md2pdf.core.flowables import BookmarkFlowable

        return isinstance(f, BookmarkFlowable)
