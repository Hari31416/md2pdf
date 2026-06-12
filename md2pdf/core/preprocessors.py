"""Pre-processor system for md2pdf.

Pre-processors transform raw Markdown text *before* it is parsed.
They run in priority order (lowest number first); each receives the output
of the previous.

Built-in pre-processors
-----------------------
- ``FrontMatterStripper``  — strips YAML front-matter (``--- ... ---``) — priority 10
- ``IncludeResolver``      — placeholder for ``!include`` directives (future) — priority 20

:class:`PreProcessorRegistry` manages registration and execution.
Plugin pre-processors should use priority ≥ 50 so they run after built-ins.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod


class PreProcessor(ABC):
    """Abstract base class for all pre-processors.

    Subclasses implement :meth:`process` to transform raw Markdown text and
    return the (possibly modified) text.
    """

    @abstractmethod
    def process(self, raw_md: str) -> str:
        """Transform *raw_md* and return the result.

        Args:
            raw_md: Raw Markdown string, possibly already modified by
                    earlier pre-processors in the chain.

        Returns:
            The transformed Markdown string.
        """
        ...


class FrontMatterStripper(PreProcessor):
    """Strip YAML front matter from the top of a Markdown document.

    Front matter is defined as a block delimited by ``---`` on the very
    first line and a closing ``---`` on a subsequent line:

    .. code-block:: markdown

        ---
        title: My Document
        author: Jane
        ---

        # Main content starts here

    The stripped block (including both delimiters) is removed; the rest
    of the document is returned unchanged.
    """

    _PATTERN: re.Pattern[str] = re.compile(
        r"^---\n.*?\n---\n",
        re.DOTALL,
    )

    def process(self, raw_md: str) -> str:
        return self._PATTERN.sub("", raw_md, count=1)


class IncludeResolver(PreProcessor):
    """Resolve ``!include path/to/other.md`` directives.

    This is a **placeholder** implementation that returns the document
    unchanged.  A real implementation will be added in a future phase.
    """

    def process(self, raw_md: str) -> str:
        # TODO: resolve !include directives
        return raw_md


class PreProcessorRegistry:
    """Priority-sorted registry of :class:`PreProcessor` instances.

    Lower priority number = runs first.  Built-ins are registered at
    construction time with priorities 10 and 20 so that plugin pre-processors
    (default priority 50) always run after them.

    Args:
        register_builtins: If ``True`` (the default), automatically register
            :class:`FrontMatterStripper` and :class:`IncludeResolver` with
            their canonical priorities.
    """

    def __init__(self, register_builtins: bool = True) -> None:
        # Each entry is a (priority, PreProcessor) tuple.
        self._processors: list[tuple[int, PreProcessor]] = []
        if register_builtins:
            self.register(FrontMatterStripper(), priority=10)
            self.register(IncludeResolver(), priority=20)

    def register(self, pp: PreProcessor, *, priority: int = 50) -> None:
        """Register *pp* at the given *priority*.

        Lower priority values run first.  If two processors share the same
        priority, they run in registration order.

        Args:
            pp: A :class:`PreProcessor` instance to register.
            priority: Execution order key.  Defaults to ``50``.
        """
        self._processors.append((priority, pp))
        self._processors.sort(key=lambda x: x[0])

    def run_all(self, raw_md: str) -> str:
        """Run all registered pre-processors in priority order.

        Args:
            raw_md: Raw Markdown string to transform.

        Returns:
            The transformed Markdown string after all processors have run.
        """
        for _, pp in self._processors:
            raw_md = pp.process(raw_md)
        return raw_md
