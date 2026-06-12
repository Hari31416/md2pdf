"""md2pdf.handlers — built-in element handler implementations."""

from __future__ import annotations

from md2pdf.handlers.blockquote import BlockQuoteHandler
from md2pdf.handlers.heading import HeadingHandler
from md2pdf.handlers.inline import inline_render
from md2pdf.handlers.latex import LatexHandler
from md2pdf.handlers.list_ import ListHandler
from md2pdf.handlers.mermaid import MermaidHandler
from md2pdf.handlers.paragraph import ParagraphHandler
from md2pdf.handlers.table import TableHandler
from md2pdf.handlers.thematic_break import ThematicBreakHandler

__all__ = [
    "HeadingHandler",
    "ParagraphHandler",
    "ListHandler",
    "BlockQuoteHandler",
    "TableHandler",
    "ThematicBreakHandler",
    "MermaidHandler",
    "LatexHandler",
    "inline_render",
]
