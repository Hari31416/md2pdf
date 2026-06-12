"""CLI entry point for md2pdf."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="md2pdf",
    help="Convert structured Markdown files to print-ready PDFs.",
    add_completion=False,
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(levelname)s  %(name)s: %(message)s",
        stream=sys.stderr,
    )


@app.command()
def convert(
    input: Path = typer.Argument(..., help="Path to input .md file"),  # noqa: B008
    output: Path = typer.Option(  # noqa: B008
        Path("output.pdf"), "-o", "--output", help="Output PDF path"
    ),
    config_file: Path = typer.Option(  # noqa: B008
        None, "-c", "--config", help="Path to md2pdf.toml"
    ),
    theme: str = typer.Option("default", "-t", "--theme", help="Theme name"),  # noqa: B008
    offline: bool = typer.Option(  # noqa: B008
        False, "--offline", help="Skip external API calls; use placeholders instead"
    ),
    verbose: bool = typer.Option(  # noqa: B008
        False, "-v", "--verbose", help="Enable debug logging to stderr"
    ),
) -> None:
    """Convert a Markdown file to a print-ready PDF."""
    _setup_logging(verbose)

    # Defer heavy imports so --help is instant even without all deps installed.
    from md2pdf.core.config import Config
    from md2pdf.core.pipeline import Pipeline
    from md2pdf.core.registry import HandlerRegistry

    if not input.exists():
        typer.echo(f"✗ Input file not found: {input}", err=True)
        raise typer.Exit(code=1)

    cfg = Config(
        input_file=str(input),
        output_file=str(output),
        theme=theme,
        offline=offline,
    )

    if config_file is not None:
        if not config_file.exists():
            typer.echo(f"✗ Config file not found: {config_file}", err=True)
            raise typer.Exit(code=1)
        cfg = Config.from_toml(str(config_file))
        # CLI arguments take precedence over config file values.
        cfg.input_file = str(input)
        cfg.output_file = str(output)

    registry = HandlerRegistry()
    registry.load_entry_points()
    registry.load_from_config(cfg.plugins)

    pipeline = Pipeline(cfg, registry)

    raw_md = input.read_text(encoding="utf-8")

    try:
        pipeline.run(raw_md)
        typer.echo(f"✓ PDF written to: {output}")
    except Exception as exc:
        logging.exception("Conversion failed")
        typer.echo(f"✗ Conversion failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
