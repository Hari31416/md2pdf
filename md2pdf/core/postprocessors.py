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
