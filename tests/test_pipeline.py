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

    # Directly run pipeline._map on a dummy unregistered token
    tokens = [{"type": "DummyUnimplementedToken", "raw": "unimplemented raw content"}]
    flowables = pipeline._map(tokens)

    # It should fall back to rendering as Preformatted code block containing the fallback text
    from reportlab.platypus import Preformatted

    assert len(flowables) == 1
    assert isinstance(flowables[0], Preformatted)
    assert any("DummyUnimplementedToken block" in line for line in flowables[0].lines)


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


def test_paragraph_handler_markdown_image(tmp_path: Path) -> None:
    """Verify that standard Markdown images in paragraphs render to ResizableImage flowables."""
    from PIL import Image as PILImage

    from md2pdf.core.flowables import ResizableImage
    from md2pdf.handlers.paragraph import ParagraphHandler

    # Create a dummy image file
    img_path = tmp_path / "test.png"
    PILImage.new("RGB", (100, 100), "blue").save(img_path)

    # Paragraph with one Image child
    token = {
        "type": "Paragraph",
        "children": [
            {
                "type": "Image",
                "attrs": {"target": str(img_path), "title": "My Title"},
                "children": [{"type": "RawText", "raw": "Alt text"}],
            }
        ],
    }

    # Setup styles with config reference
    cfg = Config(input_file=str(tmp_path / "dummy.md"), output_file="out.pdf")
    from md2pdf.styles.default import build_default_stylesheet

    styles = build_default_stylesheet()
    styles["_config"] = cfg

    from reportlab.platypus import KeepTogether

    handler = ParagraphHandler()
    flowables = handler.render(token, styles)

    assert len(flowables) == 1
    assert isinstance(flowables[0], KeepTogether)
    assert isinstance(flowables[0]._content[0], ResizableImage)


def test_paragraph_handler_html_image(tmp_path: Path) -> None:
    """Verify that HTML img tags in paragraphs are parsed and render to ResizableImage flowables."""
    from PIL import Image as PILImage

    from md2pdf.core.flowables import ResizableImage
    from md2pdf.handlers.paragraph import ParagraphHandler

    img_path = tmp_path / "test_html.png"
    PILImage.new("RGB", (200, 100), "red").save(img_path)

    # Paragraph with RawText containing HTML img tag
    html_str = f'Before <img src="{img_path}" width="50%" height="100px" alt="test" /> After'
    token = {
        "type": "Paragraph",
        "children": [{"type": "RawText", "raw": html_str}],
    }

    cfg = Config(input_file=str(tmp_path / "dummy.md"), output_file="out.pdf")
    from md2pdf.styles.default import build_default_stylesheet

    styles = build_default_stylesheet()
    styles["_config"] = cfg

    from reportlab.platypus import KeepTogether

    handler = ParagraphHandler()
    flowables = handler.render(token, styles)

    # Should split into: Paragraph ("Before"), KeepTogether(ResizableImage, Paragraph), Paragraph ("After")
    assert len(flowables) == 3
    assert flowables[0].text == "Before"
    assert isinstance(flowables[1], KeepTogether)
    img = flowables[1]._content[0]
    assert isinstance(img, ResizableImage)
    assert img.drawWidth == 225.0
    assert img.drawHeight == 100.0
    assert flowables[2].text == "After"


def test_paragraph_handler_missing_image(tmp_path: Path) -> None:
    """Verify that a missing image target produces a PlaceholderBox."""
    from md2pdf.assets.fallback import PlaceholderBox
    from md2pdf.handlers.paragraph import ParagraphHandler

    # Image that does not exist
    token = {
        "type": "Paragraph",
        "children": [
            {
                "type": "Image",
                "attrs": {"target": "nonexistent.png", "title": "Missing"},
                "children": [],
            }
        ],
    }

    cfg = Config(input_file=str(tmp_path / "dummy.md"), output_file="out.pdf")
    from md2pdf.styles.default import build_default_stylesheet

    styles = build_default_stylesheet()
    styles["_config"] = cfg

    handler = ParagraphHandler()
    flowables = handler.render(token, styles)

    assert len(flowables) == 1
    assert isinstance(flowables[0], PlaceholderBox)


def test_cli_config_auto_discovery(tmp_path: Path, monkeypatch) -> None:
    """Verify auto-discovery of md2pdf.toml in search path (CWD -> ~/.config -> ~)."""
    from typer.testing import CliRunner

    from md2pdf.cli import app

    runner = CliRunner()

    # Create a config in tmp_path (which we will mock as CWD)
    config_content = '[md2pdf]\noffline = true\ntheme = "legal"\n'
    cfg_file = tmp_path / "md2pdf.toml"
    cfg_file.write_text(config_content, encoding="utf-8")

    # Write a dummy markdown
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test Title", encoding="utf-8")

    # Change working directory to tmp_path using monkeypatch
    monkeypatch.chdir(tmp_path)

    # Run CLI without --config option
    result = runner.invoke(app, [str(md_file), "-o", "out.pdf", "--validate-only"])
    assert result.exit_code == 0


def test_pipeline_with_admonitions(tmp_path: Path) -> None:
    """Verify that a document containing admonitions and alerts is successfully built to PDF."""
    from md2pdf import convert

    md_content = """
# Showcase Document

:::note "Custom Note Title"
This is a standard admonition block with some *formatting* inside.
:::

> [!WARNING]
> This is a GitHub-style alert warning!
"""
    input_file = tmp_path / "test_admonitions.md"
    input_file.write_text(md_content, encoding="utf-8")
    output_file = tmp_path / "output_admonitions.pdf"

    convert(str(input_file), str(output_file))

    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_pipeline_with_pagebreaks(tmp_path: Path) -> None:
    """Verify that a document containing page breaks is successfully built to PDF."""
    from md2pdf import convert
    from md2pdf.core.config import Config
    from md2pdf.core.pipeline import Pipeline

    md_content = """
# Page 1

<!-- pagebreak -->

# Page 2

\\pagebreak

# Page 3
"""
    input_file = tmp_path / "test_pagebreaks.md"
    input_file.write_text(md_content, encoding="utf-8")
    output_file = tmp_path / "output_pagebreaks.pdf"

    cfg = Config(input_file=str(input_file), output_file=str(output_file))
    pipeline = Pipeline(cfg)

    # Process stage by stage and check mapped flowables
    md = pipeline._pre_process(md_content)
    tokens = pipeline._parse(md)
    flowables = pipeline._map(tokens)

    # Let's count how many PageBreak flowables we have in mapped flowables
    from reportlab.platypus import PageBreak

    page_breaks = [f for f in flowables if isinstance(f, PageBreak)]
    assert len(page_breaks) == 2

    # Now verify that it converts end-to-end without raising errors
    convert(str(input_file), str(output_file))
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_pipeline_metadata_leak_prevented(tmp_path: Path) -> None:
    """Verify that metadata from one run does not leak into a subsequent run of the same Pipeline instance."""
    cfg = Config(input_file="", output_file=str(tmp_path / "out1.pdf"), offline=True)
    pipeline = Pipeline(cfg)

    # Document 1 has YAML front matter
    doc1 = "---\ntitle: Doc 1 Title\nauthor: Doc 1 Author\n---\n# Content"
    pipeline.run(doc1)
    assert pipeline.metadata["title"] == "Doc 1 Title"
    assert pipeline.metadata["author"] == "Doc 1 Author"

    # Document 2 has no front matter
    cfg.output_file = str(tmp_path / "out2.pdf")
    doc2 = "# Content Without Metadata"
    pipeline.run(doc2)
    assert pipeline.metadata["title"] == ""
    assert pipeline.metadata["author"] == "pymd2pdf"


def test_pipeline_defensive_registry_clobbering(tmp_path: Path) -> None:
    """Verify that built-in handlers registered during Pipeline init do not clobber custom ones in the passed registry."""
    from reportlab.platypus import Paragraph

    from md2pdf.core.registry import ElementHandler, HandlerRegistry

    class CustomParagraphHandler(ElementHandler):
        token_type = "Paragraph"

        def render(self, token: dict, styles: dict) -> list:
            return [Paragraph("CUSTOM PARAGRAPH", styles["body"])]

    custom_registry = HandlerRegistry()
    custom_registry.register(CustomParagraphHandler())

    cfg = Config(input_file="", output_file=str(tmp_path / "out.pdf"), offline=True)
    pipeline = Pipeline(cfg, custom_registry)

    # The custom handler should not be overwritten by the default ParagraphHandler during register_builtins
    paragraph_handler = pipeline.registry.get("Paragraph")
    assert isinstance(paragraph_handler, CustomParagraphHandler)
