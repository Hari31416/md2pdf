"""Regression and integration tests using deterministic PDF outputs and text extraction."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pypdf import PdfReader
from typer.testing import CliRunner

from md2pdf.cli import app
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline
from md2pdf.core.registry import HandlerRegistry

runner = CliRunner()


def test_regression_deterministic_extraction(tmp_path: Path) -> None:
    """End-to-end regression test: convert mixed Markdown to PDF and assert text correctness."""
    fixture_path = Path(__file__).parent / "fixtures" / "regression_mixed.md"
    assert fixture_path.exists(), "Regression fixture file regression_mixed.md must exist."

    pdf_output = tmp_path / "regression_output.pdf"

    # Set up config with deterministic mode, custom header, and offline mode.
    cfg = Config(
        input_file=str(fixture_path),
        output_file=str(pdf_output),
        offline=True,
        deterministic=True,
        header="Testing: {title} | Section: {section}",
        header_on_first_page=True,
    )

    registry = HandlerRegistry()
    pipeline = Pipeline(cfg, registry)

    # Read the markdown input
    raw_md = fixture_path.read_text(encoding="utf-8")

    # Compile
    pipeline.run(raw_md)

    assert pdf_output.exists(), "PDF output must be generated successfully."

    # Parse and extract text using pypdf
    reader = PdfReader(pdf_output)

    # Assert correct number of pages
    assert len(reader.pages) == 2, "The document must be exactly 2 pages long."

    # Extract text from both pages
    page1_text = reader.pages[0].extract_text()
    page2_text = reader.pages[1].extract_text()

    # Log extracted text for debugging purposes if tests fail
    print("--- PAGE 1 EXTRACTED TEXT ---")
    print(page1_text)
    print("--- PAGE 2 EXTRACTED TEXT ---")
    print(page2_text)

    # PAGE 1 TEXT ASSERTIONS
    assert (
        "Testing: Regression Testing Report" in page1_text
    ), "Page 1 must contain the title/header text."
    assert "Page One: Document Intro" in page1_text, "Page 1 must contain the H1 heading."
    assert "bold" in page1_text, "Page 1 must contain styled text (bold)."
    assert "italic" in page1_text, "Page 1 must contain styled text (italic)."
    assert "strikethrough" in page1_text, "Page 1 must contain styled text (strikethrough)."
    assert "highlighted" in page1_text, "Page 1 must contain styled text (highlighted)."
    # ReportLab inline formatting (sub/sup) might split chunks, but text should be present.
    assert "subscripts" in page1_text
    assert "superscripts" in page1_text
    assert "Page 1" in page1_text, "Page 1 footer must contain page number 'Page 1'."

    # Footnote check - footnote 1 must be rendered at the bottom of Page 1
    assert (
        "This is the footnote text appearing on page 1." in page1_text
    ), "Footnote text must appear on Page 1."

    # PAGE 2 TEXT ASSERTIONS
    assert "Page Two: Complex Elements" in page2_text, "Page 2 must contain the H1 heading."
    assert "List Check" in page2_text, "Page 2 must contain the 'List Check' H2 heading."
    assert "First bullet item" in page2_text, "Page 2 must contain bullet list items."
    assert "Second bullet item" in page2_text, "Page 2 must contain bullet list items."
    assert "Nested bullet item" in page2_text, "Page 2 must contain nested bullet list items."
    assert "First ordered item" in page2_text, "Page 2 must contain ordered list items."

    # Admonition box text
    assert (
        "Admonition Check" in page2_text
    ), "Page 2 must contain the 'Admonition Check' H2 heading."
    assert (
        "This is an admonition block" in page2_text
    ), "Page 2 must contain the admonition content."

    # Table structure text
    assert "Table Check" in page2_text, "Page 2 must contain the 'Table Check' H2 heading."
    assert (
        "Column L" in page2_text and "Column C" in page2_text and "Column R" in page2_text
    ), "Page 2 must contain table header columns."
    assert (
        "Left aligned" in page2_text and "Centered" in page2_text and "Right aligned" in page2_text
    ), "Page 2 must contain table row content."

    # Running header updates with the current section name (H1 heading is "Page Two: Complex Elements")
    assert (
        "Section: Page Two: Complex Elements" in page2_text
    ), "Page 2 header must update with current section title."
    assert "Page 2" in page2_text, "Page 2 footer must contain page number 'Page 2'."


def test_regression_deterministic_cli(tmp_path: Path) -> None:
    """Verify that CLI output matches between two runs with --deterministic."""
    fixture_path = Path(__file__).parent / "fixtures" / "regression_mixed.md"
    pdf1 = tmp_path / "cli_out1.pdf"
    pdf2 = tmp_path / "cli_out2.pdf"

    # Run 1
    result1 = runner.invoke(
        app,
        [
            str(fixture_path),
            "-o",
            str(pdf1),
            "--offline",
            "--deterministic",
            "--header",
            "Doc: {title}",
        ],
    )
    assert result1.exit_code == 0, f"CLI compilation 1 failed: {result1.output}"
    assert pdf1.exists()

    # Run 2
    result2 = runner.invoke(
        app,
        [
            str(fixture_path),
            "-o",
            str(pdf2),
            "--offline",
            "--deterministic",
            "--header",
            "Doc: {title}",
        ],
    )
    assert result2.exit_code == 0, f"CLI compilation 2 failed: {result2.output}"
    assert pdf2.exists()

    # Assert byte-identity
    hash1 = hashlib.sha256(pdf1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(pdf2.read_bytes()).hexdigest()
    assert hash1 == hash2, "Deterministic CLI runs must yield byte-identical PDF files."
