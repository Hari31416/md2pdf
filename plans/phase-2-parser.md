# Phase 2: Parser & Tokenizer

**Goal:** Replace the regex/BS4 approach with a robust `mistletoe`-based AST parser that produces a normalized token stream. Add the pre-processor hook stage for plugins.

**Depends on:** Phase 1 (Pipeline skeleton, HandlerRegistry)

---

## Deliverables

- `md2pdf/core/parser.py` — `MarkdownParser` wrapping mistletoe
- `md2pdf/core/tokens.py` — canonical token type constants + helper dataclasses
- `md2pdf/core/preprocessors.py` — `PreProcessor` ABC + built-in `FrontMatterStripper`
- Updated `Pipeline._pre_process()` and `Pipeline._parse()` with real implementations
- `tests/test_parser.py` — token output tests for all supported node types

---

## Why mistletoe over markdown + BS4

| Concern | markdown + BS4 | mistletoe |
|---------|---------------|-----------|
| Output | HTML string | Typed AST |
| Extensibility | Fragile regex | Custom renderers / tokens |
| Nested structures | Parse HTML again | Native tree traversal |
| Plugin hook surface | None | Token visitors |

mistletoe's `Document` produces a tree of typed nodes that map 1:1 to our handler token types.

---

## Token Type Constants (`tokens.py`)

```python
# Canonical token type names — handlers claim one of these
HEADING      = "Heading"
PARAGRAPH    = "Paragraph"
LIST         = "List"
LIST_ITEM    = "ListItem"
TABLE        = "Table"
BLOCKQUOTE   = "BlockQuote"
CODE_FENCE   = "CodeFence"      # generic fenced block
MERMAID      = "Mermaid"        # code fence with lang="mermaid"
LATEX_BLOCK  = "LatexBlock"     # code fence with lang="latex" / $$ ... $$
THEMATIC_BREAK = "ThematicBreak"
RAW_HTML     = "RawHTML"
IMAGE        = "Image"
LINK         = "Link"
```

A token dict (what handlers receive) has this shape:

```python
{
    "type": "Heading",
    "level": 2,
    "children": [...],   # inline tokens (spans)
    "raw": "## My Heading",
    "_node": <mistletoe node>,   # escape hatch to raw AST node
}
```

---

## `MarkdownParser` (`parser.py`)

```python
import mistletoe
from mistletoe import Document
from mistletoe.block_token import CodeFence

class MarkdownParser:
    def parse(self, raw_md: str) -> list[dict]:
        """Parse markdown string into a flat list of normalized token dicts."""
        doc = Document(raw_md)
        return self._flatten(doc.children)

    def _flatten(self, nodes) -> list[dict]:
        tokens = []
        for node in nodes:
            tokens.append(self._normalize(node))
        return tokens

    def _normalize(self, node) -> dict:
        """Convert a mistletoe AST node to a canonical token dict."""
        token_type = type(node).__name__

        # Specialise fenced code blocks by language tag
        if token_type == "CodeFence":
            lang = (node.language or "").strip().lower()
            if lang == "mermaid":
                token_type = "Mermaid"
            elif lang in ("latex", "math"):
                token_type = "LatexBlock"

        return {
            "type": token_type,
            "raw": getattr(node, "content", ""),
            "children": self._extract_children(node),
            "attrs": self._extract_attrs(node),
            "_node": node,
        }

    def _extract_children(self, node) -> list[dict]:
        children = getattr(node, "children", None)
        if not children:
            return []
        return [self._normalize(c) for c in children]

    def _extract_attrs(self, node) -> dict:
        attrs: dict = {}
        for attr in ("level", "language", "start", "loose"):
            val = getattr(node, attr, None)
            if val is not None:
                attrs[attr] = val
        return attrs
```

---

## Pre-Processor System (`preprocessors.py`)

Pre-processors receive raw markdown text **before** parsing and return transformed text. They run in order.

```python
from abc import ABC, abstractmethod

class PreProcessor(ABC):
    @abstractmethod
    def process(self, raw_md: str) -> str:
        ...

class FrontMatterStripper(PreProcessor):
    """Strip YAML front matter (--- ... ---) from the top of the file."""
    def process(self, raw_md: str) -> str:
        import re
        return re.sub(r"^---\n.*?\n---\n", "", raw_md, count=1, flags=re.DOTALL)

class IncludeResolver(PreProcessor):
    """Resolve !include path/to/other.md directives (future)."""
    def process(self, raw_md: str) -> str:
        return raw_md  # placeholder
```

Plugin pre-processors are registered via a separate registry or config list:

```toml
[plugins]
preprocessors = ["my_package.preprocessors.MyPreProcessor"]
handlers = [...]
```

---

## Updated `Pipeline._pre_process()` and `Pipeline._parse()`

```python
def _pre_process(self, raw_md: str) -> str:
    for pp in self._preprocessors:       # ordered list of PreProcessor instances
        raw_md = pp.process(raw_md)
    return raw_md

def _parse(self, md: str) -> list[dict]:
    return MarkdownParser().parse(md)
```

---

## Acceptance Criteria

- [ ] `MarkdownParser().parse(md)` returns a flat token list for a sample doc containing all supported element types
- [ ] Fenced blocks with `lang="mermaid"` produce `type="Mermaid"` tokens
- [ ] Fenced blocks with `lang="latex"` produce `type="LatexBlock"` tokens
- [ ] `FrontMatterStripper` correctly strips YAML front matter and leaves body intact
- [ ] `pytest tests/test_parser.py` all pass
