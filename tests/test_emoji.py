"""Tests for the EmojiPreProcessor and related emoji helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from md2pdf.core.preprocessors import (
    EmojiPreProcessor,
    PreProcessorRegistry,
    _codepoints_to_slug,
    _fetch_emoji_png,
    _is_emoji_char,
)

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


class TestIsEmojiChar:
    def test_globe_emoji_detected(self) -> None:
        assert _is_emoji_char("🌍") is True

    def test_smile_emoji_detected(self) -> None:
        assert _is_emoji_char("😀") is True

    def test_star_emoji_detected(self) -> None:
        # ⭐ U+2B50 — in misc symbols range
        assert _is_emoji_char("⭐") is True

    def test_digit_not_emoji(self) -> None:
        for ch in "0123456789":
            assert _is_emoji_char(ch) is False, f"Expected {ch!r} to not be emoji"

    def test_hash_not_emoji(self) -> None:
        assert _is_emoji_char("#") is False

    def test_asterisk_not_emoji(self) -> None:
        assert _is_emoji_char("*") is False

    def test_ascii_letter_not_emoji(self) -> None:
        assert _is_emoji_char("A") is False

    def test_space_not_emoji(self) -> None:
        assert _is_emoji_char(" ") is False


class TestCodepointsToSlug:
    def test_single_emoji(self) -> None:
        # 🌍 = U+1F30D
        assert _codepoints_to_slug("🌍") == "1f30d"

    def test_variation_selector_stripped_when_trailing(self) -> None:
        # ☀ (U+2600) + VS16 (U+FE0F) — VS16 is trailing, should be stripped
        seq = "\u2600\ufe0f"
        assert _codepoints_to_slug(seq) == "2600"

    def test_variation_selector_kept_when_mid_sequence(self) -> None:
        # 🏳️‍🌈 = U+1F3F3 VS16 ZWJ U+1F308 — VS16 is mid-sequence, must be kept
        seq = "\U0001f3f3\ufe0f\u200d\U0001f308"
        assert _codepoints_to_slug(seq) == "1f3f3-fe0f-200d-1f308"

    def test_zwj_sequence(self) -> None:
        # 👨‍💻 = U+1F468 ZWJ U+1F4BB (no VS16)
        seq = "\U0001f468\u200d\U0001f4bb"
        slug = _codepoints_to_slug(seq)
        assert slug == "1f468-200d-1f4bb"


# ---------------------------------------------------------------------------
# _fetch_emoji_png — timeout forwarding and error handling
# ---------------------------------------------------------------------------


class TestFetchEmojiPng:
    def test_timeout_forwarded_to_urlopen(self, tmp_path: Path) -> None:
        """_fetch_emoji_png must pass *timeout* to urlopen, not ignore it."""
        import io

        fake_response = MagicMock()
        fake_response.__enter__ = lambda s: io.BytesIO(b"PNGDATA")
        fake_response.__exit__ = MagicMock(return_value=False)

        with patch("md2pdf.core.preprocessors.urlopen", return_value=fake_response) as mock_open:
            _fetch_emoji_png("1f600", tmp_path / "emoji", timeout=5.0)

        mock_open.assert_called_once()
        _, kwargs = mock_open.call_args
        assert kwargs.get("timeout") == 5.0

    def test_timeout_error_returns_none(self, tmp_path: Path) -> None:
        """A TimeoutError (network hang) must return None, not propagate."""
        with patch(
            "md2pdf.core.preprocessors.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = _fetch_emoji_png("1f600", tmp_path / "emoji", timeout=0.001)
        assert result is None

    def test_partial_file_cleaned_up_on_error(self, tmp_path: Path) -> None:
        """Partial file left from a previous failed attempt must not be returned."""
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        dest = emoji_dir / "1f600.png"
        # Simulate a leftover partial file from a prior broken download
        dest.write_bytes(b"partial")
        # Mark it as a directory so the existence check passes but it's actually stale;
        # easier: just delete it so _fetch_emoji_png attempts a fresh download that fails.
        dest.unlink()

        with patch(
            "md2pdf.core.preprocessors.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = _fetch_emoji_png("1f600", emoji_dir, timeout=0.001)

        assert result is None
        # No partial file should remain
        assert not dest.exists()


# ---------------------------------------------------------------------------
# EmojiPreProcessor unit tests (with mocked network)
# ---------------------------------------------------------------------------


@pytest.fixture
def emoji_pp(tmp_path: Path) -> EmojiPreProcessor:
    return EmojiPreProcessor(cache_dir=str(tmp_path))


class TestEmojiPreProcessor:
    def test_no_emoji_unchanged(self, emoji_pp: EmojiPreProcessor) -> None:
        text = "Hello world, no emoji here."
        assert emoji_pp.process(text) == text

    def test_emoji_replaced_with_img_tag(self, emoji_pp: EmojiPreProcessor, tmp_path: Path) -> None:
        # Pre-create a fake PNG so no network call is needed
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        fake_png = emoji_dir / "1f30d.png"
        fake_png.write_bytes(b"PNGDATA")

        result = emoji_pp.process("Hello 🌍 world!")
        assert "<img src=" in result
        assert "1f30d.png" in result
        assert "Hello" in result
        assert "world!" in result

    def test_emoji_in_code_block_skipped(self, emoji_pp: EmojiPreProcessor) -> None:
        text = "```\nHello 🌍 world\n```"
        result = emoji_pp.process(text)
        # The emoji should NOT be replaced — the whole fenced block is passed through
        assert "🌍" in result
        assert "<img" not in result

    def test_emoji_in_inline_code_skipped(self, emoji_pp: EmojiPreProcessor) -> None:
        text = "Use `🌍` for the earth emoji."
        result = emoji_pp.process(text)
        assert "🌍" in result
        assert "<img" not in result

    def test_network_failure_falls_back_to_original(self, emoji_pp: EmojiPreProcessor) -> None:
        with patch(
            "md2pdf.core.preprocessors.urlopen",
            side_effect=OSError("no network"),
        ):
            result = emoji_pp.process("Hello 🌍!")
        # Should keep the original emoji on network failure
        assert "🌍" in result

    def test_cache_hit_no_download(self, emoji_pp: EmojiPreProcessor, tmp_path: Path) -> None:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        fake_png = emoji_dir / "1f30d.png"
        fake_png.write_bytes(b"CACHED")

        mock_urlopen = MagicMock()
        with patch("md2pdf.core.preprocessors.urlopen", mock_urlopen):
            result = emoji_pp.process("🌍")

        # urlopen should NOT have been called — we already had the file
        mock_urlopen.assert_not_called()
        assert "1f30d.png" in result

    def test_multiple_emoji_in_line(self, emoji_pp: EmojiPreProcessor, tmp_path: Path) -> None:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "1f600.png").write_bytes(b"PNG1")
        (emoji_dir / "1f30d.png").write_bytes(b"PNG2")

        result = emoji_pp.process("😀 and 🌍")
        assert result.count("<img") == 2

    def test_img_tag_dimensions(self, emoji_pp: EmojiPreProcessor, tmp_path: Path) -> None:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "1f600.png").write_bytes(b"PNG")

        result = emoji_pp.process("😀")
        assert 'width="14"' in result
        assert 'height="14"' in result

    def test_custom_size(self, tmp_path: Path) -> None:
        pp = EmojiPreProcessor(cache_dir=str(tmp_path), size=20)
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "1f600.png").write_bytes(b"PNG")

        result = pp.process("😀")
        assert 'width="20"' in result
        assert 'height="20"' in result


# ---------------------------------------------------------------------------
# PreProcessorRegistry: emoji toggle
# ---------------------------------------------------------------------------


class TestPreProcessorRegistryEmojiToggle:
    def test_emoji_enabled_by_default(self, tmp_path: Path) -> None:
        reg = PreProcessorRegistry(register_builtins=True, cache_dir=str(tmp_path))
        processor_types = [type(pp).__name__ for _, pp in reg._processors]
        assert "EmojiPreProcessor" in processor_types

    def test_emoji_disabled(self, tmp_path: Path) -> None:
        reg = PreProcessorRegistry(register_builtins=True, emoji=False, cache_dir=str(tmp_path))
        processor_types = [type(pp).__name__ for _, pp in reg._processors]
        assert "EmojiPreProcessor" not in processor_types

    def test_emoji_priority_is_35(self, tmp_path: Path) -> None:
        reg = PreProcessorRegistry(register_builtins=True, cache_dir=str(tmp_path))
        for priority, pp in reg._processors:
            if type(pp).__name__ == "EmojiPreProcessor":
                assert priority == 35
                return
        pytest.fail("EmojiPreProcessor not found in registry")

    def test_emoji_default_timeout_is_10(self, tmp_path: Path) -> None:
        """The default download timeout should be 10 seconds."""
        reg = PreProcessorRegistry(register_builtins=True, cache_dir=str(tmp_path))
        for _, pp in reg._processors:
            if type(pp).__name__ == "EmojiPreProcessor":
                assert pp.timeout == 10.0
                return
        pytest.fail("EmojiPreProcessor not found in registry")

    def test_custom_emoji_timeout_propagated(self, tmp_path: Path) -> None:
        """emoji_timeout passed to the registry must reach EmojiPreProcessor."""
        reg = PreProcessorRegistry(
            register_builtins=True, cache_dir=str(tmp_path), emoji_timeout=3.5
        )
        for _, pp in reg._processors:
            if type(pp).__name__ == "EmojiPreProcessor":
                assert pp.timeout == 3.5
                return
        pytest.fail("EmojiPreProcessor not found in registry")


# ---------------------------------------------------------------------------
# Config + Pipeline integration
# ---------------------------------------------------------------------------


class TestEmojiPipelineIntegration:
    def test_emoji_config_field_default_true(self) -> None:
        from md2pdf.core.config import Config

        cfg = Config()
        assert cfg.emoji is True

    def test_emoji_config_field_false(self) -> None:
        from md2pdf.core.config import Config

        cfg = Config(emoji=False)
        assert cfg.emoji is False

    def test_pipeline_no_emoji_flag_disables_preprocessor(self, tmp_path: Path) -> None:
        from md2pdf.core.config import Config
        from md2pdf.core.pipeline import Pipeline

        cfg = Config(
            input_file="",
            output_file=str(tmp_path / "out.pdf"),
            offline=True,
            emoji=False,
            cache_dir=str(tmp_path),
        )
        pipeline = Pipeline(cfg)
        processor_types = [type(pp).__name__ for _, pp in pipeline._pre_registry._processors]
        assert "EmojiPreProcessor" not in processor_types

    def test_pipeline_emoji_enabled_registers_preprocessor(self, tmp_path: Path) -> None:
        from md2pdf.core.config import Config
        from md2pdf.core.pipeline import Pipeline

        cfg = Config(
            input_file="",
            output_file=str(tmp_path / "out.pdf"),
            offline=True,
            emoji=True,
            cache_dir=str(tmp_path),
        )
        pipeline = Pipeline(cfg)
        processor_types = [type(pp).__name__ for _, pp in pipeline._pre_registry._processors]
        assert "EmojiPreProcessor" in processor_types

    def test_end_to_end_with_emoji_no_network(self, tmp_path: Path) -> None:
        """Verify the pipeline completes when emoji are present but network is unavailable."""
        from io import BytesIO

        from PIL import Image as PILImage

        from md2pdf.core.config import Config
        from md2pdf.core.pipeline import Pipeline

        # Pre-seed the cache so no real network call is needed
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()

        buf = BytesIO()
        PILImage.new("RGBA", (72, 72), (255, 200, 0, 255)).save(buf, format="PNG")
        (emoji_dir / "1f30d.png").write_bytes(buf.getvalue())

        md = "# Emoji Test\n\nHello 🌍 world!\n"
        out_pdf = tmp_path / "out.pdf"
        cfg = Config(
            input_file="",
            output_file=str(out_pdf),
            offline=True,
            emoji=True,
            cache_dir=str(tmp_path),
        )
        pipeline = Pipeline(cfg)
        pipeline.run(md)

        assert out_pdf.exists()
        assert out_pdf.stat().st_size > 1000
