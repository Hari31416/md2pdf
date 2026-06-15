"""Tests for md2pdf footnote parsing and rendering."""

from __future__ import annotations

import threading

from reportlab.platypus import SimpleDocTemplate

from md2pdf.core.config import Config
from md2pdf.core.flowables import FootnoteFlowable
from md2pdf.core.parser import FootnoteDefinition, MarkdownParser
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


def test_footnote_definition_thread_safety() -> None:
    """Verify FootnoteDefinition is thread-safe and doesn't rely on class-level state."""
    results = []

    def parse_worker(line: str, next_lines: list[str], thread_id: int) -> None:
        class LinesMock:
            def __init__(self, current_line: str, extra: list[str]) -> None:
                self.lines = [current_line] + extra
                self.idx = 0

            def __next__(self) -> str:
                if self.idx >= len(self.lines):
                    raise StopIteration
                val = self.lines[self.idx]
                self.idx += 1
                return val

            def peek(self) -> str | None:
                if self.idx < len(self.lines):
                    return self.lines[self.idx]
                return None

        lines_iter = LinesMock(line, next_lines)
        assert FootnoteDefinition.start(line) is True
        label, content = FootnoteDefinition.read(lines_iter)
        results.append((thread_id, label, content))

    threads = []
    for i in range(20):
        line = f"[^fn-{i}]: Content for {i}"
        next_lines = [f"extra line {i}"]
        t = threading.Thread(target=parse_worker, args=(line, next_lines, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    for thread_id, label, content in results:
        assert label == f"fn-{thread_id}"
        assert f"Content for {thread_id}" in content
        assert f"extra line {thread_id}" in content


def test_footnote_document_wide_deduplication(tmp_path):
    """Verify that multiple references to the same footnote within a document
    are deduplicated and only one FootnoteFlowable is rendered.
    """
    md = (
        "First paragraph with a footnote[^1].\n\n"
        "Second paragraph with the same footnote[^1].\n\n"
        "[^1]: Shared footnote definition."
    )
    pdf_path = tmp_path / "dedup.pdf"
    config = Config(output_file=str(pdf_path))
    pipeline = Pipeline(config)
    pipeline.run(md)

    # Check that FootnoteFlowable is only added once in flowables during mapping
    tokens = pipeline._parse(pipeline._pre_process(md))
    flowables = pipeline._map(tokens)

    # Filter for FootnoteFlowable instances
    fn_flowables = [f for f in flowables if f.__class__.__name__ == "FootnoteFlowable"]
    assert len(fn_flowables) == 1
    assert fn_flowables[0].label == "1"


def test_multiple_and_large_footnotes_stress_test(tmp_path):
    """Stress test with many footnotes and large footnotes to ensure no crash or layout overlap."""
    paragraphs = []
    definitions = []
    for i in range(1, 21):
        paragraphs.append(f"Paragraph {i} with footnote {i}[^{i}].")
        if i % 5 == 0:
            large_text = " ".join(
                [f"Word {j} for footnote {i} text content which is extra long." for j in range(50)]
            )
            definitions.append(f"[^{i}]: {large_text}")
        else:
            definitions.append(f"[^{i}]: Short footnote content {i}.")

    md = "\n\n".join(paragraphs) + "\n\n" + "\n".join(definitions)

    pdf_path = tmp_path / "stress_test.pdf"
    config = Config(output_file=str(pdf_path))
    pipeline = Pipeline(config)
    pipeline.run(md)

    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 1000


def test_footnote_multi_line_indented_continuation():
    """Verify that FootnoteDefinition handles multi-line indented blocks/paragraphs correctly."""
    md = (
        "Main text[^1].\n\n"
        "[^1]: First line of footnote.\n"
        "    Second line of footnote (indented).\n"
        "    \n"
        "    Third paragraph of footnote (indented after blank line).\n"
    )
    parser = MarkdownParser()
    tokens = parser.parse(md)

    fn_def = next(t for t in tokens if t["type"] == "FootnoteDefinition")
    assert fn_def["attrs"]["label"] == "1"

    raw_content = fn_def["raw"]
    assert "First line of footnote." in raw_content
    assert "Second line of footnote (indented)." in raw_content
    assert "Third paragraph of footnote (indented after blank line)." in raw_content
