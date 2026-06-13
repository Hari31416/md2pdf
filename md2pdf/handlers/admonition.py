"""AdmonitionHandler — renders Markdown callout and admonition boxes."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph

from md2pdf.core.flowables import AdmonitionBox
from md2pdf.core.registry import ElementHandler

# Material Design / MkDocs Admonition Color Palettes
ADMONITION_STYLES: dict[str, dict[str, str]] = {
    "note": {"border": "#448aff", "bg": "#f0f5ff"},
    "info": {"border": "#0288d1", "bg": "#e3f2fd"},
    "todo": {"border": "#29b6f6", "bg": "#e1f5fe"},
    "tip": {"border": "#00c853", "bg": "#e8f5e9"},
    "success": {"border": "#4caf50", "bg": "#e8f5e9"},
    "check": {"border": "#4caf50", "bg": "#e8f5e9"},
    "warning": {"border": "#ff9100", "bg": "#fff3e0"},
    "attention": {"border": "#ff9800", "bg": "#fff3e0"},
    "caution": {"border": "#ff5722", "bg": "#fbe9e7"},
    "danger": {"border": "#ff5252", "bg": "#ffebee"},
    "error": {"border": "#f44336", "bg": "#ffebee"},
    "failure": {"border": "#f44336", "bg": "#ffebee"},
    "bug": {"border": "#e91e63", "bg": "#fce4ec"},
    "important": {"border": "#00b0ff", "bg": "#e0f7fa"},
}

DEFAULT_ADMONITION_STYLE: dict[str, str] = {"border": "#00b0ff", "bg": "#e0f7fa"}


class AdmonitionHandler(ElementHandler):
    """Render ``Admonition`` tokens inside an ``AdmonitionBox`` container."""

    token_type = "Admonition"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        registry = styles.get("_registry")
        admonition_type = token.get("attrs", {}).get("type", "note").lower()
        title = token.get("attrs", {}).get("title", "")

        # 1. Render all children block-level tokens to ReportLab flowables
        child_flowables: list[Flowable] = []
        if registry:
            for child in token.get("children", []):
                handler = registry.get(child.get("type", ""))
                if handler:
                    child_flowables.extend(handler.render(child, styles))

        # 2. Get styling colors based on type
        style_info = ADMONITION_STYLES.get(admonition_type, DEFAULT_ADMONITION_STYLE)
        border_color = colors.HexColor(style_info["border"])
        bg_color = colors.HexColor(style_info["bg"])

        # Determine title text
        title_text = title if title else admonition_type.capitalize()

        # Build title paragraph using bold heading font
        title_style = ParagraphStyle(
            "AdmonitionTitle",
            parent=styles.get("body"),
            fontName=styles.get("h4").fontName if "h4" in styles else "Helvetica-Bold",
            fontSize=styles.get("body").fontSize,
            leading=styles.get("body").leading,
            textColor=border_color,
            spaceBefore=0,
            spaceAfter=4,
        )

        title_flowable = Paragraph(title_text, title_style) if title_text else None

        # 3. Return a list containing one AdmonitionBox flowable wrapping the children
        return [
            AdmonitionBox(
                content=child_flowables,
                border_color=border_color,
                bg_color=bg_color,
                title_flowable=title_flowable,
                padding=10.0,
                left_bar_width=4.0,
            )
        ]
