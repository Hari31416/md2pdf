"""Unit tests for LayoutComposer safeguards."""

from __future__ import annotations

from unittest.mock import MagicMock

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, KeepTogether, Paragraph

from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.core.flowables import BookmarkFlowable
from md2pdf.core.layout import LayoutComposer


def test_is_heading() -> None:
    """Verify that only Paragraphs with style names starting with 'h' are headings."""
    composer = LayoutComposer()
    h1_style = ParagraphStyle("h1")
    body_style = ParagraphStyle("body")

    assert composer._is_heading(Paragraph("Header", h1_style)) is True
    assert composer._is_heading(Paragraph("Body", body_style)) is False
    assert composer._is_heading(BookmarkFlowable("key")) is False


def test_is_image_block() -> None:
    """Verify image block recognition for ReportLab Image and custom PlaceholderBox."""
    composer = LayoutComposer()
    img = MagicMock(spec=Image)
    box = PlaceholderBox("mermaid", "source")

    assert composer._is_image_block(img) is True
    assert composer._is_image_block(box) is True
    assert composer._is_image_block(Paragraph("text", ParagraphStyle("body"))) is False


def test_bond_headings_to_next() -> None:
    """Heading followed by paragraph should be wrapped in KeepTogether."""
    composer = LayoutComposer()
    h1_style = ParagraphStyle("h1")
    body_style = ParagraphStyle("body")

    h = Paragraph("Header", h1_style)
    p = Paragraph("Paragraph", body_style)
    other = Paragraph("Other", body_style)

    flowables = [h, p, other]
    composed = composer.compose(flowables)

    assert len(composed) == 2
    assert isinstance(composed[0], KeepTogether)
    assert composed[0]._content == [h, p]
    assert composed[1] is other


def test_bond_headings_to_next_with_bookmark() -> None:
    """Preceding bookmark, heading, and paragraph should be kept together."""
    composer = LayoutComposer()
    h1_style = ParagraphStyle("h1")
    body_style = ParagraphStyle("body")

    b = BookmarkFlowable("slug")
    h = Paragraph("Header", h1_style)
    p = Paragraph("Paragraph", body_style)

    flowables = [b, h, p]
    composed = composer.compose(flowables)

    assert len(composed) == 1
    assert isinstance(composed[0], KeepTogether)
    assert composed[0]._content == [b, h, p]


def test_bond_headings_to_image() -> None:
    """Heading followed by diagram/image block should be wrapped in KeepTogether."""
    composer = LayoutComposer()
    h1_style = ParagraphStyle("h1")
    box = PlaceholderBox("mermaid", "source")

    h = Paragraph("Header", h1_style)
    flowables = [h, box]
    composed = composer.compose(flowables)

    assert len(composed) == 1
    assert isinstance(composed[0], KeepTogether)
    assert composed[0]._content == [h, box]
