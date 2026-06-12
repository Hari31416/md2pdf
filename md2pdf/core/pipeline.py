"""Linear Markdown-to-PDF conversion pipeline."""

from __future__ import annotations

import logging

from md2pdf.core.config import Config
from md2pdf.core.parser import MarkdownParser
from md2pdf.core.preprocessors import FrontMatterStripper, PreProcessor
from md2pdf.core.registry import HandlerRegistry

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the four-stage Markdown → PDF conversion.

    Stage responsibilities:

    1. ``_pre_process``  — text-level transforms (front-matter, includes) [Phase 2]
    2. ``_parse``        — mistletoe AST → normalised token list           [Phase 2]
    3. ``_map``          — token list → ReportLab Flowable list            [Phase 3]
    4. ``_render``       — Flowable list → PDF file on disk                [Phase 6]
    """

    def __init__(self, config: Config, registry: HandlerRegistry) -> None:
        self.config = config
        self.registry = registry

        # Ordered list of pre-processors.  FrontMatterStripper runs first by default.
        self._preprocessors: list[PreProcessor] = [FrontMatterStripper()]

        # Stylesheet dict built from ThemeConfig — populated here so that
        # handlers can access styles without a separate initialisation call.
        self._styles: dict = self._build_styles()

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
        """Stage 1 — run registered pre-processors in order."""
        for pp in self._preprocessors:
            raw_md = pp.process(raw_md)
        return raw_md

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
        """Stage 4 placeholder — no-op until Phase 6."""
        if flowables:
            logger.debug("_render: %d flowables (PDF build not yet implemented)", len(flowables))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_styles(self) -> dict:
        """Build the stylesheet from the active theme config.

        Importing here avoids a circular-import issue at module load time,
        since styles/ imports from reportlab which may not be available in
        all test environments without the optional dependency installed.
        """
        try:
            from md2pdf.styles.default import build_default_stylesheet

            theme = getattr(self.config, "theme_config", None)
            return build_default_stylesheet(theme)
        except Exception:
            logger.debug("Could not build stylesheet; using empty styles dict", exc_info=True)
            return {}
