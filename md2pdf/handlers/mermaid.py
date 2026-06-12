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
        client: KrokiClient | None = None,
        cache: AssetCache | None = None,
        offline: bool = False,
    ) -> None:
        from md2pdf.assets.cache import AssetCache
        from md2pdf.assets.kroki import KrokiClient

        self.client = client or KrokiClient()
        self.cache = cache or AssetCache(".md2pdf_cache")
        self.offline = offline

    def render(self, token: dict, styles: dict) -> list[Flowable]:  # noqa: ARG002
        source: str = token.get("raw", "")

        png = self.cache.get(_DIAGRAM_TYPE, source)
        if png is None:
            if self.offline:
                logger.debug("MermaidHandler: offline mode (cache miss) — returning placeholder")
                return [PlaceholderBox(_DIAGRAM_TYPE, source)]
            try:
                png = self.client.render(_DIAGRAM_TYPE, source)
                self.cache.put(_DIAGRAM_TYPE, source, png)
            except Exception as exc:
                logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
                return [PlaceholderBox(_DIAGRAM_TYPE, source)]

        # Open the image using PIL to read its pixel dimensions and crop margins
        from PIL import Image as PILImage
        from PIL import ImageChops

        try:
            with PILImage.open(BytesIO(png)) as pil_img:
                # Crop transparent/white margins
                if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
                    alpha = pil_img.split()[-1]
                    bbox = alpha.getbbox()
                else:
                    gray = pil_img.convert("L")
                    inverted = ImageChops.invert(gray)
                    bbox = inverted.getbbox()

                if bbox:
                    pil_img = pil_img.crop(bbox)
                    cropped_io = BytesIO()
                    pil_img.save(cropped_io, format="PNG")
                    png = cropped_io.getvalue()
                width_px, height_px = pil_img.size
        except Exception as exc:
            logger.warning("Failed to crop/process Mermaid diagram image: %s", exc)
            try:
                with PILImage.open(BytesIO(png)) as pil_img:
                    width_px, height_px = pil_img.size
            except Exception:
                width_px, height_px = _DEFAULT_WIDTH, _DEFAULT_WIDTH

        # Map 1 pixel to 0.75 points (for 96 DPI equivalent layout rendering)
        display_width = min(400.0, width_px * 0.75)
        scale_ratio = display_width / (width_px * 0.75)
        display_height = (height_px * 0.75) * scale_ratio

        # Cap height to prevent ReportLab LayoutError from exceeding page height
        max_height = 600.0
        if display_height > max_height:
            height_scale = max_height / display_height
            display_height = max_height
            display_width = display_width * height_scale

        img = Image(BytesIO(png), width=display_width, height=display_height)
        img.hAlign = "CENTER"
        return [img]
