# Phase 5: Plugin System (Full)

**Goal:** Make the plugin system production-ready. Finalize all four hook stages (pre-process, element handler, post-render, stylesheet override), wire up both discovery mechanisms (entry points + config file), and document the third-party plugin authoring contract.

**Depends on:** Phase 1 (registry skeleton), Phase 2 (pre-processors), Phase 3 (handlers), Phase 4 (asset handlers)

---

## Overview: Four Hook Stages

```
[ Raw .md ]
    │
    ▼
┌─────────────────────────────────┐
│  Stage 1: Pre-Processors        │  ← hook: transform raw markdown text
│  (ordered list of PreProcessor) │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 2: AST Parser            │  (not pluggable — mistletoe is fixed)
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 3: Element Handlers      │  ← hook: replace / add token → Flowable mapping
│  (HandlerRegistry dispatch)     │
└─────────────────┬───────────────┘
                  │
                  ▼
┌─────────────────────────────────┐
│  Stage 4: Post-Processors       │  ← hook: mutate/annotate the final PDF doc
│  (ordered list of PostProcessor)│    e.g. watermarks, page numbers, TOC
└─────────────────────────────────┘
                  │
                  ▼
           [ PDF Output ]
```

Additionally, plugins can supply a **StyleSheet override** that is merged with the default styles before any handler sees the `styles` dict.

---

## Deliverables

- `md2pdf/core/preprocessors.py` — finalized with `PreProcessorRegistry`
- `md2pdf/core/postprocessors.py` — `PostProcessor` ABC + `PostProcessorRegistry`
- `md2pdf/core/styles.py` — `StyleRegistry` (merge mechanism)
- `md2pdf/core/plugin_loader.py` — `PluginLoader` (entry-points + config-file)
- Updated `Pipeline` — integrates all four stages
- `docs/plugin-authoring.md` — authoring guide for third-party plugin developers
- `tests/test_plugin_loader.py`

---

## Stage 1: Pre-Processor Registry

```python
class PreProcessorRegistry:
    def __init__(self) -> None:
        self._processors: list[PreProcessor] = []

    def register(self, pp: PreProcessor, *, priority: int = 50) -> None:
        """Lower priority = runs first. Default = 50."""
        self._processors.append((priority, pp))
        self._processors.sort(key=lambda x: x[0])

    def run_all(self, raw_md: str) -> str:
        for _, pp in self._processors:
            raw_md = pp.process(raw_md)
        return raw_md
```

Built-in pre-processors registered at priority 10:
- `FrontMatterStripper` (priority 10)
- `IncludeResolver` (priority 20, future)

Plugin pre-processors default to priority 50, so they run after built-ins unless overridden.

---

## Stage 4: Post-Processor System (`postprocessors.py`)

Post-processors receive the `SimpleDocTemplate` and the list of flowables **before** `doc.build()` is called. They can insert, remove, or wrap flowables, or set document metadata.

```python
from abc import ABC, abstractmethod
from reportlab.platypus import SimpleDocTemplate

class PostProcessor(ABC):
    @abstractmethod
    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        """Return (possibly modified) flowables list."""
        ...

class PageNumberPostProcessor(PostProcessor):
    """Adds a page number footer via onPage callback (built-in)."""
    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        # Attach onFirstPage / onLaterPages callbacks
        return flowables   # flowables unchanged; callback handles drawing

class WatermarkPostProcessor(PostProcessor):
    """Example plugin: stamps 'DRAFT' diagonally on every page."""
    def __init__(self, text: str = "DRAFT") -> None:
        self.text = text

    def process(self, doc: SimpleDocTemplate, flowables: list) -> list:
        ...
```

---

## StyleSheet Override

Plugins can supply additional style entries that merge with the default stylesheet. Later entries win.

```python
class StyleRegistry:
    def __init__(self) -> None:
        self._layers: list[dict] = []

    def add_layer(self, styles: dict) -> None:
        self._layers.append(styles)

    def build(self) -> dict:
        """Merge all layers; later layers override earlier ones."""
        merged: dict = {}
        for layer in self._layers:
            merged.update(layer)
        return merged
```

Usage in Pipeline:
```python
self._style_registry = StyleRegistry()
self._style_registry.add_layer(build_default_stylesheet())
# plugins add their own layer via:
#   style_registry.add_layer(plugin.get_stylesheet())
styles = self._style_registry.build()
```

---

## Plugin Loader (`plugin_loader.py`)

```python
import importlib
import logging
from importlib.metadata import entry_points

class PluginLoader:
    def __init__(
        self,
        handler_registry: HandlerRegistry,
        pre_registry: PreProcessorRegistry,
        post_registry: PostProcessorRegistry,
        style_registry: StyleRegistry,
    ) -> None:
        self.handlers = handler_registry
        self.pre = pre_registry
        self.post = post_registry
        self.styles = style_registry

    def load_entry_points(self) -> None:
        """Auto-discover installed packages that declare md2pdf.* entry points."""
        self._load_ep_group("md2pdf.handlers", self.handlers.register)
        self._load_ep_group("md2pdf.preprocessors", self.pre.register)
        self._load_ep_group("md2pdf.postprocessors", self.post.register)
        self._load_ep_group("md2pdf.stylesheets",
                            lambda cls: self.styles.add_layer(cls().get_stylesheet()))

    def _load_ep_group(self, group: str, register_fn) -> None:
        for ep in entry_points(group=group):
            try:
                cls = ep.load()
                register_fn(cls())
                logging.info("Loaded plugin: %s from %s", ep.name, ep.group)
            except Exception as exc:
                logging.error("Failed to load plugin %s: %s", ep.name, exc)

    def load_from_config(self, config_plugins: dict) -> None:
        """Load plugins declared in md2pdf.toml [plugins] section."""
        for path in config_plugins.get("handlers", []):
            self._load_class(path, self.handlers.register)
        for path in config_plugins.get("preprocessors", []):
            self._load_class(path, self.pre.register)
        for path in config_plugins.get("postprocessors", []):
            self._load_class(path, self.post.register)

    def _load_class(self, dotted_path: str, register_fn) -> None:
        module_path, cls_name = dotted_path.rsplit(".", 1)
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            register_fn(cls())
        except Exception as exc:
            logging.error("Failed to load class %s: %s", dotted_path, exc)
```

---

## Config File (`md2pdf.toml.example`)

```toml
[md2pdf]
output_file = "report.pdf"
theme = "default"
offline = false
cache_dir = ".md2pdf_cache"

[plugins]
handlers = [
    "my_package.handlers.CalloutHandler",
    "my_package.handlers.TimelineHandler",
]
preprocessors = [
    "my_package.preprocessors.IncludeDirectiveResolver",
]
postprocessors = [
    "my_package.postprocessors.WatermarkPostProcessor",
]
```

---

## Entry-Point Declaration (third-party plugin `pyproject.toml`)

```toml
[project.entry-points."md2pdf.handlers"]
callout  = "my_package.handlers:CalloutHandler"
timeline = "my_package.handlers:TimelineHandler"

[project.entry-points."md2pdf.postprocessors"]
watermark = "my_package.postprocessors:WatermarkPostProcessor"

[project.entry-points."md2pdf.stylesheets"]
my_theme = "my_package.themes:MyTheme"
```

---

## Plugin Authoring Contract (summary for `docs/plugin-authoring.md`)

A plugin is a Python package that:

1. **Implements one or more** of:
   - `ElementHandler` subclass (for new/overridden token types)
   - `PreProcessor` subclass (for markdown text transforms)
   - `PostProcessor` subclass (for PDF-level transforms)
   - A class with `get_stylesheet() -> dict` (for style overrides)

2. **Declares entry points** under the appropriate `md2pdf.*` group.

3. **Does not depend** on internal `md2pdf` private APIs (only `md2pdf.core.registry`, `md2pdf.core.preprocessors`, `md2pdf.core.postprocessors` are public API).

4. **Returns valid ReportLab `Flowable` instances** from `ElementHandler.render()`.

---

## Acceptance Criteria

- [ ] `PluginLoader.load_entry_points()` silently succeeds when no plugins are installed
- [ ] A dummy `ElementHandler` installed as a package is auto-discovered and registered
- [ ] Config-file-declared handler overrides a built-in handler (last-wins)
- [ ] `StyleRegistry.build()` correctly merges two overlapping style dicts, later wins
- [ ] `PostProcessor` chain executes in registration order
- [ ] All plugin loading errors are logged (not raised) so one bad plugin doesn't abort the run
- [ ] `docs/plugin-authoring.md` exists and documents the full authoring guide
