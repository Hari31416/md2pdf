"""Post-processor system for md2pdf.

Post-processors receive the ``SimpleDocTemplate`` and the list of flowables
**before** ``doc.build()`` is called.  They may insert, remove, or wrap
flowables, or set document-level metadata (title, author, etc.).

Built-in post-processors
------------------------
- :class:`PageNumberPostProcessor` — attaches page-number footer callbacks
  to the document (no-op body; callback handles drawing at render time).

Third-party plugins subclass :class:`PostProcessor` and declare themselves
under the ``md2pdf.postprocessors`` entry-point group.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, Spacer, Table, TableStyle

from md2pdf.core.flowables import BookmarkFlowable, find_bookmarks
from md2pdf.handlers.inline import escape_xml

if TYPE_CHECKING:
    from reportlab.platypus import SimpleDocTemplate

logger = logging.getLogger(__name__)


class PostProcessor(ABC):
    """Abstract base class for all post-processors.

    Subclasses implement :meth:`process` to inspect or mutate the flowables
    list (and optionally the document object) before the PDF is built.
    """

    @abstractmethod
    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        """Apply post-processing to *flowables*.

        Args:
            doc: The ``SimpleDocTemplate`` that will be used to build the PDF.
                Useful for setting metadata (``doc.title``, ``doc.author``).
            flowables: Current list of ReportLab ``Flowable`` instances.

        Returns:
            The (possibly modified) flowables list.  Must always return a
            list even if it is the same object passed in.
        """
        ...


class TableOfContentsPostProcessor(PostProcessor):
    """Prepend a linked Table of Contents page to the document.

    Walks flowables to find `BookmarkFlowable` instances and prepends a TOC page
    if `doc._md2pdf_config.toc` is enabled.
    """

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        config = getattr(doc, "_md2pdf_config", None)
        if not config or not getattr(config, "toc", False):
            return flowables

        bookmarks = find_bookmarks(flowables)

        if not bookmarks:
            return flowables

        styles = getattr(doc, "_md2pdf_styles", {})
        h1_style = styles.get("h1")
        body_style = styles.get("body")

        if not h1_style or not body_style:
            base_styles = getSampleStyleSheet()
            h1_style = h1_style or base_styles["Heading1"]
            body_style = body_style or base_styles["Normal"]

        toc_flowables = []
        toc_flowables.append(
            BookmarkFlowable("table-of-contents", title="Table of Contents", level=0)
        )
        toc_flowables.append(Paragraph("Table of Contents", h1_style))
        toc_flowables.append(Spacer(1, 15))

        # Create ParagraphStyles for each level (indentation is handled via Table cell padding)
        toc_styles = {}
        for level in range(6):
            toc_styles[level] = ParagraphStyle(
                f"toc_level_{level}",
                parent=body_style,
                leftIndent=0,
                spaceBefore=0,
                spaceAfter=0,
            )

        # Style H1 (level 0) entries to be bold and stand out
        bold_font = styles.get("h2", body_style).fontName
        toc_styles[0] = ParagraphStyle(
            "toc_level_0",
            parent=body_style,
            fontName=bold_font,
            leftIndent=0,
            spaceBefore=6,
            spaceAfter=2,
        )

        page_num_style = ParagraphStyle(
            "toc_page_num",
            parent=body_style,
            alignment=TA_RIGHT,
        )

        page_num_style_bold = ParagraphStyle(
            "toc_page_num_bold",
            parent=page_num_style,
            fontName=bold_font,
        )

        link_color = styles.get("color_link", "#0366d6")
        page_numbers = getattr(doc, "_md2pdf_toc_page_numbers", None)

        table_data = []
        for b in bookmarks:
            level = max(0, min(b.level, 5))

            # Clickable link for the title
            escaped_title = escape_xml(b.title)
            title_text = f'<link href="#{b.key}" color="{link_color}">{escaped_title}</link>'

            # Clickable link for the page number
            page_num = str(page_numbers.get(b.key, "")) if page_numbers is not None else "99"
            page_text = f'<link href="#{b.key}" color="{link_color}">{page_num}</link>'

            title_p = Paragraph(title_text, toc_styles[level])
            p_style = page_num_style_bold if level == 0 else page_num_style
            page_p = Paragraph(page_text, p_style)

            table_data.append([title_p, page_p])

        doc_width = getattr(doc, "width", 450)
        toc_table = Table(table_data, colWidths=[doc_width - 40, 40])

        table_commands = [
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]

        for i, b in enumerate(bookmarks):
            level = max(0, min(b.level, 5))
            indent = 20 * level
            table_commands.append(("LEFTPADDING", (0, i), (0, i), indent))

        toc_table.setStyle(TableStyle(table_commands))

        toc_flowables.append(toc_table)
        toc_flowables.append(PageBreak())

        return toc_flowables + flowables


class MetadataPostProcessor(PostProcessor):
    """Apply PDF document metadata (title, author, subject, keywords) to the document.

    Reads metadata from `doc._md2pdf_metadata` and applies it as properties
    on the `SimpleDocTemplate` object (`doc.title`, `doc.author`, etc.).
    """

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        metadata = getattr(doc, "_md2pdf_metadata", {})
        if not metadata:
            return flowables

        if metadata.get("title"):
            doc.title = metadata["title"]
        if metadata.get("author"):
            doc.author = metadata["author"]
        if metadata.get("subject"):
            doc.subject = metadata["subject"]
        if metadata.get("keywords"):
            doc.keywords = metadata["keywords"]

        return flowables


class PageNumberPostProcessor(PostProcessor):
    """Attach page-number footer callbacks to the document.

    The actual drawing is performed inside the ``onFirstPage`` /
    ``onLaterPages`` callbacks, which ReportLab calls once per page during
    ``doc.build()``.  This post-processor stores the callbacks on the
    document so the pipeline can pass them to ``doc.build()``.

    The flowables list is returned unchanged.
    """

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        # Store callbacks as attributes so Pipeline._render() can pick them up.
        doc._md2pdf_on_first_page = self._draw_page_number  # type: ignore[attr-defined]
        doc._md2pdf_on_later_pages = self._draw_page_number  # type: ignore[attr-defined]
        return flowables

    @staticmethod
    def _draw_page_number(canvas, doc) -> None:  # type: ignore[no-untyped-def]
        """Draw a centred page-number footer on *canvas*."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        page_text = f"— {doc.page} —"
        canvas.drawCentredString(doc.pagesize[0] / 2, 20, page_text)
        canvas.restoreState()


class CoverPagePostProcessor(PostProcessor):
    """Prepend a cover/title page using YAML front-matter metadata before Table of Contents."""

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        config = getattr(doc, "_md2pdf_config", None)
        if not config or not getattr(config, "cover", False):
            return flowables

        metadata = getattr(doc, "_md2pdf_metadata", {})
        metadata_keys = getattr(doc, "_md2pdf_metadata_keys", set())
        styles = getattr(doc, "_md2pdf_styles", {})

        title = metadata.get("title", "")
        author = metadata.get("author", "")
        date = metadata.get("date", "")

        from reportlab.lib import colors
        from reportlab.platypus import HRFlowable, PageBreak, Paragraph, Spacer

        from md2pdf.handlers.inline import escape_xml

        title_style = styles.get("cover_title")
        author_style = styles.get("cover_author")
        date_style = styles.get("cover_date")

        if not title_style or not author_style or not date_style:
            base_styles = getSampleStyleSheet()
            title_style = title_style or base_styles["Heading1"]
            author_style = author_style or base_styles["Normal"]
            date_style = date_style or base_styles["Normal"]

        cover_flowables = []
        cover_flowables.append(Spacer(1, 150))
        cover_flowables.append(Paragraph(escape_xml(title), title_style))

        # Check if we should render author and/or date
        has_author = "author" in metadata_keys and bool(author)
        has_date = "date" in metadata_keys and bool(date)

        if has_author or has_date:
            accent_color = styles.get("color_hr", colors.grey)
            cover_flowables.append(
                HRFlowable(
                    width="40%",
                    thickness=1.5,
                    color=accent_color,
                    spaceBefore=20,
                    spaceAfter=20,
                    hAlign="CENTER",
                )
            )
            if has_author:
                cover_flowables.append(Paragraph(escape_xml(author), author_style))
            if has_date:
                cover_flowables.append(Paragraph(escape_xml(date), date_style))

        cover_flowables.append(PageBreak())

        return cover_flowables + flowables


class PostProcessorRegistry:
    """Ordered registry of :class:`PostProcessor` instances.

    Processors execute in registration order.  Plugins registered later run
    after built-ins.
    """

    def __init__(self) -> None:
        self._processors: list[PostProcessor] = []

    def register(self, pp: PostProcessor) -> None:
        """Append *pp* to the execution chain.

        Args:
            pp: A :class:`PostProcessor` instance to register.
        """
        self._processors.append(pp)
        logger.debug("Registered post-processor: %s", type(pp).__name__)

    def run_all(self, doc: SimpleDocTemplate, flowables: list) -> list:
        """Run all registered post-processors in order.

        Each processor receives the output of the previous one.

        Args:
            doc: The ``SimpleDocTemplate`` being built.
            flowables: Initial flowables list from Stage 3.

        Returns:
            Final flowables list after all processors have run.
        """
        for pp in self._processors:
            flowables = pp.process(doc, flowables)
        return flowables
