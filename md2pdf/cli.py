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
    # Clean standard logging configuration directed to stderr
    logging.basicConfig(
        level=level,
        format="%(levelname)s  %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,  # Override any existing configuration
    )


def _report_issues(issues: list) -> None:
    for issue in issues:
        icon = "✗" if issue.severity == "error" else "⚠"
        line_str = f"Line {issue.line}" if issue.line is not None else "Line ?"
        typer.echo(f"{icon} {line_str}: [{issue.code}] {issue.message}")


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
    validate_only: bool = typer.Option(  # noqa: B008
        False, "--validate-only", help="Run validation but do not render"
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
        if theme != "default":
            cfg.theme = theme
        if offline:
            cfg.offline = True

    registry = HandlerRegistry()
    pipeline = Pipeline(cfg, registry)

    raw_md = input.read_text(encoding="utf-8")

    if validate_only:
        issues = pipeline.validate(raw_md)
        _report_issues(issues)
        has_errors = any(i.severity == "error" for i in issues)
        raise typer.Exit(code=1 if has_errors else 0)

    try:
        pipeline.run(raw_md)
        typer.echo(f"✓ PDF written to: {output}")
    except Exception as exc:
        logging.exception("Conversion failed")
        typer.echo(f"✗ Conversion failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
