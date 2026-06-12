"""CodeFenceHandler — renders Markdown code blocks using ReportLab Preformatted flowables."""

from __future__ import annotations

from reportlab.platypus import Preformatted

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import escape_xml

# Translation map to replace Unicode box drawing characters with ASCII equivalents.
# Standard PDF 14 fonts (like Courier) do not support Unicode box drawing glyphs,
# so we map them to standard ASCII counterparts to avoid fallback boxes (black squares).
_BOX_DRAWING_MAP = {
    # Light box drawing
    "┌": "+", "┐": "+", "└": "+", "┘": "+",
    "├": "+", "┤": "+", "┬": "+", "┴": "+",
    "┼": "+", "─": "-", "│": "|",
    # Heavy box drawing
    "┏": "+", "┓": "+", "┗": "+", "┛": "+",
    "┣": "+", "┫": "+", "┳": "+", "┻": "+",
    "╋": "+", "━": "-", "┃": "|",
    # Double box drawing
    "╔": "+", "╗": "+", "╚": "+", "╝": "+",
    "╠": "+", "╣": "+", "╦": "+", "╩": "+",
    "╬": "+", "═": "-", "║": "|",
}

_TRANS_TABLE = str.maketrans(_BOX_DRAWING_MAP)


def clean_box_drawing(text: str) -> str:
    """Replace Unicode box drawing characters with ASCII equivalents for standard PDF font compatibility."""
    return text.translate(_TRANS_TABLE)


class CodeFenceHandler(ElementHandler):
    """Render ``CodeFence`` block tokens as monospaced, styled code blocks."""

    token_type = "CodeFence"

    def render(self, token: dict, styles: dict) -> list:
        raw = token.get("raw", "")
        # Replace box drawing characters to render cleanly in Courier
        raw = clean_box_drawing(raw)
        
        # XML-escape the code content to prevent ReportLab from parsing code as XML tags
        escaped_code = escape_xml(raw)

        # Retrieve the code block style (falling back to inline code if not present)
        style = styles.get("code_block") or styles.get("code_inline")
        flowable = Preformatted(escaped_code, style)
        return [flowable]
