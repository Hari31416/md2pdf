"""CLI entry point for md2pdf."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

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


def cli_progress_callback(event: str, data: dict[str, Any]) -> None:
    """Callback to print compilation progress stage-by-stage."""
    if event == "preprocess_start":
        typer.echo("[1/4] Pre-processing document...", err=True)
    elif event == "preprocess_resolve_includes":
        typer.echo("  - Resolving includes...", err=True)
    elif event == "emoji_download_start":
        typer.echo(f"  - Downloading {data['total']} emoji assets...", err=True)
    elif event == "emoji_download_item":
        typer.echo(
            f"  - Downloading emoji: {data['slug']} ({data['index']}/{data['total']})\r",
            nl=False,
            err=True,
        )
        if data["index"] == data["total"]:
            typer.echo("  - Downloaded all emoji assets.                          ", err=True)
    elif event == "parse_start":
        typer.echo("[2/4] Parsing Markdown...", err=True)
    elif event == "map_start":
        typer.echo("[3/4] Mapping tokens to flowables...", err=True)
    elif event == "render_diagram":
        typer.echo(
            f"  - Rendering {data['type']} diagram ({data['index']}/{data['total']})...", err=True
        )
    elif event == "render_pass_start":
        pass_num = data["pass_num"]
        total_passes = data["total_passes"]
        desc = data["description"]
        typer.echo(
            f"[4/4] Generating PDF layout (Pass {pass_num}/{total_passes}: {desc})...", err=True
        )


@app.command()
def convert(
    input: Path = typer.Argument(..., help="Path to input .md file"),  # noqa: B008
    output: Path = typer.Option(  # noqa: B008
        None,
        "-o",
        "--output",
        help="Output PDF path. If not specified, defaults to the input filename with a .pdf extension.",
    ),
    config_file: Path = typer.Option(  # noqa: B008
        None, "-c", "--config", help="Path to md2pdf.toml"
    ),
    theme: str = typer.Option("default", "-t", "--theme", help="Theme name"),  # noqa: B008
    offline: bool | None = typer.Option(  # noqa: B008
        None,
        "--offline/--no-offline",
        help="Skip external API calls; use placeholders instead",
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
    toc: bool | None = typer.Option(  # noqa: B008
        None,
        "--toc/--no-toc",
        help="Generate a Table of Contents page",
    ),
    cover: bool | None = typer.Option(  # noqa: B008
        None,
        "--cover/--no-cover",
        help="Generate a cover/title page before the table of contents",
    ),
    header: str = typer.Option(  # noqa: B008
        None,
        "--header",
        help="Header text or template (supports {title} and {section})",
    ),
    header_on_first_page: bool | None = typer.Option(  # noqa: B008
        None,
        "--header-on-first-page/--no-header-on-first-page",
        help="Draw header on the first page of the document",
    ),
    emoji: bool | None = typer.Option(  # noqa: B008
        None,
        "--emoji/--no-emoji",
        help="Replace emoji codepoints with Twemoji PNG images (default: enabled)",
    ),
    progress: bool = typer.Option(  # noqa: B008
        True,
        "--progress/--no-progress",
        help="Show compilation progress stages on stderr (default: enabled)",
    ),
    deterministic: bool | None = typer.Option(  # noqa: B008
        None,
        "--deterministic/--no-deterministic",
        help="Pin document creation timestamps and ID hashes, enabling byte-identical builds for CI caching.",
    ),
    page_size: str | None = typer.Option(  # noqa: B008
        None,
        "--page-size",
        help="Page size name (e.g. A4, Letter, A3)",
    ),
    orientation: str | None = typer.Option(  # noqa: B008
        None,
        "--orientation",
        help="Page orientation: portrait or landscape",
    ),
    encoding: str | None = typer.Option(  # noqa: B008
        None,
        "--encoding",
        help="Source file encoding (e.g. utf-8, latin-1) or 'auto' for auto-detection.",
    ),
    format: str = typer.Option(  # noqa: B008
        "text",
        "--format",
        help="Format of the validation output (text or json).",
    ),
    watch: bool = typer.Option(  # noqa: B008
        False,
        "--watch",
        help="Watch the input file and re-render on changes.",
    ),
) -> None:
    """Convert a Markdown file to a print-ready PDF."""
    _setup_logging(verbose)

    if format not in ("text", "json"):
        typer.echo(f"✗ Invalid format: '{format}'. Supported formats: 'text', 'json'.", err=True)
        raise typer.Exit(code=1)

    if format == "json" and not validate_only:
        typer.echo("✗ JSON format is only supported when using --validate-only.", err=True)
        raise typer.Exit(code=1)

    # Defer heavy imports so --help is instant even without all deps installed.
    from md2pdf.core.config import Config
    from md2pdf.core.pipeline import Pipeline
    from md2pdf.core.registry import HandlerRegistry

    if not input.exists():
        typer.echo(f"✗ Input file not found: {input}", err=True)
        raise typer.Exit(code=1)

    import os

    def do_build() -> tuple[set[Path], Path | None, bool]:
        active_config_file = None
        if config_file is not None:
            if not config_file.exists():
                typer.echo(f"✗ Config file not found: {config_file}", err=True)
                raise typer.Exit(code=1)
            active_config_file = config_file.resolve()
        else:
            cwd_config = Path("md2pdf.toml")
            if cwd_config.is_file():
                active_config_file = cwd_config.resolve()
            else:
                home_config = Path(os.path.expanduser("~/.config/md2pdf/md2pdf.toml"))
                if home_config.is_file():
                    active_config_file = home_config.resolve()
                else:
                    home_dot = Path(os.path.expanduser("~/.md2pdf.toml"))
                    if home_dot.is_file():
                        active_config_file = home_dot.resolve()

        toml_data: dict[str, Any] = {}
        if active_config_file is not None:
            import tomllib

            with open(active_config_file, "rb") as fh:
                toml_data = tomllib.load(fh)

        if active_config_file is not None:
            cfg = Config.from_dict(toml_data)
            # CLI arguments take precedence over config file values.
            cfg.input_file = str(input)
            if output is not None:
                cfg.output_file = str(output)
            else:
                # Check if TOML file explicitly configured output_file
                toml_has_output = "output_file" in toml_data.get("md2pdf", {})
                if toml_has_output:
                    if not toml_data.get("md2pdf", {}).get("output_file"):
                        cfg.output_file = str(input.with_suffix(".pdf"))
                else:
                    cfg.output_file = str(input.with_suffix(".pdf"))

            if theme != "default":
                cfg.theme = theme
                try:
                    from md2pdf.styles.theme import PREBUILT_THEMES, ThemeConfig  # noqa: PLC0415

                    theme_data = toml_data.get("theme", {})
                    base_theme_data = PREBUILT_THEMES.get(theme, {})
                    merged_theme_data = {**base_theme_data, **theme_data}
                    cfg.theme_config = ThemeConfig.from_dict(merged_theme_data)
                except Exception:
                    logger = logging.getLogger("md2pdf")
                    logger.debug("Failed to apply theme config from TOML", exc_info=True)

            if offline is not None:
                cfg.offline = offline
            if min_image_scale is not None:
                cfg.min_image_scale = min_image_scale
            if toc is not None:
                cfg.toc = toc
            if cover is not None:
                cfg.cover = cover
            if header is not None:
                cfg.header = header
            if header_on_first_page is not None:
                cfg.header_on_first_page = header_on_first_page
            if emoji is not None:
                cfg.emoji = emoji
            if deterministic is not None:
                cfg.deterministic = deterministic
            if page_size is not None:
                cfg.page_size = page_size
            if orientation is not None:
                cfg.orientation = orientation
            if encoding is not None:
                cfg.encoding = encoding
        else:
            resolved_output = output if output is not None else input.with_suffix(".pdf")
            cfg = Config(
                input_file=str(input),
                output_file=str(resolved_output),
                theme=theme,
            )
            if offline is not None:
                cfg.offline = offline
            if min_image_scale is not None:
                cfg.min_image_scale = min_image_scale
            if toc is not None:
                cfg.toc = toc
            if cover is not None:
                cfg.cover = cover
            if header is not None:
                cfg.header = header
            if header_on_first_page is not None:
                cfg.header_on_first_page = header_on_first_page
            if emoji is not None:
                cfg.emoji = emoji
            if deterministic is not None:
                cfg.deterministic = deterministic
            if page_size is not None:
                cfg.page_size = page_size
            if orientation is not None:
                cfg.orientation = orientation
            if encoding is not None:
                cfg.encoding = encoding

        registry = HandlerRegistry()
        pipeline = Pipeline(
            cfg, registry, progress_callback=cli_progress_callback if progress else None
        )

        from md2pdf.core.config import read_file_with_encoding

        try:
            raw_md = read_file_with_encoding(input, cfg.encoding)
        except Exception as exc:
            typer.echo(f"✗ Failed to read input file: {exc}", err=True)
            raise RuntimeError(f"Failed to read input file: {exc}") from exc

        if validate_only:
            issues = pipeline.validate(raw_md)
            if format == "json":
                import dataclasses
                import json

                issues_dict = [dataclasses.asdict(i) for i in issues]
                typer.echo(json.dumps(issues_dict, indent=2))
            else:
                _report_issues(issues)
            has_errors = any(i.severity == "error" for i in issues)
            success = not has_errors
        else:
            try:
                pipeline.run(raw_md)
                typer.echo(f"✓ PDF written to: {cfg.output_file}")
                success = True
            except Exception as exc:
                logging.exception("Conversion failed")
                typer.echo(f"✗ Conversion failed: {exc}", err=True)
                raise RuntimeError(f"Conversion failed: {exc}") from exc

        watched = {Path(p).resolve() for p in pipeline.watched_files}
        return watched, active_config_file, success

    if not watch:
        try:
            _, _, success = do_build()
            if not success:
                raise typer.Exit(code=1)
        except typer.Exit:
            raise
        except Exception as exc:
            raise typer.Exit(code=1) from exc
    else:
        typer.echo("👁 Watch mode enabled. Press Ctrl+C to stop.", err=True)

        def get_mtimes(paths: set[Path]) -> dict[Path, float]:
            mtimes = {}
            for p in paths:
                try:
                    mtimes[p] = p.stat().st_mtime
                except Exception:
                    mtimes[p] = 0.0
            return mtimes

        watched_paths = {input.resolve()}
        if config_file is not None:
            watched_paths.add(config_file.resolve())

        try:
            new_paths, active_config, success = do_build()
            watched_paths.update(new_paths)
            if active_config:
                watched_paths.add(active_config)
        except Exception as exc:
            typer.echo(f"✗ Initial build failed: {exc}", err=True)

        mtimes = get_mtimes(watched_paths)

        import time

        try:
            while True:
                time.sleep(0.5)
                current_mtimes = get_mtimes(watched_paths)
                changed = False
                for p, mtime in current_mtimes.items():
                    if mtimes.get(p) != mtime:
                        changed = True
                        break

                if changed:
                    typer.echo("\n⚡ Change detected, rebuilding...", err=True)
                    try:
                        new_paths, active_config, success = do_build()
                        watched_paths = {input.resolve()}
                        watched_paths.update(new_paths)
                        if active_config:
                            watched_paths.add(active_config)
                        mtimes = get_mtimes(watched_paths)
                    except Exception as exc:
                        typer.echo(f"✗ Rebuild failed: {exc}", err=True)
                        mtimes = current_mtimes
        except KeyboardInterrupt:
            typer.echo("\nStopping watch mode.", err=True)
            raise typer.Exit(code=0) from None
