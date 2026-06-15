"""Offline / error fallback renderer for diagram blocks.

When ``Config.offline=True`` or a network/render error occurs,
:class:`PlaceholderBox` is returned instead of crashing the conversion run.
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.platypus import Flowable

_BORDER_COLOR = colors.HexColor("#aaaaaa")
_BG_COLOR = colors.HexColor("#f9f9f9")
_LABEL_COLOR = colors.HexColor("#888888")
_SOURCE_COLOR = colors.HexColor("#555555")

_LABEL_FONT = "Helvetica-Oblique"
_SOURCE_FONT = "Courier"

_LABEL_SIZE = 8
_SOURCE_SIZE = 7
_PADDING = 6
_LINE_HEIGHT = 14


class PlaceholderBox(Flowable):
    """A grey bordered box displayed when diagram rendering is unavailable.

    Shows the diagram type and a truncated preview of the source so readers
    know something was not rendered rather than silently missing content.

    Args:
        diagram_type: Kroki diagram type string (e.g. ``"mermaid"``).
        source: Raw diagram source.  Truncated to 120 characters in the box.
        width: Box width in ReportLab points.  Defaults to ``400``.
        height: Box height in ReportLab points.  Defaults to ``80``.
    """

    _MAX_SOURCE_PREVIEW = 120

    def __init__(
        self,
        diagram_type: str,
        source: str,
        width: float = 400,
        height: float = 80,
    ) -> None:
        super().__init__()
        self.diagram_type = diagram_type
        self.source_preview = source[: self._MAX_SOURCE_PREVIEW] + (
            "..." if len(source) > self._MAX_SOURCE_PREVIEW else ""
        )
        self.width = width

        # Wrap the source preview to fit the box width
        import textwrap

        from reportlab.pdfbase.pdfmetrics import stringWidth

        char_width = stringWidth("A", _SOURCE_FONT, _SOURCE_SIZE)
        avail_width = max(50.0, self.width - 2 * _PADDING)
        max_chars = max(1, int(avail_width / char_width))
        self.source_lines = textwrap.wrap(self.source_preview, width=max_chars)

        # Ensure box height is enough to hold the label and all wrapped lines without overflow
        needed_height = _PADDING * 2 + _LINE_HEIGHT + len(self.source_lines) * (_SOURCE_SIZE + 3)
        self.height = max(height, needed_height)

        self.spaceBefore = 0
        self.spaceAfter = 8

    # ReportLab calls wrap() to query our dimensions before draw().
    def wrap(
        self, available_width: float, available_height: float
    ) -> tuple[float, float]:  # noqa: ARG002
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv

        # Background + border
        c.setStrokeColor(_BORDER_COLOR)
        c.setFillColor(_BG_COLOR)
        c.rect(0, 0, self.width, self.height, fill=1)

        # Label line: "[mermaid diagram — offline / render failed]"
        c.setFillColor(_LABEL_COLOR)
        c.setFont(_LABEL_FONT, _LABEL_SIZE)
        label = f"[{self.diagram_type} diagram — offline / render failed]"
        c.drawString(_PADDING, self.height - _PADDING - _LABEL_SIZE, label)

        # Source preview lines
        c.setFillColor(_SOURCE_COLOR)
        c.setFont(_SOURCE_FONT, _SOURCE_SIZE)
        y = self.height - _PADDING - _LABEL_SIZE - 6
        for line in self.source_lines:
            c.drawString(_PADDING, y - _SOURCE_SIZE, line)
            y -= _SOURCE_SIZE + 3
