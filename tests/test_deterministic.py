"""Tests for the deterministic PDF output feature."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from md2pdf.cli import app
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.registry import HandlerRegistry

runner = CliRunner()


def test_config_deterministic_default() -> None:
    """Verify that deterministic defaults to False in Config."""
    cfg = Config()
    assert cfg.deterministic is False


def test_config_from_toml(tmp_path: Path) -> None:
    """Verify that deterministic is correctly loaded from TOML configuration."""
    toml_content = """
[md2pdf]
deterministic = true
"""
    toml_file = tmp_path / "md2pdf.toml"
    toml_file.write_text(toml_content, encoding="utf-8")

    cfg = Config.from_toml(str(toml_file))
    assert cfg.deterministic is True


def test_cli_deterministic_flag(tmp_path: Path, simple_md: str) -> None:
    """Verify that --deterministic flag is correctly parsed by the CLI."""
    src = tmp_path / "test.md"
    src.write_text(simple_md, encoding="utf-8")
    dest1 = tmp_path / "output1.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest1), "--offline", "--deterministic"])
    assert result.exit_code == 0
    assert dest1.exists()


def test_byte_identical_pdf_output(tmp_path: Path, simple_md: str) -> None:
    """Verify that two builds with deterministic=True produce byte-identical PDFs.

    To ensure that normal non-deterministic builds would differ, we can mock time.time
    to return different timestamps, showing that deterministic mode overrides them.
    """
    src = tmp_path / "test.md"
    src.write_text(simple_md, encoding="utf-8")
    dest1 = tmp_path / "output1.pdf"
    dest2 = tmp_path / "output2.pdf"

    # Compile with deterministic=True
    cfg_det1 = Config(
        input_file=str(src),
        output_file=str(dest1),
        offline=True,
        deterministic=True,
    )
    cfg_det2 = Config(
        input_file=str(src),
        output_file=str(dest2),
        offline=True,
        deterministic=True,
    )

    registry = HandlerRegistry()

    # Build PDF 1 with a mock time
    with patch("time.time", return_value=1620000000.0):
        pipeline1 = Pipeline(cfg_det1, registry)
        pipeline1.run(simple_md)

    # Build PDF 2 with a different mock time
    with patch("time.time", return_value=1620000100.0):
        pipeline2 = Pipeline(cfg_det2, registry)
        pipeline2.run(simple_md)

    # Compute hashes
    hash1 = hashlib.sha256(dest1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(dest2.read_bytes()).hexdigest()

    # Under deterministic mode, the output must be byte-identical
    assert hash1 == hash2


def test_non_deterministic_pdf_output_differs(tmp_path: Path, simple_md: str) -> None:
    """Verify that two builds with deterministic=False produce different files when times differ."""
    src = tmp_path / "test.md"
    src.write_text(simple_md, encoding="utf-8")
    dest1 = tmp_path / "output1.pdf"
    dest2 = tmp_path / "output2.pdf"

    cfg_non_det1 = Config(
        input_file=str(src),
        output_file=str(dest1),
        offline=True,
        deterministic=False,
    )
    cfg_non_det2 = Config(
        input_file=str(src),
        output_file=str(dest2),
        offline=True,
        deterministic=False,
    )

    registry = HandlerRegistry()

    # Build PDF 1 with a mock time
    with patch("time.time", return_value=1620000000.0):
        pipeline1 = Pipeline(cfg_non_det1, registry)
        pipeline1.run(simple_md)

    # Build PDF 2 with a different mock time
    with patch("time.time", return_value=1620000100.0):
        pipeline2 = Pipeline(cfg_non_det2, registry)
        pipeline2.run(simple_md)

    # Compute hashes
    hash1 = hashlib.sha256(dest1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(dest2.read_bytes()).hexdigest()

    # Under non-deterministic mode (default), the output should differ
    assert hash1 != hash2
