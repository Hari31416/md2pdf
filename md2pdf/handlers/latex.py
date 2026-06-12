"""LatexHandler — renders LaTeX math/block tokens via the Kroki tikz endpoint."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

from reportlab.platypus import Image

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.registry import ElementHandler

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

logger = logging.getLogger(__name__)

_DIAGRAM_TYPE = "tikz"
_DEFAULT_WIDTH = 400


def _wrap_latex(source: str) -> str:
    """Wrap raw LaTeX math source in a standalone document skeleton.

    Kroki's ``tikz`` endpoint expects a complete LaTeX document.  This
    helper injects the minimal preamble so bare math expressions render
    correctly.

    Args:
        source: Raw LaTeX math expression (without ``$`` delimiters or
            document skeleton).

    Returns:
        A complete, self-contained LaTeX document string.
    """
    return (
        r"\documentclass{standalone}"
        r"\usepackage{amsmath}"
        r"\begin{document}"
        f"${source}$"
        r"\end{document}"
    )


class LatexHandler(ElementHandler):
    """Render ``LatexBlock`` token blocks as PNG images via Kroki (tikz).

    Source is wrapped with a minimal ``standalone`` document skeleton before
    being sent to Kroki.  Caching and offline/error fallback follow the same
    pattern as :class:`~md2pdf.handlers.mermaid.MermaidHandler`.

    Args:
        client: :class:`~md2pdf.assets.kroki.KrokiClient` instance.
        cache: :class:`~md2pdf.assets.cache.AssetCache` instance.
        offline: If ``True``, skip all network calls and immediately return a
            placeholder.
    """

    token_type = "LatexBlock"

    def __init__(
        self,
        client: KrokiClient,
        cache: AssetCache,
        offline: bool = False,
    ) -> None:
        self.client = client
        self.cache = cache
        self.offline = offline

    def render(self, token: dict, styles: dict) -> list[Flowable]:  # noqa: ARG002
        source: str = token.get("raw", "")
        wrapped = _wrap_latex(source)

        if self.offline:
            logger.debug("LatexHandler: offline mode — returning placeholder")
            return [PlaceholderBox(_DIAGRAM_TYPE, source)]

        # Cache key uses the wrapped source so changes to the wrapper also
        # invalidate old cache entries.
        png = self.cache.get(_DIAGRAM_TYPE, wrapped)
        if png is None:
            try:
                png = self.client.render(_DIAGRAM_TYPE, wrapped)
                self.cache.put(_DIAGRAM_TYPE, wrapped, png)
            except Exception as exc:
                logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
                return [PlaceholderBox(_DIAGRAM_TYPE, source)]

        img = Image(BytesIO(png), width=_DEFAULT_WIDTH, height=None)
        img.hAlign = "CENTER"
        return [img]
