from __future__ import annotations

from md2pdf.core.parser import MarkdownParser
from md2pdf.handlers.inline import inline_render
from md2pdf.styles.default import build_default_stylesheet
from md2pdf.styles.theme import ThemeConfig


def test_strikethrough_parsing():
    parser = MarkdownParser()
    tokens = parser.parse("This is ~~strikethrough~~ text.")
    assert len(tokens) == 1
    assert tokens[0]["type"] == "Paragraph"
    children = tokens[0]["children"]
    assert len(children) == 3
    assert children[0]["type"] == "RawText"
    assert children[0]["raw"] == "This is "
    assert children[1]["type"] == "Strikethrough"
    assert children[1]["children"][0]["type"] == "RawText"
    assert children[1]["children"][0]["raw"] == "strikethrough"
    assert children[2]["type"] == "RawText"
    assert children[2]["raw"] == " text."


def test_highlight_parsing():
    parser = MarkdownParser()
    tokens = parser.parse("This is ==highlighted== text.")
    assert len(tokens) == 1
    assert tokens[0]["type"] == "Paragraph"
    children = tokens[0]["children"]
    assert len(children) == 3
    assert children[0]["type"] == "RawText"
    assert children[0]["raw"] == "This is "
    assert children[1]["type"] == "Highlight"
    assert children[1]["children"][0]["type"] == "RawText"
    assert children[1]["children"][0]["raw"] == "highlighted"
    assert children[2]["type"] == "RawText"
    assert children[2]["raw"] == " text."


def test_nested_parsing():
    parser = MarkdownParser()
    tokens = parser.parse("This is ~~**bold strikethrough**~~ text.")
    assert len(tokens) == 1
    children = tokens[0]["children"]
    strike = children[1]
    assert strike["type"] == "Strikethrough"
    assert strike["children"][0]["type"] == "Strong"
    assert strike["children"][0]["children"][0]["raw"] == "bold strikethrough"


def test_strikethrough_rendering():
    parser = MarkdownParser()
    tokens = parser.parse("~~strike~~")
    strike_token = tokens[0]["children"][0]
    styles = build_default_stylesheet()
    rendered = inline_render([strike_token], styles)
    assert rendered == "<strike>strike</strike>"


def test_highlight_rendering_default():
    parser = MarkdownParser()
    tokens = parser.parse("==highlight==")
    hl_token = tokens[0]["children"][0]
    styles = build_default_stylesheet()
    rendered = inline_render([hl_token], styles)
    assert rendered == '<span backcolor="#ffff00">highlight</span>'


def test_highlight_rendering_custom_color():
    parser = MarkdownParser()
    tokens = parser.parse("==highlight==")
    hl_token = tokens[0]["children"][0]
    theme = ThemeConfig(color_highlight="#ff00ff")
    styles = build_default_stylesheet(theme)
    rendered = inline_render([hl_token], styles)
    assert rendered == '<span backcolor="#ff00ff">highlight</span>'
