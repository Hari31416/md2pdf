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
        """Wrap each heading (or sequence of consecutive headings) with the following flowable.

        This ensures headings never appear alone at the bottom of a page.
        Supports preceding BookmarkFlowables by keeping them in the same block.
        Uses KeepTogetherParts so that splittable content (lists, paragraphs, tables, etc.)
        can start on the current page if the heading + minimum initial content fits,
        avoiding unnecessary page breaks and large blank areas.
        """
        from reportlab.platypus import PageBreak

        from md2pdf.core.flowables import KeepTogetherParts

        result: list[Flowable] = []
        i = 0
        while i < len(flowables):
            headings_group: list[Flowable] = []
            idx = i
            while idx < len(flowables):
                item = flowables[idx]
                if self._is_bookmark(item):
                    if idx + 1 < len(flowables) and (
                        self._is_heading(flowables[idx + 1])
                        or self._is_bookmark(flowables[idx + 1])
                    ):
                        headings_group.append(item)
                        idx += 1
                        continue
                    break
                elif self._is_heading(item):
                    headings_group.append(item)
                    idx += 1
                    continue
                break

            if any(self._is_heading(f) for f in headings_group):
                if idx < len(flowables):
                    nxt = flowables[idx]
                    if not isinstance(nxt, PageBreak):
                        if self._is_image_block(nxt):
                            result.append(KeepTogether(headings_group + [nxt]))
                        else:
                            result.append(KeepTogetherParts(headings_group + [nxt]))
                        i = idx + 1
                        continue

                result.extend(headings_group)
                i = idx
                continue

            result.append(flowables[i])
            i += 1
        return result

    def _bond_headings_to_images(self, flowables: list[Flowable]) -> list[Flowable]:
        """Wrap headings followed by image/diagram blocks in KeepTogether.

        Prevents ReportLab from inserting a large empty gap/page break between
        a heading and its corresponding chart/math block.
        """
        return flowables

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
