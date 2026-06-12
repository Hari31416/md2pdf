# Roadmap

Planned features and known limitations for future releases. Items are loosely ordered by priority.

---

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

- **Table of Contents generation** — auto-generate a linked TOC from heading tokens.
- **Page headers** — configurable running headers with document title / section name.
- **Multi-column layouts** — two- or three-column text flow for newsletter-style documents.
- **Footnotes** — `[^1]` footnote syntax rendered at the bottom of each page.
- **Right-to-left text** — Arabic, Hebrew, and other RTL scripts via a BiDi pre-processor.
