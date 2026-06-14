"""md2pdf: Programmatic Markdown-to-PDF typesetting engine."""

from __future__ import annotations

from md2pdf.core.config import Config
from md2pdf.core.errors import (
    ConfigError,
    Md2PdfError,
    ParseError,
    RenderError,
    ValidationIssue,
)
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.registry import HandlerRegistry

__version__ = "0.4.1"
__all__ = [
    "Config",
    "Pipeline",
    "HandlerRegistry",
    "convert",
    "ValidationIssue",
    "Md2PdfError",
    "ParseError",
    "RenderError",
    "ConfigError",
]


from collections.abc import Callable
from typing import Any


def convert(
    src: str,
    dst: str,
    config: Config | None = None,
    registry: HandlerRegistry | None = None,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    """High-level API: convert a Markdown file to a PDF.

    Args:
        src: Path to the input Markdown file.
        dst: Path to the output PDF file.
        config: Optional Config instance. If omitted, defaults are used.
        registry: Optional custom HandlerRegistry instance.
        progress_callback: Optional callback invoked with progress updates.
    """
    if config is None:
        config = Config(input_file=src, output_file=dst)
    else:
        config.input_file = src
        config.output_file = dst

    pipeline = Pipeline(config, registry, progress_callback=progress_callback)
    raw_md = open(src, encoding="utf-8").read()  # noqa: WPS515
    pipeline.run(raw_md)
