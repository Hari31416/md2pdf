"""Tests for Phase 3 ThemeConfig and build_default_stylesheet."""

from __future__ import annotations

import pytest
from reportlab.lib.styles import ParagraphStyle

from md2pdf.styles.default import build_default_stylesheet
from md2pdf.styles.theme import ThemeConfig

# ---------------------------------------------------------------------------
# ThemeConfig
# ---------------------------------------------------------------------------


class TestThemeConfig:
    def test_default_instantiation(self):
        theme = ThemeConfig()
        assert theme.font_body == "Helvetica"
        assert theme.color_table_header_bg == "#2c3e50"

    def test_from_dict_known_keys(self):
        data = {"color_link": "#e74c3c", "font_body": "Times-Roman"}
        theme = ThemeConfig.from_dict(data)
        assert theme.color_link == "#e74c3c"
        assert theme.font_body == "Times-Roman"

    def test_from_dict_ignores_unknown_keys(self):
        """Unknown keys must be silently ignored (no TypeError)."""
        theme = ThemeConfig.from_dict({"unknown_key": "x", "color_link": "#e74c3c"})
        assert theme.color_link == "#e74c3c"

    def test_from_dict_empty(self):
        """Empty dict should return all defaults."""
        theme = ThemeConfig.from_dict({})
        default = ThemeConfig()
        assert theme.font_body == default.font_body
        assert theme.color_hr == default.color_hr

    def test_hex_helper_returns_hexcolor(self):
        from reportlab.lib.colors import Color

        theme = ThemeConfig()
        result = theme.hex("color_hr")
        assert isinstance(result, Color)

    def test_custom_color_applied(self):
        theme = ThemeConfig(color_table_header_bg="#c0392b")
        assert theme.color_table_header_bg == "#c0392b"

    @pytest.mark.parametrize(
        "attr",
        [
            "color_body_text",
            "color_blockquote_text",
            "color_link",
            "color_hr",
            "color_table_header_bg",
            "color_table_header_text",
            "color_table_grid",
            "color_table_row_odd",
            "color_table_row_even",
            "color_blockquote_bar",
        ],
    )
    def test_all_color_attrs_are_hex_strings(self, attr):
        theme = ThemeConfig()
        value = getattr(theme, attr)
        assert value.startswith("#"), f"{attr} = {value!r} doesn't start with '#'"


# ---------------------------------------------------------------------------
# build_default_stylesheet
# ---------------------------------------------------------------------------


class TestBuildDefaultStylesheet:
    def test_returns_dict(self):
        ss = build_default_stylesheet()
        assert isinstance(ss, dict)

    def test_has_required_paragraph_styles(self):
        ss = build_default_stylesheet()
        for key in (
            "h1",
            "h2",
            "h3",
            "h4",
            "body",
            "blockquote",
            "list_item",
            "code_inline",
            "table_header",
            "table_cell",
        ):
            assert key in ss, f"Missing style key: {key!r}"
            assert isinstance(ss[key], ParagraphStyle), f"{key!r} is not a ParagraphStyle"

    def test_has_table_style_list(self):
        ss = build_default_stylesheet()
        assert "table_style" in ss
        assert isinstance(ss["table_style"], list)
        assert len(ss["table_style"]) > 0

    def test_has_scalar_values(self):
        ss = build_default_stylesheet()
        assert "color_hr" in ss
        assert "color_link" in ss
        assert "color_blockquote_bar" in ss

    def test_color_link_is_raw_string(self):
        """color_link must be a plain string (used in ReportLab XML markup)."""
        ss = build_default_stylesheet()
        assert isinstance(ss["color_link"], str)

    def test_none_theme_uses_defaults(self):
        ss_none = build_default_stylesheet(None)
        ss_default = build_default_stylesheet(ThemeConfig())
        # Both should produce the same font names
        assert ss_none["body"].fontName == ss_default["body"].fontName

    def test_custom_theme_applied(self):
        theme = ThemeConfig(font_heading="Times-Roman")
        ss = build_default_stylesheet(theme)
        assert ss["h1"].fontName == "Times-Roman"

    def test_no_hex_literals_in_table_style(self):
        """Table style entries should use HexColor objects, not raw strings."""

        ss = build_default_stylesheet()
        for cmd in ss["table_style"]:
            for item in cmd:
                # If it looks like a hex color string, it should have been converted
                if isinstance(item, str) and item.startswith("#"):
                    pytest.fail(
                        f"Raw hex literal found in table_style: {item!r}. "
                        "Use theme.hex() instead."
                    )
