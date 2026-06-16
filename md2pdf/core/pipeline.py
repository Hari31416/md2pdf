"""Linear Markdown-to-PDF conversion pipeline."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from reportlab.platypus import SimpleDocTemplate

from md2pdf.core.config import Config
from md2pdf.core.errors import ConfigError, ValidationIssue
from md2pdf.core.parser import MarkdownParser
from md2pdf.core.plugin_loader import PluginLoader
from md2pdf.core.postprocessors import PostProcessorRegistry
from md2pdf.core.preprocessors import PreProcessorRegistry
from md2pdf.core.registry import HandlerRegistry
from md2pdf.core.styles import StyleRegistry

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger(__name__)


class MD2PDFDocTemplate(SimpleDocTemplate):
    """Custom document template that dynamically adjusts the page frame bottom margin
    to accommodate footnotes without causing layouts to overlap.
    """

    def handle_pageBegin(self) -> None:
        super().handle_pageBegin()
        page_num = self.page
        from md2pdf.core.flowables import FootnoteFlowable

        if hasattr(self, "_md2pdf_config") and self._md2pdf_config:
            theme = self._md2pdf_config.theme_config
            if theme is not None:
                bg_color = getattr(theme, "color_page_bg", "#ffffff")
                if bg_color and bg_color.lower() != "#ffffff":
                    self.canv.saveState()
                    self.canv.setFillColor(theme.hex("color_page_bg"))
                    self.canv.rect(0, 0, self.pagesize[0], self.pagesize[1], fill=1, stroke=0)
                    self.canv.restoreState()

        if hasattr(self, "_footnote_page_footnotes"):
            fns = self._footnote_page_footnotes.get(page_num, [])
        else:
            fns = FootnoteFlowable.page_footnotes.get(page_num, [])
        frame = self.frame
        if frame:
            if not hasattr(frame, "_orig_y1"):
                frame._orig_y1 = frame.y1
                frame._orig_height = frame.height

        if fns:
            total_H = sum(f.get_height(self.width, self.height) for f in fns)
            max_H = frame._orig_height * 0.5
            if total_H > max_H:
                total_H = max_H
            frame.y1 = frame._orig_y1 + total_H
            frame.height = frame._orig_height - total_H
        else:
            frame.y1 = frame._orig_y1
            frame.height = frame._orig_height

        frame._reset()


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

    def __init__(
        self,
        config: Config,
        registry: HandlerRegistry | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.config = config
        self.registry = HandlerRegistry()
        if registry is not None:
            self.registry._handlers.update(registry._handlers)
        self._progress_callback = None
        self.progress_callback = progress_callback

        self.bookmark_page_registry: dict[str, int] = {}
        self.footnote_page_registry: dict[str, int] = {}
        self.footnote_page_footnotes: dict[int, list] = {}

        self.footnotes: dict[str, tuple[str, str]] = {}
        self._reset_metadata()

        # Stage 1 — pre-processor registry (built-ins auto-registered).
        self._pre_registry = PreProcessorRegistry(
            register_builtins=True,
            input_file=self.config.input_file,
            emoji=getattr(self.config, "emoji", True),
            cache_dir=self.config.cache_dir,
            progress_callback=self.progress_callback,
            encoding=getattr(self.config, "encoding", "utf-8"),
        )

        # Stage 4 — post-processor registry.
        self._post_registry = PostProcessorRegistry()
        from md2pdf.core.postprocessors import (
            CoverPagePostProcessor,
            MetadataPostProcessor,
            TableOfContentsPostProcessor,
        )

        self._post_registry.register(MetadataPostProcessor())
        self._post_registry.register(TableOfContentsPostProcessor())
        self._post_registry.register(CoverPagePostProcessor())

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
        loader.register_builtins(self.registry, cache_dir=self.config.cache_dir)
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
        from reportlab.lib.units import mm

        from md2pdf.core.config import resolve_page_geometry

        pagesize = resolve_page_geometry(self.config.page_size, self.config.orientation)

        self._styles["_page_width"] = pagesize[0]
        self._styles["_left_margin"] = 20 * mm
        self._styles["_right_margin"] = 20 * mm

    def _reset_metadata(self) -> None:
        self.metadata = {
            "title": "",
            "author": "pymd2pdf",
            "subject": "",
            "keywords": "",
            "date": "",
        }
        self.parsed_metadata_keys = set()
        if self.config.input_file:
            import os

            base_name = os.path.basename(self.config.input_file)
            title_default, _ = os.path.splitext(base_name)
            self.metadata["title"] = title_default
        if hasattr(self, "_pre_registry") and self._pre_registry:
            self._pre_registry.reset()

    @property
    def progress_callback(self) -> Callable[[str, dict[str, Any]], None] | None:
        return getattr(self, "_progress_callback", None)

    @progress_callback.setter
    def progress_callback(self, val: Callable[[str, dict[str, Any]], None] | None) -> None:
        self._progress_callback = val
        if hasattr(self, "_pre_registry") and self._pre_registry:
            self._pre_registry.progress_callback = val

    @property
    def watched_files(self) -> set[str]:
        """Return absolute paths of all source and recursively included files parsed."""
        import os

        from md2pdf.core.preprocessors import IncludeResolver

        files = set()
        if self.config.input_file:
            files.add(os.path.abspath(self.config.input_file))

        if hasattr(self, "_pre_registry") and self._pre_registry:
            for _, pp in self._pre_registry._processors:
                if isinstance(pp, IncludeResolver):
                    files.update(pp.resolved_files)
        return files

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

        self._reset_metadata()
        self._pre_registry.reset()
        md = self._pre_process(raw_md)
        tokens = self._parse(md)
        validator = DocumentValidator(self.registry)
        return validator.validate(tokens)

    def run(self, raw_md: str) -> None:
        """Execute the full conversion pipeline end-to-end.

        Args:
            raw_md: Raw markdown string read from the source file.
        """
        logger.debug("Pipeline.run: starting")
        self._reset_metadata()
        self._pre_registry.reset()

        # Temporarily suppress progress reporting during validation gate
        original_callback = self.progress_callback
        self.progress_callback = None
        try:
            issues = self.validate(raw_md)
        finally:
            self.progress_callback = original_callback

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

        self.bookmark_page_registry.clear()
        self.footnote_page_registry.clear()
        self.footnote_page_footnotes.clear()

        if self.progress_callback:
            self.progress_callback("preprocess_start", {})
        md = self._pre_process(raw_md)

        if self.progress_callback:
            self.progress_callback("parse_start", {})
        tokens = self._parse(md)

        has_footnotes = any(t.get("type") == "FootnoteDefinition" for t in tokens)
        has_section_header = bool(self.config.header and "{section}" in self.config.header)

        # Stage 3 — map token list to ReportLab Flowable list
        flowables = self._map(tokens)

        if self.config.toc or has_footnotes or has_section_header:
            # Pass 1: Build document with dummy/empty positions to collect page/footnote mapping
            if self.progress_callback:
                self.progress_callback(
                    "render_pass_start",
                    {
                        "pass_num": 1,
                        "total_passes": 2,
                        "description": "Analyzing layout (outlines & footnotes)",
                    },
                )
            self._render_pass(flowables, is_final=False)

            max_passes = 5
            converged = False
            pass_idx = 1

            # Intermediate passes loop
            for p_idx in range(2, max_passes):
                pass_idx = p_idx
                old_footnote_reg = self.footnote_page_registry.copy()
                old_bookmark_reg = self.bookmark_page_registry.copy()

                # Map tokens to flowables (suppressing progress callbacks)
                self.progress_callback = None
                try:
                    flowables = self._map(tokens)
                finally:
                    self.progress_callback = original_callback

                if self.progress_callback:
                    self.progress_callback(
                        "render_pass_start",
                        {
                            "pass_num": pass_idx,
                            "total_passes": pass_idx + 1,
                            "description": "Analyzing layout (outlines & footnotes)",
                        },
                    )

                # Run layout analysis pass
                self._render_pass(flowables, is_final=False)

                # Check convergence
                if (
                    old_footnote_reg == self.footnote_page_registry
                    and old_bookmark_reg == self.bookmark_page_registry
                ):
                    converged = True
                    break

            # Final Pass
            self.progress_callback = None
            try:
                flowables = self._map(tokens)
            finally:
                self.progress_callback = original_callback

            if self.progress_callback:
                self.progress_callback(
                    "render_pass_start",
                    {
                        "pass_num": (pass_idx + 1) if converged else max_passes,
                        "total_passes": (pass_idx + 1) if converged else max_passes,
                        "description": "Generating final PDF",
                    },
                )
            self._render_pass(flowables, is_final=True)
        else:
            if self.progress_callback:
                self.progress_callback(
                    "render_pass_start",
                    {"pass_num": 1, "total_passes": 1, "description": "Generating final PDF"},
                )
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
                self.parsed_metadata_keys = getattr(pp, "parsed_keys", set())
        return result

    def _parse(self, md: str) -> list[dict]:
        """Stage 2 — parse Markdown into a normalised token list."""
        return MarkdownParser().parse(md)

    def _map(self, tokens: list[dict]) -> list:
        """Stage 3 — dispatch each token to its handler and collect flowables."""

        self._styles["_seen_slugs"] = set()
        self._styles["_current_source_file"] = self.config.input_file
        # Collect footnote definitions first
        self.footnotes.clear()
        for token in tokens:
            if token.get("type") == "FootnoteDefinition":
                label = token.get("attrs", {}).get("label", "")
                text = token.get("raw", "")
                self.footnotes[f"^{label}"] = (text, "")

        # Concurrent pre-fetching of LaTeX and Mermaid assets
        self._pre_fetch_assets(tokens)

        diagram_tokens = [t for t in tokens if t.get("type") in ("Mermaid", "LatexBlock")]
        num_diagrams = len(diagram_tokens)
        if self.progress_callback:
            self.progress_callback("map_start", {"total_diagrams": num_diagrams})

        flowables = []
        diagram_idx = 0
        seen_footnotes = set()
        for token in tokens:
            source_file = _is_source_file_comment(token)
            if source_file is not None:
                self._styles["_current_source_file"] = source_file
                continue

            token_type = token.get("type", "")

            if token_type == "FootnoteDefinition":
                continue

            if token_type in ("Mermaid", "LatexBlock"):
                diagram_idx += 1
                if self.progress_callback:
                    self.progress_callback(
                        "render_diagram",
                        {"type": token_type, "index": diagram_idx, "total": num_diagrams},
                    )

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
                    if ref in seen_footnotes:
                        continue
                    fn_key = f"^{ref}"
                    if fn_key in self.footnotes:
                        seen_footnotes.add(ref)
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
        from md2pdf.core.flowables import ResizableImage, find_bookmarks
        from md2pdf.core.layout import LayoutComposer

        # Reset max available height for the current rendering pass
        ResizableImage.max_avail_height = 0.0
        ResizableImage.min_scale = self.config.min_image_scale

        composer = LayoutComposer()
        safe_flowables = composer.compose(flowables)

        doc = self._build_doc()
        doc._bookmark_page_registry = self.bookmark_page_registry
        doc._footnote_page_registry = self.footnote_page_registry
        doc._footnote_page_footnotes = self.footnote_page_footnotes

        doc._md2pdf_config = self.config
        doc._md2pdf_styles = self._styles
        doc._md2pdf_metadata = self.metadata
        doc._md2pdf_metadata_keys = getattr(self, "parsed_metadata_keys", set())

        doc._md2pdf_is_final = is_final
        # Populate page_footnotes for FootnoteFlowable on every pass to dynamically
        # adjust margins and layout positions for intermediate analysis passes.
        from md2pdf.core.flowables import FootnoteFlowable

        self.footnote_page_footnotes.clear()

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
            page_num = self.footnote_page_registry.get(f.label)
            if page_num is not None:
                self.footnote_page_footnotes.setdefault(page_num, []).append(f)

        if is_final:
            doc._md2pdf_toc_page_numbers = self.bookmark_page_registry.copy()
        else:
            doc._md2pdf_toc_page_numbers = None

        safe_flowables = self._post_registry.run_all(doc, safe_flowables)

        # Set doc reference on all FootnoteFlowables

        def set_doc_on_fns(flowables_list, doc_obj):
            from reportlab.platypus import KeepTogether

            for f in flowables_list:
                if isinstance(f, FootnoteFlowable):
                    f._doc = doc_obj
                elif isinstance(f, KeepTogether):
                    set_doc_on_fns(f._content, doc_obj)

        set_doc_on_fns(safe_flowables, doc)

        # Collect bookmarks in order to determine running section headers
        bookmarks = []
        if is_final:
            bookmarks = find_bookmarks(safe_flowables)

        page_registry = self.bookmark_page_registry

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

        from reportlab import rl_config

        old_invariant = getattr(rl_config, "invariant", 0)
        if getattr(self.config, "deterministic", False):
            rl_config.invariant = 1

        try:
            doc.build(
                safe_flowables,
                onFirstPage=PageTemplateCallback(state_first),
                onLaterPages=PageTemplateCallback(state_later),
            )
        finally:
            rl_config.invariant = old_invariant

    def _build_doc(self):
        from reportlab.lib.units import mm

        from md2pdf.core.config import resolve_page_geometry

        pagesize = resolve_page_geometry(self.config.page_size, self.config.orientation)

        return MD2PDFDocTemplate(
            self.config.output_file,
            pagesize=pagesize,
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

        Raises:
            ConfigError: If a configured font file path is missing.
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
        except ConfigError:
            raise
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

            mermaid_handler = MermaidHandler(client, cache, offline)
            if self.registry.get(mermaid_handler.token_type) is None:
                self.registry.register(mermaid_handler)

            latex_handler = LatexHandler(client, cache, offline)
            if self.registry.get(latex_handler.token_type) is None:
                self.registry.register(latex_handler)
        except Exception:
            logger.debug("Could not register asset handlers", exc_info=True)

    def _pre_fetch_assets(self, tokens: list[dict]) -> None:
        """Scan AST for LaTeX and Mermaid assets and pre-render/pre-fetch them in parallel."""
        assets = []

        def find_assets(token: dict) -> None:
            t_type = token.get("type", "")
            if t_type == "BlockCode":
                from md2pdf.handlers.code import is_latex_formula

                if is_latex_formula(token.get("raw", "")):
                    assets.append({"type": "LatexBlock", "raw": token.get("raw", "")})
            elif t_type in ("LatexBlock", "Math", "Mermaid"):
                assets.append({"type": t_type, "raw": token.get("raw", "")})
            children = token.get("children")
            if isinstance(children, list):
                for child in children:
                    find_assets(child)

        for token in tokens:
            find_assets(token)

        if not assets:
            return

        # Get cache, client, and offline status
        latex_handler = self.registry.get("LatexBlock")
        if latex_handler:
            client = latex_handler.client
            cache = latex_handler.cache
            offline = latex_handler.offline
        else:
            from md2pdf.assets.cache import AssetCache
            from md2pdf.assets.kroki import KrokiClient

            cache = AssetCache(self.config.cache_dir)
            client = KrokiClient()
            offline = getattr(self.config, "offline", False)

        # Deduplicate to avoid duplicate rendering work
        unique_assets = {}
        for asset in assets:
            key = (asset["type"], asset["raw"])
            if key not in unique_assets:
                unique_assets[key] = asset

        tasks = []
        for asset_type, raw_source in unique_assets.keys():
            if asset_type in ("LatexBlock", "Math"):
                from md2pdf.handlers.latex import _wrap_latex, clean_latex_source

                formula = clean_latex_source(raw_source)
                wrapped = _wrap_latex(formula)
                path = cache.path_for("tikz", wrapped)
            elif asset_type == "Mermaid":
                path = cache.path_for("mermaid", raw_source)
            else:
                continue

            if not path.exists():
                tasks.append((asset_type, raw_source))

        if not tasks:
            return

        logger.info("Pre-fetching %d math/diagram assets concurrently...", len(tasks))

        import concurrent.futures

        def fetch_and_cache(asset_type: str, source: str) -> None:
            try:
                if asset_type in ("LatexBlock", "Math"):
                    from md2pdf.handlers.latex import get_latex_image

                    get_latex_image(
                        source, config=self.config, client=client, cache=cache, offline=offline
                    )
                elif asset_type == "Mermaid":
                    from md2pdf.handlers.mermaid import get_mermaid_image

                    get_mermaid_image(
                        source, config=self.config, client=client, cache=cache, offline=offline
                    )
            except Exception as e:
                logger.warning("Failed to pre-fetch %s asset: %s", asset_type, e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_and_cache, dtype, src) for dtype, src in tasks]
            concurrent.futures.wait(futures)


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
        cb = getattr(
            doc,
            "_md2pdf_on_first_page" if self.state.is_first_page else "_md2pdf_on_later_pages",
            None,
        )
        if cb is not None:
            cb(canvas, doc)


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

    has_cover = False
    if state and hasattr(doc, "_md2pdf_config") and doc._md2pdf_config:
        cover_val = getattr(doc._md2pdf_config, "cover", False)
        if isinstance(cover_val, bool):
            has_cover = cover_val

    if has_cover and canvas.getPageNumber() == 1:
        return

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


def _is_source_file_comment(token: dict) -> str | None:
    """Check if the token represents a SOURCE_FILE comment, returning the filepath if matched."""
    t_type = token.get("type", "")
    raw_val = (token.get("raw") or "").strip()
    if not raw_val and token.get("children"):
        if t_type == "Paragraph" and len(token["children"]) == 1:
            child = token["children"][0]
            if child.get("type") in ("RawText", "RawHTML", "HTMLBlock"):
                raw_val = (child.get("raw") or "").strip()
        else:
            raw_val = "".join(c.get("raw", "") for c in token["children"]).strip()

    match = re.match(r"^<!--\s*SOURCE_FILE:\s*(.+?)\s*-->$", raw_val)
    if match:
        return match.group(1)
    return None
