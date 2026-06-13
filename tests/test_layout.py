"""Unit tests for LayoutComposer safeguards."""

from __future__ import annotations

from unittest.mock import MagicMock

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image, KeepTogether, Paragraph

from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.core.flowables import BookmarkFlowable, ResizableImage
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


def test_bond_headings_to_table() -> None:
    """Heading followed by Table should be wrapped in KeepTogetherParts."""
    from reportlab.platypus import Table

    from md2pdf.core.flowables import KeepTogetherParts

    composer = LayoutComposer()
    h1_style = ParagraphStyle("h1")

    h = Paragraph("Header", h1_style)
    t = Table([["A", "B"]])
    flowables = [h, t]
    composed = composer.compose(flowables)

    assert len(composed) == 1
    assert isinstance(composed[0], KeepTogetherParts)
    assert composed[0]._content == [h, t]


def _get_test_image_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image as PILImage

    img_data = BytesIO()
    PILImage.new("RGBA", (10, 10), "red").save(img_data, format="PNG")
    return img_data.getvalue()


def test_resizable_image_fits_fully() -> None:
    """Verify ResizableImage renders at 100% scale when ample space is available."""
    from io import BytesIO

    ResizableImage.max_avail_height = 0.0
    img = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # 500x500 available space, should fit completely
    w, h = img.wrap(500.0, 500.0)
    assert w == 100.0
    assert h == 100.0
    assert img._deferred is False


def test_resizable_image_scales_down_within_threshold() -> None:
    """Verify ResizableImage scales down proportionally when it fits within the 80% threshold."""
    from io import BytesIO

    ResizableImage.max_avail_height = 0.0
    img = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # Available height is 90, which requires scaling to 90% (0.9 >= 0.8)
    w, h = img.wrap(500.0, 90.0)
    assert w == 90.0
    assert h == 90.0
    assert img._deferred is False


def test_resizable_image_defers_when_too_large() -> None:
    """Verify ResizableImage defers (returns original size) when scale is below 80% on a non-fresh page."""
    from io import BytesIO

    # Pretend we know page height is 700.0
    ResizableImage.max_avail_height = 700.0
    img = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # Available height is 50. Scale s = 0.5 < 0.8.
    # Since 50 < 700 - 120 (580), it is not a fresh page, so it should defer.
    w, h = img.wrap(500.0, 50.0)
    assert w == 100.0
    assert h == 100.0
    assert img._deferred is True


def test_resizable_image_scales_on_fresh_page_even_if_below_threshold() -> None:
    """Verify ResizableImage does not defer on a fresh page even if the scale is below 80%."""
    from io import BytesIO

    # Pretend page height is 700.0
    ResizableImage.max_avail_height = 700.0
    img = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=1000.0)

    # Available height is 700 (fresh page, since 700 >= 700 - 120).
    # Scale s = 700 / 1000 = 0.7 < 0.8.
    # It must scale to fit rather than deferring to avoid infinite page breaks.
    w, h = img.wrap(500.0, 700.0)
    assert w == 70.0  # 100 * 0.7
    assert h == 700.0  # 1000 * 0.7
    assert img._deferred is False


def test_resizable_image_scales_to_fit_after_deferral() -> None:
    """Verify ResizableImage scales down to fit on the next page after having deferred once."""
    from io import BytesIO

    ResizableImage.max_avail_height = 700.0
    img = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # First wrap on a restricted space, triggers deferral
    w1, h1 = img.wrap(500.0, 50.0)
    assert w1 == 100.0
    assert h1 == 100.0
    assert img._deferred is True

    # Second wrap (simulating next page), should scale to fit even if below 80%
    w2, h2 = img.wrap(500.0, 50.0)
    assert w2 == 50.0
    assert h2 == 50.0


def test_resizable_image_respects_configured_min_scale() -> None:
    """Verify ResizableImage scales/defers according to custom min_scale."""
    from io import BytesIO

    # Test with standard min_scale = 0.8
    ResizableImage.min_scale = 0.8
    ResizableImage.max_avail_height = 700.0
    img1 = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # Available height is 75, so s = 0.75 < 0.8 -> should defer!
    w1, h1 = img1.wrap(500.0, 75.0)
    assert w1 == 100.0
    assert img1._deferred is True

    # Test with custom min_scale = 0.7
    ResizableImage.min_scale = 0.7
    ResizableImage.max_avail_height = 700.0
    img2 = ResizableImage(BytesIO(_get_test_image_bytes()), width=100.0, height=100.0)

    # Available height is 75, so s = 0.75 >= 0.7 -> should NOT defer and instead fit!
    w2, h2 = img2.wrap(500.0, 75.0)
    assert w2 == 75.0
    assert img2._deferred is False
