"""Integration tests for the End-to-End md2pdf Pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from md2pdf.core.config import Config
from md2pdf.core.pipeline import Pipeline

if TYPE_CHECKING:
    from md2pdf.core.registry import HandlerRegistry


def test_simple_doc_produces_pdf(
    simple_md: str, tmp_pdf: Path, default_registry: HandlerRegistry
) -> None:
    """Verify that a basic markdown input is parsed and rendered to a valid PDF file."""
    cfg = Config(input_file="", output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(simple_md)

    assert tmp_pdf.exists()
    assert tmp_pdf.stat().st_size > 1000  # Non-trivial sized PDF


def test_mermaid_offline_uses_placeholder(tmp_pdf: Path, default_registry: HandlerRegistry) -> None:
    """Verify that offline diagram parsing runs successfully using fallbacks."""
    diagrams_md = "# Diagrams\n\n" "```mermaid\n" "graph TD\n" "  A --> B\n" "```\n"
    cfg = Config(
        input_file="", output_file=str(tmp_pdf), cache_dir=str(tmp_pdf.parent), offline=True
    )
    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(diagrams_md)

    assert tmp_pdf.exists()
    assert tmp_pdf.stat().st_size > 1000


def test_validate_empty_mermaid(default_registry: HandlerRegistry) -> None:
    """Verify that validate() method flags empty diagram syntax."""
    cfg = Config(input_file="", output_file="out.pdf", offline=True)
    pipeline = Pipeline(cfg, default_registry)
    issues = pipeline.validate("```mermaid\n\n```\n")

    assert any(i.code == "EMPTY_DIAGRAM" for i in issues)


def test_offline_uses_cached_image_on_cache_hit(
    tmp_pdf: Path, default_registry: HandlerRegistry
) -> None:
    """Verify that offline mode correctly renders the cached diagram if it is a cache hit."""
    from md2pdf.assets.cache import AssetCache

    # Pre-populate the cache with dummy PNG bytes for the diagram
    cache = AssetCache(str(tmp_pdf.parent))
    dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    source = "graph TD\n  A --> B"
    cache.put("mermaid", source, dummy_png)

    diagrams_md = f"# Diagrams\n\n```mermaid\n{source}\n```\n"
    cfg = Config(
        input_file="", output_file=str(tmp_pdf), cache_dir=str(tmp_pdf.parent), offline=True
    )
    pipeline = Pipeline(cfg, default_registry)
    pipeline.run(diagrams_md)

    assert tmp_pdf.exists()
    assert tmp_pdf.stat().st_size > 1000
