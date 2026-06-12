"""CodeFenceHandler — renders Markdown code blocks using ReportLab Preformatted flowables."""

from __future__ import annotations

from collections.abc import Iterable
from typing import IO, TYPE_CHECKING, Any

from pygments import highlight
from pygments.formatter import Formatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound
from reportlab.platypus import XPreformatted

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import escape_xml

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

# Translation map to replace Unicode box drawing characters with ASCII equivalents.
# Standard PDF 14 fonts (like Courier) do not support Unicode box drawing glyphs,
# so we map them to standard ASCII counterparts to avoid fallback boxes (black squares).
_BOX_DRAWING_MAP = {
    # Light box drawing
    "┌": "+",
    "┐": "+",
    "└": "+",
    "┘": "+",
    "├": "+",
    "┤": "+",
    "┬": "+",
    "┴": "+",
    "┼": "+",
    "─": "-",
    "│": "|",
    # Heavy box drawing
    "┏": "+",
    "┓": "+",
    "┗": "+",
    "┛": "+",
    "┣": "+",
    "┫": "+",
    "┳": "+",
    "┻": "+",
    "╋": "+",
    "━": "-",
    "┃": "|",
    # Double box drawing
    "╔": "+",
    "╗": "+",
    "╚": "+",
    "╝": "+",
    "╠": "+",
    "╣": "+",
    "╦": "+",
    "╩": "+",
    "╬": "+",
    "═": "-",
    "║": "|",
}

_TRANS_TABLE = str.maketrans(_BOX_DRAWING_MAP)


def clean_box_drawing(text: str) -> str:
    """Replace Unicode box drawing characters with ASCII equivalents for standard PDF font compatibility."""
    return text.translate(_TRANS_TABLE)


class ReportLabFormatter(Formatter):
    """Pygments Formatter that produces ReportLab XML paragraph markup."""

    pygments_style: Any

    def __init__(self, style_name: str = "default", **options: Any) -> None:
        super().__init__(**options)
        try:
            self.pygments_style = get_style_by_name(style_name)
        except ClassNotFound:
            self.pygments_style = get_style_by_name("default")

    def format(self, tokensource: Iterable[tuple[Any, str]], outfile: IO[str]) -> None:
        for ttype, value in tokensource:
            style = self.pygments_style.style_for_token(ttype)

            # Apply styling parameters: color, bold, italic
            color: str | None = style.get("color")
            bold: bool = style.get("bold", False)
            italic: bool = style.get("italic", False)

            # Escape value first to be safe
            escaped_val: str = escape_xml(value)

            wrapped: str = escaped_val
            if bold:
                wrapped = f"<b>{wrapped}</b>"
            if italic:
                wrapped = f"<i>{wrapped}</i>"
            if color:
                wrapped = f'<font color="#{color}">{wrapped}</font>'

            outfile.write(wrapped)


class CodeFenceHandler(ElementHandler):
    """Render ``CodeFence`` block tokens as monospaced, styled code blocks."""

    token_type: str = "CodeFence"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        raw: str = token.get("raw", "")
        # Replace box drawing characters to render cleanly in Courier
        raw = clean_box_drawing(raw)

        highlighted: str | None = None
        lang: str = token.get("attrs", {}).get("language", "")
        if lang:
            lang = lang.strip().lower()
            try:
                lexer = get_lexer_by_name(lang)
                syntax_style: str = styles.get("syntax_style", "default")
                formatter = ReportLabFormatter(style_name=syntax_style)
                highlighted = highlight(raw, lexer, formatter)
            except Exception:
                # Fallback to plain text formatting if Pygments fails or lexer not found
                pass

        if highlighted is None:
            highlighted = escape_xml(raw)

        # Retrieve the code block style (falling back to inline code if not present)
        style = styles.get("code_block") or styles.get("code_inline")
        flowable = XPreformatted(highlighted, style)
        return [flowable]
