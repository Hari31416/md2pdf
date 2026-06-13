"""Tests for stage-level progress reporting and CLI flags."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from md2pdf.cli import app
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline


def test_pipeline_progress_events(tmp_path: Path) -> None:
    """Verify that Pipeline emits basic progress events during execution."""
    cfg = Config(
        input_file="",
        output_file=str(tmp_path / "output.pdf"),
        offline=True,
        emoji=False,
        cache_dir=str(tmp_path),
    )

    events: list[tuple[str, dict]] = []

    def progress_callback(event: str, data: dict) -> None:
        events.append((event, data))

    pipeline = Pipeline(cfg, progress_callback=progress_callback)
    pipeline.run("# Test Document\n\nSome paragraph.")

    # Check the standard progression of events
    event_names = [e[0] for e in events]
    assert "preprocess_start" in event_names
    assert "parse_start" in event_names
    assert "render_pass_start" in event_names

    # Check that validation does not leak progress events
    # The first event should be preprocess_start for the actual run
    assert event_names[0] == "preprocess_start"


def test_pipeline_progress_with_diagrams(tmp_path: Path) -> None:
    """Verify diagram-related progress events are correctly emitted."""
    cfg = Config(
        input_file="",
        output_file=str(tmp_path / "output.pdf"),
        offline=True,
        emoji=False,
        cache_dir=str(tmp_path),
    )

    events: list[tuple[str, dict]] = []

    def progress_callback(event: str, data: dict) -> None:
        events.append((event, data))

    pipeline = Pipeline(cfg, progress_callback=progress_callback)
    md = "# Diagram Test\n\n```mermaid\ngraph TD\nA-->B\n```\n\n"
    pipeline.run(md)

    event_names = [e[0] for e in events]
    assert "map_start" in event_names
    assert "render_diagram" in event_names

    # Verify event payload data
    map_event = next(e for e in events if e[0] == "map_start")
    assert map_event[1]["total_diagrams"] == 1

    render_event = next(e for e in events if e[0] == "render_diagram")
    assert render_event[1]["type"] == "Mermaid"
    assert render_event[1]["index"] == 1
    assert render_event[1]["total"] == 1


def test_pipeline_progress_with_emojis(tmp_path: Path) -> None:
    """Verify that emoji downloading emits progress events for uncached emojis."""
    from io import BytesIO

    from PIL import Image as PILImage

    from md2pdf.core.preprocessors import EmojiPreProcessor

    # Create valid dummy PNG bytes
    buf = BytesIO()
    PILImage.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, format="PNG")
    valid_png_bytes = buf.getvalue()

    events: list[tuple[str, dict]] = []

    def progress_callback(event: str, data: dict) -> None:
        events.append((event, data))

    emoji_pp = EmojiPreProcessor(cache_dir=str(tmp_path), progress_callback=progress_callback)

    def mock_retrieve_side_effect(url, dest):
        Path(dest).write_bytes(valid_png_bytes)

    # Mock urlretrieve to write valid dummy PNG and pretend download succeeds
    with patch(
        "md2pdf.core.preprocessors.urlretrieve", side_effect=mock_retrieve_side_effect
    ) as mock_retrieve:
        # We need two emojis: 🌍 and 😀
        emoji_pp.process("Hello 🌍 and 😀!")

        # Verify download was attempted
        assert mock_retrieve.call_count == 2

    event_names = [e[0] for e in events]
    assert "emoji_download_start" in event_names
    assert "emoji_download_item" in event_names

    # Check payload detail for emoji_download_start
    dl_start = next(e for e in events if e[0] == "emoji_download_start")
    assert dl_start[1]["total"] == 2

    # Check that individual item download events are present
    dl_items = [e for e in events if e[0] == "emoji_download_item"]
    assert len(dl_items) == 2
    assert dl_items[0][1]["total"] == 2
    assert dl_items[0][1]["index"] == 1
    assert dl_items[1][1]["index"] == 2


def test_pipeline_progress_with_cached_emojis(tmp_path: Path) -> None:
    """Verify that cached emojis do not trigger download progress events."""
    from io import BytesIO

    from PIL import Image as PILImage

    # Pre-seed the emoji cache with valid PNG bytes
    emoji_dir = tmp_path / "emoji"
    emoji_dir.mkdir(parents=True)

    buf = BytesIO()
    PILImage.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buf, format="PNG")
    (emoji_dir / "1f30d.png").write_bytes(buf.getvalue())

    cfg = Config(
        input_file="",
        output_file=str(tmp_path / "output.pdf"),
        offline=True,
        emoji=True,
        cache_dir=str(tmp_path),
    )

    events: list[tuple[str, dict]] = []

    def progress_callback(event: str, data: dict) -> None:
        events.append((event, data))

    pipeline = Pipeline(cfg, progress_callback=progress_callback)

    with patch("md2pdf.core.preprocessors.urlretrieve") as mock_retrieve:
        pipeline.run("Hello 🌍!")
        mock_retrieve.assert_not_called()

    event_names = [e[0] for e in events]
    # Since emoji is cached, no downloads are performed
    assert "emoji_download_start" not in event_names
    assert "emoji_download_item" not in event_names


def test_cli_progress_reporting(tmp_path: Path) -> None:
    """Verify CLI prints progress reports to stderr by default."""
    src = tmp_path / "test.md"
    src.write_text("# Test\n\nHello.", encoding="utf-8")
    dest = tmp_path / "output.pdf"

    runner = CliRunner()
    result = runner.invoke(app, [str(src), "-o", str(dest), "--offline", "--progress"])

    assert result.exit_code == 0
    assert "[1/4] Pre-processing document..." in result.stderr
    assert "[2/4] Parsing Markdown..." in result.stderr
    assert "[3/4] Mapping tokens to flowables..." in result.stderr
    assert "[4/4] Generating PDF layout" in result.stderr


def test_cli_no_progress(tmp_path: Path) -> None:
    """Verify CLI silences progress reports when --no-progress is supplied."""
    src = tmp_path / "test.md"
    src.write_text("# Test\n\nHello.", encoding="utf-8")
    dest = tmp_path / "output.pdf"

    runner = CliRunner()
    result = runner.invoke(app, [str(src), "-o", str(dest), "--offline", "--no-progress"])

    assert result.exit_code == 0
    # None of the progress headers should be present in stderr
    assert "[1/4]" not in result.stderr
    assert "[2/4]" not in result.stderr
    assert "[3/4]" not in result.stderr
    assert "[4/4]" not in result.stderr
