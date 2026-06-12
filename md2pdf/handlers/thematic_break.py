"""ThematicBreakHandler — renders Markdown horizontal rules (---) to HRFlowable."""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.platypus import HRFlowable

from md2pdf.core.registry import ElementHandler


class ThematicBreakHandler(ElementHandler):
    """Render ``ThematicBreak`` tokens as a thin horizontal rule."""

    token_type = "ThematicBreak"

    def render(self, token: dict, styles: dict) -> list:
        color = styles.get("color_hr", colors.grey)
        return [
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=color,
                spaceAfter=6,
                spaceBefore=6,
            )
        ]
