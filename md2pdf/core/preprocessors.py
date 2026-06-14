"""Pre-processor system for md2pdf.

Pre-processors transform raw Markdown text *before* it is parsed.
They run in priority order (lowest number first); each receives the output
of the previous.

Built-in pre-processors
-----------------------
- ``FrontMatterStripper``  — strips YAML front-matter (``--- ... ---``) — priority 10
- ``IncludeResolver``      — placeholder for ``!include`` directives (future) — priority 20
- ``PageBreakPreProcessor``  — converts pagebreak directives — priority 25
- ``AdmonitionPreProcessor`` — converts admonition blocks — priority 30
- ``EmojiPreProcessor``      — replaces emoji codepoints with Twemoji PNGs — priority 35

:class:`PreProcessorRegistry` manages registration and execution.
Plugin pre-processors should use priority ≥ 50 so they run after built-ins.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.request import urlopen

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
            "date": "",
        }
        self.parsed_keys: set[str] = set()
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
                    (val.startswith('"') and val.endswith('"'))
                    or (val.startswith("'") and val.endswith("'"))
                ):
                    val = val[1:-1]
                if key in ("title", "author", "subject", "keywords", "date"):
                    self.metadata[key] = val
                    self.parsed_keys.add(key)

    def process(self, raw_md: str) -> str:
        match = self._PATTERN.match(raw_md)
        if match:
            block = match.group(0)
            self._parse_metadata(block)
            return self._PATTERN.sub("", raw_md, count=1)
        return raw_md


class IncludeResolver(PreProcessor):
    """Resolve ``!include path/to/other.md`` directives recursively."""

    def __init__(
        self,
        main_file: str = "",
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.main_file = main_file
        self.progress_callback = progress_callback

    def process(self, raw_md: str) -> str:
        if not self.main_file:
            return raw_md
        if self.progress_callback:
            self.progress_callback("preprocess_resolve_includes", {})
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


class AdmonitionPreProcessor(PreProcessor):
    """Pre-processor to translate Admonitions and GitHub alerts into HTML containers.

    Translates:
    1. GitHub alerts `> [!NOTE]` into `:::note` fenced container blocks.
    2. `:::note` (and other types) fenced blocks into `<div class="admonition <type>">...</div>` HTML blocks.
    """

    def process(self, raw_md: str) -> str:
        md = self._process_github_alerts(raw_md)
        md = self._process_fenced_containers(md)
        return md

    def _process_github_alerts(self, raw_md: str) -> str:
        lines = raw_md.splitlines()
        processed_lines = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            m = re.match(
                r"^[ \t]*>[ \t]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s+(.*))?$",
                line,
                re.IGNORECASE,
            )
            if m:
                alert_type = m.group(1).lower()
                first_line_text = m.group(2) or ""

                alert_content_lines = []
                if first_line_text.strip():
                    alert_content_lines.append(first_line_text)

                i += 1
                while i < n:
                    next_line = lines[i]
                    if re.match(
                        r"^[ \t]*>[ \t]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]",
                        next_line,
                        re.IGNORECASE,
                    ):
                        break
                    bq_match = re.match(r"^[ \t]*>(?:[ \t](.*))?$", next_line)
                    if bq_match:
                        content = bq_match.group(1) or ""
                        alert_content_lines.append(content)
                        i += 1
                    elif next_line.strip() == "":
                        j = i + 1
                        while j < n and lines[j].strip() == "":
                            j += 1
                        if j < n and re.match(r"^[ \t]*>", lines[j]):
                            for _ in range(j - i):
                                alert_content_lines.append("")
                            i = j
                        else:
                            break
                    else:
                        break

                processed_lines.append(f":::{alert_type}")
                for content_line in alert_content_lines:
                    processed_lines.append(content_line)
                processed_lines.append(":::")
            else:
                processed_lines.append(line)
                i += 1

        return "\n".join(processed_lines)

    def _process_fenced_containers(self, raw_md: str) -> str:
        lines = raw_md.splitlines()
        processed_lines = []

        open_pattern = re.compile(r"^[ \t]*:::[ \t]*([a-zA-Z0-9_-]+)(?:\s+(.*))?$")
        close_pattern = re.compile(r"^[ \t]*:::[ \t]*$")

        for line in lines:
            open_match = open_pattern.match(line)
            if open_match:
                container_type = open_match.group(1)
                title = open_match.group(2) or ""
                title = title.strip()
                if len(title) >= 2 and (
                    (title.startswith('"') and title.endswith('"'))
                    or (title.startswith("'") and title.endswith("'"))
                ):
                    title = title[1:-1]

                if title:
                    processed_lines.append(
                        f'\n<div class="admonition {container_type}" title="{title}">\n'
                    )
                else:
                    processed_lines.append(f'\n<div class="admonition {container_type}">\n')
            elif close_pattern.match(line):
                processed_lines.append("\n</div>\n")
            else:
                processed_lines.append(line)

        return "\n".join(processed_lines)


class LatexBlockPreProcessor(PreProcessor):
    """Pre-process display/block math delimited by $$ ... $$ into ```latex ... ``` fences.

    This prevents the markdown parser from splitting equations containing escaped
    dollar signs ($) or nested syntax into fragments.
    """

    def process(self, raw_md: str) -> str:
        def replace_math(match):
            formula = match.group(1).strip()
            return f"\n\n```latex\n{formula}\n```\n\n"

        return re.sub(
            r"^[ \t]*\$\$(.*?)\$\$[ \t]*$",
            replace_math,
            raw_md,
            flags=re.MULTILINE | re.DOTALL,
        )


class PageBreakPreProcessor(PreProcessor):
    r"""Pre-processor to translate pagebreak comments and directives into HTML blocks.

    Translates:
    1. `<!-- pagebreak -->` (flexible spacing/case)
    2. `\pagebreak` (flexible spacing/case)
    into `<div class="pagebreak"></div>`.
    """

    def process(self, raw_md: str) -> str:
        # Replace <!-- pagebreak -->
        md = re.sub(
            r"^[ \t]*<!--[ \t]*pagebreak[ \t]*-->[ \t]*$",
            r'<div class="pagebreak"></div>',
            raw_md,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        # Replace \pagebreak
        md = re.sub(
            r"^[ \t]*\\pagebreak[ \t]*$",
            r'<div class="pagebreak"></div>',
            md,
            flags=re.MULTILINE | re.IGNORECASE,
        )
        return md


# ---------------------------------------------------------------------------
# Emoji helpers
# ---------------------------------------------------------------------------

# Characters that are *visually* emoji but are basic Latin/ASCII or
# common symbols that do not need image substitution.
_EMOJI_SKIP_RANGES: tuple[tuple[int, int], ...] = (
    (0x0023, 0x0023),  # # (number sign)
    (0x002A, 0x002A),  # * (asterisk)
    (0x0030, 0x0039),  # 0-9 digits
    # Pure-math Unicode blocks — "So" category but no Twemoji images exist:
    (0x2100, 0x214F),  # Letterlike Symbols (ℂ ℝ ℤ …)
    (0x2190, 0x21FF),  # Arrows (← → ↑ ↓ …)
    (0x2200, 0x22FF),  # Mathematical Operators (∅ ∈ ∩ ∪ ⊂ ≤ ≥ ≠ ≈ ∑ ∏ ∫ …)
    (0x2300, 0x23FF),  # Miscellaneous Technical (⌨ ⏎ …)
    (0x2500, 0x257F),  # Box Drawing (─ │ ┌ └ …)
    (0x2580, 0x259F),  # Block Elements
    (0x25A0, 0x25FF),  # Geometric Shapes (▶ ■ ▲ …)
    (0x27C0, 0x27EF),  # Miscellaneous Mathematical Symbols-A
    (0x27F0, 0x27FF),  # Supplemental Arrows-A
    (0x2900, 0x297F),  # Supplemental Arrows-B
    (0x2980, 0x29FF),  # Miscellaneous Mathematical Symbols-B
    (0x2A00, 0x2AFF),  # Supplemental Mathematical Operators
)

# Variation selector 16 (U+FE0F) forces emoji presentation; strip it when
# building the Twemoji filename so we don't include it in the codepoint slug.
_VARIATION_SELECTOR_16 = 0xFE0F
# Zero-width joiner used to combine multi-codepoint sequences (e.g. family emoji).
_ZWJ = 0x200D

_TWEMOJI_BASE = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{slug}.png"


def _is_emoji_char(ch: str) -> bool:
    """Return True if *ch* is a character we want to substitute with an image."""
    cp = ord(ch)
    for lo, hi in _EMOJI_SKIP_RANGES:
        if lo <= cp <= hi:
            return False
    cat = unicodedata.category(ch)
    # "So" (Symbol, Other) covers emoji-family characters.
    # Explicitly exclude "Sm" (Symbol, Math) — operators like ∑ ∫ ≤ ≠ ≈
    # are mathematical and should never be treated as emoji.
    if cat == "So":
        return cp > 0x2000  # skip common currency/misc symbols below U+2000
    # Private-use area characters are not emoji.
    if 0xE000 <= cp <= 0xF8FF:
        return False
    # Supplementary multilingual plane emoji ranges
    if 0x1F000 <= cp <= 0x1FFFF:
        return True
    # Enclosed alphanumeric supplement / dingbats / misc symbols
    if 0x2600 <= cp <= 0x27BF:
        return True
    # Enclosed ideographic supplement
    if 0x1F200 <= cp <= 0x1F2FF:
        return True
    return False


def _codepoints_to_slug(chars: str) -> str:
    """Convert an emoji character (or ZWJ sequence) to a Twemoji filename slug.

    Variation selector U+FE0F is stripped only when it is the *last* character
    in the sequence.  When it appears mid-sequence (e.g. before a ZWJ in the
    rainbow-flag sequence 🏳\ufe0f\u200d🌈) it must be kept because Twemoji
    includes it in the filename slug.
    """
    result = []
    for idx, c in enumerate(chars):
        cp = ord(c)
        # Strip a trailing-only VS16
        if cp == _VARIATION_SELECTOR_16 and idx == len(chars) - 1:
            continue
        result.append(hex(cp)[2:])
    return "-".join(result)


def _fetch_emoji_png(slug: str, emoji_cache_dir: Path, timeout: float = 10.0) -> Path | None:
    """Return path to a cached PNG for *slug*, downloading it on first use.

    Args:
        slug: Twemoji codepoint slug (e.g. ``"1f600"``).
        emoji_cache_dir: Directory where PNG files are cached.
        timeout: Network timeout in seconds for the download request.
                 Defaults to ``10.0``.  A :class:`TimeoutError` or
                 ``socket.timeout`` raised by :func:`urllib.request.urlopen`
                 is caught and treated as a regular download failure.

    Returns:
        The :class:`~pathlib.Path` to the local PNG file, or ``None`` if the
        download fails (network unavailable, 404, timeout, etc.).
    """
    dest = emoji_cache_dir / f"{slug}.png"
    if dest.exists():
        return dest

    url = _TWEMOJI_BASE.format(slug=slug)
    try:
        emoji_cache_dir.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            with open(dest, "wb") as fh:
                shutil.copyfileobj(response, fh)
        logger.debug("Downloaded emoji PNG: %s → %s", url, dest)
        return dest
    except Exception as exc:
        logger.warning("Could not fetch emoji PNG for %s: %s", slug, exc)
        # Remove partially-written file if any
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        return None


class EmojiPreProcessor(PreProcessor):
    """Replace emoji codepoints in raw Markdown with Twemoji ``<img>`` tags.

    Each emoji character (including ZWJ sequences and variation-selector
    sequences) is replaced with::

        <img src="/path/to/cache/emoji/1f600.png" width="14" height="14"/>

    The PNG files are downloaded from the Twemoji CDN on first use and
    permanently cached under ``{cache_dir}/emoji/``.

    Args:
        cache_dir: Root cache directory (same as :attr:`~md2pdf.core.config.Config.cache_dir`).
        size: Pixel size used for both the ``width`` and ``height`` attributes.
              Defaults to ``14`` which is approximately one line-height at 10 pt.
        timeout: Network timeout in seconds for each emoji PNG download.
                 Defaults to ``10.0``.  If a download exceeds the timeout it
                 is treated as a failure and the original emoji character is
                 kept as a fallback.
    """

    def __init__(
        self,
        cache_dir: str = "",
        size: int = 14,
        timeout: float = 10.0,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.emoji_cache_dir = (
            Path(cache_dir) / "emoji" if cache_dir else Path.home() / ".cache/pymd2pdf/emoji"
        )
        self.size = size
        self.timeout = timeout
        self.progress_callback = progress_callback

    def process(self, raw_md: str) -> str:
        """Scan *raw_md* for emoji and replace them with ``<img>`` references."""
        result: list[str] = []
        i = 0
        text = raw_md
        n = len(text)

        # Pre-scan to identify unique emojis that need downloading
        if self.progress_callback:
            slugs_to_download = []
            seen_slugs = set()
            while i < n:
                ch = text[i]
                if text[i : i + 3] == "```":
                    end = text.find("```", i + 3)
                    if end == -1:
                        break
                    i = end + 3
                    continue
                if ch == "`":
                    end = text.find("`", i + 1)
                    if end == -1:
                        break
                    i = end + 1
                    continue
                if not _is_emoji_char(ch):
                    i += 1
                    continue
                seq_chars = [ch]
                j = i + 1
                while j < n:
                    next_cp = ord(text[j])
                    if next_cp in (_ZWJ, _VARIATION_SELECTOR_16) or _is_emoji_char(text[j]):
                        seq_chars.append(text[j])
                        j += 1
                    else:
                        break
                slug = _codepoints_to_slug("".join(seq_chars))
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    dest = self.emoji_cache_dir / f"{slug}.png"
                    if not dest.exists():
                        slugs_to_download.append(slug)
                i = j

            # Reset scanning pointer
            i = 0

            if slugs_to_download:
                self.progress_callback("emoji_download_start", {"total": len(slugs_to_download)})
                for idx, slug in enumerate(slugs_to_download, 1):
                    self.progress_callback(
                        "emoji_download_item",
                        {"slug": slug, "index": idx, "total": len(slugs_to_download)},
                    )
                    _fetch_emoji_png(slug, self.emoji_cache_dir, self.timeout)

        while i < n:
            ch = text[i]

            # --- skip fenced code blocks verbatim ---
            if text[i : i + 3] == "```":
                end = text.find("```", i + 3)
                if end == -1:
                    result.append(text[i:])
                    break
                result.append(text[i : end + 3])
                i = end + 3
                continue

            # --- skip inline code spans ---
            if ch == "`":
                end = text.find("`", i + 1)
                if end == -1:
                    result.append(text[i:])
                    break
                result.append(text[i : end + 1])
                i = end + 1
                continue

            if not _is_emoji_char(ch):
                result.append(ch)
                i += 1
                continue

            # Collect a full ZWJ / variation-selector sequence
            seq_chars = [ch]
            j = i + 1
            while j < n:
                next_cp = ord(text[j])
                if next_cp in (_ZWJ, _VARIATION_SELECTOR_16) or _is_emoji_char(text[j]):
                    seq_chars.append(text[j])
                    j += 1
                else:
                    break

            slug = _codepoints_to_slug("".join(seq_chars))
            png_path = _fetch_emoji_png(slug, self.emoji_cache_dir, self.timeout)
            if png_path is not None:
                img_tag = f'<img src="{png_path}" ' f'width="{self.size}" height="{self.size}"/>'
                result.append(img_tag)
            else:
                # Fallback: keep the original emoji characters
                result.append("".join(seq_chars))

            i = j

        return "".join(result)


class PreProcessorRegistry:
    """Priority-sorted registry of :class:`PreProcessor` instances.

    Lower priority number = runs first.  Built-ins are registered at
    construction time with priorities 10 and 20 so that plugin pre-processors
    (default priority 50) always run after them.

    Args:
        register_builtins: If ``True`` (the default), automatically register
            built-in pre-processors with their canonical priorities.
        input_file: Path to the source Markdown file (used by
            :class:`FrontMatterStripper` and :class:`IncludeResolver`).
        emoji: If ``True`` (the default), register :class:`EmojiPreProcessor`
            at priority 35.
        cache_dir: Cache directory forwarded to :class:`EmojiPreProcessor`.
    """

    def __init__(
        self,
        register_builtins: bool = True,
        input_file: str = "",
        emoji: bool = True,
        cache_dir: str = "",
        emoji_timeout: float = 10.0,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        # Each entry is a (priority, PreProcessor) tuple.
        self._processors: list[tuple[int, PreProcessor]] = []
        self._progress_callback = None
        self.progress_callback = progress_callback
        if register_builtins:
            self.register(FrontMatterStripper(input_file), priority=10)
            self.register(
                IncludeResolver(input_file, progress_callback=progress_callback), priority=20
            )
            self.register(LatexBlockPreProcessor(), priority=22)
            self.register(PageBreakPreProcessor(), priority=25)
            self.register(AdmonitionPreProcessor(), priority=30)
            if emoji:
                self.register(
                    EmojiPreProcessor(
                        cache_dir=cache_dir,
                        timeout=emoji_timeout,
                        progress_callback=progress_callback,
                    ),
                    priority=35,
                )

    @property
    def progress_callback(self) -> Callable[[str, dict[str, Any]], None] | None:
        return getattr(self, "_progress_callback", None)

    @progress_callback.setter
    def progress_callback(self, val: Callable[[str, dict[str, Any]], None] | None) -> None:
        self._progress_callback = val
        for _, pp in self._processors:
            if hasattr(pp, "progress_callback"):
                pp.progress_callback = val

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
