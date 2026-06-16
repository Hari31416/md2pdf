"""Unit tests for encoding detection and support in md2pdf."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from md2pdf.cli import app
from md2pdf.core.config import detect_encoding, read_file_with_encoding
from md2pdf.core.preprocessors import IncludeResolver

runner = CliRunner()


def test_detect_encoding(tmp_path: Path) -> None:
    # Test empty file
    empty_file = tmp_path / "empty.md"
    empty_file.write_bytes(b"")
    assert detect_encoding(empty_file) == "utf-8"

    # Test UTF-8 BOM
    bom_file = tmp_path / "bom.md"
    bom_file.write_bytes(b"\xef\xbb\xbf# Hello BOM")
    assert detect_encoding(bom_file) == "utf-8-sig"

    # Test Shift-JIS text (Japanese: "こんにちは")
    sjis_text = "こんにちは".encode("shift_jis")
    sjis_file = tmp_path / "sjis.md"
    sjis_file.write_bytes(sjis_text)
    # charset_normalizer should detect shift_jis or a similar/compatible encoding
    detected = detect_encoding(sjis_file).lower().replace("_", "-")
    assert "shift" in detected or "sjis" in detected or "cp932" in detected

    # Test Latin-1 (ISO-8859-1) text (umlaut: "äöü")
    latin_text = (
        "Dies ist ein längerer Text in deutscher Sprache, der in Latin-1 kodiert ist. "
        "Er enthält die Umlaute ä, ö und ü sowie das Eszett ß. Wir prüfen die automatische Erkennung."
    ).encode("latin-1")
    latin_file = tmp_path / "latin.md"
    latin_file.write_bytes(latin_text)
    detected_latin = detect_encoding(latin_file).lower().replace("_", "-")
    assert any(
        x in detected_latin
        for x in ("latin", "iso-8859", "cp125", "cp775", "cp850", "hp-roman", "utf-8")
    )


def test_read_file_with_encoding(tmp_path: Path) -> None:
    sjis_text = "こんにちは".encode("shift_jis")
    sjis_file = tmp_path / "sjis.md"
    sjis_file.write_bytes(sjis_text)

    # Manual SJIS reading
    read_manual = read_file_with_encoding(sjis_file, "shift_jis")
    assert read_manual == "こんにちは"

    # Auto SJIS reading
    read_auto = read_file_with_encoding(sjis_file, "auto")
    assert read_auto == "こんにちは"


def test_cli_encoding_flag(tmp_path: Path) -> None:
    # Shift-JIS file containing some headers
    sjis_content = "# 日本語タイトル\n\nこんにちは世界".encode("shift_jis")
    src = tmp_path / "sjis.md"
    src.write_bytes(sjis_content)
    dest = tmp_path / "output.pdf"

    # Convert specifying shift-jis
    result = runner.invoke(app, [str(src), "-o", str(dest), "--encoding", "shift-jis", "--offline"])
    assert result.exit_code == 0
    assert dest.exists()

    # Convert specifying auto-detection
    dest_auto = tmp_path / "output_auto.pdf"
    result_auto = runner.invoke(
        app, [str(src), "-o", str(dest_auto), "--encoding", "auto", "--offline"]
    )
    assert result_auto.exit_code == 0
    assert dest_auto.exists()


def test_cli_reading_error(tmp_path: Path) -> None:
    # Intentionally trigger decoding error by reading non-UTF-8 as UTF-8
    sjis_content = bytes([0x82, 0xA1, 0x82, 0xA3])  # Invalid UTF-8 sequence
    src = tmp_path / "invalid_utf8.md"
    src.write_bytes(sjis_content)

    result = runner.invoke(app, [str(src), "--encoding", "utf-8", "--offline"])
    assert result.exit_code == 1
    assert "Failed to read input file" in result.output


def test_include_resolver_encoding(tmp_path: Path) -> None:
    # Test nested inclusion of a Shift-JIS file
    main_content = "Main file\n!include sjis_inc.md"
    main_file = tmp_path / "main.md"
    main_file.write_text(main_content, encoding="utf-8")

    inc_content = "こんにちは、インクルードファイルです。".encode("shift_jis")
    inc_file = tmp_path / "sjis_inc.md"
    inc_file.write_bytes(inc_content)

    # Instantiate IncludeResolver with main file and shift-jis encoding
    resolver = IncludeResolver(main_file=str(main_file), encoding="shift_jis")
    resolved = resolver.process(main_content)
    assert "こんにちは、インクルードファイルです。" in resolved
