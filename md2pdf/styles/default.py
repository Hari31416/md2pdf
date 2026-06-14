"""Default stylesheet builder for md2pdf.

``build_default_stylesheet`` returns a dict that maps style names to
ReportLab ``ParagraphStyle`` instances (and a few scalar values).
All colors and font names are read from a ``ThemeConfig`` — no hex
literals or magic strings appear in this file.
"""

from __future__ import annotations

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from md2pdf.styles.theme import ThemeConfig


def build_default_stylesheet(theme: ThemeConfig | None = None) -> dict:
    """Build and return the default stylesheet dict.

    Args:
        theme: A :class:`ThemeConfig` instance.  If ``None``, all defaults
               from :class:`ThemeConfig` are used (matching the previously
               hard-coded values).

    Returns:
        A dict mapping style name strings to ``ParagraphStyle`` instances
        and a few scalar values consumed by non-Paragraph handlers.
    """
    if theme is None:
        theme = ThemeConfig()

    base = getSampleStyleSheet()

    return {
        # ---------------------------------------------------------------- #
        # Heading styles
        # ---------------------------------------------------------------- #
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName=theme.font_heading,
            fontSize=20,
            leading=24,
            spaceBefore=theme.spacing_base * 2,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=theme.font_heading,
            fontSize=16,
            leading=20,
            spaceBefore=int(theme.spacing_base * 1.5),
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName=theme.font_heading,
            fontSize=13,
            leading=16,
            spaceBefore=int(theme.spacing_base * 1.2),
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        "h4": ParagraphStyle(
            "h4",
            parent=base["Heading4"],
            fontName=theme.font_heading,
            fontSize=11,
            leading=14,
            spaceBefore=theme.spacing_base,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        # ---------------------------------------------------------------- #
        # Body / prose styles
        # ---------------------------------------------------------------- #
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName=theme.font_body,
            fontSize=theme.font_size_body,
            leading=14,
            spaceBefore=0,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        "blockquote": ParagraphStyle(
            "blockquote",
            parent=base["Normal"],
            fontName=theme.font_body,
            leftIndent=12,
            textColor=theme.hex("color_blockquote_text"),
            borderPad=4,
            fontSize=theme.font_size_body,
            leading=14,
            spaceBefore=0,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        "list_item": ParagraphStyle(
            "list_item",
            parent=base["Normal"],
            fontName=theme.font_body,
            fontSize=theme.font_size_body,
            leading=13,
            spaceBefore=0,
            spaceAfter=theme.spacing_base // 2,
            allowWidows=0,
            allowOrphans=0,
        ),
        "code_inline": ParagraphStyle(
            "code_inline",
            parent=base["Code"],
            fontName=theme.font_mono,
            fontSize=theme.font_size_small,
            allowWidows=0,
            allowOrphans=0,
        ),
        "code_block": ParagraphStyle(
            "code_block",
            parent=base["Code"],
            fontName=theme.font_mono,
            fontSize=theme.font_size_small - 1,
            leading=10,
            backColor=theme.hex("color_code_bg"),
            borderColor=theme.hex("color_blockquote_bar"),
            borderWidth=0.5,
            borderPadding=6,
            leftIndent=12,
            rightIndent=12,
            spaceBefore=0,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        # ---------------------------------------------------------------- #
        # Table styles
        # ---------------------------------------------------------------- #
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName=theme.font_heading,
            fontSize=theme.font_size_small,
            textColor=theme.hex("color_table_header_text"),
            allowWidows=0,
            allowOrphans=0,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName=theme.font_body,
            fontSize=theme.font_size_small,
            leading=12,
            allowWidows=0,
            allowOrphans=0,
        ),
        # Raw TableStyle command list (used by TableHandler).
        "table_style": [
            ("BACKGROUND", (0, 0), (-1, 0), theme.hex("color_table_header_bg")),
            ("TEXTCOLOR", (0, 0), (-1, 0), theme.hex("color_table_header_text")),
            ("GRID", (0, 0), (-1, -1), 0.5, theme.hex("color_table_grid")),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [theme.hex("color_table_row_odd"), theme.hex("color_table_row_even")],
            ),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ],
        "footnote": ParagraphStyle(
            "footnote",
            parent=base["Normal"],
            fontName=theme.font_body,
            fontSize=theme.font_size_small - 1,
            leading=10,
            textColor=theme.hex("color_body_text"),
            allowWidows=0,
            allowOrphans=0,
        ),
        "image_caption": ParagraphStyle(
            "image_caption",
            parent=base["Normal"],
            fontName=theme.font_body,
            fontSize=theme.font_size_small - 1,
            leading=10,
            textColor=theme.hex("color_body_text"),
            alignment=TA_CENTER,
            spaceBefore=theme.spacing_base // 2,
            spaceAfter=theme.spacing_base,
            allowWidows=0,
            allowOrphans=0,
        ),
        # ---------------------------------------------------------------- #
        # Scalar values consumed by non-Paragraph handlers
        # ---------------------------------------------------------------- #
        "color_hr": theme.hex("color_hr"),
        "color_link": theme.color_link,  # raw str for XML attr
        "color_highlight": theme.color_highlight,  # raw str for XML attr
        "color_blockquote_bar": theme.hex("color_blockquote_bar"),
        "syntax_style": theme.syntax_style,
        "spacing_base": theme.spacing_base,
    }
