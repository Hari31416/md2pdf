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
from typing import Any

from mistletoe import Document
from mistletoe.base_renderer import BaseRenderer
from mistletoe.latex_token import Math

logger = logging.getLogger(__name__)

# Languages that specialise a CodeFence into a Mermaid token
_MERMAID_LANGS: frozenset[str] = frozenset({"mermaid"})
# Languages that specialise a CodeFence into a LatexBlock token
_LATEX_LANGS: frozenset[str] = frozenset({"latex", "math"})

# Remap mistletoe class names that differ from our canonical token names.
# mistletoe ≥1.4 renamed BlockQuote → Quote.
_CLASS_NAME_REMAP: dict[str, str] = {
    "Quote": "BlockQuote",
}


class _MathRegistrationRenderer(BaseRenderer):
    """Dummy renderer used solely as a context manager to register the Math span token.

    Because mistletoe registers span tokens dynamically when entering the renderer
    context, using this context manager enables mistletoe to parse '$math$' and '$$math$$'.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(Math, *args, **kwargs)

    def render_math(self, token: Any) -> str:
        return ""


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
            tokens = self._flatten(doc.children)
        logger.debug("MarkdownParser.parse: produced %d top-level tokens", len(tokens))
        return tokens

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
