"""Theme configuration dataclass for md2pdf.

``ThemeConfig`` is the single source of truth for all colors, fonts, and
spacing values.  No hex literals or font names are hardcoded anywhere else
in the codebase — they all come from this dataclass.

The fields map 1:1 to entries in the ``[theme]`` section of ``md2pdf.toml``.
The entire section is optional — omitting it produces the built-in defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from md2pdf.assets._font_registry import FONT_MONO, FONT_SANS, FONT_SANS_BOLD


@dataclass
class ThemeConfig:
    """User-editable color and font palette.

    Example ``md2pdf.toml`` section::

        [theme]
        font_body            = "DejaVuSans"
        color_table_header_bg = "#2c3e50"

    To use a **custom TTF font**, supply both the logical name and the path::

        [theme]
        font_body      = "MyCustomFont"
        font_file_body = "/path/to/MyCustomFont.ttf"

    The logical name is the string ReportLab uses in the PDF; the path tells
    the engine where to find the ``.ttf`` file on disk.  If a ``font_file_*``
    is provided, it is registered automatically — no plugin needed.

    All fields have sensible defaults so the ``[theme]`` section is
    entirely optional.
    """

    # --- Typography ---
    # Defaults use DejaVu Sans, which is bundled with md2pdf and provides
    # broad Unicode coverage (Latin Extended, Greek, Cyrillic, math symbols,
    # arrows, box-drawing, currency, etc.).  Users may override these with
    # any ReportLab-registered font name via the [theme] section of md2pdf.toml.
    font_body: str = FONT_SANS
    font_heading: str = FONT_SANS_BOLD
    font_mono: str = FONT_MONO
    font_size_body: int = 10
    font_size_small: int = 9

    # Optional TTF file paths for custom fonts.
    # When set, the engine registers the font under the corresponding
    # ``font_body`` / ``font_heading`` / ``font_mono`` name automatically.
    # Leave empty (the default) to use the bundled DejaVu fonts.
    font_file_body: str = ""
    font_file_heading: str = ""
    font_file_mono: str = ""

    # --- Spacing ---
    spacing_base: int = 8

    # --- Body colors ---
    color_body_text: str = "#000000"
    color_blockquote_text: str = "#555555"
    color_link: str = "#0366d6"
    color_hr: str = "#cccccc"

    # --- Table colors ---
    color_table_header_bg: str = "#2c3e50"
    color_table_header_text: str = "#ffffff"
    color_table_grid: str = "#cccccc"
    color_table_row_odd: str = "#ffffff"
    color_table_row_even: str = "#f5f5f5"

    # --- Blockquote bar ---
    color_blockquote_bar: str = "#cccccc"

    # --- Code blocks ---
    color_code_bg: str = "#f5f5f5"
    syntax_style: str = "default"

    # ------------------------------------------------------------------ #
    # Class methods
    # ------------------------------------------------------------------ #

    @classmethod
    def from_dict(cls, data: dict) -> ThemeConfig:
        """Build a ``ThemeConfig`` from a plain dict (e.g. a TOML table).

        Unknown keys are silently ignored so that future theme fields can
        be added without breaking existing config files.

        Args:
            data: Mapping of field names to values.

        Returns:
            A ``ThemeConfig`` instance with known fields populated.
        """
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def hex(self, attr: str):
        """Return a ReportLab ``HexColor`` for the named attribute.

        Args:
            attr: Attribute name on this dataclass (e.g. ``"color_hr"``).

        Returns:
            A ``reportlab.lib.colors.HexColor`` instance.
        """
        from reportlab.lib import colors  # noqa: PLC0415

        return colors.HexColor(getattr(self, attr))
