"""Unit tests for Phase 4 asset components: AssetCache, KrokiClient, MermaidHandler, LatexHandler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from md2pdf.assets.cache import AssetCache
from md2pdf.assets.fallback import PlaceholderBox
from md2pdf.assets.kroki import KrokiClient
from md2pdf.handlers.latex import LatexHandler, _wrap_latex
from md2pdf.handlers.mermaid import MermaidHandler, _render_with_merman, get_mermaid_image

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

    def test_put_is_atomic(self, tmp_path: Path) -> None:
        cache = AssetCache(str(tmp_path / "cache"))
        with patch("os.replace", side_effect=RuntimeError("disk full")):
            with pytest.raises(RuntimeError):
                cache.put("mermaid", "source", _FAKE_PNG)
        files = list((tmp_path / "cache").iterdir())
        assert len(files) == 0


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

    def test_render_validates_diagram_type(self) -> None:
        client = KrokiClient()
        with pytest.raises(ValueError, match="Invalid diagram type"):
            client.render("mermaid/../../traversal", "source")

        with pytest.raises(ValueError, match="Invalid diagram type"):
            client.render("mermaid; ls", "source")


# ===========================================================================
# MermaidHandler
# ===========================================================================


class TestMermaidHandler:
    @pytest.fixture(autouse=True)
    def disable_optional_merman_for_legacy_cases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("md2pdf.handlers.mermaid._merman_cli", lambda: None)

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

    def test_local_merman_runs_offline_and_uses_versioned_cache(self, tmp_path: Path) -> None:
        source = "graph TD; A-->B"
        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        with (
            patch("md2pdf.handlers.mermaid._merman_cli", return_value=("/bin/merman-cli", "0.9.2")),
            patch("md2pdf.handlers.mermaid._render_with_merman", return_value=_FAKE_PNG) as render,
        ):
            path = get_mermaid_image(source, client=client, cache=cache, offline=True)
        assert path == str(cache.path_for("merman-png-native-v1-0.9.2", source))
        assert Path(path).exists()
        render.assert_called_once_with(source, "/bin/merman-cli")
        client.render.assert_not_called()
        with patch(
            "md2pdf.handlers.mermaid._merman_cli", return_value=("/bin/merman-cli", "0.9.2")
        ):
            assert get_mermaid_image(source, client=client, cache=cache, offline=True) == path
        render.assert_called_once()

        with (
            patch("md2pdf.handlers.mermaid._merman_cli", return_value=("/bin/merman-cli", "0.9.3")),
            patch(
                "md2pdf.handlers.mermaid._render_with_merman", return_value=_FAKE_PNG
            ) as new_version_render,
        ):
            newer_path = get_mermaid_image(source, client=client, cache=cache, offline=True)
        assert newer_path != path
        assert newer_path == str(cache.path_for("merman-png-native-v1-0.9.3", source))
        new_version_render.assert_called_once()

    def test_local_merman_failure_falls_back_to_kroki(self, tmp_path: Path) -> None:
        source = "graph TD; A-->B"
        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        client.render.return_value = _FAKE_PNG
        with (
            patch("md2pdf.handlers.mermaid._merman_cli", return_value=("/bin/merman-cli", "0.9.2")),
            patch(
                "md2pdf.handlers.mermaid._render_with_merman",
                side_effect=TimeoutError("render timed out"),
            ),
        ):
            path = get_mermaid_image(source, client=client, cache=cache, offline=False)
        assert path == str(cache.path_for("mermaid", source))
        client.render.assert_called_once_with("mermaid", source)

    def test_local_merman_failure_stays_offline(self, tmp_path: Path) -> None:
        client = MagicMock(spec=KrokiClient)
        with (
            patch("md2pdf.handlers.mermaid._merman_cli", return_value=("/bin/merman-cli", "0.9.2")),
            patch("md2pdf.handlers.mermaid._render_with_merman", side_effect=TimeoutError),
        ):
            path = get_mermaid_image(
                "graph TD; A-->B",
                client=client,
                cache=AssetCache(str(tmp_path / "cache")),
                offline=True,
            )
        assert path is None
        client.render.assert_not_called()

    def test_merman_math_labels_skip_local_renderer(self, tmp_path: Path) -> None:
        source = 'flowchart LR\n A["$$E=mc^2$$"] --> B'
        client = MagicMock(spec=KrokiClient)
        with (
            patch("md2pdf.handlers.mermaid._merman_cli") as discover,
            patch("md2pdf.handlers.mermaid._render_with_merman") as render,
        ):
            path = get_mermaid_image(
                source, client=client, cache=AssetCache(str(tmp_path / "cache")), offline=True
            )
        assert path is None
        discover.assert_not_called()
        render.assert_not_called()
        client.render.assert_not_called()


def test_merman_cli_reads_stdin_and_writes_native_measured_png() -> None:
    from io import BytesIO

    from PIL import Image

    png_buffer = BytesIO()
    Image.new("RGBA", (2, 2), color="blue").save(png_buffer, format="PNG")
    response = MagicMock(stdout=png_buffer.getvalue())
    with patch("md2pdf.handlers.mermaid.subprocess.run", return_value=response) as run:
        png = _render_with_merman("graph TD; A-->B", "/bin/merman-cli")

    assert png == png_buffer.getvalue()
    assert run.call_args.args[0] == [
        "/bin/merman-cli",
        "render",
        "-",
        "--format",
        "png",
        "--output",
        "-",
        "--font-measurement",
        "native",
    ]
    assert run.call_args.kwargs["input"] == b"graph TD; A-->B"
    assert run.call_args.kwargs["timeout"] == 30


def test_merman_cli_rejects_non_png_output() -> None:
    with patch(
        "md2pdf.handlers.mermaid.subprocess.run", return_value=MagicMock(stdout=b"not a png")
    ):
        with pytest.raises(ValueError, match="did not return PNG"):
            _render_with_merman("graph TD; A-->B", "/bin/merman-cli")


def test_missing_merman_cli_falls_back_to_kroki(tmp_path: Path) -> None:
    from md2pdf.handlers import mermaid as mermaid_module

    source = "graph TD; A-->B"
    cache = AssetCache(str(tmp_path / "cache"))
    client = MagicMock(spec=KrokiClient)
    client.render.return_value = _FAKE_PNG
    mermaid_module._merman_cli.cache_clear()
    with patch("md2pdf.handlers.mermaid.shutil.which", return_value=None):
        path = get_mermaid_image(source, client=client, cache=cache, offline=False)
    mermaid_module._merman_cli.cache_clear()
    assert path == str(cache.path_for("mermaid", source))
    client.render.assert_called_once_with("mermaid", source)


# ===========================================================================
# LatexHandler
# ===========================================================================


class TestLatexHandler:
    @patch.dict("sys.modules", {"matplotlib": None})
    def test_offline_returns_raw_latex(self, tmp_path: Path) -> None:
        from reportlab.platypus import Preformatted

        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        handler = LatexHandler(client=client, cache=cache, offline=True)
        result = handler.render({"type": "LatexBlock", "raw": "x^2"}, {})
        assert isinstance(result[0], Preformatted)
        assert "x^2" in "".join(result[0].lines)

    def test_wrap_latex_produces_document(self) -> None:
        wrapped = _wrap_latex("x^2")
        assert r"\documentclass[preview,varwidth]{standalone}" in wrapped
        assert r"\usepackage{amsmath}" in wrapped
        assert r"\begin{document}" in wrapped
        assert "$x^2$" in wrapped
        assert r"\end{document}" in wrapped

    def test_wrap_latex_with_begin_environment_omits_inline_delimiters(self) -> None:
        wrapped = _wrap_latex(r"\begin{align*}x=1\end{align*}")
        assert "$" not in wrapped
        assert r"\begin{align*}" in wrapped

    @patch.dict("sys.modules", {"matplotlib": None})
    def test_http_error_returns_raw_latex(self, tmp_path: Path) -> None:
        import requests
        from reportlab.platypus import Preformatted

        cache = AssetCache(str(tmp_path / "cache"))
        client = MagicMock(spec=KrokiClient)
        client.render.side_effect = requests.HTTPError("500")
        handler = LatexHandler(client=client, cache=cache, offline=False)
        result = handler.render({"type": "LatexBlock", "raw": "x^2"}, {})
        assert isinstance(result[0], Preformatted)
        assert "x^2" in "".join(result[0].lines)


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


# ===========================================================================
# PlaceholderBox
# ===========================================================================


class TestPlaceholderBox:
    def test_placeholder_box_wrapping(self) -> None:
        long_source = "A" * 200
        box = PlaceholderBox("mermaid", long_source, width=200, height=50)
        # width is 200. Padding is 6 on each side, so avail_width = 188.
        # StringWidth of "A" in Courier at 7 points is 4.2 points.
        # 188 / 4.2 = 44 characters per line.
        # 120 chars wrapped at 44 chars/line should result in 3 lines.
        assert len(box.source_lines) == 3
        # Ensure height dynamically expanded
        # needed_height = padding(12) + label_height(14) + 3 lines * 10 = 56.
        # Height is max(50, 56) = 56.
        assert box.height == 56
