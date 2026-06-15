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


def test_theme_color_validation() -> None:
    """Verify ThemeConfig raises TypeError or ValueError on invalid colors."""
    import pytest

    from md2pdf.styles.theme import ThemeConfig

    # Non-string color
    with pytest.raises(TypeError):
        ThemeConfig(color_body_text=123)

    # Invalid hex string
    with pytest.raises(ValueError):
        ThemeConfig(color_body_text="not-a-color")


def test_stylesheet_font_validation() -> None:
    """Verify build_default_stylesheet raises ConfigError on unregistered fonts."""
    import pytest

    from md2pdf.core.errors import ConfigError
    from md2pdf.styles.default import build_default_stylesheet
    from md2pdf.styles.theme import ThemeConfig

    theme = ThemeConfig(font_body="UnregisteredFont")
    with pytest.raises(ConfigError) as exc:
        build_default_stylesheet(theme)
    assert "configured in 'font_body' is not registered" in str(exc.value)


def test_escape_xml_no_double_escaping() -> None:
    """Verify escape_xml does not double-escape already escaped strings."""
    from md2pdf.handlers.inline import escape_xml

    assert escape_xml("A & B") == "A &amp; B"
    assert escape_xml("A &amp; B") == "A &amp; B"
    assert escape_xml("A &lt; B") == "A &lt; B"


def test_inline_code_uses_theme_mono_font() -> None:
    """Verify inline_render uses the font defined in styles['code_inline']."""
    from reportlab.lib.styles import ParagraphStyle

    from md2pdf.handlers.inline import inline_render

    style = ParagraphStyle("code_inline", fontName="Times-Roman")
    styles = {"code_inline": style}
    tokens = [{"type": "InlineCode", "raw": "foo", "children": [], "attrs": {}}]
    result = inline_render(tokens, styles=styles)
    assert "<font name='Times-Roman'>" in result


def test_latex_formula_delimiter_checking() -> None:
    """Verify is_latex_formula checks delimiters correctly."""
    from md2pdf.handlers.code import is_latex_formula

    assert is_latex_formula("$$x^2$$") is True
    assert is_latex_formula("$x^2$") is True
    assert is_latex_formula("$ x^2$") is False
    assert is_latex_formula("$x^2") is False
    assert is_latex_formula("$$x^2") is False
    assert is_latex_formula("$$") is False


def test_table_column_widths_heuristics_and_overrides() -> None:
    """Verify column widths heuristic and overrides logic."""
    from md2pdf.handlers.table import TableHandler

    handler = TableHandler()

    # Heuristic test
    widths = handler._compute_col_widths(
        col_count=3,
        styles=None,
        width_overrides=None,
        clean_header_texts=["A", "B", "C"],
        data_rows_texts=[["very long cell content here", "x", "y"]],
    )
    # The first column has longer content so it should get more width
    assert widths[0] > widths[1]
    assert widths[1] == widths[2]

    # Percentage override
    widths_override = handler._compute_col_widths(
        col_count=2,
        styles=None,
        width_overrides=[("pct", 0.3), None],
        clean_header_texts=["A", "B"],
        data_rows_texts=[["x", "y"]],
    )
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    available = A4[0] - 2 * 20 * mm
    expected_col0 = available * 0.3
    assert abs(widths_override[0] - expected_col0) < 1e-4


def test_nested_image_paths_relative_to_includes(tmp_path) -> None:
    """Verify recursive include tracking resolves nested images correctly."""
    import os

    from md2pdf.core.config import Config
    from md2pdf.core.pipeline import Pipeline

    main_md = tmp_path / "main.md"
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    sub_md = sub_dir / "sub.md"

    # Create a dummy image in sub_dir
    img_path = sub_dir / "test.png"
    from PIL import Image

    Image.new("RGB", (10, 10)).save(img_path)

    # main includes sub.md. sub.md references the image relatively as "test.png"
    main_md.write_text("!include sub/sub.md\n", encoding="utf-8")
    sub_md.write_text("![alt](test.png)\n", encoding="utf-8")

    cfg = Config(input_file=str(main_md), output_file=str(tmp_path / "out.pdf"), offline=True)
    pipeline = Pipeline(cfg)
    pipeline.run(main_md.read_text(encoding="utf-8"))

    # The PDF composer should have successfully found and resolved "sub/test.png" relative to sub.md
    assert os.path.exists(cfg.output_file)
