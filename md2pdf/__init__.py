"""md2pdf: Programmatic Markdown-to-PDF typesetting engine."""

from __future__ import annotations

from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.registry import HandlerRegistry

__version__ = "0.1.0"
__all__ = ["Config", "Pipeline", "HandlerRegistry", "convert"]


def convert(src: str, dst: str, config: Config | None = None) -> None:
    """High-level API: convert a Markdown file to a PDF.

    Args:
        src: Path to the input Markdown file.
        dst: Path to the output PDF file.
        config: Optional Config instance. If omitted, defaults are used
                with *src* as input and *dst* as output.
    """
    if config is None:
        config = Config(input_file=src, output_file=dst)

    registry = HandlerRegistry()
    registry.load_entry_points()
    registry.load_from_config(config.plugins)

    pipeline = Pipeline(config, registry)
    raw_md = open(src, encoding="utf-8").read()  # noqa: WPS515
    pipeline.run(raw_md)
