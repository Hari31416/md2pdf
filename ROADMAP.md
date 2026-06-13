# Roadmap

Planned features and known limitations for future releases. Items are loosely ordered by priority.

---

## PDF Bookmark / Outline Panel ✅

**Status:** Implemented in v0.1.4.

`BookmarkFlowable` now calls both `canvas.bookmarkPage` (internal anchor) **and**
`canvas.addOutlineEntry` (outline entry visible in the PDF viewer's bookmarks/navigation
panel). Every heading (H1–H6) becomes a clickable entry at the correct nesting depth.

---

## Table of Contents Generation ✅

**Status:** Implemented in v0.2.0.

Prepend a dynamically generated, A4-aligned Table of Contents page before the content by walking bookmark flowables. Can be enabled via the `--toc` CLI flag and `toc` config property.

---

## YAML Front-Matter PDF Metadata ✅

**Status:** Implemented in v0.2.0.

Integrated yaml front-matter parsing to extract PDF metadata (`title`, `author`, `subject`, `keywords`) and applied them to the final PDF properties. Fallbacks are set to "pymd2pdf" for author and the input filename for title.

---

## Footnotes Support ✅

**Status:** Implemented in v0.2.0.

Registered FootnoteReference and FootnoteDefinition markdown tokens. Implemented `FootnoteFlowable` with eager height calculations for overlapping stack prevention, supporting internal clickable links and two-pass page resolving.

---

## Running Page Headers & Section Titles ✅

**Status:** Implemented in v0.2.0.

Added configurable page headers/running titles. Supported `--header` and `--header-on-first-page` CLI options, template placeholders (`{title}`, `{section}`), and two-pass layout rendering for section titles.

---

## Hyperlink Pass-Through ✅

**Status:** Implemented.

Markdown links `[text](https://...)` are compiled into HTML-like `<a href="...">` XML tags in `inline_render()`, enabling ReportLab to write active, clickable URI annotations directly into the generated PDF.

## Colour Emoji Support ✅

**Status:** Implemented — Option A (Twemoji image substitution).

Standard PDF fonts and ReportLab's text rendering pipeline do not support colour font tables
(`CBDT/CBLC`, `COLR/CPAL`, `sbix`, `SVG`). Colour emojis cannot be delivered via a font alone.

The two viable approaches, both fitting the existing pre-processor plugin architecture:

### Option A — Twemoji image substitution (recommended)
A `PreProcessor` detects emoji codepoints in the Markdown source and replaces them with
inline `<img>` references pointing to cached PNG files from the
[Twemoji](https://github.com/twitter/twemoji) set (CC-BY 4.0).
The existing `AssetCache` would store the downloaded PNGs after the first run.

```
Input:  "Hello 🌍 world!"
Output: 'Hello <img src="~/.cache/pymd2pdf/emoji/1f30d.png" width="10" height="10" valign="middle"/> world!'
```

- ✅ Full colour, matches Twitter/Slack/GitHub emoji
- ✅ Slots in as a built-in `PreProcessor` at priority 30
- ⚠️ Requires a network call on first run; fully cached after

### Option B — Bundled Noto Emoji PNG subset
Bundle a curated subset of the
[Noto Emoji](https://github.com/googlefonts/noto-emoji) PNG set (Apache 2.0)
directly in the package for full offline support. A larger download (~5–25 MB depending
on subset size), but zero runtime network dependency.

### Non-options (investigated, ruled out)
- **Symbola / Noto Emoji TTF fonts** — render emoji as monochrome outlines only; no colour support via ReportLab.
- **Pillow + system colour emoji font** — Pillow's `ImageFont` does not support colour font tables; requires `harfbuzz`/`cairo` bindings.
- **WeasyPrint / Playwright backend** — full browser-quality colour emoji, but requires replacing the entire ReportLab pipeline.

---

## `<!-- pagebreak -->` Directive ✅

**Status:** Implemented in v0.3.0.

`PageBreakPreProcessor` translates `<!-- pagebreak -->` HTML comments and `\pagebreak` backslash syntax into `PageBreak` tokens. `PageBreakHandler` emits a ReportLab `PageBreak` flowable, giving authors explicit pagination control.

---

## Admonition / Callout Blocks ✅

**Status:** Implemented in v0.3.0.

`AdmonitionPreProcessor` converts MkDocs/Obsidian-style fenced containers (`:::note`, `:::warning`, `:::tip`, `:::info`, `:::caution`) and GitHub-style alerts (`> [!NOTE]`, `> [!WARNING]`, etc.) into HTML before parsing. `AdmonitionHandler` renders them with `AdmonitionBox` flowables — coloured left border and tinted background — with distinct colour themes per severity level.

---

## Task List Checkboxes ✅

**Status:** Implemented

GFM-style task list checkboxes (`- [ ] todo` / `- [x] done`) are detected in `ListHandler` and replaced with Twemoji images (if `emoji` option is enabled and downloaded successfully) or with ballot box Unicode characters (`☐` / `☑`) from the default DejaVu Sans font.

---

## Short-term (implementation path is clear)

- **Table column alignment** — `mistletoe` already parses column alignment (`:---`,
  `:---:`, `---:`) and exposes it on the table node. `TableHandler` currently ignores it.
  Pass alignment through to ReportLab `TableStyle` `ALIGN` commands.

- **Superscript & subscript** — `x^2^` and `H~2~O` syntax. ReportLab supports `<sup>`
  and `<sub>` tags natively; this needs a new `SpanToken` subclass + `inline_render` case.

---

## Medium-term (needs design work)

- **Multi-column layouts** — two- or three-column text flow for newsletter-style documents.
  ReportLab supports multi-frame layouts via `BaseDocTemplate` + `PageTemplate`; this
  would require replacing `SimpleDocTemplate` with a more configurable template class.

- **Right-to-left text** — Arabic, Hebrew, and other RTL scripts via a BiDi pre-processor
  (using `python-bidi`) that reorders paragraphs before they reach the ReportLab pipeline.

- **Strikethrough & highlight** — `~~strikethrough~~` and `==highlight==` inline spans.
  Strikethrough can be simulated by drawing a line over the text in a custom `Paragraph`
  subclass; highlight requires a filled background rectangle behind the glyph runs.

- **Cover page generation** — a `--cover` flag that auto-generates a title page from
  YAML front-matter (`title`, `author`, `date`) and prepends it before the TOC. Natural
  extension of the existing `MetadataPostProcessor` + `TableOfContentsPostProcessor`.

---

## Robustness & DX

- **Font path validation** — if a user-specified `font_file_body` path in `[theme]`
  doesn't exist, the pipeline crashes with a cryptic ReportLab error during
  `register_fonts()`. A pre-flight check that validates font paths and emits a clear
  `ConfigError` would help.

- **Encoding detection** — `cli.py` hard-codes `encoding="utf-8"`. Files in Latin-1 or
  Windows-1252 will crash. Add an `--encoding` CLI flag with optional auto-detection.

- **Emoji download timeout** — `EmojiPreProcessor` uses bare `urlretrieve` with no
  timeout. A slow or unresponsive CDN will hang the pipeline indefinitely.

- **`--dry-run` flag** — show what the pipeline would do (pre-processors matched,
  handlers dispatched, token counts) without actually rendering the PDF.

- **Structured JSON validation output** — `--validate-only` currently writes
  human-readable text to stdout. A `--format json` option would allow CI integration
  (e.g. GitHub Actions annotations).

- **Progress reporting** — for multi-page documents with external assets (Mermaid,
  LaTeX, emoji downloads), the CLI is silent until completion. Stage-level logging
  or a progress bar would improve UX.

- **Deterministic PDF output** — ReportLab embeds a creation timestamp and unique `/ID`
  in every PDF. A `--deterministic` flag that pins these values (e.g. to the source
  file's mtime) would enable byte-identical CI rebuilds.

---

## Longer-term / exploratory

- **Watch mode** — `md2pdf --watch input.md` that re-renders on file change using
  `watchfiles` or `watchdog`, useful for live-preview workflows.

- **HTML snapshot output** — a second output target (`--format html`) that reuses the
  same pipeline but emits styled HTML instead of a PDF, useful for CI preview artefacts.

- **Page-size / orientation config** — expose `pagesize` (A4, Letter, A3, …) and
  `landscape` as `[md2pdf]` TOML options and CLI flags.

- **Image captions** — render `![caption](url)` caption text below figures using a
  small italic `Paragraph` with a configurable style, matching academic document conventions.

- **Pre-built themes** — ship 2–3 additional themes (e.g. `academic`, `minimal`, `dark`)
  as built-in options selectable via `--theme academic`. The `[theme]` system is powerful
  but currently only has a `default`.

- **Integration tests** — the test suite is unit-focused. An end-to-end test that converts
  a reference `.md` → `.pdf` and extracts text (via `pdfplumber` or `PyMuPDF`) to assert
  content correctness would catch regressions that unit tests miss.
