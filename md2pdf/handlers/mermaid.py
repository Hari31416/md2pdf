"""MermaidHandler — renders Mermaid diagram tokens via the Kroki API."""

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

_DIAGRAM_TYPE = "mermaid"
_DEFAULT_WIDTH = 400


class MermaidHandler(ElementHandler):
    """Render ``Mermaid`` token blocks as PNG images via Kroki.io.

    On first encounter the source is POSTed to Kroki; the returned PNG is
    cached on disk.  Subsequent renders for the same source are served from
    the cache (zero network calls).

    When *offline* is ``True``, or when the Kroki call fails for any reason,
    a :class:`~md2pdf.assets.fallback.PlaceholderBox` is returned instead so
    the conversion never crashes due to a network issue.

    Args:
        client: :class:`~md2pdf.assets.kroki.KrokiClient` instance.
        cache: :class:`~md2pdf.assets.cache.AssetCache` instance.
        offline: If ``True``, skip all network calls and immediately return a
            placeholder.
    """

    token_type = "Mermaid"

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

        if self.offline:
            logger.debug("MermaidHandler: offline mode — returning placeholder")
            return [PlaceholderBox(_DIAGRAM_TYPE, source)]

        png = self.cache.get(_DIAGRAM_TYPE, source)
        if png is None:
            try:
                png = self.client.render(_DIAGRAM_TYPE, source)
                self.cache.put(_DIAGRAM_TYPE, source, png)
            except Exception as exc:
                logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
                return [PlaceholderBox(_DIAGRAM_TYPE, source)]

        img = Image(BytesIO(png), width=_DEFAULT_WIDTH, height=None)
        img.hAlign = "CENTER"
        return [img]
