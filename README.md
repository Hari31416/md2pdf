# md2pdf

**Automated Programmatic Markdown-to-PDF Typesetting Engine**

Convert structured Markdown to print-ready PDFs — no Pandoc, no Node.js, no headless browsers.

---

> ⚠️ **Work in progress.** This README will be expanded in Phase 8.

## Quick start

```bash
uv tool install md2pdf
md2pdf report.md -o report.pdf
```

## Features

- Standard elements: headings, paragraphs, lists, blockquotes, hyperlinks
- Multi-page tables with repeating headers and row-split protection
- Mermaid diagrams and LaTeX math via Kroki.io (offline fallback + disk caching)
- Plugin system: add element handlers, pre/post processors, and themes via entry points
- Strict layout safeguards: no ghost pages, no orphaned lines, no mid-row splits

## Documentation

See [`plans/README.md`](plans/README.md) for the phased implementation plan.
