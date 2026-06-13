"""Canonical token type constants for the md2pdf pipeline.

Handlers claim one of these strings via their ``token_type`` attribute.
The parser produces dicts whose ``"type"`` key matches one of these constants.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Block-level token types
# ---------------------------------------------------------------------------
HEADING = "Heading"
PARAGRAPH = "Paragraph"
LIST = "List"
LIST_ITEM = "ListItem"
TABLE = "Table"
BLOCKQUOTE = "BlockQuote"
CODE_FENCE = "CodeFence"  # generic fenced code block
MERMAID = "Mermaid"  # code fence with lang="mermaid"
LATEX_BLOCK = "LatexBlock"  # code fence with lang="latex" or lang="math"
THEMATIC_BREAK = "ThematicBreak"
RAW_HTML = "RawHTML"
FOOTNOTE_DEFINITION = "FootnoteDefinition"
ADMONITION = "Admonition"

# ---------------------------------------------------------------------------
# Inline token types  (used inside token["children"])
# ---------------------------------------------------------------------------
IMAGE = "Image"
LINK = "Link"
FOOTNOTE_REFERENCE = "FootnoteReference"


# ---------------------------------------------------------------------------
# All recognised block-level types — used by tests / validators
# ---------------------------------------------------------------------------
ALL_BLOCK_TYPES: tuple[str, ...] = (
    HEADING,
    PARAGRAPH,
    LIST,
    LIST_ITEM,
    TABLE,
    BLOCKQUOTE,
    CODE_FENCE,
    MERMAID,
    LATEX_BLOCK,
    THEMATIC_BREAK,
    RAW_HTML,
    FOOTNOTE_DEFINITION,
    ADMONITION,
)
