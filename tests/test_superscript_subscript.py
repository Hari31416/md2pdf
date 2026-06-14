from __future__ import annotations

from md2pdf.core.parser import MarkdownParser
from md2pdf.handlers.inline import inline_render
from md2pdf.styles.default import build_default_stylesheet


def test_superscript_parsing_and_rendering():
    parser = MarkdownParser()
    tokens = parser.parse("This is x^2^ and y^123^.")
    assert len(tokens) == 1
    assert tokens[0]["type"] == "Paragraph"

    children = tokens[0]["children"]
    # Expected children:
    # 0: RawText ("This is x")
    # 1: Superscript ("2")
    # 2: RawText (" and y")
    # 3: Superscript ("123")
    # 4: RawText (".")
    assert len(children) == 5

    assert children[1]["type"] == "Superscript"
    assert children[1]["children"][0]["type"] == "RawText"
    assert children[1]["children"][0]["raw"] == "2"

    assert children[3]["type"] == "Superscript"
    assert children[3]["children"][0]["type"] == "RawText"
    assert children[3]["children"][0]["raw"] == "123"

    styles = build_default_stylesheet()
    rendered = inline_render(children, styles)
    assert "x<sup>2</sup>" in rendered
    assert "y<sup>123</sup>" in rendered


def test_subscript_parsing_and_rendering():
    parser = MarkdownParser()
    tokens = parser.parse("Formula is H~2~O and carbon~dioxide~.")
    assert len(tokens) == 1
    assert tokens[0]["type"] == "Paragraph"

    children = tokens[0]["children"]
    # Expected children:
    # 0: RawText ("Formula is H")
    # 1: Subscript ("2")
    # 2: RawText ("O and carbon")
    # 3: Subscript ("dioxide")
    # 4: RawText (".")
    assert len(children) == 5

    assert children[1]["type"] == "Subscript"
    assert children[1]["children"][0]["type"] == "RawText"
    assert children[1]["children"][0]["raw"] == "2"

    assert children[3]["type"] == "Subscript"
    assert children[3]["children"][0]["type"] == "RawText"
    assert children[3]["children"][0]["raw"] == "dioxide"

    styles = build_default_stylesheet()
    rendered = inline_render(children, styles)
    assert "H<sub>2</sub>O" in rendered
    assert "carbon<sub>dioxide</sub>" in rendered


def test_invalid_syntax_not_parsed():
    parser = MarkdownParser()
    # No space should be allowed right after opening or before closing symbol
    tokens = parser.parse("No ^ 2^, no ^2 ^, no ~ 2~, no ~2 ~.")
    children = tokens[0]["children"]
    # Should not contain Superscript or Subscript
    types = [c["type"] for c in children]
    assert "Superscript" not in types
    assert "Subscript" not in types
