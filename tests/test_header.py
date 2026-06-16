"""Tests for page headers and running titles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from reportlab.lib.pagesizes import A4

from md2pdf.core.config import Config
from md2pdf.core.flowables import BookmarkFlowable
from md2pdf.core.pipeline import (
    PageCallbackState,
    Pipeline,
    _get_current_section,
    draw_page_number,
)


def test_get_current_section() -> None:
    """Verify section extraction from bookmark sequence."""
    b1 = BookmarkFlowable("sec1", "Section One", level=0)
    b2 = BookmarkFlowable("sec2", "Section Two", level=1)
    b3 = BookmarkFlowable("sec3", "Subsection Three", level=2)

    bookmarks = [b1, b2, b3]
    page_registry = {
        "sec1": 1,
        "sec2": 2,
        "sec3": 2,
    }

    # Page 1: should be Section One (most recent level <= 1)
    assert _get_current_section(1, bookmarks, page_registry) == "Section One"
    # Page 2: should be Section Two (most recent level <= 1 is sec2)
    assert _get_current_section(2, bookmarks, page_registry) == "Section Two"

    # Fallback when no level <= 1 is found (e.g. only H3 is registered on page 1)
    b_only_h3 = BookmarkFlowable("h3", "Sub", level=2)
    assert _get_current_section(1, [b_only_h3], {"h3": 1}) == "Sub"


def test_draw_page_number_with_header() -> None:
    """Verify header and line drawing logic with configured state."""
    canvas = MagicMock()
    canvas.getPageNumber.return_value = 2

    doc = MagicMock()
    doc.pagesize = A4

    b1 = BookmarkFlowable("sec1", "Introduction", level=0)
    state = PageCallbackState(
        header_template="{title} | {section}",
        header_on_first_page=False,
        metadata={"title": "My Doc"},
        bookmarks=[b1],
        page_registry={"sec1": 1},
        is_first_page=False,
    )

    draw_page_number(canvas, doc, state=state)

    # Assert footer was drawn
    canvas.drawRightString.assert_called_once()

    # Assert header was drawn
    canvas.drawString.assert_called_once()
    args, _ = canvas.drawString.call_args
    # Third arg is the text
    assert args[2] == "My Doc | Introduction"
    canvas.line.assert_called_once()


def test_draw_page_number_first_page_suppressed() -> None:
    """Verify that header drawing is suppressed on page 1 by default."""
    canvas = MagicMock()
    canvas.getPageNumber.return_value = 1

    doc = MagicMock()
    doc.pagesize = A4

    state = PageCallbackState(
        header_template="Static Header",
        header_on_first_page=False,
        metadata={},
        bookmarks=[],
        page_registry={},
        is_first_page=True,
    )

    draw_page_number(canvas, doc, state=state)

    canvas.drawRightString.assert_called_once()
    canvas.drawString.assert_not_called()
    canvas.line.assert_not_called()


def test_draw_page_number_first_page_enabled() -> None:
    """Verify that header drawing works on page 1 if explicitly configured."""
    canvas = MagicMock()
    canvas.getPageNumber.return_value = 1

    doc = MagicMock()
    doc.pagesize = A4

    state = PageCallbackState(
        header_template="Static Header",
        header_on_first_page=True,
        metadata={},
        bookmarks=[],
        page_registry={},
        is_first_page=True,
    )

    draw_page_number(canvas, doc, state=state)

    canvas.drawRightString.assert_called_once()
    canvas.drawString.assert_called_once()
    args, _ = canvas.drawString.call_args
    assert args[2] == "Static Header"
    canvas.line.assert_called_once()


def test_pipeline_with_section_headers(tmp_path: Path) -> None:
    """End-to-End integration test validating headers in full pipeline execution."""
    pdf_path = tmp_path / "test_headers.pdf"
    md_content = """# Title
Some text on page 1.

# First Section
More text here.
"""
    cfg = Config(
        input_file="",
        output_file=str(pdf_path),
        header="{title} - {section}",
        header_on_first_page=False,
        offline=True,
    )
    pipeline = Pipeline(cfg)
    pipeline.run(md_content)
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000


def test_unescape_html_entities_in_headers_and_outlines(tmp_path: Path) -> None:
    """Verify that headings with HTML entities are unescaped in outlines and headers."""
    canvas = MagicMock()
    canvas.getPageNumber.return_value = 2

    doc = MagicMock()
    doc.pagesize = A4

    # Test draw_page_number unescapes header text
    state = PageCallbackState(
        header_template="LLM Notes | {section}",
        header_on_first_page=False,
        metadata={"title": "My &amp; Doc"},
        bookmarks=[BookmarkFlowable("sec1", "Self-Attention &amp; Transformers", level=0)],
        page_registry={"sec1": 2},
        is_first_page=False,
    )

    draw_page_number(canvas, doc, state=state)
    canvas.drawString.assert_called_once()
    args, _ = canvas.drawString.call_args
    assert args[2] == "LLM Notes | Self-Attention & Transformers"

    # Test HeadingHandler unescapes in plain_title
    from md2pdf.handlers.heading import HeadingHandler
    from md2pdf.styles.default import build_default_stylesheet

    styles = build_default_stylesheet()
    token = {
        "type": "Heading",
        "attrs": {"level": 2},
        "children": [{"type": "RawText", "raw": "Self-Attention & Transformers"}],
    }

    handler = HeadingHandler()
    flowables = handler.render(token, styles)

    # flowables[0] is the BookmarkFlowable
    assert isinstance(flowables[0], BookmarkFlowable)
    assert flowables[0].title == "Self-Attention & Transformers"
