"""Unit tests for page size and orientation configurations."""

from __future__ import annotations

import pytest

from md2pdf.core.config import Config, resolve_page_geometry
from md2pdf.core.errors import ConfigError


def test_page_size_and_orientation_defaults() -> None:
    cfg = Config()
    assert cfg.page_size == "A4"
    assert cfg.orientation == "portrait"


def test_resolve_page_geometry() -> None:
    from reportlab.lib.pagesizes import A3, A4, LETTER

    assert resolve_page_geometry("A4", "portrait") == A4
    assert resolve_page_geometry("a4", "landscape") == (A4[1], A4[0])
    assert resolve_page_geometry("Letter", "portrait") == LETTER
    assert resolve_page_geometry("LETTER", "landscape") == (LETTER[1], LETTER[0])
    assert resolve_page_geometry("a3", "portrait") == A3


def test_invalid_orientation_raises_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Config(orientation="invalid")
    assert "Invalid orientation" in str(exc_info.value)


def test_invalid_page_size_raises_error() -> None:
    with pytest.raises(ConfigError) as exc_info:
        Config(page_size="invalid_size")
    assert "Unknown page size" in str(exc_info.value)


def test_dynamic_page_size_and_orientation_modification() -> None:
    cfg = Config()

    cfg.page_size = "Letter"
    assert cfg.page_size == "Letter"

    cfg.orientation = "landscape"
    assert cfg.orientation == "landscape"

    with pytest.raises(ConfigError):
        cfg.page_size = "invalid"

    with pytest.raises(ConfigError):
        cfg.orientation = "invalid"


def test_cli_page_config(tmp_path) -> None:
    from typer.testing import CliRunner

    from md2pdf.cli import app

    runner = CliRunner()
    input_file = tmp_path / "test.md"
    input_file.write_text("# Hello World", encoding="utf-8")
    output_file = tmp_path / "test.pdf"

    # Run conversion with custom page size and orientation
    result = runner.invoke(
        app,
        [
            str(input_file),
            "-o",
            str(output_file),
            "--page-size",
            "A3",
            "--orientation",
            "landscape",
        ],
    )
    assert result.exit_code == 0
    assert output_file.exists()
