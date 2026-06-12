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

from mistletoe import Document

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

# Attributes we extract from mistletoe nodes into the ``attrs`` dict
_ATTRS_TO_EXTRACT: tuple[str, ...] = ("level", "language", "start", "loose", "target", "title")

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

        return {
            "type": token_type,
            "raw": getattr(node, "content", "") or "",
            "children": self._extract_children(node),
            "attrs": self._extract_attrs(node),
            "_node": node,
        }

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
