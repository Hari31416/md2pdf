"""Tests for PDF metadata generation in the Pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline


def test_pdf_metadata_defaults(tmp_path: Path) -> None:
    """Verify that default metadata (author: 'pymd2pdf', title: filename) is set when no front-matter is present."""
    md_file = tmp_path / "hello_world.md"
    md_file.write_text("# Hello World\nJust some text.", encoding="utf-8")
    
    pdf_file = tmp_path / "hello_world.pdf"
    
    cfg = Config(input_file=str(md_file), output_file=str(pdf_file), offline=True)
    pipeline = Pipeline(cfg)
    pipeline.run(md_file.read_text(encoding="utf-8"))
    
    assert pdf_file.exists()
    content = pdf_file.read_bytes()
    
    # Check default author "pymd2pdf"
    assert b"pymd2pdf" in content
    # Check default title "hello_world" (filename without extension)
    assert b"hello_world" in content


def test_pdf_metadata_from_front_matter(tmp_path: Path) -> None:
    """Verify that front-matter values override the default metadata."""
    md_content = """---
title: Custom Document Title
author: Jane Author
subject: Integration Testing
keywords: pytest, md2pdf, metadata
---
# Main Heading
Some content here.
"""
    md_file = tmp_path / "custom_doc.md"
    md_file.write_text(md_content, encoding="utf-8")
    
    pdf_file = tmp_path / "custom_doc.pdf"
    
    cfg = Config(input_file=str(md_file), output_file=str(pdf_file), offline=True)
    pipeline = Pipeline(cfg)
    pipeline.run(md_content)
    
    assert pdf_file.exists()
    content = pdf_file.read_bytes()
    
    assert b"Custom Document Title" in content
    assert b"Jane Author" in content
    assert b"Integration Testing" in content
    assert b"pytest, md2pdf, metadata" in content


def test_pdf_metadata_partial_front_matter(tmp_path: Path) -> None:
    """Verify that specifying only some front-matter keys overrides those, while others keep defaults."""
    md_content = """---
title: Another Title
---
# Main Heading
Some content here.
"""
    md_file = tmp_path / "partial_doc.md"
    md_file.write_text(md_content, encoding="utf-8")
    
    pdf_file = tmp_path / "partial_doc.pdf"
    
    cfg = Config(input_file=str(md_file), output_file=str(pdf_file), offline=True)
    pipeline = Pipeline(cfg)
    pipeline.run(md_content)
    
    assert pdf_file.exists()
    content = pdf_file.read_bytes()
    
    assert b"Another Title" in content
    assert b"pymd2pdf" in content  # should keep default author
