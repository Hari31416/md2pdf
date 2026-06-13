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


## Colour Emoji Support

**Status:** Research complete — not yet implemented.

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

## Additional Planned Items

### Near-term (fits current architecture)

- **`<!-- pagebreak -->` directive** — a `PreProcessor` that converts the HTML comment
  (or a custom `\pagebreak` syntax) into a `PageBreak` flowable token, giving authors
  explicit control over pagination without editing the pipeline.

- **Admonition / callout blocks** — `:::note`, `:::warning`, `:::tip` fenced containers
  (standard in MkDocs/Obsidian). Implementable as a `PreProcessor` that rewrites them
  to HTML `<div class="admonition …">` before parsing, then a matching `ElementHandler`.

### Medium-term (needs design work)

- **Hyperlink pass-through** — `[text](https://…)` links currently render as styled text.
  Emit `<link href="…">` XML in `inline_render` so ReportLab writes a real clickable
  URI annotation into the PDF.

- **Multi-column layouts** — two- or three-column text flow for newsletter-style documents.
  ReportLab supports multi-frame layouts via `BaseDocTemplate` + `PageTemplate`; this
  would require replacing `SimpleDocTemplate` with a more configurable template class.

- **Right-to-left text** — Arabic, Hebrew, and other RTL scripts via a BiDi pre-processor
  (using `python-bidi`) that reorders paragraphs before they reach the ReportLab pipeline.

- **Strikethrough & highlight** — `~~strikethrough~~` and `==highlight==` inline spans.
  Strikethrough can be simulated by drawing a line over the text in a custom `Paragraph`
  subclass; highlight requires a filled background rectangle behind the glyph runs.

### Longer-term / exploratory

- **Watch mode** — `md2pdf --watch input.md` that re-renders on file change using
  `watchfiles` or `watchdog`, useful for live-preview workflows.

- **HTML snapshot output** — a second output target (`--format html`) that reuses the
  same pipeline but emits styled HTML instead of a PDF, useful for CI preview artefacts.

- **Page-size / orientation config** — expose `pagesize` (A4, Letter, A3, …) and
  `landscape` as `[md2pdf]` TOML options and CLI flags.

- **Image captions** — render `![caption](url)` caption text below figures using a
  small italic `Paragraph` with a configurable style, matching academic document conventions.
