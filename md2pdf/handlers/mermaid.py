"""Render Mermaid diagrams locally with Merman, or fall back to Kroki."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
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
_MERMAN_TIMEOUT = 30


@lru_cache(maxsize=1)
def _merman_cli() -> tuple[str, str] | None:
    """Return the installed Merman executable and version, if available."""
    executable = shutil.which("merman-cli")
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5, check=True
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Could not query merman-cli version: %s", exc)
        return None
    version = (result.stdout or result.stderr).strip().splitlines()
    if not version:
        return None
    return executable, version[0]


def _merman_cache_type() -> str | None:
    """Cache namespace for the installed Merman renderer."""
    cli = _merman_cli()
    return f"merman-png-native-v1-{cli[1]}" if cli else None


def _render_with_merman(source: str, executable: str) -> bytes:
    """Render Mermaid source to PNG with the local Merman CLI."""
    result = subprocess.run(
        [
            executable,
            "render",
            "-",
            "--format",
            "png",
            "--output",
            "-",
            "--font-measurement",
            "native",
        ],
        input=source.encode("utf-8"),
        capture_output=True,
        timeout=_MERMAN_TIMEOUT,
        check=True,
    )
    png = result.stdout
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("merman-cli did not return PNG data")
    from PIL import Image

    with Image.open(BytesIO(png)) as image:
        image.verify()
    return png


def get_mermaid_image(
    source: str,
    config: Any | None = None,
    client: KrokiClient | None = None,
    cache: AssetCache | None = None,
    offline: bool | None = None,
) -> str | None:
    """Fetch/render a Mermaid diagram, crop it, cache it on disk, and return the cached path."""
    import os

    if offline is None:
        offline = config.offline if config else False

    if cache is None:
        cache_dir = config.cache_dir if config else os.path.expanduser("~/.cache/pymd2pdf")
        cache = AssetCache(cache_dir)

    # Merman 0.9.2 currently leaves Mermaid's $$...$$ label math blank.
    # Route those diagrams through Kroki instead of caching an incomplete image.
    supports_math_labels = "$$" not in source
    merman = _merman_cli() if supports_math_labels else None
    merman_type = _merman_cache_type() if merman else None
    if merman_type:
        path = cache.path_for(merman_type, source)
        if path.exists():
            return str(path)
        try:
            png = _render_with_merman(source, merman[0])
            _save_cropped_png(path, png)
            return str(path) if path.exists() else None
        except Exception as exc:
            logger.warning("Local Merman render failed: %s", exc)

    # Keep the existing Kroki cache namespace for compatibility with cached assets.
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

    _save_cropped_png(path, png)
    return str(path)


def _save_cropped_png(path, png: bytes) -> None:
    """Crop transparent/white margins and atomically save a renderer's PNG."""
    from PIL import Image as PILImage
    from PIL import ImageChops

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
            output = BytesIO()
            pil_img.save(output, format="PNG")
            _atomic_write(path, output.getvalue())
    except Exception as exc:
        logger.warning("Failed to crop/process Mermaid diagram image: %s", exc)
        try:
            _atomic_write(path, png)
        except Exception:
            pass


def _atomic_write(path, data: bytes) -> None:
    """Replace a cached asset only after its complete contents are written."""
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class MermaidHandler(ElementHandler):
    """Render ``Mermaid`` token blocks with Merman or Kroki.

    If ``merman-cli`` is installed, md2pdf renders locally first with native
    font measurement. Otherwise, or if local rendering fails, it uses Kroki.
    Sources with ``$$...$$`` math labels use Kroki because Merman 0.9.2 renders
    those labels blank. Each renderer has a separate cache entry.

    When *offline* is ``True``, Kroki is skipped. If local rendering also
    fails, or if Kroki fails for any reason,
    a :class:`~md2pdf.assets.fallback.PlaceholderBox` is returned instead so
    the conversion never crashes due to a network issue.

    Args:
        client: :class:`~md2pdf.assets.kroki.KrokiClient` instance used as fallback.
        cache: :class:`~md2pdf.assets.cache.AssetCache` instance.
        offline: If ``True``, skip Kroki and use a placeholder only when local
            rendering is unavailable.
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
