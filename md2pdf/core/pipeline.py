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

        self.metadata: dict[str, str] = {
            "title": "",
            "author": "pymd2pdf",
            "subject": "",
            "keywords": "",
        }
        self.footnotes: dict[str, tuple[str, str]] = {}
        if self.config.input_file:
            import os

            base_name = os.path.basename(self.config.input_file)
            title_default, _ = os.path.splitext(base_name)
            self.metadata["title"] = title_default

        # Stage 1 — pre-processor registry (built-ins auto-registered).
        self._pre_registry = PreProcessorRegistry(
            register_builtins=True,
            input_file=self.config.input_file,
            emoji=getattr(self.config, "emoji", True),
            cache_dir=self.config.cache_dir,
        )

        # Stage 4 — post-processor registry.
        self._post_registry = PostProcessorRegistry()
        from md2pdf.core.postprocessors import MetadataPostProcessor, TableOfContentsPostProcessor

        self._post_registry.register(MetadataPostProcessor())
        self._post_registry.register(TableOfContentsPostProcessor())

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
        self._styles["_registry"] = self.registry

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

        from md2pdf.core.flowables import BookmarkFlowable, FootnoteFlowable

        BookmarkFlowable.page_registry.clear()
        FootnoteFlowable.page_registry.clear()
        FootnoteFlowable.page_footnotes.clear()

        md = self._pre_process(raw_md)
        tokens = self._parse(md)
        has_footnotes = any(t.get("type") == "FootnoteDefinition" for t in tokens)
        has_section_header = bool(self.config.header and "{section}" in self.config.header)

        if self.config.toc or has_footnotes or has_section_header:
            # Pass 1: Build document with dummy/empty positions to collect page/footnote mapping
            flowables = self._map(tokens)
            self._render_pass(flowables, is_final=False)

            # Pass 2: Re-build document with populated page numbers and footnotes
            md = self._pre_process(raw_md)
            tokens = self._parse(md)
            flowables = self._map(tokens)
            self._render_pass(flowables, is_final=True)
        else:
            flowables = self._map(tokens)
            self._render_pass(flowables, is_final=True)

        logger.debug("Pipeline.run: done → %s", self.config.output_file)

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _pre_process(self, raw_md: str) -> str:
        """Stage 1 — run registered pre-processors in priority order."""
        result = self._pre_registry.run_all(raw_md)
        from md2pdf.core.preprocessors import FrontMatterStripper

        for _, pp in self._pre_registry._processors:
            if isinstance(pp, FrontMatterStripper):
                self.metadata.update(pp.metadata)
        return result

    def _parse(self, md: str) -> list[dict]:
        """Stage 2 — parse Markdown into a normalised token list."""
        return MarkdownParser().parse(md)

    def _map(self, tokens: list[dict]) -> list:
        """Stage 3 — dispatch each token to its handler and collect flowables."""
        # Collect footnote definitions first
        self.footnotes.clear()
        for token in tokens:
            if token.get("type") == "FootnoteDefinition":
                label = token.get("attrs", {}).get("label", "")
                text = token.get("raw", "")
                self.footnotes[f"^{label}"] = (text, "")

        flowables = []
        for token in tokens:
            token_type = token.get("type", "")
            if token_type == "FootnoteDefinition":
                continue

            handler = self.registry.get(token_type)
            if handler:
                block_flowables = handler.render(token, self._styles)
                flowables.extend(block_flowables)

                # Recursively find all footnote references in this block token
                refs = _find_footnote_references(token)
                seen = set()
                unique_refs = []
                for r in refs:
                    if r not in seen:
                        seen.add(r)
                        unique_refs.append(r)

                for ref in unique_refs:
                    fn_key = f"^{ref}"
                    if fn_key in self.footnotes:
                        text = self.footnotes[fn_key][0]
                        from md2pdf.core.flowables import FootnoteFlowable

                        flowables.append(FootnoteFlowable(ref, text, self._styles))
            else:
                logger.warning("No handler registered for token type '%s'", token_type)
                # Fallback: render the unimplemented component as a code block
                from reportlab.platypus import Preformatted

                from md2pdf.handlers.inline import escape_xml, inline_render

                raw_content = token.get("raw", "")
                if not raw_content and token.get("children"):
                    raw_content = inline_render(token["children"], self._styles)

                repr_str = f"[{token_type} block — not implemented]"
                if raw_content:
                    repr_str += f"\n{raw_content}"

                style = self._styles.get("code_block") or self._styles.get("code_inline")
                flowables.append(Preformatted(escape_xml(repr_str), style))
        return flowables

    def _render_pass(self, flowables: list, is_final: bool) -> None:
        """Stage 4 — run post-processors then build the PDF with layout safeguards."""
        from md2pdf.core.flowables import BookmarkFlowable, ResizableImage
        from md2pdf.core.layout import LayoutComposer

        # Reset max available height for the current rendering pass
        ResizableImage.max_avail_height = 0.0
        ResizableImage.min_scale = self.config.min_image_scale

        composer = LayoutComposer()
        safe_flowables = composer.compose(flowables)

        doc = self._build_doc()
        doc._md2pdf_config = self.config
        doc._md2pdf_styles = self._styles
        doc._md2pdf_metadata = self.metadata

        doc._md2pdf_is_final = is_final
        if is_final:
            doc._md2pdf_toc_page_numbers = BookmarkFlowable.page_registry.copy()

            # Populate page_footnotes for FootnoteFlowable
            from md2pdf.core.flowables import FootnoteFlowable

            FootnoteFlowable.page_footnotes.clear()

            def extract_fns(flowables_list):
                from reportlab.platypus import KeepTogether

                result = []
                for f in flowables_list:
                    if isinstance(f, FootnoteFlowable):
                        result.append(f)
                    elif isinstance(f, KeepTogether):
                        result.extend(extract_fns(f._content))
                return result

            all_fns = extract_fns(safe_flowables)
            for f in all_fns:
                page_num = FootnoteFlowable.page_registry.get(f.label)
                if page_num is not None:
                    FootnoteFlowable.page_footnotes.setdefault(page_num, []).append(f)
        else:
            doc._md2pdf_toc_page_numbers = None

        safe_flowables = self._post_registry.run_all(doc, safe_flowables)

        # Collect bookmarks in order to determine running section headers
        bookmarks = []

        def find_bookmarks(items: list) -> list:
            res = []
            for item in items:
                from md2pdf.core.flowables import BookmarkFlowable

                if isinstance(item, BookmarkFlowable):
                    if item.title:
                        res.append(item)
                elif hasattr(item, "_content") and isinstance(item._content, list):
                    res.extend(find_bookmarks(item._content))
                elif hasattr(item, "inner") and item.inner:
                    res.extend(find_bookmarks([item.inner]))
            return res

        if is_final:
            bookmarks = find_bookmarks(safe_flowables)

        from md2pdf.core.flowables import BookmarkFlowable

        page_registry = BookmarkFlowable.page_registry

        state_first = PageCallbackState(
            header_template=self.config.header,
            header_on_first_page=self.config.header_on_first_page,
            metadata=self.metadata,
            bookmarks=bookmarks,
            page_registry=page_registry,
            is_first_page=True,
        )

        state_later = PageCallbackState(
            header_template=self.config.header,
            header_on_first_page=self.config.header_on_first_page,
            metadata=self.metadata,
            bookmarks=bookmarks,
            page_registry=page_registry,
            is_first_page=False,
        )

        doc.build(
            safe_flowables,
            onFirstPage=PageTemplateCallback(state_first),
            onLaterPages=PageTemplateCallback(state_later),
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
        """Build the base stylesheet from the active theme config.

        Font registration is performed first so that DejaVu (or any other
        bundled font) is available to ReportLab before the stylesheet
        references it by name.
        """
        try:
            from md2pdf.assets._font_registry import (  # noqa: PLC0415
                register_fonts,
                register_theme_fonts,
            )
            from md2pdf.styles.default import build_default_stylesheet  # noqa: PLC0415

            register_fonts()
            theme = getattr(self.config, "theme_config", None)
            register_theme_fonts(theme)
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


class PageCallbackState:
    """Carries dynamic document and rendering state to the page rendering callbacks."""

    def __init__(
        self,
        header_template: str,
        header_on_first_page: bool,
        metadata: dict[str, str],
        bookmarks: list,
        page_registry: dict[str, int],
        is_first_page: bool,
    ) -> None:
        self.header_template = header_template
        self.header_on_first_page = header_on_first_page
        self.metadata = metadata
        self.bookmarks = bookmarks
        self.page_registry = page_registry
        self.is_first_page = is_first_page


class PageTemplateCallback:
    """Callable wrapper that binds PageCallbackState to reportlab's page template callbacks."""

    def __init__(self, state: PageCallbackState) -> None:
        self.state = state

    def __call__(self, canvas, doc) -> None:
        draw_page_number(canvas, doc, state=self.state)


def _get_current_section(page_num: int, bookmarks: list, page_registry: dict[str, int]) -> str:
    """Retrieve the title of the heading applying to the current page number."""
    best_title = ""
    best_page = -1
    best_level = 99

    # First pass: try to find the most recent H1/H2 heading (level <= 1)
    for b in bookmarks:
        p = page_registry.get(b.key)
        if p is not None and p <= page_num:
            if b.level <= 1:
                if p > best_page or (p == best_page and b.level < best_level):
                    best_title = b.title
                    best_page = p
                    best_level = b.level

    # If no H1/H2 heading found, fall back to any heading level
    if not best_title:
        for b in bookmarks:
            p = page_registry.get(b.key)
            if p is not None and p <= page_num:
                if p > best_page:
                    best_title = b.title
                    best_page = p
                    best_level = b.level

    return best_title


def draw_page_number(canvas, doc, state: PageCallbackState | None = None) -> None:
    """Draw the 'Page X' footer centered/aligned on each page."""
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    page_text = f"Page {canvas.getPageNumber()}"
    canvas.drawRightString(doc.pagesize[0] - 20 * mm, 15, page_text)

    if state and state.header_template:
        should_draw = True
        if state.is_first_page and not state.header_on_first_page:
            should_draw = False

        if should_draw:
            header_text = state.header_template
            if "{title}" in header_text:
                title = state.metadata.get("title", "")
                header_text = header_text.replace("{title}", title)
            if "{section}" in header_text:
                section = _get_current_section(
                    canvas.getPageNumber(), state.bookmarks, state.page_registry
                )
                header_text = header_text.replace("{section}", section)

            header_text = header_text.strip()
            if header_text:
                canvas.drawString(20 * mm, doc.pagesize[1] - 15 * mm, header_text)

                canvas.setStrokeColor(colors.HexColor("#cccccc"))
                canvas.setLineWidth(0.5)
                canvas.line(
                    20 * mm,
                    doc.pagesize[1] - 18 * mm,
                    doc.pagesize[0] - 20 * mm,
                    doc.pagesize[1] - 18 * mm,
                )

    canvas.restoreState()


def _find_footnote_references(token: dict) -> list[str]:
    refs = []
    if token.get("type") == "FootnoteReference":
        raw = token.get("raw", "")
        if raw:
            refs.append(raw)
    for child in token.get("children", []):
        refs.extend(_find_footnote_references(child))
    return refs
