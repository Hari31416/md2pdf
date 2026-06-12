"""LatexHandler — renders LaTeX math/block tokens via the Kroki tikz endpoint."""

from __future__ import annotations

import logging
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

_DIAGRAM_TYPE = "tikz"
_DEFAULT_WIDTH = 400


def clean_latex_source(source: str) -> str:
    """Strip math delimiters ($ or $$) from start/end of the source string."""
    source = source.strip()
    if source.startswith("$$") and source.endswith("$$"):
        return source[2:-2].strip()
    if source.startswith("$") and source.endswith("$"):
        return source[1:-1].strip()
    return source


def get_latex_image(
    source: str,
    config: Any | None = None,
    client: KrokiClient | None = None,
    cache: AssetCache | None = None,
    offline: bool | None = None,
) -> tuple[str | None, float, float]:
    """Render a LaTeX formula using Kroki tikz, crop it, cache it, and return metadata.

    Args:
        source: LaTeX formula string (can contain $ or $$ delimiters).
        config: Optional Config instance.
        client: Optional KrokiClient instance.
        cache: Optional AssetCache instance.
        offline: Optional boolean to override offline setting.

    Returns:
        A tuple of (cached_image_path, display_width, display_height).
        If offline and not in cache, or if rendering fails, returns (None, 0.0, 0.0).
    """
    import os

    from PIL import Image as PILImage
    from PIL import ImageChops

    from md2pdf.assets.cache import AssetCache
    from md2pdf.assets.kroki import KrokiClient

    formula = clean_latex_source(source)
    wrapped = _wrap_latex(formula)

    if offline is None:
        offline = config.offline if config else False

    if cache is None:
        cache_dir = config.cache_dir if config else os.path.expanduser("~/.cache/pymd2pdf")
        cache = AssetCache(cache_dir)

    if client is None:
        client = KrokiClient()

    # The cache path
    path = cache._path(_DIAGRAM_TYPE, wrapped)

    if path.exists():
        try:
            with PILImage.open(path) as pil_img:
                width_px, height_px = pil_img.size
            display_width = width_px * 0.75
            display_height = height_px * 0.75
            return str(path), display_width, display_height
        except Exception:
            # Re-render if cached image is corrupted
            pass

    if offline:
        logger.debug("get_latex_image: offline mode (cache miss) — returning None")
        return None, 0.0, 0.0

    try:
        png = client.render(_DIAGRAM_TYPE, wrapped)
    except Exception as exc:
        logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
        return None, 0.0, 0.0

    try:
        with PILImage.open(BytesIO(png)) as pil_img:
            gray = pil_img.convert("L")
            inverted = ImageChops.invert(gray)
            bbox = inverted.getbbox()
            if bbox:
                pil_img = pil_img.crop(bbox)
            pil_img.save(path, format="PNG")
            width_px, height_px = pil_img.size
    except Exception as exc:
        logger.warning("Failed to crop/process LaTeX image: %s", exc)
        try:
            path.write_bytes(png)
            with PILImage.open(path) as pil_img:
                width_px, height_px = pil_img.size
        except Exception:
            width_px, height_px = _DEFAULT_WIDTH, _DEFAULT_WIDTH

    display_width = width_px * 0.75
    display_height = height_px * 0.75
    return str(path), display_width, display_height


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
        import os

        config = styles.get("_config")
        source: str = token.get("raw", "")

        path, w, h = get_latex_image(
            source, config, client=self.client, cache=self.cache, offline=self.offline
        )
        if path is None or not os.path.exists(path):
            logger.debug("LatexHandler: returning placeholder due to missing image path")
            box = PlaceholderBox(_DIAGRAM_TYPE, source)
            box.spaceBefore = 0
            box.spaceAfter = styles.get("spacing_base", 8)
            return [box]

        # Map 1 pixel to 0.75 points (for 96 DPI equivalent layout rendering)
        # Cap display_width to min(400.0, display_width)
        original_display_width = w
        display_width = min(400.0, original_display_width)
        if original_display_width > 0:
            scale_ratio = display_width / original_display_width
            display_height = h * scale_ratio
        else:
            display_height = h

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
