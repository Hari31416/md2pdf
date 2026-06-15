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
