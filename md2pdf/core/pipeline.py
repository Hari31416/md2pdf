"""Linear Markdown-to-PDF conversion pipeline."""

from __future__ import annotations

import logging

from md2pdf.core.config import Config
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

    def __init__(self, config: Config, registry: HandlerRegistry) -> None:
        self.config = config
        self.registry = registry

        # Stage 1 — pre-processor registry (built-ins auto-registered).
        self._pre_registry = PreProcessorRegistry(register_builtins=True)

        # Stage 4 — post-processor registry.
        self._post_registry = PostProcessorRegistry()

        # Stylesheet registry — base layer added immediately; plugins add more.
        self._style_registry = StyleRegistry()
        self._style_registry.add_layer(self._build_base_styles())

        # Register asset handlers (need KrokiClient + AssetCache).
        self._register_asset_handlers()

        # Plugin discovery — entry points + config-file declared plugins.
        loader = PluginLoader(
            handler_registry=self.registry,
            pre_registry=self._pre_registry,
            post_registry=self._post_registry,
            style_registry=self._style_registry,
        )
        loader.load_entry_points()
        loader.load_from_config(config.plugins_dict)

        # Build the final merged stylesheet after all plugin layers are in.
        self._styles: dict = self._style_registry.build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, raw_md: str) -> None:
        """Execute the full conversion pipeline end-to-end.

        Args:
            raw_md: Raw markdown string read from the source file.
        """
        logger.debug("Pipeline.run: starting")
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
        return flowables

    def _render(self, flowables: list) -> None:
        """Stage 4 — run post-processors then build PDF (PDF build in Phase 6)."""
        # Post-processors run even though the actual PDF build is a Phase 6 stub.
        # They are called here so plugins can be wired up end-to-end before Phase 6.
        try:
            from reportlab.platypus import SimpleDocTemplate  # noqa: PLC0415

            doc = SimpleDocTemplate(self.config.output_file)
            flowables = self._post_registry.run_all(doc, flowables)
            if flowables:
                logger.debug(
                    "_render: %d flowables after post-processing (PDF build not yet implemented)",
                    len(flowables),
                )
        except Exception:
            logger.debug("_render: post-processing skipped (reportlab unavailable)", exc_info=True)
            if flowables:
                logger.debug(
                    "_render: %d flowables (PDF build not yet implemented)", len(flowables)
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
