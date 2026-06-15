"""Extended tests for md2pdf CLI covering previously untested branches."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from md2pdf.cli import _report_issues, _setup_logging, app, cli_progress_callback

runner = CliRunner()


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from CLI output before asserting."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


# ---------------------------------------------------------------------------
# _setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_verbose() -> None:
    """Verify _setup_logging sets DEBUG level when verbose=True."""
    import logging

    _setup_logging(verbose=True)
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_non_verbose() -> None:
    """Verify _setup_logging sets WARNING level when verbose=False."""
    import logging

    _setup_logging(verbose=False)
    assert logging.getLogger().level == logging.WARNING


# ---------------------------------------------------------------------------
# _report_issues
# ---------------------------------------------------------------------------


class _FakeIssue:
    def __init__(self, severity: str, code: str, message: str, line: int | None) -> None:
        self.severity = severity
        self.code = code
        self.message = message
        self.line = line


def test_report_issues_error(capsys) -> None:
    """Verify that error issues are reported with the ✗ icon."""
    issues = [_FakeIssue("error", "E001", "Bad thing", 10)]
    _report_issues(issues)
    captured = capsys.readouterr()
    assert "✗" in captured.out
    assert "Line 10" in captured.out
    assert "E001" in captured.out
    assert "Bad thing" in captured.out


def test_report_issues_warning(capsys) -> None:
    """Verify that warning issues are reported with the ⚠ icon."""
    issues = [_FakeIssue("warning", "W001", "Maybe bad", None)]
    _report_issues(issues)
    captured = capsys.readouterr()
    assert "⚠" in captured.out
    assert "Line ?" in captured.out
    assert "W001" in captured.out


def test_report_issues_empty(capsys) -> None:
    """Verify that no output is produced when issue list is empty."""
    _report_issues([])
    captured = capsys.readouterr()
    assert captured.out == ""


# ---------------------------------------------------------------------------
# cli_progress_callback
# ---------------------------------------------------------------------------


def test_progress_callback_preprocess_start(capsys) -> None:
    cli_progress_callback("preprocess_start", {})
    captured = capsys.readouterr()
    assert "Pre-processing" in captured.err


def test_progress_callback_preprocess_resolve_includes(capsys) -> None:
    cli_progress_callback("preprocess_resolve_includes", {})
    captured = capsys.readouterr()
    assert "Resolving includes" in captured.err


def test_progress_callback_emoji_download_start(capsys) -> None:
    cli_progress_callback("emoji_download_start", {"total": 5})
    captured = capsys.readouterr()
    assert "5" in captured.err
    assert "emoji" in captured.err.lower()


def test_progress_callback_emoji_download_item_in_progress(capsys) -> None:
    """Verify emoji download item progress line (not last item)."""
    cli_progress_callback("emoji_download_item", {"slug": "heart", "index": 1, "total": 3})
    captured = capsys.readouterr()
    assert "heart" in captured.err


def test_progress_callback_emoji_download_item_last(capsys) -> None:
    """Verify emoji download item completion message printed on last item."""
    cli_progress_callback("emoji_download_item", {"slug": "star", "index": 3, "total": 3})
    captured = capsys.readouterr()
    assert "Downloaded all emoji assets" in captured.err


def test_progress_callback_parse_start(capsys) -> None:
    cli_progress_callback("parse_start", {})
    captured = capsys.readouterr()
    assert "Parsing Markdown" in captured.err


def test_progress_callback_map_start(capsys) -> None:
    cli_progress_callback("map_start", {})
    captured = capsys.readouterr()
    assert "Mapping tokens" in captured.err


def test_progress_callback_render_diagram(capsys) -> None:
    cli_progress_callback("render_diagram", {"type": "mermaid", "index": 1, "total": 2})
    captured = capsys.readouterr()
    assert "mermaid" in captured.err
    assert "1/2" in captured.err


def test_progress_callback_render_pass_start(capsys) -> None:
    cli_progress_callback(
        "render_pass_start",
        {"pass_num": 1, "total_passes": 2, "description": "Building layout"},
    )
    captured = capsys.readouterr()
    assert "Pass 1/2" in captured.err
    assert "Building layout" in captured.err


def test_progress_callback_unknown_event_no_output(capsys) -> None:
    """Unrecognised events should produce no output (no crash)."""
    cli_progress_callback("totally_unknown_event", {"foo": "bar"})
    captured = capsys.readouterr()
    assert captured.err == ""


# ---------------------------------------------------------------------------
# --config with missing config file
# ---------------------------------------------------------------------------


def test_missing_config_file(tmp_path: Path, simple_md: str) -> None:
    """Verify error message and non-zero exit when --config points to missing file."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    result = runner.invoke(app, [str(src), "--config", str(tmp_path / "nonexistent.toml")])
    assert result.exit_code != 0
    assert "Config file not found" in strip_ansi(result.output + (result.stderr or ""))


# ---------------------------------------------------------------------------
# Config file auto-discovery
# ---------------------------------------------------------------------------


def test_config_auto_discovery_cwd(tmp_path: Path, simple_md: str, monkeypatch) -> None:
    """Verify that md2pdf.toml in the cwd is auto-discovered and used."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\noffline = true\n", encoding="utf-8")

    # Change working directory so that md2pdf.toml is in cwd
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, [str(src), "-o", str(dest)])
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_config_auto_discovery_home_config(tmp_path: Path, simple_md: str, monkeypatch) -> None:
    """Verify ~/.config/md2pdf/md2pdf.toml is auto-discovered as a fallback."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    fake_home = tmp_path / "fake_home"
    config_dir = fake_home / ".config" / "md2pdf"
    config_dir.mkdir(parents=True)
    cfg_toml = config_dir / "md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\noffline = true\n", encoding="utf-8")

    def fake_expanduser(path: str) -> str:
        return path.replace("~", str(fake_home))

    monkeypatch.chdir(tmp_path)  # Ensure no cwd md2pdf.toml leaks in
    with patch("os.path.expanduser", side_effect=fake_expanduser):
        result = runner.invoke(app, [str(src), "-o", str(dest)])
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_config_auto_discovery_home_dot(tmp_path: Path, simple_md: str, monkeypatch) -> None:
    """Verify ~/.md2pdf.toml is auto-discovered as the last fallback."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    fake_home = tmp_path / "fake_home2"
    fake_home.mkdir(parents=True)
    cfg_toml = fake_home / ".md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\noffline = true\n", encoding="utf-8")

    def fake_expanduser(path: str) -> str:
        return path.replace("~", str(fake_home))

    monkeypatch.chdir(tmp_path)
    with patch("os.path.expanduser", side_effect=fake_expanduser):
        result = runner.invoke(app, [str(src), "-o", str(dest)])
    assert result.exit_code == 0, result.output
    assert dest.exists()


# ---------------------------------------------------------------------------
# CLI overrides applied on top of TOML config
# ---------------------------------------------------------------------------


def test_config_toml_cli_overrides(tmp_path: Path, simple_md: str) -> None:
    """Verify that CLI flags override values from a TOML config file."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text('[md2pdf]\noffline = false\ntheme = "default"\n', encoding="utf-8")

    result = runner.invoke(
        app,
        [str(src), "-o", str(dest), "--config", str(cfg_toml), "--offline", "--no-progress"],
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_config_toml_output_file_set_in_toml(tmp_path: Path, simple_md: str) -> None:
    """When TOML explicitly sets output_file, the CLI respects it (no output override needed)."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "from_toml.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text(
        f'[md2pdf]\noffline = true\noutput_file = "{dest}"\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, [str(src), "--config", str(cfg_toml), "--no-progress"])
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_config_toml_with_toc_header_emoji_overrides(tmp_path: Path, simple_md: str) -> None:
    """Verify --toc, --header, --header-on-first-page, --no-emoji and --min-image-scale are applied over TOML."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\noffline = true\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            str(src),
            "-o",
            str(dest),
            "--config",
            str(cfg_toml),
            "--toc",
            "--header",
            "My Header",
            "--header-on-first-page",
            "--no-emoji",
            "--min-image-scale",
            "0.5",
            "--no-progress",
        ],
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


# ---------------------------------------------------------------------------
# Pipeline failure handling
# ---------------------------------------------------------------------------


def test_convert_pipeline_failure(tmp_path: Path, simple_md: str) -> None:
    """Verify that pipeline errors result in non-zero exit and an error message."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    with patch("md2pdf.core.pipeline.Pipeline.run", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, [str(src), "-o", str(dest), "--offline", "--no-progress"])

    assert result.exit_code != 0
    out = strip_ansi(result.output)
    assert "Conversion failed" in out or "boom" in out


# ---------------------------------------------------------------------------
# --verbose flag
# ---------------------------------------------------------------------------


def test_verbose_flag(tmp_path: Path, simple_md: str) -> None:
    """Verify --verbose flag does not break normal conversion."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    result = runner.invoke(
        app, [str(src), "-o", str(dest), "--offline", "--verbose", "--no-progress"]
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


# ---------------------------------------------------------------------------
# --no-progress flag
# ---------------------------------------------------------------------------


def test_no_progress_flag(tmp_path: Path, simple_md: str) -> None:
    """Verify --no-progress flag suppresses all progress output."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--offline", "--no-progress"])
    assert result.exit_code == 0, result.output
    # No progress lines should be emitted to stderr
    assert "1/4" not in (result.stderr or "")


# ---------------------------------------------------------------------------
# --toc flag (no config)
# ---------------------------------------------------------------------------


def test_toc_flag_no_config(tmp_path: Path, simple_md: str) -> None:
    """Verify --toc flag works without a config file."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--offline", "--toc", "--no-progress"])
    assert result.exit_code == 0, result.output
    assert dest.exists()


# ---------------------------------------------------------------------------
# --validate-only with warnings only (exit 0)
# ---------------------------------------------------------------------------


def test_validate_only_warnings_exit_zero(tmp_path: Path) -> None:
    """Validate-only with only warnings (not errors) should exit 0."""
    # A simple valid markdown that produces no validation errors
    src = tmp_path / "input.md"
    src.write_text("# Hello\n\nSome text.\n", encoding="utf-8")

    result = runner.invoke(app, [str(src), "--validate-only"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Pre-built themes CLI conversion tests
# ---------------------------------------------------------------------------


def test_cli_theme_academic(tmp_path: Path, simple_md: str) -> None:
    """Verify that --theme academic runs successfully."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "academic.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--theme", "academic", "--offline"])
    assert result.exit_code == 0
    assert dest.exists()
    assert dest.stat().st_size > 1000


def test_cli_theme_minimal(tmp_path: Path, simple_md: str) -> None:
    """Verify that --theme minimal runs successfully."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "minimal.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--theme", "minimal", "--offline"])
    assert result.exit_code == 0
    assert dest.exists()
    assert dest.stat().st_size > 1000


def test_cli_theme_dark(tmp_path: Path, simple_md: str) -> None:
    """Verify that --theme dark runs successfully."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "dark.pdf"

    result = runner.invoke(app, [str(src), "-o", str(dest), "--theme", "dark", "--offline"])
    assert result.exit_code == 0
    assert dest.exists()
    assert dest.stat().st_size > 1000


# ---------------------------------------------------------------------------
# New CLI tests for overrides and theme exceptions
# ---------------------------------------------------------------------------


def test_cli_boolean_overrides_to_false(tmp_path: Path, simple_md: str) -> None:
    """Verify that CLI flags (e.g. --no-toc) can override TOML settings from true to false."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\ntoc = true\noffline = true\n", encoding="utf-8")

    # Override toc to false, but keep offline as true (not specified, defaults to None, preserves TOML)
    result = runner.invoke(
        app, [str(src), "-o", str(dest), "--config", str(cfg_toml), "--no-toc", "--no-progress"]
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_cli_boolean_overrides_to_true(tmp_path: Path, simple_md: str) -> None:
    """Verify that CLI flags (e.g. --toc) can override TOML settings from false to true."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    cfg_toml.write_text("[md2pdf]\ntoc = false\noffline = true\n", encoding="utf-8")

    # Override toc to true
    result = runner.invoke(
        app, [str(src), "-o", str(dest), "--config", str(cfg_toml), "--toc", "--no-progress"]
    )
    assert result.exit_code == 0, result.output
    assert dest.exists()


def test_cli_theme_merge_exception_logging(tmp_path: Path, simple_md: str) -> None:
    """Verify that failures in applying theme config from TOML are logged to debug."""
    src = tmp_path / "input.md"
    src.write_text(simple_md, encoding="utf-8")
    dest = tmp_path / "out.pdf"

    cfg_toml = tmp_path / "md2pdf.toml"
    # Malformed theme setting (string instead of dict) to trigger a TypeError during merge
    cfg_toml.write_text('theme = "not a dict"\n[md2pdf]\noffline = true\n', encoding="utf-8")

    with patch("logging.Logger.debug") as mock_debug:
        result = runner.invoke(
            app,
            [
                str(src),
                "-o",
                str(dest),
                "--config",
                str(cfg_toml),
                "--theme",
                "academic",
                "--no-progress",
            ],
        )
        assert result.exit_code == 0
        mock_debug.assert_any_call("Failed to apply theme config from TOML", exc_info=True)
