# Plugin Authoring Guide for md2pdf

This document describes the public API available to third-party plugin authors, the four hook stages, and how to publish a plugin package.

---

## Overview

md2pdf processes a Markdown document through four sequential stages. Plugins
can intercept at any of the first three stages, plus supply stylesheet
overrides:

```txt
[ Raw .md ]
    │
    ▼
┌─────────────────────────────────┐
│  Stage 1: Pre-Processors        │  ← hook: transform raw Markdown text
│  (PreProcessorRegistry)         │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 2: AST Parser            │  (not pluggable — mistletoe is fixed)
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 3: Element Handlers      │  ← hook: add / replace token → Flowable
│  (HandlerRegistry dispatch)     │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 4: Post-Processors       │  ← hook: mutate the Flowable list
│  (PostProcessorRegistry)        │    e.g. watermarks, page numbers, TOC
└─────────────────┬───────────────┘
                  │
                  ▼
           [ PDF Output ]
```

Additionally, plugins can supply a **stylesheet layer** that is merged with
the default styles before any handler sees the `styles` dict.

---

## Public API

Only the following modules are part of the **public, stable API**. Do not
import from `md2pdf.core._*` private internals.

| Module                       | Public symbols                           |
| ---------------------------- | ---------------------------------------- |
| `md2pdf.core.registry`       | `ElementHandler`                         |
| `md2pdf.core.preprocessors`  | `PreProcessor`, `PreProcessorRegistry`   |
| `md2pdf.core.postprocessors` | `PostProcessor`, `PostProcessorRegistry` |
| `md2pdf.core.styles`         | `StyleRegistry`                          |

---

## Hook 1 — Pre-Processor

Subclass `PreProcessor` and implement `process(raw_md: str) -> str`.

```python
from md2pdf.core.preprocessors import PreProcessor

class MyPreProcessor(PreProcessor):
    def process(self, raw_md: str) -> str:
        # Replace all occurrences of ":warning:" with ⚠️
        return raw_md.replace(":warning:", "⚠️")
```

**Priority:** Declare under `md2pdf.preprocessors` entry points. The
`register()` call accepts a `priority` keyword (default `50`). Built-ins run
at priorities 10 and 20, so plugin pre-processors at priority 50 always run
after them.

---

## Hook 2 — Element Handler

Subclass `ElementHandler`, set `token_type`, and implement `render()`.

```python
from md2pdf.core.registry import ElementHandler
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

class CalloutHandler(ElementHandler):
    """Render custom ``Callout`` token blocks as styled paragraphs."""

    token_type = "Callout"

    def render(self, token: dict, styles: dict) -> list:
        text = token.get("raw", "")
        style = getSampleStyleSheet()["Normal"]
        return [Paragraph(f"📢 {text}", style)]
```

The `styles` dict is the merged stylesheet (defaults + plugin layers). You
can add your own style keys to it via a stylesheet plugin (Hook 4).

**Last-writer-wins:** registering a handler for a `token_type` that already
has one (e.g. `"Heading"`) replaces the built-in handler.

---

## Hook 3 — Post-Processor

Subclass `PostProcessor` and implement
`process(doc: SimpleDocTemplate, flowables: list) -> list`.

```python
from reportlab.platypus import SimpleDocTemplate
from md2pdf.core.postprocessors import PostProcessor

class WatermarkPostProcessor(PostProcessor):
    """Stamps 'DRAFT' diagonally on every page."""

    def __init__(self, text: str = "DRAFT") -> None:
        self.text = text

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        # Attach an onPage callback to the document.
        text = self.text

        def _stamp(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 72)
            canvas.setFillAlpha(0.1)
            canvas.translate(doc.pagesize[0] / 2, doc.pagesize[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, text)
            canvas.restoreState()

        doc._md2pdf_on_later_pages = _stamp  # type: ignore
        return flowables
```

Post-processors run in **registration order**. The flowables list returned by
each processor is passed as input to the next.

---

## Hook 4 — Stylesheet Override

Implement a class with a `get_stylesheet() -> dict` method. Return a dict
whose keys override the default stylesheet values.

```python
class DarkTheme:
    def get_stylesheet(self) -> dict:
        return {
            "color_body_text": "#e0e0e0",
            "color_link": "#80bfff",
            "font_size_body": 11,
        }
```

---

## Entry-Point Declaration

In your plugin package's `pyproject.toml`:

```toml
[project.entry-points."md2pdf.handlers"]
callout  = "my_package.handlers:CalloutHandler"
timeline = "my_package.handlers:TimelineHandler"

[project.entry-points."md2pdf.preprocessors"]
emoji = "my_package.preprocessors:EmojiPreProcessor"

[project.entry-points."md2pdf.postprocessors"]
watermark = "my_package.postprocessors:WatermarkPostProcessor"

[project.entry-points."md2pdf.stylesheets"]
dark_theme = "my_package.themes:DarkTheme"
```

After installation (`pip install my-plugin-package`), md2pdf auto-discovers
and loads the plugin on every run — no config file changes needed.

---

## Config-File Alternative

If you cannot use entry points (e.g. local scripts), declare plugins in
`md2pdf.toml`:

```toml
[plugins]
handlers = [
    "my_package.handlers:CalloutHandler",
]
preprocessors = [
    "my_package.preprocessors:EmojiPreProcessor",
]
postprocessors = [
    "my_package.postprocessors:WatermarkPostProcessor",
]
```

Config-file plugins are loaded **after** entry-point plugins, so they can
override built-ins declared via entry points.

---

## Error Handling Contract

- **All plugin loading errors are caught and logged** — a bad plugin never
  aborts a conversion run.
- Errors appear at `ERROR` level in the `md2pdf.core.plugin_loader` logger.
- Enable logging in your application to see plugin load failures:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Rules for Plugin Authors

1. **Only subclass public ABCs** (`ElementHandler`, `PreProcessor`,
   `PostProcessor`). Do not subclass internal implementation classes.
2. **Return valid `Flowable` instances** from `ElementHandler.render()`.
3. **Never raise from `render()` or `process()`** — return a fallback value
   instead. An unhandled exception will propagate and crash the conversion.
4. **Declare dependencies** in your `pyproject.toml` — do not assume md2pdf's
   dependencies (reportlab, mistletoe, requests) are available beyond their
   published API.
5. **Pin to `md2pdf >= 0.1.0`** — the public API is stable from this version.
