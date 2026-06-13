from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table

from md2pdf.core.config import Config
from md2pdf.core.flowables import BookmarkFlowable
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.postprocessors import TableOfContentsPostProcessor


def test_toc_disabled_by_default(default_registry) -> None:
    """Verify that when toc is disabled (default), no TOC flowables are added."""
    cfg = Config(input_file="", output_file="", offline=True)
    assert not cfg.toc

    doc = MagicMock()
    doc._md2pdf_config = cfg
    doc._md2pdf_styles = {}

    style = ParagraphStyle("test_style", fontName="Helvetica", fontSize=10)
    flowables = [
        BookmarkFlowable("introduction", "Introduction", 0),
        Paragraph("Introduction content", style),
    ]

    pp = TableOfContentsPostProcessor()
    result = pp.process(doc, flowables)

    # Should remain unchanged
    assert len(result) == 2
    assert result == flowables


def test_toc_enabled_prepends_toc_page(default_registry) -> None:
    """Verify that enabling toc prepends a table of contents page with links and pagebreak."""
    cfg = Config(input_file="", output_file="", offline=True, toc=True)
    assert cfg.toc

    style = ParagraphStyle("test_style", fontName="Helvetica", fontSize=10)
    doc = MagicMock()
    doc._md2pdf_config = cfg
    doc._md2pdf_styles = {
        "color_link": "#00ff00",
        "h1": style,
        "body": style,
    }

    flowables = [
        BookmarkFlowable("section-1", "Section 1", level=0),
        Paragraph("Content 1", style),
        BookmarkFlowable("section-2", "Section 2 & More", level=1),
        Paragraph("Content 2", style),
    ]

    pp = TableOfContentsPostProcessor()
    result = pp.process(doc, flowables)

    # Result should prepend:
    # 1. BookmarkFlowable for TOC itself ("table-of-contents")
    # 2. Paragraph ("Table of Contents")
    # 3. Spacer
    # 4. Table (containing entries)
    # 5. PageBreak
    # And then the rest of the flowables
    assert len(result) == len(flowables) + 5
    assert isinstance(result[0], BookmarkFlowable)
    assert result[0].key == "table-of-contents"

    assert isinstance(result[1], Paragraph)
    assert result[1].text == "Table of Contents"

    assert isinstance(result[2], Spacer)

    assert isinstance(result[3], Table)
    cell_values = result[3]._cellvalues
    assert len(cell_values) == 2

    # Row 0: Section 1
    assert '<link href="#section-1"' in cell_values[0][0].text
    assert "Section 1" in cell_values[0][0].text
    assert cell_values[0][0].style.leftIndent == 0
    assert result[3]._cellStyles[0][0].leftPadding == 0

    # Row 1: Section 2
    assert '<link href="#section-2"' in cell_values[1][0].text
    assert "Section 2 &amp; More" in cell_values[1][0].text
    assert cell_values[1][0].style.leftIndent == 0
    assert result[3]._cellStyles[1][0].leftPadding == 20

    assert isinstance(result[4], PageBreak)


def test_toc_empty_if_no_headings(default_registry) -> None:
    """Verify that if there are no headings, no TOC page is prepended even if toc=True."""
    cfg = Config(input_file="", output_file="", offline=True, toc=True)
    doc = MagicMock()
    doc._md2pdf_config = cfg

    style = ParagraphStyle("test_style", fontName="Helvetica", fontSize=10)
    flowables = [
        Paragraph("Just normal text.", style),
    ]

    pp = TableOfContentsPostProcessor()
    result = pp.process(doc, flowables)

    assert result == flowables


def test_toc_pipeline_integration(tmp_path: Path, default_registry) -> None:
    """Verify end-to-end integration: run the pipeline with toc enabled and check PDF is generated."""
    md_content = """# Title 1

Some text.

## Subtitle 2

More text.
"""
    pdf_path = tmp_path / "test_toc.pdf"
    cfg = Config(input_file="", output_file=str(pdf_path), offline=True, toc=True)

    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(md_content)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000


def test_toc_finds_nested_bookmarks(default_registry) -> None:
    """Verify that TableOfContentsPostProcessor finds bookmarks nested inside KeepTogether or BlockQuoteBar."""
    from reportlab.platypus import KeepTogether

    from md2pdf.core.flowables import BlockQuoteBar

    cfg = Config(input_file="", output_file="", offline=True, toc=True)
    doc = MagicMock()
    doc._md2pdf_config = cfg
    doc._md2pdf_styles = {}

    style = ParagraphStyle("test_style", fontName="Helvetica", fontSize=10)

    # 1. Bookmark inside KeepTogether
    kt_bookmark = BookmarkFlowable("kt-title", "Keep Together Title", level=0)
    kt = KeepTogether([kt_bookmark, Paragraph("KT text", style)])

    # 2. Bookmark inside BlockQuoteBar
    bq_bookmark = BookmarkFlowable("bq-title", "Block Quote Title", level=1)
    bq = BlockQuoteBar(bq_bookmark)

    flowables = [kt, bq]

    pp = TableOfContentsPostProcessor()
    result = pp.process(doc, flowables)

    # Prepend should have succeeded and found both bookmarks
    assert len(result) == len(flowables) + 5

    # TOC title
    assert isinstance(result[1], Paragraph)
    assert result[1].text == "Table of Contents"

    assert isinstance(result[2], Spacer)

    assert isinstance(result[3], Table)
    cell_values = result[3]._cellvalues
    assert len(cell_values) == 2

    # Links
    assert "Keep Together Title" in cell_values[0][0].text
    assert "Block Quote Title" in cell_values[1][0].text
    assert cell_values[0][0].style.leftIndent == 0
    assert cell_values[1][0].style.leftIndent == 0

    # Verify cell leftPadding
    assert result[3]._cellStyles[0][0].leftPadding == 0
    assert result[3]._cellStyles[1][0].leftPadding == 20
