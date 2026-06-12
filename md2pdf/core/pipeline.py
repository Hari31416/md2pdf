"""Linear Markdown-to-PDF conversion pipeline."""

from __future__ import annotations

import logging

from md2pdf.core.config import Config
from md2pdf.core.errors import ValidationIssue
from md2pdf.core.parser import MarkdownParser
from md2pdf.core.plugin_loader import PluginLoader
from md2pdf.core.postprocessors import PostProcessorRegistry
from md2pdf.core.preprocessors import PreProcessorRegistry
from md2pdf.core.registry import HandlerRegistry
from md2pdf.core.styles import StyleRegistry

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the four-stage Markdown → PDF conversion.

    Stage responsibilities:

    1. ``_pre_process``  — text-level transforms (front-matter, includes)
    2. ``_parse``        — mistletoe AST → normalised token list
    3. ``_map``          — token list → ReportLab Flowable list
    4. ``_render``       — post-processors + PDF file on disk (Phase 6)

    Plugin system (Phase 5):

    - :class:`~md2pdf.core.preprocessors.PreProcessorRegistry` drives Stage 1.
    - :class:`~md2pdf.core.registry.HandlerRegistry` drives Stage 3.
    - :class:`~md2pdf.core.postprocessors.PostProcessorRegistry` runs in Stage 4.
    - :class:`~md2pdf.core.styles.StyleRegistry` merges base + plugin stylesheets.
    - :class:`~md2pdf.core.plugin_loader.PluginLoader` performs discovery.
    """

    def __init__(self, config: Config, registry: HandlerRegistry | None = None) -> None:
        self.config = config
        self.registry = HandlerRegistry()

        # Stage 1 — pre-processor registry (built-ins auto-registered).
        self._pre_registry = PreProcessorRegistry(
            register_builtins=True, input_file=self.config.input_file
        )

        # Stage 4 — post-processor registry.
        self._post_registry = PostProcessorRegistry()

        # Stylesheet registry — base layer added immediately; plugins add more.
        self._style_registry = StyleRegistry()
        self._style_registry.add_layer(self._build_base_styles())

        # Plugin discovery — entry points + config-file declared plugins.
        loader = PluginLoader(
            handler_registry=self.registry,
            pre_registry=self._pre_registry,
            post_registry=self._post_registry,
            style_registry=self._style_registry,
        )
        loader.register_builtins(self.registry)
        loader.load_entry_points()
        loader.load_from_config(config.plugins_dict)

        # Register asset handlers (need KrokiClient + AssetCache).
        # This is done last so that the pipeline's configured asset handlers
        # take precedence and override default handlers loaded from entry points.
        self._register_asset_handlers()

        # Overlay any user-provided custom handlers last so they take highest
        # precedence and avoid mutating the passed-in registry object.
        if registry is not None:
            for _, handler in registry._handlers.items():
                self.registry.register(handler)

        # Build the final merged stylesheet after all plugin layers are in.
        self._styles: dict = self._style_registry.build()
        self._styles["_config"] = self.config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, raw_md: str) -> list[ValidationIssue]:
        """Stage 1.5 — pre-render validation gate.

        Args:
            raw_md: Raw markdown text.

        Returns:
            A list of ValidationIssue instances.
        """
        from md2pdf.core.validator import DocumentValidator

        md = self._pre_process(raw_md)
        tokens = self._parse(md)
        validator = DocumentValidator()
        return validator.validate(tokens)

    def run(self, raw_md: str) -> None:
        """Execute the full conversion pipeline end-to-end.

        Args:
            raw_md: Raw markdown string read from the source file.
        """
        logger.debug("Pipeline.run: starting")
        issues = self.validate(raw_md)
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        for w in warnings:
            logger.warning("[%s] Line %s: %s", w.code, w.line, w.message)
        for e in errors:
            logger.error("[%s] Line %s: %s", e.code, e.line, e.message)

        md = self._pre_process(raw_md)
        tokens = self._parse(md)
        flowables = self._map(tokens)
        self._render(flowables)
        logger.debug("Pipeline.run: done → %s", self.config.output_file)

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _pre_process(self, raw_md: str) -> str:
        """Stage 1 — run registered pre-processors in priority order."""
        return self._pre_registry.run_all(raw_md)

    def _parse(self, md: str) -> list[dict]:
        """Stage 2 — parse Markdown into a normalised token list."""
        return MarkdownParser().parse(md)

    def _map(self, tokens: list[dict]) -> list:
        """Stage 3 — dispatch each token to its handler and collect flowables."""
        flowables = []
        for token in tokens:
            token_type = token.get("type", "")
            handler = self.registry.get(token_type)
            if handler:
                flowables.extend(handler.render(token, self._styles))
            else:
                logger.warning("No handler registered for token type '%s'", token_type)
                # Fallback: render the unimplemented component as a code block
                from reportlab.platypus import Preformatted

                from md2pdf.handlers.code import clean_box_drawing
                from md2pdf.handlers.inline import escape_xml, inline_render

                raw_content = token.get("raw", "")
                if not raw_content and token.get("children"):
                    raw_content = inline_render(token["children"], self._styles)

                # Clean box drawing characters for compatibility
                raw_content = clean_box_drawing(raw_content)

                repr_str = f"[{token_type} block — not implemented]"
                if raw_content:
                    repr_str += f"\n{raw_content}"

                style = self._styles.get("code_block") or self._styles.get("code_inline")
                flowables.append(Preformatted(escape_xml(repr_str), style))
        return flowables

    def _render(self, flowables: list) -> None:
        """Stage 4 — run post-processors then build the PDF with layout safeguards."""
        from md2pdf.core.flowables import ResizableImage

        # Reset max available height for the current rendering pass
        ResizableImage.max_avail_height = 0.0
        ResizableImage.min_scale = self.config.min_image_scale

        from md2pdf.core.layout import LayoutComposer

        composer = LayoutComposer()
        safe_flowables = composer.compose(flowables)

        doc = self._build_doc()
        safe_flowables = self._post_registry.run_all(doc, safe_flowables)

        doc.build(
            safe_flowables,
            onFirstPage=draw_page_number,
            onLaterPages=draw_page_number,
        )

    def _build_doc(self):
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate

        return SimpleDocTemplate(
            self.config.output_file,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=22 * mm,
            bottomMargin=22 * mm,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_base_styles(self) -> dict:
        """Build the base stylesheet from the active theme config."""
        try:
            from md2pdf.styles.default import build_default_stylesheet  # noqa: PLC0415

            theme = getattr(self.config, "theme_config", None)
            return build_default_stylesheet(theme)
        except Exception:
            logger.debug("Could not build stylesheet; using empty styles dict", exc_info=True)
            return {}

    def _register_asset_handlers(self) -> None:
        """Instantiate and register Mermaid and LaTeX asset handlers."""
        try:
            from md2pdf.assets.cache import AssetCache  # noqa: PLC0415
            from md2pdf.assets.kroki import KrokiClient  # noqa: PLC0415
            from md2pdf.handlers.latex import LatexHandler  # noqa: PLC0415
            from md2pdf.handlers.mermaid import MermaidHandler  # noqa: PLC0415

            cache = AssetCache(self.config.cache_dir)
            client = KrokiClient()
            offline = getattr(self.config, "offline", False)

            self.registry.register(MermaidHandler(client, cache, offline))
            self.registry.register(LatexHandler(client, cache, offline))
        except Exception:
            logger.debug("Could not register asset handlers", exc_info=True)


def draw_page_number(canvas, doc) -> None:
    """Draw the 'Page X' footer centered/aligned on each page."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    page_text = f"Page {canvas.getPageNumber()}"
    canvas.drawRightString(doc.pagesize[0] - 20 * mm, 15, page_text)
    canvas.restoreState()
