"""MermaidHandler — renders Mermaid diagram tokens via the Kroki API."""

from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import TYPE_CHECKING, Any

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.flowables import ResizableImage
from md2pdf.core.registry import ElementHandler

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

logger = logging.getLogger(__name__)

_DIAGRAM_TYPE = "mermaid"
_DEFAULT_WIDTH = 400


def get_mermaid_image(
    source: str,
    config: Any | None = None,
    client: KrokiClient | None = None,
    cache: AssetCache | None = None,
    offline: bool | None = None,
) -> str | None:
    """Fetch/render a Mermaid diagram, crop it, cache it on disk, and return the cached path."""
    import os

    from PIL import Image as PILImage
    from PIL import ImageChops

    if offline is None:
        offline = config.offline if config else False

    if cache is None:
        cache_dir = config.cache_dir if config else os.path.expanduser("~/.cache/pymd2pdf")
        cache = AssetCache(cache_dir)

    path = cache.path_for(_DIAGRAM_TYPE, source)

    if path.exists():
        return str(path)

    if offline:
        return None

    if client is None:
        client = KrokiClient()

    attempts = 2
    png = None
    for attempt in range(attempts):
        try:
            png = client.render(_DIAGRAM_TYPE, source)
            break
        except Exception as e:
            if attempt == attempts - 1:
                logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, e)
                return None
            logger.debug("Kroki render attempt %d failed: %s. Retrying...", attempt + 1, e)
            import time

            time.sleep(1)

    if not png:
        return None

    try:
        # Save cropped version to disk cache
        with PILImage.open(BytesIO(png)) as pil_img:
            if pil_img.mode in ("RGBA", "LA") or (
                pil_img.mode == "P" and "transparency" in pil_img.info
            ):
                alpha = pil_img.split()[-1]
                bbox = alpha.getbbox()
            else:
                gray = pil_img.convert("L")
                inverted = ImageChops.invert(gray)
                bbox = inverted.getbbox()

            if bbox:
                pil_img = pil_img.crop(bbox)
            pil_img.save(path, format="PNG")
    except Exception as exc:
        logger.warning("Failed to crop/process Mermaid diagram image: %s", exc)
        try:
            path.write_bytes(png)
        except Exception:
            pass

    return str(path)


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
        self.client = client or KrokiClient()
        default_cache = os.path.expanduser("~/.cache/pymd2pdf")
        self.cache = cache or AssetCache(default_cache)
        self.offline = offline

    def render(self, token: dict, styles: dict) -> list[Flowable]:  # noqa: ARG002
        source: str = token.get("raw", "")
        config = styles.get("_config")

        path = get_mermaid_image(
            source, config, client=self.client, cache=self.cache, offline=self.offline
        )
        if path is None or not os.path.exists(path):
            logger.debug("MermaidHandler: falling back to placeholder due to missing image path")
            box = PlaceholderBox(_DIAGRAM_TYPE, source)
            box.spaceBefore = 0
            box.spaceAfter = styles.get("spacing_base", 8)
            return [box]

        from PIL import Image as PILImage

        try:
            with PILImage.open(path) as pil_img:
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

        img = ResizableImage(path, width=display_width, height=display_height)
        img.hAlign = "CENTER"
        img.spaceBefore = 0
        img.spaceAfter = styles.get("spacing_base", 8)
        return [img]
