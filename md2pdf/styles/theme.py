"""Theme configuration dataclass for md2pdf.

``ThemeConfig`` is the single source of truth for all colors, fonts, and
spacing values.  No hex literals or font names are hardcoded anywhere else
in the codebase — they all come from this dataclass.

The fields map 1:1 to entries in the ``[theme]`` section of ``md2pdf.toml``.
The entire section is optional — omitting it produces the built-in defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass
class ThemeConfig:
    """User-editable color and font palette.

    Example ``md2pdf.toml`` section::

        [theme]
        font_body            = "Helvetica"
        color_table_header_bg = "#2c3e50"

    All fields have sensible defaults so the ``[theme]`` section is
    entirely optional.
    """

    # --- Typography ---
    font_body: str = "Helvetica"
    font_heading: str = "Helvetica-Bold"
    font_mono: str = "Courier"
    font_size_body: int = 10
    font_size_small: int = 9

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
