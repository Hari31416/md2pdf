"""LatexHandler — renders LaTeX math/block tokens via the Kroki tikz endpoint."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.flowables import ResizableImage
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
    if r"\documentclass" in source:
        return source

    # If the source already contains a block math environment (like align*),
    # do not wrap it in inline math delimiters ($...$) which causes compile errors.
    if r"\begin{" in source:
        math_content = source
    else:
        math_content = f"${source}$"

    return (
        r"\documentclass[preview,varwidth]{standalone}" + "\n"
        r"\usepackage{amsmath}" + "\n"
        r"\begin{document}" + "\n"
        f"{math_content}" + "\n"
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
        client: KrokiClient | None = None,
        cache: AssetCache | None = None,
        offline: bool = False,
    ) -> None:
        import os

        from md2pdf.assets.cache import AssetCache
        from md2pdf.assets.kroki import KrokiClient

        self.client = client or KrokiClient()
        default_cache = os.path.expanduser("~/.cache/pymd2pdf")
        self.cache = cache or AssetCache(default_cache)
        self.offline = offline

    def render(self, token: dict, styles: dict) -> list[Flowable]:  # noqa: ARG002
        source: str = token.get("raw", "")
        wrapped = _wrap_latex(source)

        # Cache key uses the wrapped source so changes to the wrapper also
        # invalidate old cache entries.
        png = self.cache.get(_DIAGRAM_TYPE, wrapped)
        if png is None:
            if self.offline:
                logger.debug("LatexHandler: offline mode (cache miss) — returning placeholder")
                box = PlaceholderBox(_DIAGRAM_TYPE, source)
                box.spaceBefore = 0
                box.spaceAfter = styles.get("spacing_base", 8)
                return [box]
            try:
                png = self.client.render(_DIAGRAM_TYPE, wrapped)
                self.cache.put(_DIAGRAM_TYPE, wrapped, png)
            except Exception as exc:
                logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
                box = PlaceholderBox(_DIAGRAM_TYPE, source)
                box.spaceBefore = 0
                box.spaceAfter = styles.get("spacing_base", 8)
                return [box]

        # Open the image using PIL to read its pixel dimensions and crop margins
        from PIL import Image as PILImage
        from PIL import ImageChops

        try:
            with PILImage.open(BytesIO(png)) as pil_img:
                # Crop white margins
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
            logger.warning("Failed to crop/process LaTeX diagram image: %s", exc)
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

        img = ResizableImage(BytesIO(png), width=display_width, height=display_height)
        img.hAlign = "CENTER"
        img.spaceBefore = 0
        img.spaceAfter = styles.get("spacing_base", 8)
        return [img]
