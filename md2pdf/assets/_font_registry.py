"""Font registration for md2pdf.

Registers the bundled DejaVu Sans TrueType fonts with ReportLab's font
metrics system so that all styles can reference them by logical name.

DejaVu Sans was chosen because:
- Broad Unicode coverage (Latin Extended, Greek, Cyrillic, Hebrew, Arabic,
  box-drawing, math operators, arrows, currency symbols, …)
- Permissive Bitstream Vera / DejaVu open-font licence — safe to bundle.
- Widely maintained and well-hinted for screen and print.

Note: Colour emojis (U+1F000+) are NOT covered by DejaVu. Special characters
and most non-Latin scripts are handled correctly.

Font name constants
-------------------
``FONT_SANS``        → ``"DejaVuSans"``
``FONT_SANS_BOLD``   → ``"DejaVuSans-Bold"``
``FONT_MONO``        → ``"DejaVuSansMono"``
``FONT_MONO_BOLD``   → ``"DejaVuSansMono-Bold"``

Usage::

    from md2pdf.assets.fonts import register_fonts, FONT_SANS
    register_fonts()   # safe to call multiple times — no-op after first call
"""

from __future__ import annotations

import logging
from importlib.resources import files
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public logical font name constants
# ---------------------------------------------------------------------------

FONT_SANS: str = "DejaVuSans"
FONT_SANS_BOLD: str = "DejaVuSans-Bold"
FONT_SANS_OBLIQUE: str = "DejaVuSans-Oblique"
FONT_SANS_BOLD_OBLIQUE: str = "DejaVuSans-BoldOblique"
FONT_MONO: str = "DejaVuSansMono"
FONT_MONO_BOLD: str = "DejaVuSansMono-Bold"

# Map logical ReportLab font name → TTF filename inside this package.
_FONT_FILES: dict[str, str] = {
    FONT_SANS: "DejaVuSans.ttf",
    FONT_SANS_BOLD: "DejaVuSans-Bold.ttf",
    FONT_SANS_BOLD_OBLIQUE: "DejaVuSans-BoldOblique.ttf",
    FONT_MONO: "DejaVuSansMono.ttf",
    FONT_MONO_BOLD: "DejaVuSansMono-Bold.ttf",
}

_registered: bool = False


def _fonts_dir() -> Path:
    """Return the absolute path to the bundled ``fonts/`` directory."""
    # importlib.resources works for both installed packages and editable installs.
    pkg = files("md2pdf.assets") / "fonts"
    return Path(str(pkg))


def register_fonts() -> None:
    """Register all bundled DejaVu fonts with ReportLab.

    This function is **idempotent** — calling it more than once is safe and
    has no effect after the first successful registration.

    Raises:
        Nothing — individual font failures are logged as warnings and skipped
        so that a missing file never aborts a conversion run.
    """
    global _registered
    if _registered:
        return

    try:
        from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415
        from reportlab.pdfbase.ttfonts import TTFont  # noqa: PLC0415
    except ImportError:
        logger.warning("reportlab is not installed; font registration skipped.")
        return

    fonts_dir = _fonts_dir()
    registered_count = 0

    for logical_name, filename in _FONT_FILES.items():
        ttf_path = fonts_dir / filename
        if not ttf_path.is_file():
            logger.warning("Bundled font '%s' not found at %s — skipping.", logical_name, ttf_path)
            continue
        try:
            pdfmetrics.registerFont(TTFont(logical_name, str(ttf_path)))
            registered_count += 1
            logger.debug("Registered font '%s' from %s", logical_name, ttf_path)
        except Exception:
            logger.warning(
                "Failed to register font '%s' from %s", logical_name, ttf_path, exc_info=True
            )

    if registered_count > 0:
        # Register a font family so ReportLab can resolve bold/italic automatically
        # when Paragraph markup uses <b> or <i> tags.
        try:
            from reportlab.pdfbase.pdfmetrics import registerFontFamily  # noqa: PLC0415

            registerFontFamily(
                FONT_SANS,
                normal=FONT_SANS,
                bold=FONT_SANS_BOLD,
                italic=FONT_SANS,  # DejaVu has no separate italic variant
                boldItalic=FONT_SANS_BOLD,
            )
            registerFontFamily(
                FONT_MONO,
                normal=FONT_MONO,
                bold=FONT_MONO_BOLD,
                italic=FONT_MONO,
                boldItalic=FONT_MONO_BOLD,
            )
            logger.debug("Registered DejaVu font families.")
        except Exception:
            logger.warning("Could not register font families.", exc_info=True)

    _registered = True
    logger.debug(
        "Font registration complete (%d/%d fonts loaded).", registered_count, len(_FONT_FILES)
    )


def register_theme_fonts(theme: object) -> None:
    """Register any custom TTF fonts declared in a :class:`ThemeConfig`.

    Reads the ``font_file_body``, ``font_file_heading``, and ``font_file_mono``
    fields from *theme*.  For each non-empty path, the corresponding TTF file
    is registered with ReportLab under the logical name given by the paired
    ``font_body`` / ``font_heading`` / ``font_mono`` field.

    This means users only need to add two lines per font in ``md2pdf.toml``:

    .. code-block:: toml

        [theme]
        font_body      = "MyFont"
        font_file_body = "/path/to/MyFont-Regular.ttf"

    Args:
        theme: A :class:`~md2pdf.styles.theme.ThemeConfig` instance, or any
               object exposing the same ``font_*`` / ``font_file_*`` attributes.
               If *theme* is ``None`` the function is a no-op.

    Raises:
        Nothing — failures are logged as warnings so a bad font path never
        aborts a conversion run.
    """
    if theme is None:
        return

    try:
        from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415
        from reportlab.pdfbase.ttfonts import TTFont  # noqa: PLC0415
    except ImportError:
        logger.warning("reportlab is not installed; custom font registration skipped.")
        return

    pairs: list[tuple[str, str]] = [
        (getattr(theme, "font_body", ""), getattr(theme, "font_file_body", "")),
        (getattr(theme, "font_heading", ""), getattr(theme, "font_file_heading", "")),
        (getattr(theme, "font_mono", ""), getattr(theme, "font_file_mono", "")),
    ]

    for logical_name, ttf_path_str in pairs:
        if not ttf_path_str:
            continue  # no custom file specified for this slot

        ttf_path = Path(ttf_path_str).expanduser().resolve()
        if not ttf_path.is_file():
            logger.warning(
                "Custom font file not found for '%s': %s — skipping.", logical_name, ttf_path
            )
            continue

        try:
            pdfmetrics.registerFont(TTFont(logical_name, str(ttf_path)))
            logger.debug("Registered custom font '%s' from %s", logical_name, ttf_path)
        except Exception:
            logger.warning(
                "Failed to register custom font '%s' from %s",
                logical_name,
                ttf_path,
                exc_info=True,
            )
