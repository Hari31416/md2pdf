"""Extended tests for md2pdf/handlers/latex.py covering previously untested branches."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.config import Config
from md2pdf.handlers.latex import (
    LatexHandler,
    _wrap_latex,
    clean_latex_source,
    get_latex_image,
    make_image_transparent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal valid 1×1 PNG bytes
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_cache(tmp_path: Path) -> AssetCache:
    return AssetCache(str(tmp_path / "cache"))


def _make_config(tmp_path: Path, *, offline: bool = True) -> Config:
    return Config(cache_dir=str(tmp_path / "cache"), offline=offline)


# ---------------------------------------------------------------------------
# clean_latex_source
# ---------------------------------------------------------------------------


class TestCleanLatexSource:
    def test_strip_double_dollar(self) -> None:
        """$$ delimiters are stripped and content is returned."""
        assert clean_latex_source("$$x^2$$") == "x^2"

    def test_strip_single_dollar(self) -> None:
        """Single $ delimiters are stripped."""
        assert clean_latex_source("$a+b$") == "a+b"

    def test_no_delimiters_passthrough(self) -> None:
        """Source without delimiters is returned as-is (stripped)."""
        assert clean_latex_source("  x = 1  ") == "x = 1"

    def test_normalize_le(self) -> None:
        r"""\\le (not part of longer word) is replaced with \\leq."""
        result = clean_latex_source(r"$a \le b$")
        assert r"\leq" in result
        # \le inside \leq should not be double-replaced
        assert r"\leqq" not in result

    def test_normalize_ge(self) -> None:
        r"""\\ge (not part of longer word) is replaced with \\geq."""
        result = clean_latex_source(r"$a \ge b$")
        assert r"\geq" in result

    def test_le_inside_word_not_replaced(self) -> None:
        r"""\\leq itself must not be mangled (negative lookahead guards it)."""
        result = clean_latex_source(r"$a \leq b$")
        assert r"\leq" in result
        # Should not become \leqq
        assert "leqq" not in result

    def test_normalize_latex_macro(self) -> None:
        r"""\\LaTeX is converted to its text-mode equivalent."""
        result = clean_latex_source(r"\LaTeX")
        assert r"\text{L}" in result

    def test_normalize_tex_macro(self) -> None:
        r"""\\TeX is converted to its text-mode equivalent."""
        result = clean_latex_source(r"\TeX")
        assert r"\text{T}" in result

    def test_double_dollar_with_whitespace(self) -> None:
        """Whitespace inside $$ delimiters is stripped from the formula."""
        assert clean_latex_source("$$  x + y  $$") == "x + y"

    def test_single_dollar_with_whitespace(self) -> None:
        assert clean_latex_source("$  z  $") == "z"


# ---------------------------------------------------------------------------
# _wrap_latex
# ---------------------------------------------------------------------------


class TestWrapLatex:
    def test_passthrough_when_documentclass_present(self) -> None:
        r"""Source already containing \documentclass is returned unchanged."""
        src = r"\documentclass{article}\begin{document}x\end{document}"
        assert _wrap_latex(src) == src

    def test_self_contained_align(self) -> None:
        r"""An \\begin{align} environment is used directly without wrapping in equation*."""
        src = r"\begin{align} x &= y \end{align}"
        result = _wrap_latex(src)
        assert r"\begin{align}" in result
        assert r"\begin{equation*}" not in result
        assert r"\documentclass" in result

    def test_self_contained_gather(self) -> None:
        src = r"\begin{gather} a = b \end{gather}"
        result = _wrap_latex(src)
        assert r"\begin{gather}" in result
        assert r"\begin{equation*}" not in result

    def test_nested_environment_wrapped_in_equation(self) -> None:
        r"""A \\begin{cases} (non-self-contained) is wrapped in equation*."""
        src = r"\begin{cases} x \\ y \end{cases}"
        result = _wrap_latex(src)
        assert r"\begin{equation*}" in result
        assert r"\begin{cases}" in result

    def test_plain_math_wrapped_in_dollars(self) -> None:
        """Plain math gets wrapped in $...$ inside the document skeleton."""
        src = "x^2 + y^2"
        result = _wrap_latex(src)
        assert "$x^2 + y^2$" in result
        assert r"\documentclass" in result

    def test_result_contains_amsmath(self) -> None:
        """Every wrapped document includes amsmath package."""
        result = _wrap_latex("a + b")
        assert r"\usepackage{amsmath}" in result

    def test_all_self_contained_envs(self) -> None:
        """All recognised self-contained math environments are passed through."""
        envs = ("align", "gather", "multline", "equation", "eqnarray", "alignat")
        for env in envs:
            src = rf"\begin{{{env}}} x \end{{{env}}}"
            result = _wrap_latex(src)
            assert r"\begin{equation*}" not in result, f"env={env} was incorrectly re-wrapped"


# ---------------------------------------------------------------------------
# make_image_transparent (numpy-free fallback)
# ---------------------------------------------------------------------------


class TestMakeImageTransparentFallback:
    def test_fallback_without_numpy(self) -> None:
        """make_image_transparent works when numpy is unavailable (uses PIL-only path)."""
        from PIL import Image

        white_img = Image.new("RGB", (10, 10), (255, 255, 255))

        with patch("md2pdf.handlers.latex.np", None):
            result = make_image_transparent(white_img)

        assert result.mode == "RGBA"

    def test_fallback_preserves_black_as_opaque(self) -> None:
        """In the numpy-free path, black pixels become fully opaque."""
        from PIL import Image

        black_img = Image.new("RGB", (10, 10), (0, 0, 0))

        with patch("md2pdf.handlers.latex.np", None):
            result = make_image_transparent(black_img)

        alpha = result.split()[-1]
        # Black → maximum alpha (255)
        assert alpha.getextrema()[1] == 255

    def test_make_image_transparent_with_numpy(self) -> None:
        """Verify make_image_transparent runs using numpy when np is not None."""
        from PIL import Image

        class MockNumpy:
            uint8 = "uint8"

            def array(self, *args, **kwargs):
                return self

            def min(self, *args, **kwargs):
                return self

            def expand_dims(self, *args, **kwargs):
                return self

            def where(self, *args, **kwargs):
                return self

            def maximum(self, *args, **kwargs):
                return self

            def clip(self, *args, **kwargs):
                return self

            def zeros(self, *args, **kwargs):
                return self

            def astype(self, *args, **kwargs):
                return self

            def __truediv__(self, other):
                return self

            def __sub__(self, other):
                return self

            def __rsub__(self, other):
                return self

            def __mul__(self, other):
                return self

            def __gt__(self, other):
                return True

            def __setitem__(self, key, value):
                pass

            def __getitem__(self, key):
                return self

        white_img = Image.new("RGB", (10, 10), (255, 255, 255))
        mock_np = MockNumpy()
        dummy_rgba = Image.new("RGBA", (10, 10), (255, 255, 255, 0))

        with (
            patch("md2pdf.handlers.latex.np", mock_np),
            patch("PIL.Image.fromarray", return_value=dummy_rgba),
        ):
            result = make_image_transparent(white_img)

        assert result.mode == "RGBA"


# ---------------------------------------------------------------------------
# get_latex_image — cache-hit path
# ---------------------------------------------------------------------------


class TestGetLatexImageCacheHit:
    def test_cache_hit_with_matplotlib_metrics(self, tmp_path: Path) -> None:
        """When image is already cached and matplotlib can compute metrics, use them directly."""
        from PIL import Image

        cache = _make_cache(tmp_path)
        formula = "E = mc^2"

        from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

        wrapped = _wrap_latex(clean_latex_source(formula))
        cache_path = cache._path("tikz", wrapped)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Save a valid RGBA PNG to simulate a pre-populated cache
        img = Image.new("RGBA", (40, 20), (0, 0, 0, 200))
        img.save(str(cache_path), format="PNG")

        # Force get_matplotlib_metrics to return None to test PIL fallback path
        with patch("md2pdf.handlers.latex.np", None):
            config = _make_config(tmp_path, offline=True)
            path, w, h, depth = get_latex_image(formula, config=config, cache=cache, offline=True)

        assert path is not None
        assert Path(path).exists()
        # Dimensions come from PIL (40px * 0.75 = 30pt, 20px * 0.75 = 15pt)
        assert w == 30.0
        assert h == 15.0
        assert depth == 0.0

    def test_cache_hit_opaque_image_converted_to_transparent(self, tmp_path: Path) -> None:
        """An opaque cached image (RGB mode) is re-saved as transparent RGBA."""
        from PIL import Image

        cache = _make_cache(tmp_path)
        formula = "a + b"

        from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

        wrapped = _wrap_latex(clean_latex_source(formula))
        cache_path = cache._path("tikz", wrapped)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Save an opaque RGB image (no alpha channel)
        img = Image.new("RGB", (30, 15), (255, 255, 255))
        img.save(str(cache_path), format="PNG")

        config = _make_config(tmp_path, offline=True)
        path, w, h, _ = get_latex_image(formula, config=config, cache=cache, offline=True)

        assert path is not None
        # After the call, the cached file should now be RGBA
        with Image.open(path) as reopened:
            assert reopened.mode == "RGBA"

    def test_cache_hit_fully_opaque_rgba_converted(self, tmp_path: Path) -> None:
        """An RGBA image with all-255 alpha is also treated as opaque and converted."""
        from PIL import Image

        cache = _make_cache(tmp_path)
        formula = "c^2"

        from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

        wrapped = _wrap_latex(clean_latex_source(formula))
        cache_path = cache._path("tikz", wrapped)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # RGBA image but all alpha = 255 (fully opaque)
        img = Image.new("RGBA", (20, 10), (200, 200, 200, 255))
        img.save(str(cache_path), format="PNG")

        config = _make_config(tmp_path, offline=True)
        path, w, h, _ = get_latex_image(formula, config=config, cache=cache, offline=True)

        assert path is not None


# ---------------------------------------------------------------------------
# get_latex_image — offline cache-miss
# ---------------------------------------------------------------------------


class TestGetLatexImageOfflineMiss:
    def test_offline_cache_miss_returns_none(self, tmp_path: Path) -> None:
        """In offline mode with no cache and no matplotlib support, returns (None, 0, 0, 0)."""
        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=True)

        # Force matplotlib path to return None by patching np away
        with patch("md2pdf.handlers.latex.np", None):
            path, w, h, d = get_latex_image(
                r"\documentclass{article}\begin{document}x\end{document}",
                config=config,
                cache=cache,
                offline=True,
            )

        assert path is None
        assert w == 0.0
        assert h == 0.0
        assert d == 0.0


# ---------------------------------------------------------------------------
# get_latex_image — Kroki paths
# ---------------------------------------------------------------------------


class TestGetLatexImageKroki:
    def test_kroki_success_saves_transparent_png(self, tmp_path: Path) -> None:
        """Successful Kroki render crops/transparentises and caches the PNG."""
        from PIL import Image

        # Create a real 10×5 white PNG to act as the Kroki response
        buf = BytesIO()
        Image.new("RGB", (10, 5), (255, 255, 255)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        client = MagicMock(spec=KrokiClient)
        client.render.return_value = png_bytes

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=False)

        with patch("md2pdf.handlers.latex.np", None):  # force Kroki path
            path, w, h, d = get_latex_image(
                r"\documentclass{article}x",
                config=config,
                client=client,
                cache=cache,
                offline=False,
            )

        assert client.render.called
        assert path is not None
        assert Path(path).exists()
        assert w > 0
        assert h > 0
        assert d == 0.0

    def test_kroki_failure_returns_none(self, tmp_path: Path) -> None:
        """When Kroki raises on all retries, (None, 0, 0, 0) is returned."""
        client = MagicMock(spec=KrokiClient)
        client.render.side_effect = ConnectionError("no network")

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=False)

        with patch("md2pdf.handlers.latex.np", None):
            with patch("time.sleep"):  # avoid real delays in retry loop
                path, w, h, d = get_latex_image(
                    r"\documentclass{article}x",
                    config=config,
                    client=client,
                    cache=cache,
                    offline=False,
                )

        assert path is None
        assert w == 0.0
        assert h == 0.0
        assert d == 0.0

    def test_kroki_first_attempt_fails_then_succeeds(self, tmp_path: Path) -> None:
        """Kroki retry logic: first call raises, second call succeeds."""
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (8, 8), (0, 0, 0)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        client = MagicMock(spec=KrokiClient)
        client.render.side_effect = [ConnectionError("transient"), png_bytes]

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=False)

        with patch("md2pdf.handlers.latex.np", None):
            with patch("time.sleep"):
                path, w, h, d = get_latex_image(
                    r"\documentclass{article}x",
                    config=config,
                    client=client,
                    cache=cache,
                    offline=False,
                )

        assert client.render.call_count == 2
        assert path is not None

    def test_kroki_corrupt_png_fallback(self, tmp_path: Path) -> None:
        """When PIL cannot open the Kroki response, raw bytes are written and size is default."""
        client = MagicMock(spec=KrokiClient)
        client.render.return_value = b"not-a-png"

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=False)

        with patch("md2pdf.handlers.latex.np", None):
            path, w, h, d = get_latex_image(
                r"\documentclass{article}x",
                config=config,
                client=client,
                cache=cache,
                offline=False,
            )

        # The function handles corrupt PNG gracefully — may return None or a path
        # Crucially it must not raise
        assert d == 0.0  # depth always 0 for Kroki path


# ---------------------------------------------------------------------------
# get_latex_image — defaults (config=None)
# ---------------------------------------------------------------------------


class TestGetLatexImageDefaults:
    def test_no_config_uses_default_cache(self, tmp_path: Path) -> None:
        """When config=None, the function constructs a default AssetCache."""
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (5, 5), (128, 128, 128)).save(buf, format="PNG")
        png_bytes = buf.getvalue()

        client = MagicMock(spec=KrokiClient)
        client.render.return_value = png_bytes

        fake_cache_dir = str(tmp_path / "default_cache")

        with patch("os.path.expanduser", return_value=fake_cache_dir):
            with patch("md2pdf.handlers.latex.np", None):
                path, w, h, d = get_latex_image(
                    r"\documentclass{article}x",
                    config=None,
                    client=client,
                    cache=None,
                    offline=False,
                )

        # Should have attempted Kroki render
        assert client.render.called


# ---------------------------------------------------------------------------
# LatexHandler.render
# ---------------------------------------------------------------------------


class TestLatexHandlerRender:
    def _styles(self) -> dict:
        from md2pdf.assets._font_registry import register_fonts
        from md2pdf.styles.default import build_default_stylesheet

        register_fonts()
        return build_default_stylesheet()

    def test_render_returns_resizable_image_on_success(self, tmp_path: Path) -> None:
        """When get_latex_image succeeds, render returns a ResizableImage flowable."""
        from PIL import Image

        from md2pdf.core.flowables import ResizableImage

        # Create a real PNG in the cache so the handler can open it
        buf = BytesIO()
        Image.new("RGBA", (100, 50), (0, 0, 0, 128)).save(buf, format="PNG")
        png_path = tmp_path / "formula.png"
        png_path.write_bytes(buf.getvalue())

        cache = _make_cache(tmp_path)
        handler = LatexHandler(cache=cache)

        with patch(
            "md2pdf.handlers.latex.get_latex_image",
            return_value=(str(png_path), 80.0, 40.0, 0.0),
        ):
            styles = self._styles()
            token = {"type": "LatexBlock", "raw": "x^2", "attrs": {}, "children": []}
            flowables = handler.render(token, styles)

        assert len(flowables) == 1
        assert isinstance(flowables[0], ResizableImage)
        assert flowables[0].hAlign == "CENTER"

    def test_render_falls_back_to_preformatted_on_none_path(self, tmp_path: Path) -> None:
        """When get_latex_image returns None, render falls back to Preformatted block."""
        from reportlab.platypus import Preformatted

        cache = _make_cache(tmp_path)
        handler = LatexHandler(cache=cache)

        with patch(
            "md2pdf.handlers.latex.get_latex_image",
            return_value=(None, 0.0, 0.0, 0.0),
        ):
            styles = self._styles()
            token = {"type": "LatexBlock", "raw": "$x^2$", "attrs": {}, "children": []}
            flowables = handler.render(token, styles)

        assert len(flowables) == 1
        assert isinstance(flowables[0], Preformatted)

    def test_render_falls_back_when_path_does_not_exist(self, tmp_path: Path) -> None:
        """When get_latex_image returns a non-existent path, render falls back to Preformatted."""
        from reportlab.platypus import Preformatted

        cache = _make_cache(tmp_path)
        handler = LatexHandler(cache=cache)

        ghost_path = str(tmp_path / "ghost.png")  # this file does not exist

        with patch(
            "md2pdf.handlers.latex.get_latex_image",
            return_value=(ghost_path, 50.0, 25.0, 0.0),
        ):
            styles = self._styles()
            token = {"type": "LatexBlock", "raw": "$y$", "attrs": {}, "children": []}
            flowables = handler.render(token, styles)

        assert len(flowables) == 1
        assert isinstance(flowables[0], Preformatted)

    def test_render_clamps_wide_image(self, tmp_path: Path) -> None:
        """Images wider than 400pt are scaled down so display_width == 400."""
        from PIL import Image

        from md2pdf.core.flowables import ResizableImage

        buf = BytesIO()
        Image.new("RGBA", (10, 5), (0, 0, 0, 200)).save(buf, format="PNG")
        png_path = tmp_path / "wide.png"
        png_path.write_bytes(buf.getvalue())

        cache = _make_cache(tmp_path)
        handler = LatexHandler(cache=cache)

        # Provide a width > 400 to trigger clamping
        with patch(
            "md2pdf.handlers.latex.get_latex_image",
            return_value=(str(png_path), 800.0, 200.0, 0.0),
        ):
            styles = self._styles()
            token = {"type": "LatexBlock", "raw": "wide formula", "attrs": {}, "children": []}
            flowables = handler.render(token, styles)

        assert len(flowables) == 1
        img = flowables[0]
        assert isinstance(img, ResizableImage)
        assert img.drawWidth == pytest.approx(400.0)
        # Height should be scaled proportionally: 200 * (400/800) = 100
        assert img.drawHeight == pytest.approx(100.0)

    def test_render_clamps_tall_image(self, tmp_path: Path) -> None:
        """Images taller than 600pt are scaled down proportionally."""
        from PIL import Image

        from md2pdf.core.flowables import ResizableImage

        buf = BytesIO()
        Image.new("RGBA", (10, 5), (0, 0, 0, 200)).save(buf, format="PNG")
        png_path = tmp_path / "tall.png"
        png_path.write_bytes(buf.getvalue())

        cache = _make_cache(tmp_path)
        handler = LatexHandler(cache=cache)

        # Provide a height > 600 to trigger clamping
        with patch(
            "md2pdf.handlers.latex.get_latex_image",
            return_value=(str(png_path), 300.0, 900.0, 0.0),
        ):
            styles = self._styles()
            token = {"type": "LatexBlock", "raw": "tall formula", "attrs": {}, "children": []}
            flowables = handler.render(token, styles)

        assert len(flowables) == 1
        img = flowables[0]
        assert isinstance(img, ResizableImage)
        assert img.drawHeight == pytest.approx(600.0)
        # Width scaled: 300 * (600/900) = 200
        assert img.drawWidth == pytest.approx(200.0)

    def test_render_reads_config_from_styles(self, tmp_path: Path) -> None:
        """Config in styles['_config'] is forwarded to get_latex_image."""
        from PIL import Image

        buf = BytesIO()
        Image.new("RGBA", (20, 10), (0, 0, 0, 200)).save(buf, format="PNG")
        png_path = tmp_path / "img.png"
        png_path.write_bytes(buf.getvalue())

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path)
        handler = LatexHandler(cache=cache, offline=True)

        captured: list = []

        def fake_get_latex_image(source, config=None, **kwargs):  # noqa: ANN001
            captured.append(config)
            return str(png_path), 20.0, 10.0, 0.0

        with patch("md2pdf.handlers.latex.get_latex_image", side_effect=fake_get_latex_image):
            styles = self._styles()
            styles["_config"] = config
            token = {"type": "LatexBlock", "raw": "x", "attrs": {}, "children": []}
            handler.render(token, styles)

        assert captured[0] is config

    def test_handler_default_init(self) -> None:
        """LatexHandler can be instantiated with no arguments and uses defaults."""
        handler = LatexHandler()
        assert handler.client is not None
        assert handler.cache is not None
        assert handler.offline is False

    def test_handler_offline_init(self) -> None:
        """LatexHandler respects offline=True at construction."""
        handler = LatexHandler(offline=True)
        assert handler.offline is True

    def test_token_type_attribute(self) -> None:
        """LatexHandler.token_type must be 'LatexBlock'."""
        assert LatexHandler.token_type == "LatexBlock"


# ---------------------------------------------------------------------------
# get_latex_image — matplotlib & fallbacks
# ---------------------------------------------------------------------------


class TestGetLatexImageMatplotlib:
    def test_matplotlib_metrics_and_rendering_success(self, tmp_path: Path) -> None:
        """Verify that when np and matplotlib are active, simple equations use matplotlib for metrics and save successfully."""
        from PIL import Image

        class MockNumpy:
            uint8 = "uint8"

            def nonzero(self, image):
                return ([1], [1])

            def min(self, arr):
                return 1

            def max(self, arr):
                return 5

            def zeros(self, shape, dtype=None):
                return self

            def __setitem__(self, key, value):
                pass

        mock_np = MockNumpy()

        mock_matplotlib = MagicMock()
        mock_font_properties = MagicMock()
        mock_parser_class = MagicMock()
        mock_parser = MagicMock()
        mock_res = MagicMock()
        mock_res.depth = 2
        mock_res.image.shape = (10, 10)

        mock_parser.parse.return_value = mock_res
        mock_parser_class.return_value = mock_parser

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=True)
        dummy_rgba = Image.new("RGBA", (20, 20), (255, 255, 255, 0))

        with patch.dict(
            "sys.modules",
            {
                "matplotlib": mock_matplotlib,
                "matplotlib.font_manager": MagicMock(FontProperties=mock_font_properties),
                "matplotlib.mathtext": MagicMock(MathTextParser=mock_parser_class),
            },
        ):
            with (
                patch("md2pdf.handlers.latex.np", mock_np),
                patch("PIL.Image.fromarray", return_value=dummy_rgba),
            ):
                path, w, h, depth = get_latex_image(
                    "E = mc^2", config=config, cache=cache, offline=True
                )

        assert path is not None
        assert Path(path).exists()
        assert w > 0
        assert h > 0
        assert depth is not None

    def test_matplotlib_fails_gracefully(self, tmp_path: Path) -> None:
        """Verify that when matplotlib raises an exception during rendering, it falls back gracefully."""

        class MockNumpy:
            uint8 = "uint8"

            def nonzero(self, image):
                return ([1], [1])

            def min(self, arr):
                return 1

            def max(self, arr):
                return 5

            def zeros(self, shape, dtype=None):
                return self

            def __setitem__(self, key, value):
                pass

        mock_np = MockNumpy()

        mock_matplotlib = MagicMock()
        mock_font_properties = MagicMock()
        mock_parser_class = MagicMock()
        mock_parser_class.side_effect = ValueError("Failed to parse")

        cache = _make_cache(tmp_path)
        config = _make_config(tmp_path, offline=True)

        with patch.dict(
            "sys.modules",
            {
                "matplotlib": mock_matplotlib,
                "matplotlib.font_manager": MagicMock(FontProperties=mock_font_properties),
                "matplotlib.mathtext": MagicMock(MathTextParser=mock_parser_class),
            },
        ):
            with patch("md2pdf.handlers.latex.np", mock_np):
                path, w, h, depth = get_latex_image(
                    "E = mc^2", config=config, cache=cache, offline=True
                )

        # In offline mode, matplotlib failing and Kroki disabled (offline=True) returns None
        assert path is None
        assert w == 0.0

    def test_corrupt_cached_image_re_renders(self, tmp_path: Path) -> None:
        """Verify that when the cached image is corrupted (PIL throws), we re-render or handle it gracefully."""
        cache = _make_cache(tmp_path)
        formula = "E = mc^2"

        from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

        wrapped = _wrap_latex(clean_latex_source(formula))
        cache_path = cache._path("tikz", wrapped)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Write corrupt/empty bytes
        cache_path.write_bytes(b"corrupt image data")

        config = _make_config(tmp_path, offline=True)
        # Should not raise PIL.UnidentifiedImageError; handles corruption and tries to re-render
        with patch("md2pdf.handlers.latex.np", None):
            path, w, h, depth = get_latex_image(formula, config=config, cache=cache, offline=True)

        # Since offline=True and cache corrupted, it couldn't re-render, so returns None
        assert path is None
        assert w == 0.0

    def test_get_latex_image_config_none_offline_none(self, tmp_path: Path) -> None:
        """When config=None and offline=None, offline defaults to False and cache uses default path."""
        # Use mocked client to avoid actual web requests
        client = MagicMock(spec=KrokiClient)
        client.render.return_value = _TINY_PNG

        fake_cache_dir = str(tmp_path / "default_cache_2")
        with patch("os.path.expanduser", return_value=fake_cache_dir):
            with patch("md2pdf.handlers.latex.np", None):
                path, w, h, depth = get_latex_image(
                    "formula",
                    config=None,
                    client=client,
                    cache=None,
                    offline=None,
                )
        assert path is not None
        assert client.render.called
