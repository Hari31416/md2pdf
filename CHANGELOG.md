# Changelog

All notable changes to the `md2pdf` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-06-12

### Fixed
- **PDF bookmark / outline panel** — `BookmarkFlowable` now calls `canvas.addOutlineEntry`
  in addition to `canvas.bookmarkPage`, so all headings (H1–H6) appear as clickable,
  correctly nested entries in the PDF viewer's bookmarks/navigation panel.

### Changed
- `HeadingHandler` passes the plain-text heading title (HTML tags stripped) and the
  0-indexed heading level to `BookmarkFlowable` so the outline nesting depth is correct.
- Expanded `ROADMAP.md` with near-term, medium-term, and longer-term feature plans,
  all grounded in the current pipeline architecture.

## [0.1.3] - 2026-06-12

### Added
- Bundled **DejaVu Sans** TrueType fonts (`DejaVuSans`, `DejaVuSans-Bold`, `DejaVuSansMono`, `DejaVuSansMono-Bold`) inside the package for broad Unicode coverage out-of-the-box — no system font dependency required.
- Unicode characters now render natively: Latin Extended, Greek, Cyrillic, mathematical operators, arrows, box-drawing characters, currency symbols, and typographic punctuation.
- New `font_file_body`, `font_file_heading`, and `font_file_mono` fields in `ThemeConfig` and `md2pdf.toml` let users supply custom TTF fonts by file path. The engine registers them automatically — no plugin or Python code required.
- Updated `docs/showcase.md` with a new **Section 12: Unicode & Special Characters** showcasing all supported character classes and the custom font configuration pattern.

### Changed
- Default fonts changed from `Helvetica` / `Helvetica-Bold` / `Courier` (PDF core fonts, Latin-1 only) to `DejaVuSans` / `DejaVuSans-Bold` / `DejaVuSansMono` (bundled, broad Unicode coverage).
- `md2pdf.toml.example` updated to reflect new font defaults and document the `font_file_*` fields.

### Removed
- `clean_box_drawing()` function and `_BOX_DRAWING_MAP` translation table from `md2pdf/handlers/code.py` — previously worked around Courier's missing box-drawing glyphs; no longer needed with DejaVuSansMono as the default mono font.
- Corresponding `clean_box_drawing` calls removed from `CodeFenceHandler.render()` and the pipeline fallback renderer.

## [0.1.2] - 2026-06-12

### Added
- Support for inline (`$formula$`) and block (`$$formula$$`) LaTeX equations via Kroki tikz endpoint.
- Recursive file inclusion (`!include path/to/file.md`) with relative path resolution and cycle/loop detection.
- Spacing configuration options and uniform margins for layout elements.

### Changed
- Relocated default cache directory to standard user cache `~/.cache/pymd2pdf`.

### Fixed
- Fixed Markdown image path resolution: mapped the `src` attribute to `target` during parser normalization to prevent local images from failing loading checks.
- Fixed list indentation alignment.

## [0.1.1] - 2026-06-12

### Added
- Full rendering support for standard Markdown images (`[alt](path)`) and HTML `<img>` tags inside paragraphs.
- Parse custom `width` and `height` attributes (pixels/percentages) for HTML `<img>` tags, matching aspect ratios.
- Fallback placeholder boxes (`PlaceholderBox`) for missing or corrupt local image paths.
- Exposed core validation/exception types (`ValidationIssue`, `Md2PdfError`, `ParseError`, `RenderError`, `ConfigError`) at the package level.
- Config file auto-discovery: automatically search `./md2pdf.toml`, `~/.config/md2pdf/md2pdf.toml`, and `~/.md2pdf.toml`.

### Changed
- Relocated default cache directory from local `.md2pdf_cache` to cross-platform standard user cache `~/.cache/pymd2pdf`.
- Made `registry` argument optional in `Pipeline.__init__` and `convert()`.
- Implemented safe registry copy/overlay logic to prevent mutating caller's registry objects and support custom handler overrides.
- Ensured `convert()` respects explicit `src`/`dst` path parameters when overriding custom config values.

## [0.1.0] - 2026-06-12

### Added
- Linear PDF rendering pipeline using ReportLab and mistletoe.
- Pre-render document validation (`DocumentValidator`) with structured error/warning types:
  - `UNSUPPORTED_ELEMENT` for unhandled elements.
  - `EMPTY_TABLE` and `NESTED_TABLE` for table checks.
  - `EMPTY_DIAGRAM` for diagram blocks.
- Typesetting safeguards and anti-fail composition logic (`LayoutComposer`):
  - Orphaned heading prevention via `KeepTogether`.
  - Heading-diagram association to eliminate blank ghost pages.
  - Page number callbacks rendering "Page X" on footers.
  - Left vertical accent bar rendering for blockquotes using custom `BlockQuoteBar` flowable (supporting multi-page page-split).
  - Bookmark metadata generation for Table of Contents targets via `BookmarkFlowable`.
- Extensible 4-stage plugin system:
  - Supports Entry-points (`pyproject.toml`) and config-file (`md2pdf.toml`) loading strategies.
  - Dynamic stylesheet registry and theme override configurations.
- Kroki.io client integration for Mermaid diagrams and LaTeX tikz blocks.
  - Includes SHA-256 disk caching (`.md2pdf_cache/`) and offline rendering placeholder fallback modes.
- Complete test suite covering registry, handlers, parser, theme, layout, validator, and CLI integration.

### Fixed
- Fixed LaTeX compilation failure for block math environments (like `align*`) on the Kroki `tikz` endpoint by adding newlines to the document wrapper.
- Fixed diagram sizing issues and whitespace margins by implementing PIL-based auto-cropping for both LaTeX (Tikz) and Mermaid diagrams, removing empty borders and centering diagrams correctly in the PDF layout.
- Added a height-capping layout safeguard (max 600.0 points) to dynamically scale down tall/large diagrams and prevent ReportLab `LayoutError` crashes.
- Fixed inline code rendering to correctly resolve text nested within the mistletoe AST's children array.
- Implemented `CodeFenceHandler` using a monospaced font, thin border, and light gray background to render generic fenced code blocks.
- Implemented a pipeline-level fallback formatting rule that converts any unimplemented/unsupported markdown elements to monospaced debug blocks showing their token type and content.

