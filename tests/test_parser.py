"""Tests for md2pdf.core.parser and md2pdf.core.preprocessors (Phase 2)."""

from __future__ import annotations

from md2pdf.core.parser import MarkdownParser
from md2pdf.core.preprocessors import FrontMatterStripper, IncludeResolver
from md2pdf.core.tokens import (
    BLOCKQUOTE,
    CODE_FENCE,
    HEADING,
    LATEX_BLOCK,
    LIST,
    MERMAID,
    PARAGRAPH,
    TABLE,
    THEMATIC_BREAK,
)

# ---------------------------------------------------------------------------
# MarkdownParser — helpers
# ---------------------------------------------------------------------------


def _types(tokens: list[dict]) -> list[str]:
    """Extract just the 'type' field from a list of token dicts."""
    return [t["type"] for t in tokens]


# ---------------------------------------------------------------------------
# MarkdownParser — basic token types
# ---------------------------------------------------------------------------


class TestMarkdownParserTokenTypes:
    def test_heading(self):
        tokens = MarkdownParser().parse("# Hello World\n")
        assert HEADING in _types(tokens)

    def test_heading_level(self):
        tokens = MarkdownParser().parse("## H2\n")
        heading = next(t for t in tokens if t["type"] == HEADING)
        assert heading["attrs"]["level"] == 2

    def test_setext_heading(self):
        tokens = MarkdownParser().parse("Hello World\n===\n")
        assert HEADING in _types(tokens)
        heading = next(t for t in tokens if t["type"] == HEADING)
        assert heading["attrs"]["level"] == 1

    def test_setext_heading_level2(self):
        tokens = MarkdownParser().parse("Hello H2\n---\n")
        assert HEADING in _types(tokens)
        heading = next(t for t in tokens if t["type"] == HEADING)
        assert heading["attrs"]["level"] == 2

    def test_paragraph(self):
        tokens = MarkdownParser().parse("Just some text.\n")
        assert PARAGRAPH in _types(tokens)

    def test_unordered_list(self):
        md = "- item one\n- item two\n"
        tokens = MarkdownParser().parse(md)
        assert LIST in _types(tokens)

    def test_ordered_list(self):
        md = "1. first\n2. second\n"
        tokens = MarkdownParser().parse(md)
        assert LIST in _types(tokens)
        lst = next(t for t in tokens if t["type"] == LIST)
        # ordered lists have a 'start' attribute
        assert lst["attrs"].get("start") is not None

    def test_blockquote(self):
        tokens = MarkdownParser().parse("> A quoted line.\n")
        assert BLOCKQUOTE in _types(tokens)

    def test_thematic_break(self):
        tokens = MarkdownParser().parse("---\n")
        assert THEMATIC_BREAK in _types(tokens)

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
        tokens = MarkdownParser().parse(md)
        assert TABLE in _types(tokens)

    def test_code_fence_generic(self):
        md = "```python\nprint('hello')\n```\n"
        tokens = MarkdownParser().parse(md)
        assert CODE_FENCE in _types(tokens)

    def test_code_fence_mermaid(self):
        md = "```mermaid\ngraph LR\n  A --> B\n```\n"
        tokens = MarkdownParser().parse(md)
        assert MERMAID in _types(tokens), f"Got types: {_types(tokens)}"

    def test_code_fence_latex(self):
        md = "```latex\nE = mc^2\n```\n"
        tokens = MarkdownParser().parse(md)
        assert LATEX_BLOCK in _types(tokens), f"Got types: {_types(tokens)}"

    def test_code_fence_math(self):
        md = "```math\nx^2 + y^2 = z^2\n```\n"
        tokens = MarkdownParser().parse(md)
        assert LATEX_BLOCK in _types(tokens), f"Got types: {_types(tokens)}"


class TestMarkdownParserTokenStructure:
    """Verify the shape of returned token dicts."""

    def test_token_has_required_keys(self):
        tokens = MarkdownParser().parse("Hello\n")
        for tok in tokens:
            assert "type" in tok
            assert "raw" in tok
            assert "children" in tok
            assert "attrs" in tok
            assert "_node" in tok

    def test_heading_children_contain_inline(self):
        tokens = MarkdownParser().parse("# My **Bold** Heading\n")
        heading = next(t for t in tokens if t["type"] == HEADING)
        child_types = [c["type"] for c in heading["children"]]
        assert any(ct in child_types for ct in ("Strong", "RawText")), child_types

    def test_paragraph_children(self):
        tokens = MarkdownParser().parse("Plain text.\n")
        para = next(t for t in tokens if t["type"] == PARAGRAPH)
        assert isinstance(para["children"], list)

    def test_code_fence_raw_content(self):
        md = "```python\nprint('hello')\n```\n"
        tokens = MarkdownParser().parse(md)
        fence = next(t for t in tokens if t["type"] == CODE_FENCE)
        assert "print" in fence["raw"]

    def test_multi_block_document(self):
        md = "# Title\n\nParagraph text.\n\n- item\n"
        tokens = MarkdownParser().parse(md)
        types = _types(tokens)
        assert HEADING in types
        assert PARAGRAPH in types
        assert LIST in types


# ---------------------------------------------------------------------------
# FrontMatterStripper
# ---------------------------------------------------------------------------


class TestFrontMatterStripper:
    def _strip(self, text: str) -> str:
        return FrontMatterStripper().process(text)

    def test_strips_yaml_front_matter(self):
        md = "---\ntitle: Doc\nauthor: Test\n---\n# Body\n"
        result = self._strip(md)
        assert "title" not in result
        assert "# Body" in result

    def test_leaves_body_intact(self):
        md = "---\nkey: val\n---\nSome paragraph.\n"
        result = self._strip(md)
        assert "Some paragraph." in result

    def test_no_front_matter_unchanged(self):
        md = "# Just a heading\n\nSome text.\n"
        result = self._strip(md)
        assert result == md

    def test_front_matter_only(self):
        md = "---\nkey: val\n---\n"
        result = self._strip(md)
        assert result.strip() == ""

    def test_strips_only_once(self):
        """Should not strip a second --- block in the body."""
        md = "---\nkey: val\n---\nBody text.\n---\nnot-fm: true\n---\n"
        result = self._strip(md)
        assert "not-fm" in result

    def test_multiline_front_matter(self):
        md = "---\na: 1\nb: 2\nc: 3\n---\nContent.\n"
        result = self._strip(md)
        assert "Content." in result
        assert "a: 1" not in result

    def test_default_metadata(self):
        stripper = FrontMatterStripper()
        assert stripper.metadata["author"] == "pymd2pdf"
        assert stripper.metadata["title"] == ""
        assert stripper.metadata["subject"] == ""
        assert stripper.metadata["keywords"] == ""

    def test_default_metadata_with_input_file(self):
        stripper = FrontMatterStripper(input_file="docs/showcase.md")
        assert stripper.metadata["title"] == "showcase"
        assert stripper.metadata["author"] == "pymd2pdf"

    def test_parses_metadata_from_front_matter(self):
        stripper = FrontMatterStripper()
        md = "---\ntitle: Custom Title\nauthor: John Doe\nsubject: Test Subj\nkeywords: one, two\n---\n# Content"
        stripper.process(md)
        assert stripper.metadata["title"] == "Custom Title"
        assert stripper.metadata["author"] == "John Doe"
        assert stripper.metadata["subject"] == "Test Subj"
        assert stripper.metadata["keywords"] == "one, two"

    def test_strips_quotes_from_metadata(self):
        stripper = FrontMatterStripper()
        md = "---\ntitle: \"Double Quotes\"\nauthor: 'Single Quotes'\n---\n# Content"
        stripper.process(md)
        assert stripper.metadata["title"] == "Double Quotes"
        assert stripper.metadata["author"] == "Single Quotes"

    def test_crlf_and_eof(self):
        # Test CRLF
        stripper = FrontMatterStripper()
        raw_crlf = "---\r\ntitle: Test\r\nauthor: John\r\n---\r\n# Hello"
        processed_crlf = stripper.process(raw_crlf)
        assert processed_crlf == "# Hello"
        assert stripper.metadata["title"] == "Test"
        assert stripper.metadata["author"] == "John"

        # Test EOF (no trailing newline)
        stripper_eof = FrontMatterStripper()
        raw_eof = "---\ntitle: EOF Test\n---"
        processed_eof = stripper_eof.process(raw_eof)
        assert processed_eof == ""
        assert stripper_eof.metadata["title"] == "EOF Test"


# ---------------------------------------------------------------------------
# IncludeResolver (placeholder — should be a no-op)
# ---------------------------------------------------------------------------


class TestIncludeResolver:
    def test_returns_input_unchanged_without_main_file(self):
        md = "Some !include path/to/file.md text.\n"
        result = IncludeResolver().process(md)
        assert result == md

    def test_resolves_basic_inclusion(self, tmp_path):
        main_file = tmp_path / "main.md"
        inc_file = tmp_path / "inc.md"

        main_file.write_text("Hello\n!include inc.md\nWorld\n")
        inc_file.write_text("Inside included file")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert result == "Hello\nInside included file\nWorld\n"

    def test_resolves_recursive_inclusion(self, tmp_path):
        main_file = tmp_path / "main.md"
        sub_dir = tmp_path / "sub"
        sub_dir.mkdir()

        inc1 = sub_dir / "inc1.md"
        inc2 = sub_dir / "inc2.md"

        main_file.write_text("Begin\n!include sub/inc1.md\nEnd\n")
        inc1.write_text("Mid1\n!include inc2.md\n")
        inc2.write_text("Mid2")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert "Begin\nMid1\nMid2\nEnd\n" in result

    def test_prevents_circular_inclusion(self, tmp_path):
        main_file = tmp_path / "main.md"
        inc_file = tmp_path / "inc.md"

        main_file.write_text("Hello\n!include inc.md\n")
        inc_file.write_text("Inside\n!include main.md\n")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert (
            "Circular inclusion of" in result or "Circular inclusion of main.md skipped" in result
        )

    def test_handles_missing_file_gracefully(self, tmp_path):
        main_file = tmp_path / "main.md"
        main_file.write_text("Hello\n!include missing.md\n")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert "Included file not found: missing.md" in result

    def test_ignores_include_in_fenced_code_blocks(self, tmp_path):
        main_file = tmp_path / "main.md"
        main_file.write_text("Hello\n```\n!include missing.md\n```\n")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert "!include missing.md" in result
        assert "Included file not found" not in result

    def test_strips_front_matter_from_included_files(self, tmp_path):
        main_file = tmp_path / "main.md"
        inc_file = tmp_path / "inc.md"

        main_file.write_text("Hello\n!include inc.md\n")
        inc_file.write_text("---\ntitle: Subfile\n---\nActual content here")

        resolver = IncludeResolver(str(main_file))
        result = resolver.process(main_file.read_text())
        assert "Actual content here" in result
        assert "Subfile" not in result
        assert "---" not in result


# ---------------------------------------------------------------------------
# Math Parsing Tests
# ---------------------------------------------------------------------------


class TestMarkdownParserMath:
    def test_block_math_promoted_to_latex_block(self):
        md = "$$\nf(x) = x^2\n$$\n"
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == LATEX_BLOCK
        assert "f(x) = x^2" in tokens[0]["raw"]

    def test_inline_math_remains_span(self):
        md = "Hello $x^2$ world.\n"
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == PARAGRAPH
        children = tokens[0]["children"]
        assert len(children) == 3
        assert children[0]["type"] == "RawText"
        assert children[1]["type"] == "Math"
        assert children[1]["raw"] == "$x^2$"
        assert children[2]["type"] == "RawText"


class TestMarkdownParserAdmonitions:
    def test_admonition_fenced_conversion(self):
        from md2pdf.core.preprocessors import AdmonitionPreProcessor

        md = ":::note\nThis is a note.\n:::\n"
        md = AdmonitionPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == "Admonition"
        assert tokens[0]["attrs"]["type"] == "note"
        assert tokens[0]["attrs"]["title"] == ""
        assert tokens[0]["children"][0]["type"] == PARAGRAPH

    def test_admonition_fenced_custom_title(self):
        from md2pdf.core.preprocessors import AdmonitionPreProcessor

        md = ':::warning "Read Carefully"\nBe warned!\n:::\n'
        md = AdmonitionPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == "Admonition"
        assert tokens[0]["attrs"]["type"] == "warning"
        assert tokens[0]["attrs"]["title"] == "Read Carefully"

    def test_github_alerts_conversion(self):
        from md2pdf.core.preprocessors import AdmonitionPreProcessor

        md = "> [!TIP]\n> Use this tip!\n"
        md = AdmonitionPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == "Admonition"
        assert tokens[0]["attrs"]["type"] == "tip"
        assert tokens[0]["attrs"]["title"] == ""

    def test_github_alerts_same_line_text(self):
        from md2pdf.core.preprocessors import AdmonitionPreProcessor

        md = "> [!IMPORTANT] Crucial info here\n> More info\n"
        md = AdmonitionPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == "Admonition"
        assert tokens[0]["attrs"]["type"] == "important"
        assert tokens[0]["children"][0]["type"] == PARAGRAPH

    def test_nested_admonitions(self):
        from md2pdf.core.preprocessors import AdmonitionPreProcessor

        md = ":::note\n:::warning\nNested\n:::\n:::\n"
        md = AdmonitionPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 1
        assert tokens[0]["type"] == "Admonition"
        assert tokens[0]["attrs"]["type"] == "note"
        assert len(tokens[0]["children"]) == 1
        nested = tokens[0]["children"][0]
        assert nested["type"] == "Admonition"
        assert nested["attrs"]["type"] == "warning"


class TestPageBreakParsing:
    def test_comment_pagebreak(self):
        from md2pdf.core.preprocessors import PageBreakPreProcessor

        md = "Some content\n\n<!-- pagebreak -->\n\nMore content"
        md = PageBreakPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 3
        assert tokens[0]["type"] == PARAGRAPH
        assert tokens[1]["type"] == "PageBreak"
        assert tokens[2]["type"] == PARAGRAPH

    def test_backslash_pagebreak(self):
        from md2pdf.core.preprocessors import PageBreakPreProcessor

        md = "Some content\n\n\\pagebreak\n\nMore content"
        md = PageBreakPreProcessor().process(md)
        tokens = MarkdownParser().parse(md)
        assert len(tokens) == 3
        assert tokens[0]["type"] == PARAGRAPH
        assert tokens[1]["type"] == "PageBreak"
        assert tokens[2]["type"] == PARAGRAPH

    def test_case_insensitive_and_whitespace_pagebreak(self):
        from md2pdf.core.preprocessors import PageBreakPreProcessor

        md1 = "  <!--   PageBreak   -->  "
        md1 = PageBreakPreProcessor().process(md1)
        tokens1 = MarkdownParser().parse(md1)
        assert len(tokens1) == 1
        assert tokens1[0]["type"] == "PageBreak"

        md2 = "  \\PageBreak  "
        md2 = PageBreakPreProcessor().process(md2)
        tokens2 = MarkdownParser().parse(md2)
        assert len(tokens2) == 1
        assert tokens2[0]["type"] == "PageBreak"
