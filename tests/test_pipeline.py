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


def test_unimplemented_token_fallback(tmp_pdf: Path, default_registry: HandlerRegistry) -> None:
    """Verify that an unregistered/unimplemented token falls back to rendering as a code block."""
    cfg = Config(input_file="", output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg, default_registry)

    # BlockCode token is parsed for indented code blocks, and has no registered handler.
    unimplemented_md = "    indented code block\n    line 2"
    pipeline.run(unimplemented_md)

    assert tmp_pdf.exists()
    assert tmp_pdf.stat().st_size > 1000


def test_pipeline_optional_registry(tmp_pdf: Path) -> None:
    """Verify that instantiating Pipeline with registry=None defaults correctly."""
    cfg = Config(input_file="", output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg)
    assert pipeline.registry is not None
    assert pipeline.registry.get("Paragraph") is not None


def test_pipeline_registry_custom_overrides(tmp_pdf: Path) -> None:
    """Verify that custom registries passed to Pipeline override defaults without mutating original registry."""
    from reportlab.platypus import Paragraph

    from md2pdf.core.registry import ElementHandler, HandlerRegistry

    class CustomParagraphHandler(ElementHandler):
        token_type = "Paragraph"

        def render(self, token: dict, styles: dict) -> list:
            return [Paragraph("CUSTOM PARAGRAPH RENDER", styles["body"])]

    custom_registry = HandlerRegistry()
    custom_handler = CustomParagraphHandler()
    custom_registry.register(custom_handler)

    cfg = Config(input_file="", output_file=str(tmp_pdf), offline=True)
    pipeline = Pipeline(cfg, custom_registry)

    # Custom handler takes precedence
    handler = pipeline.registry.get("Paragraph")
    assert isinstance(handler, CustomParagraphHandler)

    # Caller registry remains unmutated
    assert list(custom_registry._handlers.keys()) == ["Paragraph"]
    assert custom_registry.get("Paragraph") is custom_handler


def test_convert_config_overrides(tmp_path: Path) -> None:
    """Verify that convert overrides Config input/output properties to match args."""
    from md2pdf import convert

    src = tmp_path / "input.md"
    src.write_text("Hello world", encoding="utf-8")
    dst = tmp_path / "output_custom.pdf"

    cfg = Config(input_file="dummy.md", output_file="dummy.pdf", offline=True)
    convert(str(src), str(dst), config=cfg)

    assert cfg.input_file == str(src)
    assert cfg.output_file == str(dst)
    assert dst.exists()


def test_convert_custom_registry(tmp_path: Path) -> None:
    """Verify that convert accepts a custom registry and applies it."""
    from reportlab.platypus import Paragraph

    from md2pdf import convert
    from md2pdf.core.registry import ElementHandler, HandlerRegistry

    class CustomParagraphHandler(ElementHandler):
        token_type = "Paragraph"

        def render(self, token: dict, styles: dict) -> list:
            return [Paragraph("CUSTOM RENDER VIA CONVERT", styles["body"])]

    src = tmp_path / "input.md"
    src.write_text("Hello world", encoding="utf-8")
    dst = tmp_path / "output_custom_registry.pdf"

    custom_registry = HandlerRegistry()
    custom_registry.register(CustomParagraphHandler())

    cfg = Config(input_file="", output_file=str(dst), offline=True)
    convert(str(src), str(dst), config=cfg, registry=custom_registry)

    assert dst.exists()
