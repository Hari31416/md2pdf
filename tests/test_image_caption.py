from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import KeepTogether, Paragraph

from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.core.flowables import ResizableImage
from md2pdf.core.layout import LayoutComposer
from md2pdf.handlers.paragraph import ParagraphHandler
from md2pdf.styles.default import build_default_stylesheet


@pytest.fixture
def styles() -> dict:
    from md2pdf.assets._font_registry import register_fonts

    register_fonts()
    return build_default_stylesheet()


def test_image_caption_style(styles):
    """Verify that image_caption style is present, has center alignment, and has correct font size."""
    assert "image_caption" in styles
    style = styles["image_caption"]
    assert style.alignment == TA_CENTER
    assert style.fontSize == styles["body"].fontSize - 2 or style.fontSize == 8


def test_layout_composer_is_image_block(styles):
    """Verify LayoutComposer._is_image_block correctly handles KeepTogether containing images."""
    composer = LayoutComposer()
    from reportlab.platypus import Image

    img = MagicMock(spec=Image)
    box = PlaceholderBox("image", "source")
    p = Paragraph("caption", style=styles["image_caption"])

    # Directly checking Image and PlaceholderBox
    assert composer._is_image_block(img) is True
    assert composer._is_image_block(box) is True
    assert composer._is_image_block(p) is False

    # Checking KeepTogether
    kt_with_img = KeepTogether([img, p])
    kt_with_box = KeepTogether([box, p])
    kt_without_img = KeepTogether([p, p])

    assert composer._is_image_block(kt_with_img) is True
    assert composer._is_image_block(kt_with_box) is True
    assert composer._is_image_block(kt_without_img) is False


def test_paragraph_handler_markdown_image_with_caption(styles, tmp_path):
    """Verify block MarkdownImage with non-empty alt text is rendered inside KeepTogether with a caption."""
    # Write a dummy image file so path resolution and PIL loading work
    from PIL import Image as PILImage

    img_file = tmp_path / "test_img.png"
    PILImage.new("RGB", (100, 100), color="blue").save(img_file)

    token = {
        "type": "Paragraph",
        "raw": "![Test Caption](test_img.png)",
        "attrs": {},
        "children": [
            {
                "type": "Image",
                "attrs": {"target": "test_img.png"},
                "children": [
                    {"type": "RawText", "raw": "Test Caption", "children": [], "attrs": {}}
                ],
            }
        ],
        "_node": None,
    }

    # Setup config context inside styles
    config = MagicMock()
    config.input_file = str(tmp_path / "dummy_doc.md")
    styles["_config"] = config

    flowables = ParagraphHandler().render(token, styles)

    # Since it is a block image with alt-text, it should return a KeepTogether
    assert len(flowables) == 1
    assert isinstance(flowables[0], KeepTogether)

    kt = flowables[0]
    assert len(kt._content) == 2
    assert isinstance(kt._content[0], ResizableImage)
    assert isinstance(kt._content[1], Paragraph)

    # Check text and style of the caption Paragraph
    assert kt._content[1].text == "Test Caption"
    assert kt._content[1].style.name == "image_caption"

    # Verify spaceAfter was reduced on the image
    assert kt._content[0].spaceAfter == styles.get("spacing_base", 8) // 2


def test_paragraph_handler_markdown_image_without_caption(styles, tmp_path):
    """Verify block MarkdownImage with empty alt text is rendered as standalone ResizableImage."""
    from PIL import Image as PILImage

    img_file = tmp_path / "test_img.png"
    PILImage.new("RGB", (100, 100), color="blue").save(img_file)

    token = {
        "type": "Paragraph",
        "raw": "![](test_img.png)",
        "attrs": {},
        "children": [{"type": "Image", "attrs": {"target": "test_img.png"}, "children": []}],
        "_node": None,
    }

    config = MagicMock()
    config.input_file = str(tmp_path / "dummy_doc.md")
    styles["_config"] = config

    flowables = ParagraphHandler().render(token, styles)

    # Without caption, it is just a standalone ResizableImage
    assert len(flowables) == 1
    assert isinstance(flowables[0], ResizableImage)
    assert flowables[0].spaceAfter == styles.get("spacing_base", 8)


def test_paragraph_handler_html_image_with_caption(styles):
    """Verify block HTMLImage with non-empty alt text is escaped and rendered inside KeepTogether with a caption."""
    # Let's mock a missing image to trigger PlaceholderBox flow but verify captioning logic on it
    token = {
        "type": "Paragraph",
        "raw": '<img src="missing.png" alt="A & B & C" />',
        "attrs": {},
        "children": [
            {
                "type": "RawText",
                "raw": '<img src="missing.png" alt="A & B & C" />',
                "children": [],
                "attrs": {},
            }
        ],
        "_node": None,
    }

    config = MagicMock()
    config.input_file = ""
    styles["_config"] = config

    flowables = ParagraphHandler().render(token, styles)

    # Should be PlaceholderBox with caption wrapped in KeepTogether
    assert len(flowables) == 1
    assert isinstance(flowables[0], KeepTogether)

    kt = flowables[0]
    assert len(kt._content) == 2
    assert isinstance(kt._content[0], PlaceholderBox)
    assert isinstance(kt._content[1], Paragraph)

    # Alt text should be escaped: "A & B & C" -> "A &amp; B &amp; C"
    assert kt._content[1].text == "A &amp; B &amp; C"
    assert kt._content[1].style.name == "image_caption"
