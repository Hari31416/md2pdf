"""Tests for cover/title page generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, Spacer

from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.postprocessors import CoverPagePostProcessor


def test_cover_page_post_processor_disabled() -> None:
    """Verify that CoverPagePostProcessor does nothing when cover is disabled."""
    doc = MagicMock()
    doc._md2pdf_config = Config(cover=False)
    doc._md2pdf_metadata = {"title": "Test Title", "author": "Jane Author", "date": "2026-06-14"}
    doc._md2pdf_metadata_keys = {"title", "author", "date"}
    doc._md2pdf_styles = {}

    flowables = [Paragraph("Hello", getSampleStyleSheet()["Normal"])]
    pp = CoverPagePostProcessor()
    result = pp.process(doc, flowables)

    assert result == flowables
    assert len(result) == 1


def test_cover_page_post_processor_enabled_only_title() -> None:
    """Verify that CoverPagePostProcessor prepends title cover page when only title is present."""
    doc = MagicMock()
    doc._md2pdf_config = Config(cover=True)
    doc._md2pdf_metadata = {"title": "Test Title", "author": "pymd2pdf", "date": ""}
    doc._md2pdf_metadata_keys = {"title"}
    doc._md2pdf_styles = {}

    flowables = [Paragraph("Hello", getSampleStyleSheet()["Normal"])]
    pp = CoverPagePostProcessor()
    result = pp.process(doc, flowables)

    # Expected cover flowables: Spacer, Paragraph (title), PageBreak
    assert len(result) == 4
    assert isinstance(result[0], Spacer)
    assert isinstance(result[1], Paragraph)
    assert result[1].text == "Test Title"
    assert isinstance(result[2], PageBreak)
    assert result[3] == flowables[0]


def test_cover_page_post_processor_enabled_with_author_and_date() -> None:
    """Verify cover page generates with author, date, and divider if explicitly declared."""
    doc = MagicMock()
    doc._md2pdf_config = Config(cover=True)
    doc._md2pdf_metadata = {"title": "Test Title", "author": "Jane Author", "date": "2026-06-14"}
    doc._md2pdf_metadata_keys = {"title", "author", "date"}
    doc._md2pdf_styles = {}

    flowables = [Paragraph("Hello", getSampleStyleSheet()["Normal"])]
    pp = CoverPagePostProcessor()
    result = pp.process(doc, flowables)

    # Expected cover flowables: Spacer, Paragraph (title), HRFlowable, Paragraph (author), Paragraph (date), PageBreak
    assert len(result) == 7
    assert isinstance(result[0], Spacer)
    assert isinstance(result[1], Paragraph)
    assert result[1].text == "Test Title"
    assert isinstance(result[2], HRFlowable)
    assert isinstance(result[3], Paragraph)
    assert result[3].text == "Jane Author"
    assert isinstance(result[4], Paragraph)
    assert result[4].text == "2026-06-14"
    assert isinstance(result[5], PageBreak)


def test_pipeline_integration_cover_only(tmp_path: Path) -> None:
    """Run full pipeline integration to verify cover generation works and does not crash."""
    md_content = """---
title: Beautiful Doc
author: Author Name
date: June 2026
---
# First Heading
Some body text.
"""
    md_file = tmp_path / "test.md"
    md_file.write_text(md_content, encoding="utf-8")
    pdf_file = tmp_path / "test.pdf"

    cfg = Config(input_file=str(md_file), output_file=str(pdf_file), cover=True, offline=True)
    pipeline = Pipeline(cfg)
    pipeline.run(md_content)

    assert pdf_file.exists()
    content = pdf_file.read_bytes()
    # Check that metadata components are present in final PDF metadata section
    assert b"Beautiful Doc" in content
    assert b"Author Name" in content
    assert pipeline.metadata["date"] == "June 2026"


def test_draw_page_number_suppresses_on_cover_page() -> None:
    """Test draw_page_number helper to ensure it skips cover page (page 1) but draws on later pages."""
    from md2pdf.core.pipeline import PageCallbackState, draw_page_number

    canvas = MagicMock()
    canvas.getPageNumber.return_value = 1

    doc = MagicMock()
    doc._md2pdf_config = Config(cover=True)
    doc.pagesize = (500, 700)

    state = PageCallbackState(
        header_template="{title} | {section}",
        header_on_first_page=False,
        metadata={"title": "Doc Title"},
        bookmarks=[],
        page_registry={},
        is_first_page=True,
    )

    # Call on cover page (page 1)
    draw_page_number(canvas, doc, state=state)
    canvas.saveState.assert_not_called()

    # Call on later page (page 2)
    canvas.getPageNumber.return_value = 2
    state.is_first_page = False
    draw_page_number(canvas, doc, state=state)
    canvas.saveState.assert_called_once()
