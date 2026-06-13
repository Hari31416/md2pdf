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

import logging
import os
import re
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


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

    def __init__(self, input_file: str = "") -> None:
        self.input_file = input_file
        self.metadata: dict[str, str] = {
            "title": "",
            "author": "pymd2pdf",
            "subject": "",
            "keywords": "",
        }
        if self.input_file:
            base_name = os.path.basename(self.input_file)
            title_default, _ = os.path.splitext(base_name)
            self.metadata["title"] = title_default

    def _parse_metadata(self, block: str) -> None:
        lines = block.splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str == "---" or not line_str:
                continue
            if ":" in line_str:
                key, val = line_str.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if len(val) >= 2 and (
                    (val.startswith('"') and val.endswith('"')) or
                    (val.startswith("'") and val.endswith("'"))
                ):
                    val = val[1:-1]
                if key in ("title", "author", "subject", "keywords"):
                    self.metadata[key] = val

    def process(self, raw_md: str) -> str:
        match = self._PATTERN.match(raw_md)
        if match:
            block = match.group(0)
            self._parse_metadata(block)
            return self._PATTERN.sub("", raw_md, count=1)
        return raw_md


class IncludeResolver(PreProcessor):
    """Resolve ``!include path/to/other.md`` directives recursively."""

    def __init__(self, main_file: str = "") -> None:
        self.main_file = main_file

    def process(self, raw_md: str) -> str:
        if not self.main_file:
            return raw_md
        return self._resolve_includes(raw_md, os.path.abspath(self.main_file), set())

    def _resolve_includes(self, text: str, current_file_path: str, visited: set[str]) -> str:
        current_dir = os.path.dirname(current_file_path)
        visited = visited | {current_file_path}

        lines = text.splitlines(keepends=True)
        resolved_lines = []
        include_pattern = re.compile(r"^[ \t]*!include[ \t]+([^\n]+?)[ \t]*$")

        for line in lines:
            m = include_pattern.match(line.rstrip("\r\n"))
            if m:
                include_target = m.group(1).strip()
                if not os.path.isabs(include_target):
                    target_path = os.path.abspath(os.path.join(current_dir, include_target))
                else:
                    target_path = os.path.abspath(include_target)

                if target_path in visited:
                    logger.warning("Circular inclusion detected: %s", target_path)
                    resolved_lines.append(
                        f"<!-- Circular inclusion of {include_target} skipped -->\n"
                    )
                    continue

                if not os.path.isfile(target_path):
                    logger.warning("Included file not found: %s", target_path)
                    resolved_lines.append(f"<!-- Included file not found: {include_target} -->\n")
                    continue

                try:
                    with open(target_path, encoding="utf-8") as f:
                        included_content = f.read()
                    resolved_content = self._resolve_includes(
                        included_content, target_path, visited
                    )
                    resolved_lines.append(resolved_content)
                    if resolved_content and not resolved_content.endswith("\n"):
                        resolved_lines.append("\n")
                except Exception as exc:
                    logger.error("Failed to read included file %s: %s", target_path, exc)
                    resolved_lines.append(
                        f"<!-- Failed to read included file: {include_target} -->\n"
                    )
            else:
                resolved_lines.append(line)

        return "".join(resolved_lines)


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

    def __init__(self, register_builtins: bool = True, input_file: str = "") -> None:
        # Each entry is a (priority, PreProcessor) tuple.
        self._processors: list[tuple[int, PreProcessor]] = []
        if register_builtins:
            self.register(FrontMatterStripper(input_file), priority=10)
            self.register(IncludeResolver(input_file), priority=20)

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
