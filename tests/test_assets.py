"""Unit tests for Phase 4 asset components: AssetCache, KrokiClient, MermaidHandler, LatexHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.assets.kroki import KrokiClient
from md2pdf.handlers.latex import LatexHandler, _wrap_latex
from md2pdf.handlers.mermaid import MermaidHandler

# ---------------------------------------------------------------------------
# Minimal 1×1 transparent PNG for use as a mock response body
# ---------------------------------------------------------------------------

_FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ===========================================================================
# AssetCache
# ===========================================================================


class TestAssetCache:
    def test_miss_returns_none(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        assert cache.get("mermaid", "graph TD; A-->B") is None

    def test_put_then_get_returns_bytes(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        cache.put("mermaid", "graph TD; A-->B", _FAKE_PNG)
        result = cache.get("mermaid", "graph TD; A-->B")
        assert result == _FAKE_PNG

    def test_different_source_is_different_key(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        cache.put("mermaid", "A", _FAKE_PNG)
        assert cache.get("mermaid", "B") is None

    def test_different_type_is_different_key(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        cache.put("mermaid", "src", _FAKE_PNG)
        assert cache.get("tikz", "src") is None

    def test_cache_dir_created_on_init(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "nested" / "cache"
        AssetCache(str(cache_dir))
        assert cache_dir.is_dir()

    def test_cached_file_is_png_extension(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        cache.put("mermaid", "src", _FAKE_PNG)
        png_files = list(Path(str(tmp_path / "cache")).glob("*.png"))
        assert len(png_files) == 1


# ===========================================================================
# KrokiClient
# ===========================================================================


class TestKrokiClient:
    def test_render_posts_to_correct_url(self) -> None:
        client = KrokiClient(base_url="https://kroki.io")
        mock_resp = MagicMock()
        mock_resp.content = _FAKE_PNG
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            result = client.render("mermaid", "graph TD; A-->B")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.args[0] == "https://kroki.io/mermaid/png"
        assert result == _FAKE_PNG

    def test_render_sends_source_as_utf8_body(self) -> None:
        client = KrokiClient()
        mock_resp = MagicMock()
        mock_resp.content = _FAKE_PNG
        mock_resp.raise_for_status = MagicMock()
        source = "graph TD; A-->B"

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.render("mermaid", source)

        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["data"] == source.encode("utf-8")

    def test_render_raises_on_http_error(self) -> None:
        import requests

        client = KrokiClient()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                client.render("mermaid", "graph TD; A-->B")


# ===========================================================================
# MermaidHandler
# ===========================================================================


class TestMermaidHandler:
    def _make_handler(
        self,
        tmp_path: Path,
        offline: bool = False,
        cached_png: bytes | None = None,
        kroki_returns: bytes | None = None,
        kroki_raises: Exception | None = None,
    ) -> MermaidHandler:
        cache = AssetCache(str(tmp_path / "cache"))
        if cached_png is not None:
            cache.put("mermaid", "graph TD; A-->B", cached_png)
        client = MagicMock(spec=KrokiClient)
        if kroki_raises:
            client.render.side_effect = kroki_raises
        else:
            client.render.return_value = kroki_returns or _FAKE_PNG
        return MermaidHandler(client=client, cache=cache, offline=offline)

    def test_offline_returns_placeholder(self, tmp_path: Path) -> None:
        handler = self._make_handler(tmp_path, offline=True)
        result = handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
        assert len(result) == 1
        assert isinstance(result[0], PlaceholderBox)

    def test_offline_makes_no_http_call(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        handler = MermaidHandler(client=client, cache=cache, offline=True)
        handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
        client.render.assert_not_called()

    def test_http_error_returns_placeholder(self, tmp_path: Path) -> None:
        import requests

        handler = self._make_handler(tmp_path, kroki_raises=requests.HTTPError("503"))
        result = handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
        assert isinstance(result[0], PlaceholderBox)

    def test_network_error_returns_placeholder(self, tmp_path: Path) -> None:
        import requests

        handler = self._make_handler(tmp_path, kroki_raises=requests.ConnectionError("offline"))
        result = handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
        assert isinstance(result[0], PlaceholderBox)

    def test_cache_hit_skips_http(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        source = "graph TD; A-->B"
        cache.put("mermaid", source, _FAKE_PNG)
        client = MagicMock(spec=KrokiClient)
        handler = MermaidHandler(client=client, cache=cache, offline=False)
        handler.render({"type": "Mermaid", "raw": source}, {})
        client.render.assert_not_called()

    def test_same_source_makes_exactly_one_http_call(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        source = "graph TD; A-->B"
        client = MagicMock(spec=KrokiClient)
        client.render.return_value = _FAKE_PNG
        handler = MermaidHandler(client=client, cache=cache, offline=False)
        # Render twice — only the first call should hit the network.
        handler.render({"type": "Mermaid", "raw": source}, {})
        handler.render({"type": "Mermaid", "raw": source}, {})
        client.render.assert_called_once()

    def test_success_returns_image_flowable(self, tmp_path: Path) -> None:
        from reportlab.platypus import Image

        handler = self._make_handler(tmp_path)
        result = handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
        assert len(result) == 1
        assert isinstance(result[0], Image)


# ===========================================================================
# LatexHandler
# ===========================================================================


class TestLatexHandler:
    def test_offline_returns_placeholder(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        handler = LatexHandler(client=client, cache=cache, offline=True)
        result = handler.render({"type": "LatexBlock", "raw": "x^2"}, {})
        assert isinstance(result[0], PlaceholderBox)

    def test_wrap_latex_produces_document(self) -> None:
        wrapped = _wrap_latex("x^2")
        assert r"\documentclass{standalone}" in wrapped
        assert r"\usepackage{amsmath}" in wrapped
        assert r"\begin{document}" in wrapped
        assert "$x^2$" in wrapped
        assert r"\end{document}" in wrapped

    def test_http_error_returns_placeholder(self, tmp_path: Path) -> None:
        import requests

        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        client.render.side_effect = requests.HTTPError("500")
        handler = LatexHandler(client=client, cache=cache, offline=False)
        result = handler.render({"type": "LatexBlock", "raw": "x^2"}, {})
        assert isinstance(result[0], PlaceholderBox)


# ===========================================================================
# Network integration test (skipped in CI)
# ===========================================================================


@pytest.mark.network
def test_mermaid_real_kroki_call(tmp_path: Path) -> None:
    """Smoke test: real Kroki API call returns a valid PNG."""
    cache = AssetCache(str(tmp_path / "cache"))
    client = KrokiClient()
    handler = MermaidHandler(client=client, cache=cache, offline=False)
    result = handler.render({"type": "Mermaid", "raw": "graph TD; A-->B"}, {})
    assert len(result) == 1
    # PNG magic bytes
    png_bytes = cache.get("mermaid", "graph TD; A-->B")
    assert png_bytes is not None
    assert png_bytes[:4] == b"\x89PNG"
