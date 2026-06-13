"""Tests for Phase 3 built-in element handlers."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from reportlab.platypus import HRFlowable, ListFlowable, Paragraph, Table

from md2pdf.core.flowables import BlockQuoteBar, BookmarkFlowable
from md2pdf.handlers.blockquote import BlockQuoteHandler
from md2pdf.handlers.heading import HeadingHandler
from md2pdf.handlers.inline import escape_xml, inline_render
from md2pdf.handlers.list_ import ListHandler
from md2pdf.handlers.paragraph import ParagraphHandler
from md2pdf.handlers.table import TableHandler
from md2pdf.handlers.thematic_break import ThematicBreakHandler
from md2pdf.styles.default import build_default_stylesheet
from md2pdf.styles.theme import ThemeConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def styles() -> dict:
    """Default stylesheet with no custom theme."""
    return build_default_stylesheet()


@pytest.fixture
def custom_styles() -> dict:
    """Stylesheet built from a custom ThemeConfig."""
    theme = ThemeConfig(color_table_header_bg="#c0392b")
    return build_default_stylesheet(theme)


# ---------------------------------------------------------------------------
# Inline renderer
# ---------------------------------------------------------------------------


class TestInlineRender:
    def test_plain_text(self, styles):
        result = inline_render([{"type": "RawText", "raw": "Hello", "children": [], "attrs": {}}])
        assert result == "Hello"

    def test_xml_escape(self, styles):
        result = inline_render(
            [{"type": "RawText", "raw": "a < b & c > d", "children": [], "attrs": {}}]
        )
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_bold(self, styles):
        children = [{"type": "RawText", "raw": "bold", "children": [], "attrs": {}}]
        result = inline_render([{"type": "Strong", "raw": "", "children": children, "attrs": {}}])
        assert result == "<b>bold</b>"

    def test_italic(self, styles):
        children = [{"type": "RawText", "raw": "em", "children": [], "attrs": {}}]
        result = inline_render([{"type": "Emphasis", "raw": "", "children": children, "attrs": {}}])
        assert result == "<i>em</i>"

    def test_inline_code(self, styles):
        result = inline_render(
            [{"type": "InlineCode", "raw": "x = 1", "children": [], "attrs": {}}]
        )
        assert "Courier" in result
        assert "x = 1" in result

    def test_link(self, styles):
        children = [{"type": "RawText", "raw": "click", "children": [], "attrs": {}}]
        result = inline_render(
            [
                {
                    "type": "Link",
                    "raw": "",
                    "children": children,
                    "attrs": {"target": "https://example.com"},
                }
            ],
            styles,
        )
        assert 'href="https://example.com"' in result
        assert "click" in result

    def test_empty_children(self):
        assert inline_render([]) == ""

    def test_nested_bold_italic(self):
        italic_children = [{"type": "RawText", "raw": "x", "children": [], "attrs": {}}]
        bold_children = [{"type": "Emphasis", "raw": "", "children": italic_children, "attrs": {}}]
        result = inline_render(
            [{"type": "Strong", "raw": "", "children": bold_children, "attrs": {}}]
        )
        assert result == "<b><i>x</i></b>"

    def test_escape_xml_helper(self):
        assert escape_xml("<b>") == "&lt;b&gt;"
        assert escape_xml("AT&T") == "AT&amp;T"

    def test_raw_html_linebreak(self, styles):
        result = inline_render(
            [
                {
                    "type": "RawText",
                    "raw": "Line 1<br>Line 2<br />Line 3<BR/>Line 4",
                    "children": [],
                    "attrs": {},
                }
            ]
        )
        assert result == "Line 1<br/>Line 2<br/>Line 3<br/>Line 4"


# ---------------------------------------------------------------------------
# HeadingHandler
# ---------------------------------------------------------------------------


class TestHeadingHandler:
    def _token(self, level: int, text: str) -> dict:
        return {
            "type": "Heading",
            "raw": text,
            "attrs": {"level": level},
            "children": [{"type": "RawText", "raw": text, "children": [], "attrs": {}}],
            "_node": None,
        }

    def test_returns_paragraph_flowable(self, styles):
        handler = HeadingHandler()
        flowables = handler.render(self._token(1, "Title"), styles)
        assert len(flowables) == 2
        assert isinstance(flowables[0], BookmarkFlowable)
        assert isinstance(flowables[1], Paragraph)

    @pytest.mark.parametrize("level", [1, 2, 3, 4])
    def test_all_heading_levels(self, styles, level):
        handler = HeadingHandler()
        flowables = handler.render(self._token(level, f"H{level}"), styles)
        assert isinstance(flowables[0], BookmarkFlowable)
        assert isinstance(flowables[1], Paragraph)

    def test_h5_falls_back_to_h4(self, styles):
        """Headings beyond H4 should use the h4 style (not raise KeyError)."""
        handler = HeadingHandler()
        flowables = handler.render(self._token(5, "H5"), styles)
        assert isinstance(flowables[0], BookmarkFlowable)
        assert isinstance(flowables[1], Paragraph)

    def test_h6_falls_back_to_h4(self, styles):
        handler = HeadingHandler()
        flowables = handler.render(self._token(6, "H6"), styles)
        assert isinstance(flowables[0], BookmarkFlowable)
        assert isinstance(flowables[1], Paragraph)


# ---------------------------------------------------------------------------
# ParagraphHandler
# ---------------------------------------------------------------------------


class TestParagraphHandler:
    def _token(self, text: str) -> dict:
        return {
            "type": "Paragraph",
            "raw": text,
            "attrs": {},
            "children": [{"type": "RawText", "raw": text, "children": [], "attrs": {}}],
            "_node": None,
        }

    def test_returns_paragraph_flowable(self, styles):
        flowables = ParagraphHandler().render(self._token("Hello"), styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], Paragraph)

    def test_empty_paragraph(self, styles):
        flowables = ParagraphHandler().render(self._token(""), styles)
        assert isinstance(flowables[0], Paragraph)


# ---------------------------------------------------------------------------
# ThematicBreakHandler
# ---------------------------------------------------------------------------


class TestThematicBreakHandler:
    _TOKEN: dict = {"type": "ThematicBreak", "raw": "", "attrs": {}, "children": [], "_node": None}

    def test_returns_hrflowable(self, styles):
        flowables = ThematicBreakHandler().render(self._TOKEN, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], HRFlowable)


# ---------------------------------------------------------------------------
# ListHandler
# ---------------------------------------------------------------------------


def _make_list_token(items: list[str], ordered: bool = False) -> dict:
    """Build a minimal list token dict."""
    item_tokens = []
    for text in items:
        item_tokens.append(
            {
                "type": "ListItem",
                "raw": text,
                "attrs": {},
                "children": [{"type": "RawText", "raw": text, "children": [], "attrs": {}}],
                "_node": None,
            }
        )
    attrs: dict = {"start": 1} if ordered else {}
    return {
        "type": "List",
        "raw": "",
        "attrs": attrs,
        "children": item_tokens,
        "_node": None,
    }


class TestListHandler:
    def test_unordered_list_returns_list_flowable(self, styles):
        token = _make_list_token(["a", "b", "c"])
        flowables = ListHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], ListFlowable)

    def test_ordered_list_returns_list_flowable(self, styles):
        token = _make_list_token(["first", "second"], ordered=True)
        flowables = ListHandler().render(token, styles)
        assert isinstance(flowables[0], ListFlowable)

    def test_nested_list(self, styles):
        """A ListItem containing a nested List should not raise."""
        inner = _make_list_token(["x", "y"])
        outer_item = {
            "type": "ListItem",
            "raw": "",
            "attrs": {},
            "children": [
                {"type": "RawText", "raw": "outer", "children": [], "attrs": {}},
                inner,
            ],
            "_node": None,
        }
        outer_token = {
            "type": "List",
            "raw": "",
            "attrs": {},
            "children": [outer_item],
            "_node": None,
        }
        flowables = ListHandler().render(outer_token, styles)
        assert isinstance(flowables[0], ListFlowable)

    def test_empty_list(self, styles):
        token = _make_list_token([])
        flowables = ListHandler().render(token, styles)
        assert isinstance(flowables[0], ListFlowable)


# ---------------------------------------------------------------------------
# TableHandler
# ---------------------------------------------------------------------------


class TestTableHandler:
    def _build_table_token(self) -> dict:
        """Build a real mistletoe-parsed Table token."""
        from md2pdf.core.parser import MarkdownParser

        md = "| Name | Age |\n|------|-----|\n| Alice | 30 |\n| Bob   | 25 |\n"
        tokens = MarkdownParser().parse(md)
        return next(t for t in tokens if t["type"] == "Table")

    def test_returns_table_flowable(self, styles):
        token = self._build_table_token()
        flowables = TableHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], Table)

    def test_table_has_repeat_rows(self, styles):
        """The Table flowable must have repeatRows=1 for header repetition."""
        token = self._build_table_token()
        tbl = TableHandler().render(token, styles)[0]
        assert tbl.repeatRows == 1

    def test_no_node_returns_empty(self, styles):
        token = {"type": "Table", "raw": "", "attrs": {}, "children": [], "_node": None}
        flowables = TableHandler().render(token, styles)
        assert flowables == []


# ---------------------------------------------------------------------------
# BlockQuoteHandler
# ---------------------------------------------------------------------------


def _bq_token(text: str) -> dict:
    return {
        "type": "BlockQuote",
        "raw": "",
        "attrs": {},
        "children": [
            {
                "type": "Paragraph",
                "raw": text,
                "attrs": {},
                "children": [{"type": "RawText", "raw": text, "children": [], "attrs": {}}],
                "_node": None,
            }
        ],
        "_node": None,
    }


class TestBlockQuoteHandler:
    def test_returns_flowables(self, styles):
        flowables = BlockQuoteHandler().render(_bq_token("A quote."), styles)
        assert len(flowables) >= 1
        assert isinstance(flowables[0], BlockQuoteBar)

    def test_contains_paragraph(self, styles):
        flowables = BlockQuoteHandler().render(_bq_token("Quote text"), styles)
        assert any(
            isinstance(f, BlockQuoteBar) and isinstance(f.inner, Paragraph) for f in flowables
        )

    def test_empty_blockquote(self, styles):
        token = {"type": "BlockQuote", "raw": "", "attrs": {}, "children": [], "_node": None}
        flowables = BlockQuoteHandler().render(token, styles)
        assert flowables == []


# ---------------------------------------------------------------------------
# CodeFenceHandler
# ---------------------------------------------------------------------------


class TestCodeFenceHandler:
    def test_returns_preformatted_flowable(self, styles):
        from reportlab.platypus import XPreformatted

        from md2pdf.handlers.code import CodeFenceHandler

        token = {
            "type": "CodeFence",
            "raw": "print('hello')",
            "attrs": {"language": "python"},
            "children": [],
            "_node": None,
        }
        flowables = CodeFenceHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], XPreformatted)
        assert flowables[0].style.name == "code_block"
        assert '<font color="#008000">print</font>' in flowables[0].text

    def test_no_language_fallback(self, styles):
        from reportlab.platypus import XPreformatted

        from md2pdf.handlers.code import CodeFenceHandler

        token = {
            "type": "CodeFence",
            "raw": "some raw text",
            "attrs": {},
            "children": [],
            "_node": None,
        }
        flowables = CodeFenceHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], XPreformatted)
        assert flowables[0].text == "some raw text"


# ---------------------------------------------------------------------------
# Spacing Properties
# ---------------------------------------------------------------------------


class TestSpacingProperties:
    def test_list_spacing(self, styles):
        token = _make_list_token(["a"])
        flowables = ListHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], ListFlowable)
        assert flowables[0].spaceBefore == 0
        assert flowables[0].spaceAfter == 8

        # Nested list
        nested_flowables = ListHandler().render(token, styles, _depth=1)
        assert len(nested_flowables) == 1
        assert isinstance(nested_flowables[0], ListFlowable)
        assert nested_flowables[0].spaceBefore == 0
        assert nested_flowables[0].spaceAfter == 0

    def test_table_spacing(self, styles):
        from md2pdf.core.parser import MarkdownParser

        md = "| Name |\n|------|\n| Alice |\n"
        tokens = MarkdownParser().parse(md)
        table_token = next(t for t in tokens if t["type"] == "Table")
        flowables = TableHandler().render(table_token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], Table)
        assert flowables[0].spaceBefore == 0
        assert flowables[0].spaceAfter == 8

    def test_thematic_break_spacing(self, styles):
        token = {"type": "ThematicBreak", "raw": "", "attrs": {}, "children": [], "_node": None}
        flowables = ThematicBreakHandler().render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], HRFlowable)
        assert flowables[0].spaceBefore == 8
        assert flowables[0].spaceAfter == 8

    def test_resizable_image_spacing(self):
        from io import BytesIO

        from md2pdf.core.flowables import ResizableImage

        # Create a tiny 1x1 GIF in memory for Image loading compatibility
        gif_data = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x01\x04\x00;"
        img = ResizableImage(BytesIO(gif_data), width=10, height=10)
        assert img.spaceBefore == 0
        assert img.spaceAfter == 8

    def test_placeholder_box_spacing(self):
        from md2pdf.assets.fallback import PlaceholderBox

        box = PlaceholderBox("mermaid", "graph TD")
        assert box.spaceBefore == 0
        assert box.spaceAfter == 8


class TestInlineMathRender:
    @patch("md2pdf.handlers.latex.get_latex_image")
    def test_math_inline_render_success(self, mock_get, styles):
        mock_get.return_value = ("/path/to/img.png", 20.0, 10.0)
        tokens = [{"type": "Math", "raw": "$x^2$", "children": [], "attrs": {}}]
        result = inline_render(tokens, styles)
        assert '<img src="/path/to/img.png" width="20.0" height="10.0" valign="middle"/>' in result

    @patch("md2pdf.handlers.latex.get_latex_image")
    def test_math_inline_render_fallback(self, mock_get, styles):
        mock_get.return_value = (None, 0.0, 0.0)
        tokens = [{"type": "Math", "raw": "$x^2$", "children": [], "attrs": {}}]
        result = inline_render(tokens, styles)
        assert result == "$x^2$"


class TestAdmonitionHandler:
    def test_admonition_handler_renders_box(self, styles):
        from md2pdf.core.flowables import AdmonitionBox
        from md2pdf.core.registry import HandlerRegistry
        from md2pdf.handlers.admonition import AdmonitionHandler

        # Setup handler registry mock in styles
        reg = HandlerRegistry()
        reg.register(ParagraphHandler())
        styles["_registry"] = reg

        token = {
            "type": "Admonition",
            "raw": "",
            "attrs": {"type": "note", "title": "My Note"},
            "children": [
                {
                    "type": "Paragraph",
                    "raw": "Hello",
                    "attrs": {},
                    "children": [{"type": "RawText", "raw": "Hello", "children": [], "attrs": {}}],
                    "_node": None,
                }
            ],
            "_node": None,
        }

        handler = AdmonitionHandler()
        flowables = handler.render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], AdmonitionBox)
        box = flowables[0]
        assert box.title_flowable is not None
        assert isinstance(box.title_flowable, Paragraph)
        assert "My Note" in box.title_flowable.text
        assert len(box.content) == 1
        assert isinstance(box.content[0], Paragraph)
        assert "Hello" in box.content[0].text


class TestPageBreakHandler:
    def test_renders_page_break(self, styles):
        from reportlab.platypus import PageBreak

        from md2pdf.handlers.pagebreak import PageBreakHandler

        token = {"type": "PageBreak", "raw": "", "attrs": {}, "children": [], "_node": None}
        handler = PageBreakHandler()
        flowables = handler.render(token, styles)
        assert len(flowables) == 1
        assert isinstance(flowables[0], PageBreak)
