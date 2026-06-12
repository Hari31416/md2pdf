"""Pre-processor system for md2pdf.

Pre-processors transform raw Markdown text *before* it is parsed.
They run in registration order and each receives the output of the previous.

Built-in pre-processors
-----------------------
- ``FrontMatterStripper``  — strips YAML front-matter (``--- ... ---``)
- ``IncludeResolver``      — placeholder for ``!include`` directives (future)
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
