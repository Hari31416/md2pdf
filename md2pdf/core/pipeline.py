"""Linear Markdown-to-PDF conversion pipeline."""

from __future__ import annotations

import logging
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

        fns = FootnoteFlowable.page_footnotes.get(page_num, [])
        frame = self.frame
        if frame:
            if not hasattr(frame, "_orig_y1"):
                frame._orig_y1 = frame.y1
                frame._orig_height = frame.height

            if fns:
                total_H = sum(f.get_height(self.width, self.height) for f in fns)
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
        self._progress_callback = None
        self.progress_callback = progress_callback

        self.metadata: dict[str, str] = {
            "title": "",
            "author": "pymd2pdf",
            "subject": "",
            "keywords": "",
            "date": "",
        }
        self.parsed_metadata_keys: set[str] = set()
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
            progress_callback=self.progress_callback,
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

    @property
    def progress_callback(self) -> Callable[[str, dict[str, Any]], None] | None:
        return getattr(self, "_progress_callback", None)

    @progress_callback.setter
    def progress_callback(self, val: Callable[[str, dict[str, Any]], None] | None) -> None:
        self._progress_callback = val
        if hasattr(self, "_pre_registry") and self._pre_registry:
            self._pre_registry.progress_callback = val

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

            # Pass 2: Re-build document with populated page numbers and footnotes
            # Temporarily suppress sub-stage logs for the pass 2 rebuild
            self.progress_callback = None
            try:
                md = self._pre_process(raw_md)
                tokens = self._parse(md)
                flowables = self._map(tokens)
            finally:
                self.progress_callback = original_callback

            if self.progress_callback:
                self.progress_callback(
                    "render_pass_start",
                    {"pass_num": 2, "total_passes": 2, "description": "Generating final PDF"},
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
        for token in tokens:
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
        doc._md2pdf_metadata_keys = getattr(self, "parsed_metadata_keys", set())

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

        return MD2PDFDocTemplate(
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

            self.registry.register(MermaidHandler(client, cache, offline))
            self.registry.register(LatexHandler(client, cache, offline))
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

        from PIL import Image as PILImage

        from md2pdf.handlers.latex import _wrap_latex, clean_latex_source, make_image_transparent

        # Deduplicate to avoid duplicate rendering work
        unique_assets = {}
        for asset in assets:
            key = (asset["type"], asset["raw"])
            if key not in unique_assets:
                unique_assets[key] = asset

        kroki_tasks = []

        for asset_type, raw_source in unique_assets.keys():
            if asset_type in ("LatexBlock", "Math"):
                formula = clean_latex_source(raw_source)
                wrapped = _wrap_latex(formula)
                path = cache._path("tikz", wrapped)

                if path.exists():
                    continue
                try:
                    if np is None or r"\documentclass" in formula or r"\begin{" in formula:
                        raise ValueError("Matplotlib does not support documentclass or begin")

                    import matplotlib

                    matplotlib.use("agg")
                    from matplotlib.font_manager import FontProperties
                    from matplotlib.mathtext import MathTextParser
                    from PIL import Image as PILImage

                    dpi = 200
                    prop = FontProperties(size=10)
                    parser = MathTextParser("agg")
                    res = parser.parse(f"${formula}$", dpi=dpi, prop=prop)

                    img_rgba = np.zeros((res.image.shape[0], res.image.shape[1], 4), dtype=np.uint8)
                    img_rgba[..., 3] = res.image
                    pil_img = PILImage.fromarray(img_rgba, mode="RGBA")

                    nonzero = np.nonzero(res.image)
                    if len(nonzero[0]) > 0:
                        ymin, ymax = np.min(nonzero[0]), np.max(nonzero[0])
                        xmin, xmax = np.min(nonzero[1]), np.max(nonzero[1])
                        left, top, right, bottom = xmin, ymin, xmax + 1, ymax + 1
                        pil_img = pil_img.crop((left, top, right, bottom))

                    pil_img.save(path, format="PNG")
                    logger.debug(
                        "Pre-fetched and rendered LaTeX locally via matplotlib: %s", formula
                    )
                    continue
                except (ImportError, Exception):
                    pass

                if not offline:
                    kroki_tasks.append(("tikz", wrapped, path))

            elif asset_type == "Mermaid":
                path = cache._path("mermaid", raw_source)
                if path.exists():
                    continue
                if not offline:
                    kroki_tasks.append(("mermaid", raw_source, path))

        if not kroki_tasks:
            return

        logger.info(
            "Pre-fetching %d math/diagram assets from Kroki concurrently...", len(kroki_tasks)
        )

        import concurrent.futures

        def fetch_and_cache(diagram_type: str, source: str, cache_path) -> None:
            attempts = 2
            png = None
            for attempt in range(attempts):
                try:
                    png = client.render(diagram_type, source)
                    break
                except Exception as e:
                    if attempt == attempts - 1:
                        logger.warning(
                            "Failed to pre-fetch %s asset from Kroki after %d attempts: %s",
                            diagram_type,
                            attempts,
                            e,
                        )
                        return
                    logger.debug(
                        "Kroki pre-fetch attempt %d failed: %s. Retrying...", attempt + 1, e
                    )
                    import time

                    time.sleep(1)

            if not png:
                return

            try:
                from io import BytesIO

                from PIL import ImageChops

                if diagram_type == "tikz":
                    with PILImage.open(BytesIO(png)) as pil_img:
                        gray = pil_img.convert("L")
                        inverted = ImageChops.invert(gray)
                        bbox = inverted.getbbox()
                        if bbox:
                            pil_img = pil_img.crop(bbox)
                        pil_img = make_image_transparent(pil_img)
                        pil_img.save(cache_path, format="PNG")
                else:
                    cache_path.write_bytes(png)
                logger.debug("Successfully pre-fetched and cached %s asset", diagram_type)
            except Exception as exc:
                logger.warning("Failed to save pre-fetched asset to cache: %s", exc)
                try:
                    cache_path.write_bytes(png)
                except Exception:
                    pass

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(fetch_and_cache, dtype, src, cpath)
                for dtype, src, cpath in kroki_tasks
            ]
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
