from __future__ import annotations

import logging

from md2pdf.core.parser import MarkdownParser
from md2pdf.core.preprocessors import (
    AdmonitionPreProcessor,
    FrontMatterStripper,
    IncludeResolver,
)


def test_unclosed_admonition_warning(caplog) -> None:
    """Verify that a warning is logged when there is an unclosed admonition block."""
    md = ":::note\nThis block is not closed\n"
    # Preprocess
    md_processed = AdmonitionPreProcessor().process(md)

    with caplog.at_level(logging.WARNING):
        _ = MarkdownParser().parse(md_processed)

    assert any(
        "Unclosed admonition container block(s) detected: note" in r.message for r in caplog.records
    )


def test_admonition_title_escaping() -> None:
    """Verify that special characters in admonition titles are HTML escaped."""
    md = ':::note "My title with <tags> and & and \\"quotes\\""\nContent\n:::\n'
    md_processed = AdmonitionPreProcessor().process(md)

    assert 'title="My title with &lt;tags&gt; and &amp; and \\&quot;quotes\\&quot;"' in md_processed


def test_front_matter_debug_logging(caplog) -> None:
    """Verify that a debug message is logged when YAML front matter lines cannot be parsed."""
    md = "---\ntitle: Document\ninvalid_yaml_line_without_colon\n---\n"

    with caplog.at_level(logging.DEBUG):
        FrontMatterStripper().process(md)

    assert any("YAML line ignored or cannot be parsed" in r.message for r in caplog.records)


def test_include_resolver_recursion_limit(tmp_path, caplog) -> None:
    """Verify that IncludeResolver limits include recursion depth and logs a warning."""
    # Create a deep chain: a.md -> b.md -> c.md
    a_file = tmp_path / "a.md"
    b_file = tmp_path / "b.md"
    c_file = tmp_path / "c.md"

    a_file.write_text("!include b.md\n", encoding="utf-8")
    b_file.write_text("!include c.md\n", encoding="utf-8")
    c_file.write_text("Bottom of include chain\n", encoding="utf-8")

    # Set max_depth to 1 (only a.md can include b.md, b.md's include of c.md should be rejected)
    resolver = IncludeResolver(main_file=str(a_file), max_depth=1)

    with caplog.at_level(logging.WARNING):
        result = resolver.process("!include b.md\n")

    assert any("Maximum include depth" in r.message for r in caplog.records)
    # The output should contain b.md's contents unresolved or resolved up to depth 1
    assert "Bottom of include chain" not in result
    assert "!include c.md" in result


def test_include_resolver_path_restrictions(tmp_path, caplog) -> None:
    """Verify that IncludeResolver restricts includes to files inside the source directory."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    main_file = source_dir / "main.md"
    main_file.write_text("!include ../secret.md\n", encoding="utf-8")

    secret_file = tmp_path / "secret.md"
    secret_file.write_text("Secret content\n", encoding="utf-8")

    resolver = IncludeResolver(main_file=str(main_file))

    with caplog.at_level(logging.WARNING):
        result = resolver.process("!include ../secret.md\n")

    assert any("outside the source directory" in r.message for r in caplog.records)
    assert "Secret content" not in result
    assert "Include path outside source directory" in result


def test_custom_page_callbacks_wired() -> None:
    """Verify that custom page callbacks registered on the document are called."""
    from unittest.mock import MagicMock

    from md2pdf.core.pipeline import PageCallbackState, PageTemplateCallback

    state = PageCallbackState(
        header_template="",
        header_on_first_page=False,
        metadata={},
        bookmarks=[],
        page_registry={},
        is_first_page=True,
    )
    callback = PageTemplateCallback(state)

    canvas = MagicMock()
    doc = MagicMock()
    first_page_called = False
    later_page_called = False

    def on_first_page(c, d):
        nonlocal first_page_called
        first_page_called = True

    def on_later_page(c, d):
        nonlocal later_page_called
        later_page_called = True

    doc._md2pdf_on_first_page = on_first_page
    doc._md2pdf_on_later_pages = on_later_page

    # Call first page template callback
    callback(canvas, doc)
    assert first_page_called
    assert not later_page_called

    # Switch to later page
    state.is_first_page = False
    callback(canvas, doc)
    assert later_page_called


def test_validator_with_custom_registry() -> None:
    """Verify that DocumentValidator recognizes custom tokens from the registry."""
    from md2pdf.core.registry import ElementHandler, HandlerRegistry
    from md2pdf.core.validator import DocumentValidator

    class DummyCustomHandler(ElementHandler):
        token_type = "CustomToken"

        def render(self, token, styles):
            return []

    registry = HandlerRegistry()
    registry.register(DummyCustomHandler())

    validator = DocumentValidator(registry)
    tokens = [{"type": "CustomToken", "_node": None}]
    issues = validator.validate(tokens)
    assert len(issues) == 0


def test_toc_page_number_fallback_when_missing_first_pass() -> None:
    """Verify TOC page numbers default to empty string when first pass layout data is empty."""
    from unittest.mock import MagicMock

    from reportlab.lib.styles import ParagraphStyle

    from md2pdf.core.config import Config
    from md2pdf.core.flowables import BookmarkFlowable
    from md2pdf.core.postprocessors import TableOfContentsPostProcessor

    cfg = Config(input_file="", output_file="", offline=True, toc=True)
    style = ParagraphStyle("test_style", fontName="Helvetica", fontSize=10)
    doc = MagicMock()
    doc._md2pdf_config = cfg
    doc._md2pdf_styles = {
        "color_link": "#00ff00",
        "h1": style,
        "body": style,
    }
    doc._md2pdf_toc_page_numbers = {}

    flowables = [
        BookmarkFlowable("section-1", "Section 1", level=0),
    ]

    pp = TableOfContentsPostProcessor()
    result = pp.process(doc, flowables)

    # Inspect the generated table
    from reportlab.platypus import Table

    table = [f for f in result if isinstance(f, Table)][0]
    cell_values = table._cellvalues
    page_num_cell = cell_values[0][1]
    assert 'href="#section-1"' in page_num_cell.text
    assert '<link href="#section-1" color="#00ff00"></link>' in page_num_cell.text
