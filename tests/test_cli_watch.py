"""Tests for the md2pdf CLI watch mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from md2pdf.cli import app

runner = CliRunner()


def test_watch_mode_init_and_keyboard_interrupt(tmp_path: Path) -> None:
    """Verify that watch mode starts and exits cleanly on KeyboardInterrupt."""
    src = tmp_path / "test.md"
    src.write_text("# Hello World\n", encoding="utf-8")
    dest = tmp_path / "output.pdf"

    # Mock time.sleep to immediately raise KeyboardInterrupt to exit the loop
    with patch("time.sleep", side_effect=KeyboardInterrupt) as mock_sleep:
        result = runner.invoke(
            app,
            [
                str(src),
                "-o",
                str(dest),
                "--watch",
                "--offline",
            ],
        )

        assert result.exit_code == 0
        assert "Watch mode enabled" in result.stderr or "Watch mode enabled" in result.stdout
        assert "Stopping watch mode" in result.stderr or "Stopping watch mode" in result.stdout
        assert dest.exists()
        mock_sleep.assert_called_once()


def test_watch_mode_rebuilds_on_change(tmp_path: Path) -> None:
    """Verify that watch mode detects changes and rebuilds the PDF."""
    src = tmp_path / "test.md"
    src.write_text("# Hello World\n", encoding="utf-8")
    dest = tmp_path / "output.pdf"

    calls = 0

    def mock_sleep(seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            # Change the file content to trigger a rebuild
            src.write_text("# Hello Changed\n", encoding="utf-8")
            # Update mtime manually since filesystem resolution can be coarse
            st = src.stat()
            new_mtime = st.st_mtime + 5.0
            import os

            os.utime(src, (st.st_atime, new_mtime))
        else:
            raise KeyboardInterrupt

    with patch("time.sleep", side_effect=mock_sleep):
        result = runner.invoke(
            app,
            [
                str(src),
                "-o",
                str(dest),
                "--watch",
                "--offline",
            ],
        )

        assert result.exit_code == 0
        output = result.stdout + result.stderr
        assert "Watch mode enabled" in output
        assert "Change detected, rebuilding" in output
        assert "✓ PDF written to" in output
        assert "Stopping watch mode" in output


def test_watch_mode_recovers_from_build_failure(tmp_path: Path) -> None:
    """Verify that watch mode handles compilation errors gracefully and recovers."""
    src = tmp_path / "test.md"
    src.write_text("# Hello World\n", encoding="utf-8")

    calls = 0

    def mock_sleep(seconds: float) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            # Write invalid content that causes a validation/compilation error.
            # We can use an empty Mermaid block to trigger validation error.
            src.write_text("```mermaid\n\n```\n", encoding="utf-8")
            st = src.stat()
            new_mtime = st.st_mtime + 5.0
            import os

            os.utime(src, (st.st_atime, new_mtime))
        elif calls == 2:
            # Revert to valid content
            src.write_text("# Hello Recovered\n", encoding="utf-8")
            st = src.stat()
            new_mtime = st.st_mtime + 10.0
            import os

            os.utime(src, (st.st_atime, new_mtime))
        else:
            raise KeyboardInterrupt

    # Run the CLI convert command in validation-only mode to check error propagation as well.
    # Note: validate-only exits with 1 on validation error, but watch mode should print and keep going.
    with patch("time.sleep", side_effect=mock_sleep):
        result = runner.invoke(
            app,
            [
                str(src),
                "--validate-only",
                "--watch",
                "--offline",
            ],
        )

        assert result.exit_code == 0
        output = result.stdout + result.stderr
        assert "Watch mode enabled" in output
        # Verify the failure was printed
        assert "EMPTY_DIAGRAM" in output
        # Verify it attempted to rebuild after failure and succeeded on recovery
        assert "Change detected, rebuilding" in output
        assert "Stopping watch mode" in output
