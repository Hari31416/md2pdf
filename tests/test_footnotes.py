"""Tests for md2pdf footnote parsing and rendering."""

from __future__ import annotations

from reportlab.platypus import SimpleDocTemplate

from md2pdf.core.config import Config
from md2pdf.core.flowables import FootnoteFlowable
from md2pdf.core.parser import MarkdownParser
from md2pdf.core.pipeline import Pipeline
from md2pdf.handlers.inline import inline_render
from md2pdf.styles.default import build_default_stylesheet


def test_footnotes_parsing():
    """Verify that footnote references and definitions are parsed correctly."""
    md = "This is some text[^1] with a footnote.\n\n[^1]: Here is the footnote definition."
    parser = MarkdownParser()
    tokens = parser.parse(md)

    # Footnote definitions should be parsed as block-level tokens.
    fn_def = next(t for t in tokens if t["type"] == "FootnoteDefinition")
    assert fn_def["attrs"]["label"] == "1"
    assert fn_def["raw"] == "Here is the footnote definition."

    # The footnote reference token should exist in the inline elements
    para_token = next(t for t in tokens if t["type"] == "Paragraph")
    ref_token = next(c for c in para_token["children"] if c["type"] == "FootnoteReference")
    assert ref_token["raw"] == "1"


def test_inline_render_footnotes():
    """Verify that inline_render formats the FootnoteReference correctly."""
    styles = build_default_stylesheet()
    children = [
        {"type": "RawText", "raw": "text", "children": [], "attrs": {}},
        {"type": "FootnoteReference", "raw": "123", "children": [], "attrs": {}},
    ]
    result = inline_render(children, styles)
    assert "text" in result
    assert "<sup>" in result
    assert 'href="#fn-123"' in result
    assert "123" in result


def test_footnote_flowable_wrap_and_draw(tmp_path):
    """Verify wrap and draw behavior of FootnoteFlowable."""
    styles = build_default_stylesheet()
    fn = FootnoteFlowable("1", "Hello **world**", styles)

    # Paragraph text should have styling and parsed inline content (strong)
    assert "fn-1" in fn.para_text
    assert "<b>world</b>" in fn.para_text

    # Test wrap
    w, h = fn.wrap(400, 800)
    assert w == 0.0
    assert h == 0.0

    # Clean registries
    FootnoteFlowable.page_registry.clear()
    FootnoteFlowable.page_footnotes.clear()

    # Create a real document and canvas in memory
    from io import BytesIO

    from reportlab.pdfgen.canvas import Canvas

    pdf_path = tmp_path / "test.pdf"
    doc = SimpleDocTemplate(str(pdf_path))
    doc._md2pdf_is_final = False

    buf = BytesIO()
    canvas = Canvas(buf, pagesize=(595.27, 841.89))
    canvas._doctemplate = doc
    fn.canv = canvas

    fn.draw()
    # Registry should have recorded page 1
    assert FootnoteFlowable.page_registry["1"] == 1

    # Simulate Pass 2 setup
    doc._md2pdf_is_final = True
    FootnoteFlowable.page_footnotes[1] = [fn]

    # Mock line & drawOn to verify final pass rendering
    called_line = False
    called_draw_on = False

    def mock_line(x1, y1, x2, y2):
        nonlocal called_line
        called_line = True

    def mock_draw_on(canv, x, y):
        nonlocal called_draw_on
        called_draw_on = True

    canvas.line = mock_line
    fn.paragraph.drawOn = mock_draw_on

    fn.draw()
    assert called_line is True
    assert called_draw_on is True


def test_footnotes_pipeline_integration(tmp_path):
    """Test full document pipeline with footnotes from end to end."""
    md = (
        "# Title\n\n"
        "Some text with a footnote[^abc] and another[^123].\n\n"
        "[^abc]: Description of abc footnote.\n"
        "[^123]: Description of 123 footnote.\n"
    )
    pdf_path = tmp_path / "out.pdf"
    config = Config(output_file=str(pdf_path))
    pipeline = Pipeline(config)
    pipeline.run(md)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000
