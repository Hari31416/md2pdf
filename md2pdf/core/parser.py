"""mistletoe-based Markdown parser that produces a normalised token stream.

The parser converts a mistletoe AST into a flat list of token dicts whose
shape is documented in ``tokens.py``.  Each dict has the form::

    {
        "type":     str,          # one of the constants in tokens.py
        "raw":      str,          # raw text content of the node (if any)
        "children": list[dict],   # normalised child tokens (inline or block)
        "attrs":    dict,         # node-specific attributes (level, language, …)
        "_node":    object,       # escape hatch — raw mistletoe AST node
    }

Specialisation rules
--------------------
- ``CodeFence`` nodes with ``language == "mermaid"`` → ``type = "Mermaid"``
- ``CodeFence`` nodes with ``language in ("latex", "math")`` → ``type = "LatexBlock"``
- All other ``CodeFence`` nodes remain ``type = "CodeFence"``
"""

from __future__ import annotations

import logging
import re
from typing import Any

from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer
from mistletoe.block_token import BlockToken
from mistletoe.latex_token import Math
from mistletoe.span_token import SpanToken

logger = logging.getLogger(__name__)


class FootnoteReference(SpanToken):
    pattern = re.compile(r"\[\^([^\]\s]+)\]")
    parse_inner = False
    parse_group = 1


class FootnoteDefinition(BlockToken):
    pattern = re.compile(r"^ {0,3}\[\^([^\]]+)\]:\s*(.*)$")

    def __init__(self, match):
        self.label, self.text = match
        self.content = self.text

    @classmethod
    def start(cls, line):
        cls.match_obj = cls.pattern.match(line)
        return cls.match_obj is not None

    @classmethod
    def read(cls, lines):
        next(lines)
        content = [cls.match_obj.group(2).strip()]
        next_line = lines.peek()
        while (
            next_line is not None
            and next_line.strip() != ""
            and not next_line.lstrip().startswith("[")
        ):
            content.append(next(lines).strip())
            next_line = lines.peek()
        return cls.match_obj.group(1), " ".join(content)


class _MathRegistrationRenderer(BaseRenderer):
    """Dummy renderer used solely as a context manager to register the Math span token.

    Because mistletoe registers span tokens dynamically when entering the renderer
    context, using this context manager enables mistletoe to parse '$math$' and '$$math$$'.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(Math, FootnoteReference, FootnoteDefinition, *args, **kwargs)

    def render_math(self, token: Any) -> str:
        return ""

    def render_footnote_reference(self, token: Any) -> str:
        return ""

    def render_footnote_definition(self, token: Any) -> str:
        return ""


# Languages that specialise a CodeFence into a Mermaid token
_MERMAID_LANGS: frozenset[str] = frozenset({"mermaid"})
# Languages that specialise a CodeFence into a LatexBlock token
_LATEX_LANGS: frozenset[str] = frozenset({"latex", "math"})

# Remap mistletoe class names that differ from our canonical token names.
# mistletoe ≥1.4 renamed BlockQuote → Quote.
_CLASS_NAME_REMAP: dict[str, str] = {
    "Quote": "BlockQuote",
}


# Attributes we extract from mistletoe nodes into the ``attrs`` dict
_ATTRS_TO_EXTRACT: tuple[str, ...] = (
    "level",
    "language",
    "start",
    "loose",
    "target",
    "title",
    "src",
)

# mistletoe often stores ``start`` as an unbound class method on List nodes.
# We only want it when it is an integer (ordered list start number).
_SKIP_NON_INT_START = True


class MarkdownParser:
    """Parse Markdown text into a flat list of normalised token dicts.

    Example::

        parser = MarkdownParser()
        tokens = parser.parse("# Hello\\n\\nSome **bold** text.")
        # tokens == [{"type": "Heading", ...}, {"type": "Paragraph", ...}]
    """

    def parse(self, raw_md: str) -> list[dict]:
        """Parse *raw_md* and return a flat list of normalised token dicts.

        Args:
            raw_md: Raw Markdown string (after pre-processing).

        Returns:
            A list of token dicts, one per top-level block element.
        """
        with _MathRegistrationRenderer():
            doc = Document(raw_md)
            self.footnotes = getattr(doc, "footnotes", {})
            tokens = self._flatten(doc.children)
        logger.debug("MarkdownParser.parse: produced %d top-level tokens", len(tokens))
        return self._group_admonitions(tokens)

    def _group_admonitions(self, tokens: list[dict]) -> list[dict]:
        """Group top-level tokens between admonition open/close HTML tags into Admonition tokens."""
        output = []
        stack = [output]

        start_pattern = re.compile(r'^<div class="admonition\s+([^"]+)"(?:\s+title="([^"]*)")?\s*>')
        end_pattern = re.compile(r"^</div>$")

        for token in tokens:
            is_start = False
            is_end = False
            tag_match = None

            if token.get("type") == "Paragraph" and len(token.get("children", [])) == 1:
                child = token["children"][0]
                if child.get("type") == "RawText":
                    raw_val = (child.get("raw") or "").strip()
                    tag_match = start_pattern.match(raw_val)
                    if tag_match:
                        is_start = True
                    elif end_pattern.match(raw_val):
                        is_end = True

            if is_start:
                admonition_type = tag_match.group(1)
                admonition_title = tag_match.group(2) or ""

                new_token = {
                    "type": "Admonition",
                    "raw": "",
                    "children": [],
                    "attrs": {
                        "type": admonition_type,
                        "title": admonition_title,
                    },
                }
                stack[-1].append(new_token)
                stack.append(new_token["children"])
            elif is_end:
                if len(stack) > 1:
                    stack.pop()
                else:
                    stack[-1].append(token)
            else:
                if token.get("children"):
                    token["children"] = self._group_admonitions(token["children"])
                stack[-1].append(token)

        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _flatten(self, nodes: list | None) -> list[dict]:
        """Convert a list of mistletoe AST nodes into token dicts."""
        if not nodes:
            return []
        return [self._normalize(node) for node in nodes]

    def _normalize(self, node: object) -> dict:
        """Convert a single mistletoe AST node to a canonical token dict."""
        token_type = type(node).__name__
        token_type = _CLASS_NAME_REMAP.get(token_type, token_type)

        # Specialise fenced code blocks by their language tag
        if token_type == "CodeFence":
            lang = (getattr(node, "language", "") or "").strip().lower()
            if lang in _MERMAID_LANGS:
                token_type = "Mermaid"
            elif lang in _LATEX_LANGS:
                token_type = "LatexBlock"

        attrs = self._extract_attrs(node)
        if token_type == "Image" and "src" in attrs and "target" not in attrs:
            attrs["target"] = attrs["src"]

        if token_type == "FootnoteDefinition":
            attrs["label"] = getattr(node, "label", "")

        token = {
            "type": token_type,
            "raw": getattr(node, "content", "") or "",
            "children": self._extract_children(node),
            "attrs": attrs,
            "_node": node,
        }

        # Promote paragraph containing only block math to a LatexBlock
        if token["type"] == "Paragraph":
            non_empty = []
            for c in token.get("children", []):
                if c.get("type") == "RawText" and not (c.get("raw") or "").strip():
                    continue
                non_empty.append(c)
            if len(non_empty) == 1:
                child = non_empty[0]
                if (
                    child.get("type") == "RawText"
                    and (child.get("raw") or "").strip() == '<div class="pagebreak"></div>'
                ):
                    return {
                        "type": "PageBreak",
                        "raw": "",
                        "children": [],
                        "attrs": {},
                        "_node": node,
                    }
            if len(non_empty) == 1 and non_empty[0].get("type") == "Math":
                math_raw = non_empty[0].get("raw") or ""
                if math_raw.startswith("$$") and math_raw.endswith("$$"):
                    return {
                        "type": "LatexBlock",
                        "raw": math_raw,
                        "children": [],
                        "attrs": {},
                        "_node": node,
                    }
        elif (
            token["type"] in ("HTMLBlock", "RawHTML")
            and token.get("raw", "").strip() == '<div class="pagebreak"></div>'
        ):
            return {
                "type": "PageBreak",
                "raw": "",
                "children": [],
                "attrs": {},
                "_node": node,
            }

        return token

    def _extract_children(self, node: object) -> list[dict]:
        """Recursively normalise child nodes."""
        children = getattr(node, "children", None)
        if not children:
            return []
        return [self._normalize(child) for child in children]

    def _extract_attrs(self, node: object) -> dict:
        """Pull well-known attributes from *node* into a plain dict.

        Skips any value that is callable (e.g. mistletoe stores ``start`` as
        a classmethod reference on some node types) or is not a basic scalar.
        """
        attrs: dict = {}
        for attr in _ATTRS_TO_EXTRACT:
            val = getattr(node, attr, None)
            if val is None:
                continue
            # Skip callables — mistletoe sometimes stores methods under
            # attribute names we care about (e.g. List.start is a classmethod).
            if callable(val):
                continue
            attrs[attr] = val
        return attrs
