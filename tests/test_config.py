"""Unit tests for the Config dataclass."""

from __future__ import annotations

import textwrap

import pytest

from md2pdf.core.config import Config


def test_defaults() -> None:
    cfg = Config()
    assert cfg.output_file == "output.pdf"
    assert cfg.theme == "default"
    assert cfg.offline is False
    assert cfg.cache_dir == ".md2pdf_cache"
    assert cfg.min_image_scale == 0.8
    assert cfg.plugins_dict == {}


def test_from_toml_basic(tmp_path) -> None:
    toml_content = textwrap.dedent("""\
        [md2pdf]
        output_file = "report.pdf"
        theme = "legal"
        offline = true
        min_image_scale = 0.65
    """)
    cfg_file = tmp_path / "md2pdf.toml"
    cfg_file.write_text(toml_content, encoding="utf-8")

    cfg = Config.from_toml(str(cfg_file))

    assert cfg.output_file == "report.pdf"
    assert cfg.theme == "legal"
    assert cfg.offline is True
    assert cfg.min_image_scale == 0.65


def test_from_toml_ignores_unknown_keys(tmp_path) -> None:
    """Keys not in Config are silently ignored (forward-compat)."""
    toml_content = textwrap.dedent("""\
        [md2pdf]
        output_file = "out.pdf"
        future_option = "some_value"
    """)
    cfg_file = tmp_path / "md2pdf.toml"
    cfg_file.write_text(toml_content, encoding="utf-8")

    cfg = Config.from_toml(str(cfg_file))
    assert cfg.output_file == "out.pdf"


def test_from_toml_empty_section(tmp_path) -> None:
    """Missing [md2pdf] section yields all defaults."""
    toml_content = "[other_section]\nfoo = 1\n"
    cfg_file = tmp_path / "md2pdf.toml"
    cfg_file.write_text(toml_content, encoding="utf-8")

    cfg = Config.from_toml(str(cfg_file))
    assert cfg.output_file == "output.pdf"


def test_from_toml_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        Config.from_toml("/nonexistent/path/md2pdf.toml")


def test_from_toml_roundtrip_example(tmp_path) -> None:
    """The shipped example config parses without error."""
    import shutil
    from pathlib import Path

    example = Path(__file__).parent.parent / "md2pdf.toml.example"
    dest = tmp_path / "md2pdf.toml"
    shutil.copy(example, dest)

    cfg = Config.from_toml(str(dest))
    assert cfg.output_file == "output.pdf"
    assert cfg.offline is False
