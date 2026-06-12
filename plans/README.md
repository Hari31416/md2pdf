# MD-Flow Implementation Plan Index

Automated Programmatic Markdown-to-PDF Typesetting Engine

---

## Phase Overview

| Phase | File | Focus | Key Output |
|-------|------|-------|------------|
| 1 | [phase-1-foundation.md](./phase-1-foundation.md) | Project skeleton, plugin registry core, CLI stub | `pyproject.toml`, `HandlerRegistry`, `Pipeline` skeleton |
| 2 | [phase-2-parser.md](./phase-2-parser.md) | mistletoe AST parser, token normalization, pre-processor hook | `MarkdownParser`, `PreProcessorRegistry`, token types |
| 3 | [phase-3-handlers.md](./phase-3-handlers.md) | All built-in element handlers + default stylesheet | `HeadingHandler`, `TableHandler`, `ListHandler`, `inline_render` |
| 4 | [phase-4-assets.md](./phase-4-assets.md) | Kroki API, disk cache, offline fallback | `KrokiClient`, `AssetCache`, `MermaidHandler`, `LatexHandler` |
| 5 | [phase-5-plugins.md](./phase-5-plugins.md) | Full plugin system (all 4 hook stages, both discovery mechanisms) | `PluginLoader`, `PostProcessor`, `StyleRegistry` |
| 6 | [phase-6-layout.md](./phase-6-layout.md) | Layout safeguards: ghost pages, orphans, table splits | `LayoutComposer`, `BlockQuoteBar`, page number footer |
| 7 | [phase-7-cli.md](./phase-7-cli.md) | Full CLI, validation pass with line-number errors | `DocumentValidator`, `ValidationIssue`, full `cli.py` |
| 8 | [phase-8-testing.md](./phase-8-testing.md) | Test suite, packaging, README, plugin authoring docs | `tests/`, `README.md`, `docs/plugin-authoring.md` |

---

## Dependency Graph

```
Phase 1 (Foundation)
    └── Phase 2 (Parser)
            └── Phase 3 (Handlers) ──────────────┐
            └── Phase 4 (Assets)  ──────────────┤
                                                  ├── Phase 5 (Plugins)
                                                  ├── Phase 6 (Layout)
                                                  ├── Phase 7 (CLI)
                                                  └── Phase 8 (Testing)
```

Phases 5, 6, 7 can be worked in parallel once Phases 1–4 are complete.

---

## Architectural Decisions (Deviations from original overview.md)

| Original | Changed To | Reason |
|---------|-----------|--------|
| `markdown` + BS4 parser | `mistletoe` AST parser | Produces a typed AST; far more reliable for pipelines and plugin hook points |
| No caching | SHA-256 disk cache (`.md2pdf_cache/`) | Avoids redundant Kroki API calls on iterative runs |
| Hard failure on network error | `PlaceholderBox` fallback + `--offline` flag | Network outage should never abort a run |
| No style system | `StyleSheet` dataclass + `StyleRegistry` | Enables theme plugins and config-driven style overrides |
| No validation | `DocumentValidator` with line-number reporting | Structured pre-render validation for better DX |
| No plugin system | 4-stage plugin hook (pre-process, handler, post-process, stylesheet) | Extensible by design; entry-points + config-file discovery |

---

## Plugin System Quick Reference

```
Entry-point groups:
  md2pdf.handlers       → ElementHandler subclass
  md2pdf.preprocessors  → PreProcessor subclass
  md2pdf.postprocessors → PostProcessor subclass
  md2pdf.stylesheets    → class with get_stylesheet() -> dict

Config-file alternative (md2pdf.toml):
  [plugins]
  handlers = ["my_pkg.handlers:MyHandler"]
  preprocessors = [...]
  postprocessors = [...]
```

See [phase-5-plugins.md](./phase-5-plugins.md) for the full plugin authoring contract.
