"""CodeFenceHandler — renders Markdown code blocks using ReportLab Preformatted flowables."""

from __future__ import annotations

from collections.abc import Iterable
from typing import IO, TYPE_CHECKING, Any

from pygments import highlight
from pygments.formatter import Formatter
from pygments.lexers import get_lexer_by_name
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound

from md2pdf.core.flowables import WrappedXPreformatted
from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import escape_xml

if TYPE_CHECKING:
    from reportlab.platypus import Flowable


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


def is_latex_formula(text: str) -> bool:
    """Detect if a block of code contains a LaTeX math formula."""
    text = text.strip()
    if text.startswith("$$"):
        return text.endswith("$$") and len(text) >= 5
    if text.startswith("$") and text.endswith("$") and not text.startswith("$ ") and len(text) >= 3:
        return True
    return False


class CodeFenceHandler(ElementHandler):
    """Render ``CodeFence`` block tokens as monospaced, styled code blocks."""

    token_type: str = "CodeFence"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        raw: str = token.get("raw", "")

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
        flowable = WrappedXPreformatted(highlighted, style)
        return [flowable]


class BlockCodeHandler(ElementHandler):
    """Render ``BlockCode`` block tokens.

    If the content contains a LaTeX formula, it delegates rendering to ``LatexHandler``.
    Otherwise, it delegates rendering to ``CodeFenceHandler``.
    """

    token_type: str = "BlockCode"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        raw: str = token.get("raw", "")
        if is_latex_formula(raw):
            registry = styles.get("_registry")
            latex_handler = registry.get("LatexBlock") if registry else None

            if not latex_handler:
                config = styles.get("_config")
                client = None
                cache = None
                offline = False
                if config:
                    from md2pdf.assets.cache import AssetCache
                    from md2pdf.assets.kroki import KrokiClient

                    offline = getattr(config, "offline", False)
                    cache = AssetCache(config.cache_dir)
                    client = KrokiClient()

                from md2pdf.handlers.latex import LatexHandler

                latex_handler = LatexHandler(client=client, cache=cache, offline=offline)

            latex_token = token.copy()
            latex_token["type"] = "LatexBlock"
            return latex_handler.render(latex_token, styles)
        else:
            code_handler = CodeFenceHandler()
            code_token = token.copy()
            code_token["type"] = "CodeFence"
            return code_handler.render(code_token, styles)
