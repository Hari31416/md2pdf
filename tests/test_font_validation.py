"""Tests for pre-flight font path validation (ConfigError on missing font files)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from md2pdf.assets._font_registry import validate_font_paths
from md2pdf.core.errors import ConfigError
from md2pdf.styles.theme import ThemeConfig

# ---------------------------------------------------------------------------
# validate_font_paths
# ---------------------------------------------------------------------------


class TestValidateFontPaths:
    def test_none_theme_is_noop(self) -> None:
        """validate_font_paths(None) must never raise."""
        validate_font_paths(None)  # should not raise

    def test_no_font_files_configured_is_noop(self) -> None:
        """Default ThemeConfig with no custom font paths must pass validation."""
        validate_font_paths(ThemeConfig())  # should not raise

    def test_valid_font_file_body_passes(self, tmp_path: Path) -> None:
        fake_ttf = tmp_path / "MyFont.ttf"
        fake_ttf.write_bytes(b"\x00\x01\x00\x00")  # fake TTF content
        theme = ThemeConfig(font_body="MyFont", font_file_body=str(fake_ttf))
        validate_font_paths(theme)  # should not raise

    def test_valid_font_file_heading_passes(self, tmp_path: Path) -> None:
        fake_ttf = tmp_path / "MyHeading.ttf"
        fake_ttf.write_bytes(b"\x00\x01\x00\x00")
        theme = ThemeConfig(font_heading="MyHeading", font_file_heading=str(fake_ttf))
        validate_font_paths(theme)  # should not raise

    def test_valid_font_file_mono_passes(self, tmp_path: Path) -> None:
        fake_ttf = tmp_path / "MyMono.ttf"
        fake_ttf.write_bytes(b"\x00\x01\x00\x00")
        theme = ThemeConfig(font_mono="MyMono", font_file_mono=str(fake_ttf))
        validate_font_paths(theme)  # should not raise

    def test_missing_font_file_body_raises_config_error(self) -> None:
        theme = ThemeConfig(font_body="MyFont", font_file_body="/nonexistent/MyFont.ttf")
        with pytest.raises(ConfigError, match="font_file_body"):
            validate_font_paths(theme)

    def test_missing_font_file_heading_raises_config_error(self) -> None:
        theme = ThemeConfig(font_heading="MyFont", font_file_heading="/nonexistent/MyFont.ttf")
        with pytest.raises(ConfigError, match="font_file_heading"):
            validate_font_paths(theme)

    def test_missing_font_file_mono_raises_config_error(self) -> None:
        theme = ThemeConfig(font_mono="MyMono", font_file_mono="/nonexistent/MyMono.ttf")
        with pytest.raises(ConfigError, match="font_file_mono"):
            validate_font_paths(theme)

    def test_error_message_includes_path(self) -> None:
        missing = "/tmp/definitely_missing_font.ttf"
        theme = ThemeConfig(font_body="X", font_file_body=missing)
        with pytest.raises(ConfigError) as exc_info:
            validate_font_paths(theme)
        assert "definitely_missing_font.ttf" in str(exc_info.value)

    def test_first_missing_field_reported(self, tmp_path: Path) -> None:
        """When multiple font files are missing, the first (body) is reported."""
        theme = ThemeConfig(
            font_body="A",
            font_file_body="/nonexistent/a.ttf",
            font_heading="B",
            font_file_heading="/nonexistent/b.ttf",
        )
        with pytest.raises(ConfigError, match="font_file_body"):
            validate_font_paths(theme)


# ---------------------------------------------------------------------------
# register_theme_fonts propagates ConfigError
# ---------------------------------------------------------------------------


class TestRegisterThemeFontsValidation:
    def test_missing_font_raises_config_error(self) -> None:
        from md2pdf.assets._font_registry import register_theme_fonts

        theme = ThemeConfig(font_body="Ghost", font_file_body="/no/such/Ghost.ttf")
        with pytest.raises(ConfigError):
            register_theme_fonts(theme)

    def test_none_theme_no_error(self) -> None:
        from md2pdf.assets._font_registry import register_theme_fonts

        register_theme_fonts(None)  # must not raise


# ---------------------------------------------------------------------------
# Pipeline propagates ConfigError to the caller
# ---------------------------------------------------------------------------


class TestPipelineFontValidation:
    def test_pipeline_raises_config_error_on_missing_font(self, tmp_path: Path) -> None:
        from md2pdf.core.config import Config
        from md2pdf.core.pipeline import Pipeline

        # Build a TOML with a missing font path
        toml_content = textwrap.dedent("""\
            [md2pdf]
            output_file = "out.pdf"

            [theme]
            font_body      = "GhostFont"
            font_file_body = "/nonexistent/GhostFont.ttf"
        """)
        cfg_file = tmp_path / "md2pdf.toml"
        cfg_file.write_text(toml_content, encoding="utf-8")

        cfg = Config.from_toml(str(cfg_file))
        cfg.output_file = str(tmp_path / "out.pdf")

        with pytest.raises(ConfigError, match="GhostFont.ttf"):
            Pipeline(cfg)
