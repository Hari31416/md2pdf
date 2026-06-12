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
        None, "-o", "--output", help="Output PDF path. If not specified, defaults to the input filename with a .pdf extension."
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
    min_image_scale: float = typer.Option(  # noqa: B008
        None,
        "--min-image-scale",
        help="Minimum scale factor for resizing images before deferring to a new page (e.g. 0.8)",
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

    import os

    active_config_file = None
    if config_file is not None:
        if not config_file.exists():
            typer.echo(f"✗ Config file not found: {config_file}", err=True)
            raise typer.Exit(code=1)
        active_config_file = str(config_file)
    else:
        cwd_config = Path("md2pdf.toml")
        if cwd_config.is_file():
            active_config_file = str(cwd_config)
        else:
            home_config = Path(os.path.expanduser("~/.config/md2pdf/md2pdf.toml"))
            if home_config.is_file():
                active_config_file = str(home_config)
            else:
                home_dot = Path(os.path.expanduser("~/.md2pdf.toml"))
                if home_dot.is_file():
                    active_config_file = str(home_dot)

    if active_config_file is not None:
        cfg = Config.from_toml(active_config_file)
        # CLI arguments take precedence over config file values.
        cfg.input_file = str(input)
        if output is not None:
            cfg.output_file = str(output)
        else:
            # Check if TOML file explicitly configured output_file
            import tomllib
            toml_has_output = False
            try:
                with open(active_config_file, "rb") as fh:
                    data = tomllib.load(fh)
                    if "output_file" in data.get("md2pdf", {}):
                        toml_has_output = True
            except Exception:
                pass

            if toml_has_output:
                if not cfg.output_file:
                    cfg.output_file = str(input.with_suffix(".pdf"))
            else:
                cfg.output_file = str(input.with_suffix(".pdf"))

        if theme != "default":
            cfg.theme = theme
        if offline:
            cfg.offline = True
        if min_image_scale is not None:
            cfg.min_image_scale = min_image_scale
    else:
        resolved_output = output if output is not None else input.with_suffix(".pdf")
        cfg = Config(
            input_file=str(input),
            output_file=str(resolved_output),
            theme=theme,
            offline=offline,
        )
        if min_image_scale is not None:
            cfg.min_image_scale = min_image_scale

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
        typer.echo(f"✓ PDF written to: {cfg.output_file}")
    except Exception as exc:
        logging.exception("Conversion failed")
        typer.echo(f"✗ Conversion failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
