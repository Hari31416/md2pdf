from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.kroki import KrokiClient
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.handlers.latex import get_latex_image


def test_matplotlib_math_rendering_success(tmp_path: Path) -> None:
    """Verify that matplotlib local rendering successfully creates a cropped PNG and returns correct sizes."""
    cache = AssetCache(str(tmp_path / "cache"))
    config = Config(cache_dir=str(tmp_path / "cache"), offline=True)

    # Render a simple equation
    path, w, h, depth = get_latex_image("E = mc^2", config=config, cache=cache, offline=True)

    # Should succeed locally since matplotlib is installed
    assert path is not None
    assert Path(path).exists()
    assert w > 0
    assert h > 0
    assert depth is not None
    assert isinstance(depth, (int, float))
    assert path.endswith(".png")


def test_latex_transparency_conversion() -> None:
    """Verify that an opaque/solid-white background PNG is converted to transparent."""
    from PIL import Image, ImageDraw

    from md2pdf.handlers.latex import make_image_transparent

    # Create a dummy solid white RGB image
    white_img = Image.new("RGB", (50, 20), (255, 255, 255))

    # Run the transparency conversion
    transparent_img = make_image_transparent(white_img)

    # Check that it is now RGBA and transparent
    assert transparent_img.mode == "RGBA"
    alpha = transparent_img.split()[-1]
    # The extrema should be (0, 0) since it was solid white
    assert alpha.getextrema() == (0, 0)

    # Create a white image with a black line (representing text)
    img_with_text = Image.new("RGB", (50, 20), (255, 255, 255))
    draw = ImageDraw.Draw(img_with_text)
    draw.line((0, 10, 50, 10), fill=(0, 0, 0))

    transparent_text_img = make_image_transparent(img_with_text)
    assert transparent_text_img.mode == "RGBA"
    alpha_text = transparent_text_img.split()[-1]
    # Text line is opaque (255) and background is transparent (0)
    assert alpha_text.getextrema() == (0, 255)


def test_matplotlib_math_rendering_fallback_on_unsupported_latex(tmp_path: Path) -> None:
    """Verify that unsupported LaTeX constructs (like align environment or documentclass) fall back to Kroki."""
    cache = AssetCache(str(tmp_path / "cache"))
    config = Config(cache_dir=str(tmp_path / "cache"), offline=False)

    # Mock Kroki client
    client = MagicMock(spec=KrokiClient)
    client.render.return_value = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # This contains \begin{align*} which should fail matplotlib path and request Kroki
    formula = r"\begin{align*} x &= y \end{align*}"
    path, w, h, depth = get_latex_image(
        formula, config=config, client=client, cache=cache, offline=False
    )

    # Should fall back to Kroki render call
    client.render.assert_called_once()
    assert path is not None
    assert Path(path).exists()


def test_pipeline_pre_fetch_assets(tmp_path: Path) -> None:
    """Verify that Pipeline._pre_fetch_assets concurrently scans AST and pre-populates caches."""
    config = Config(cache_dir=str(tmp_path / "cache"), offline=False)
    pipeline = Pipeline(config)

    # Tokens representing inline math, block math, and a mermaid diagram
    tokens = [
        {"type": "Paragraph", "children": [{"type": "Math", "raw": "a^2 + b^2 = c^2"}]},
        {"type": "LatexBlock", "raw": r"\begin{align*} x = 1 \end{align*}"},
        {"type": "Mermaid", "raw": "graph TD; A-->B"},
    ]

    # Mock KrokiClient render
    fake_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # Create handler mock
    latex_handler = pipeline.registry.get("LatexBlock")
    client_mock = MagicMock(spec=KrokiClient)
    client_mock.render.return_value = fake_png
    latex_handler.client = client_mock

    mermaid_handler = pipeline.registry.get("Mermaid")
    mermaid_handler.client = client_mock

    # Run pre-fetch
    pipeline._pre_fetch_assets(tokens)

    # 1. "a^2 + b^2 = c^2" should render via Matplotlib locally (no Kroki call for tikz simple math)
    # 2. "\begin{align*} x = 1 \end{align*}" should fall back and be fetched via Kroki
    # 3. "graph TD; A-->B" should be fetched via Kroki
    # Check that client.render was called for tikz (complex math) and mermaid
    assert client_mock.render.call_count == 2

    # Check cache has all items populated
    cache = latex_handler.cache
    from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

    p1 = cache._path("tikz", _wrap_latex(clean_latex_source("a^2 + b^2 = c^2")))
    p2 = cache._path("tikz", _wrap_latex(clean_latex_source(r"\begin{align*} x = 1 \end{align*}")))
    p3 = cache._path("mermaid", "graph TD; A-->B")

    assert p1.exists()
    assert p2.exists()
    assert p3.exists()
