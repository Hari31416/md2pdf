"""Integration tests for the md2pdf CLI using typer CliRunner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from md2pdf.cli import app

runner = CliRunner()


def test_help() -> None:
    """Verify that --help options are correctly listed and parsed."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Convert" in result.output
    assert "--output" in result.output
    assert "--config" in result.output
    assert "--theme" in result.output
    assert "--offline" in result.output
    assert "--validate-only" in result.output


def test_missing_file() -> None:
    """Verify CLI error and non-zero exit code when input file is missing."""
    result = runner.invoke(app, ["nonexistent.md"])
    assert result.exit_code != 0
    assert "Input file not found" in result.stdout or "Input file not found" in result.stderr


def test_validate_only(tmp_path: Path, simple_md: str) -> None:
    """Verify validation runner behavior for standard conformant files."""
    src = tmp_path / "test.md"
    src.write_text(simple_md, encoding="utf-8")
    result = runner.invoke(app, [str(src), "--validate-only"])

    assert result.exit_code == 0


def test_validate_only_fails_on_empty_diagram(tmp_path: Path) -> None:
    """Verify validation runner flags errors and exits with non-zero code on failures."""
    src = tmp_path / "test.md"
    src.write_text("```mermaid\n\n```\n", encoding="utf-8")
    result = runner.invoke(app, [str(src), "--validate-only"])

    assert result.exit_code == 1
    assert "EMPTY_DIAGRAM" in result.output


def test_convert(tmp_path: Path, simple_md: str) -> None:
    """Verify end-to-end file generation path via command line options."""
    src = tmp_path / "test.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "output.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--offline"])

    assert result.exit_code == 0
    assert dest.exists()
    assert dest.stat().st_size > 1000
    assert "✓ PDF written to:" in result.output
