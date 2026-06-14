"""LatexHandler — renders LaTeX math/block tokens via the Kroki tikz endpoint."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.flowables import ResizableImage
from md2pdf.core.registry import ElementHandler

if TYPE_CHECKING:
    from reportlab.platypus import Flowable

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None

_DIAGRAM_TYPE = "tikz"
_DEFAULT_WIDTH = 400


def clean_latex_source(source: str) -> str:
    """Strip math delimiters ($ or $$) from start/end of the source string,
    and normalize LaTeX shorthand symbols like \\le and \\ge to \\leq and \\geq.
    """
    import re

    source = source.strip()
    if source.startswith("$$") and source.endswith("$$"):
        formula = source[2:-2].strip()
    elif source.startswith("$") and source.endswith("$"):
        formula = source[1:-1].strip()
    else:
        formula = source

    # Normalize LaTeX shorthand commands to full commands for matplotlib support
    formula = re.sub(r"\\le(?![a-zA-Z])", r"\\leq", formula)
    formula = re.sub(r"\\ge(?![a-zA-Z])", r"\\geq", formula)
    formula = re.sub(r"\\LaTeX\b", r"\\text{L}^{\\text{A}}\\text{T}_{\\text{E}}\\text{X}", formula)
    formula = re.sub(r"\\TeX\b", r"\\text{T}_{\\text{E}}\\text{X}", formula)
    return formula


def make_image_transparent(pil_img: Any) -> Any:
    """Make the white background of the image transparent, preserving other colors."""
    from PIL import Image as PILImage
    from PIL import ImageChops

    if np is not None:
        c_arr = np.array(pil_img.convert("RGB"), dtype=float) / 255.0
        min_val = np.min(c_arr, axis=-1)
        a = 1.0 - min_val
        a_expanded = np.expand_dims(a, axis=-1)
        f_arr = np.where(
            a_expanded > 0.001, (c_arr - (1.0 - a_expanded)) / np.maximum(a_expanded, 1e-9), 0.0
        )
        f_arr = np.clip(f_arr, 0.0, 1.0)
        rgba_arr = np.zeros((pil_img.height, pil_img.width, 4), dtype=np.uint8)
        rgba_arr[..., :3] = (f_arr * 255.0).astype(np.uint8)
        rgba_arr[..., 3] = (a * 255.0).astype(np.uint8)
        return PILImage.fromarray(rgba_arr, mode="RGBA")
    else:
        gray = pil_img.convert("L")
        inverted = ImageChops.invert(gray)
        black_img = PILImage.new("RGB", pil_img.size, (0, 0, 0))
        return PILImage.merge("RGBA", (*black_img.split(), inverted))


def get_latex_image(
    source: str,
    config: Any | None = None,
    client: KrokiClient | None = None,
    cache: AssetCache | None = None,
    offline: bool | None = None,
    fontsize: float = 10,
) -> tuple[str | None, float, float, float]:
    """Render a LaTeX formula using matplotlib or Kroki tikz, crop it, cache it, and return metadata.

    Args:
        source: LaTeX formula string (can contain $ or $$ delimiters).
        config: Optional Config instance.
        client: Optional KrokiClient instance.
        cache: Optional AssetCache instance.
        offline: Optional boolean to override offline setting.
        fontsize: Font size for rendering.

    Returns:
        A tuple of (cached_image_path, display_width, display_height, baseline_depth_pt).
        If offline and not in cache, or if rendering fails, returns (None, 0.0, 0.0, 0.0).
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

    # Helper to compute matplotlib metrics if available
    def get_matplotlib_metrics() -> tuple[float, float, float] | None:
        if np is None or r"\documentclass" in formula or r"\begin{" in formula:
            return None
        try:
            import matplotlib

            matplotlib.use("agg")
            from matplotlib.font_manager import FontProperties
            from matplotlib.mathtext import MathTextParser

            dpi = 200
            prop = FontProperties(size=fontsize)
            parser = MathTextParser("agg")
            res = parser.parse(f"${formula}$", dpi=dpi, prop=prop)

            nonzero = np.nonzero(res.image)
            if len(nonzero[0]) > 0:
                ymin, ymax = np.min(nonzero[0]), np.max(nonzero[0])
                xmin, xmax = np.min(nonzero[1]), np.max(nonzero[1])
                left, top, right, bottom = xmin, ymin, xmax + 1, ymax + 1
            else:
                left, top, right, bottom = 0, 0, res.image.shape[1], res.image.shape[0]

            new_depth_px = bottom - (res.image.shape[0] - res.depth)
            depth_pt = (new_depth_px / dpi) * 72.0
            w_pt = ((right - left) / dpi) * 72.0
            h_pt = ((bottom - top) / dpi) * 72.0
            return w_pt, h_pt, depth_pt
        except (ImportError, Exception):
            return None

    if path.exists():
        try:
            with PILImage.open(path) as img:
                is_opaque = False
                if img.mode != "RGBA":
                    is_opaque = True
                else:
                    alpha = img.split()[-1]
                    if alpha.getextrema() == (255, 255):
                        is_opaque = True

                if is_opaque:
                    logger.debug("Converting opaque cached image to transparent: %s", path)
                    transparent_img = make_image_transparent(img)
                    transparent_img.save(path, format="PNG")
        except Exception as exc:
            logger.debug("Failed to check/convert cached image transparency: %s", exc)

        metrics = get_matplotlib_metrics()
        if metrics is not None:
            w_pt, h_pt, depth_pt = metrics
            return str(path), w_pt, h_pt, depth_pt
        try:
            with PILImage.open(path) as pil_img:
                width_px, height_px = pil_img.size
            display_width = width_px * 0.75
            display_height = height_px * 0.75
            return str(path), display_width, display_height, 0.0
        except Exception:
            # Re-render if cached image is corrupted
            pass

    # Try local rendering with matplotlib if installed and formula is simple math
    metrics = get_matplotlib_metrics()
    if metrics is not None:
        try:
            import matplotlib

            matplotlib.use("agg")
            from matplotlib.font_manager import FontProperties
            from matplotlib.mathtext import MathTextParser

            dpi = 200
            prop = FontProperties(size=fontsize)
            parser = MathTextParser("agg")
            res = parser.parse(f"${formula}$", dpi=dpi, prop=prop)

            img_rgba = np.zeros((res.image.shape[0], res.image.shape[1], 4), dtype=np.uint8)
            img_rgba[..., 3] = res.image
            pil_img = PILImage.fromarray(img_rgba, mode="RGBA")

            nonzero = np.nonzero(res.image)
            if len(nonzero[0]) > 0:
                ymin, ymax = np.min(nonzero[0]), np.max(nonzero[0])
                xmin, xmax = np.min(nonzero[1]), np.max(nonzero[1])
                left, top, right, bottom = xmin, ymin, xmax + 1, ymax + 1
                pil_img = pil_img.crop((left, top, right, bottom))

            # Save the cropped/reshaped image to cache
            pil_img.save(path, format="PNG")

            w_pt, h_pt, depth_pt = metrics
            logger.debug("Rendered LaTeX locally using matplotlib: %s", formula)
            return str(path), w_pt, h_pt, depth_pt
        except Exception as exc:
            logger.debug("Matplotlib rendering failed/unavailable: %s", exc)

    if offline:
        logger.debug("get_latex_image: offline mode (cache miss) — returning None")
        return None, 0.0, 0.0, 0.0

    try:
        attempts = 2
        for attempt in range(attempts):
            try:
                png = client.render(_DIAGRAM_TYPE, wrapped)
                break
            except Exception as e:
                if attempt == attempts - 1:
                    raise
                logger.warning("Kroki render attempt %d failed: %s. Retrying...", attempt + 1, e)
                import time

                time.sleep(1)
    except Exception as exc:
        logger.warning("Kroki render failed (%s): %s", _DIAGRAM_TYPE, exc)
        return None, 0.0, 0.0, 0.0

    try:
        with PILImage.open(BytesIO(png)) as pil_img:
            gray = pil_img.convert("L")
            inverted = ImageChops.invert(gray)
            bbox = inverted.getbbox()
            if bbox:
                pil_img = pil_img.crop(bbox)
            pil_img = make_image_transparent(pil_img)
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
    return str(path), display_width, display_height, 0.0


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

    # Determine if it's a self-contained math block environment
    _SELF_CONTAINED_ENVS = ("align", "gather", "multline", "equation", "eqnarray", "alignat")
    stripped = source.strip()
    is_self_contained = any(stripped.startswith(f"\\begin{{{env}") for env in _SELF_CONTAINED_ENVS)

    if is_self_contained:
        math_content = source
    elif r"\begin{" in source:
        # Contains nested environments (like cases or matrix) but is not a self-contained top-level math env
        math_content = f"\\begin{{equation*}}\n{source}\n\\end{{equation*}}"
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

        path, w, h, _ = get_latex_image(
            source, config, client=self.client, cache=self.cache, offline=self.offline
        )
        if path is None or not os.path.exists(path):
            logger.debug("LatexHandler: falling back to raw LaTeX block due to missing image path")
            from reportlab.platypus import Preformatted

            from md2pdf.handlers.inline import escape_xml

            style = styles.get("code_block") or styles.get("code_inline")
            block = Preformatted(escape_xml(source), style)
            block.spaceBefore = 0
            block.spaceAfter = styles.get("spacing_base", 8)
            return [block]

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
