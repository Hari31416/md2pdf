# Changelog

All notable changes to the `md2pdf` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.3] - 2026-06-15

### Added
- **Setext Heading Support**: Remapped `SetextHeading` to `Heading` in the parser to natively support Markdown headings underlined with `===` and `---`.

### Fixed
- **Fenced Code Block Protection**: Ensured `IncludeResolver` ignores `!include` directives nested inside fenced code blocks.
- **Included Files Front-Matter Stripping**: Stripped YAML front-matter blocks from recursively included files, preventing them from leaking into the body or being parsed as Setext headings.
- **Checkbox Emoji Fallback**: Added ballot box character `U+2610` to `_EMOJI_SKIP_RANGES` to prevent failed Twemoji CDN requests, falling back to standard Unicode rendering.
- **Wired Page Numbers**: Re-wired/refactored `PageNumberPostProcessor` and resolved TOC page number fallback placeholder leaks.
- **Validator Registry Support**: Added `BlockCode` to supported types and enabled validation of custom tokens added by plugins.
- **Atomic Cache & Asset Operations**: Implemented atomic file writes (via temporary file staging and renaming) in the local asset cache and LaTeX diagram rendering cache.
- **Table Column Width Heuristics**: Improved column auto-sizing to support dynamic width heuristics based on cell content, alongside custom manual overrides.
- **Nested List & Blockquote Rendering**: Restored block-level rendering (e.g., nested lists, tables, and code blocks) inside blockquotes and list items instead of discarding/flattening them.
- **Thread Safety**: Avoided class-level state mutations in image flowables to support thread-safe concurrent rendering.
- **Documentation & Build Script**: Configured `build_docs.py` to exit with a non-zero status code on compilation failure.
- **Shared Kroki/Cache Clients**: Reused Kroki client and Cache instances inside rendering handlers instead of constructing them per-render.

## [0.5.2] - 2026-06-15

### Added
- **Deterministic PDF Output**: Introduced a `--deterministic` CLI flag and `deterministic` configuration option to enable byte-identical PDF builds. This pins document creation timestamps and ID hashes, suppressing dynamic PDF metadata variance to support CI/CD caching and clean git histories.
- **Performance Benchmarking**: Added a benchmarking suite under `scripts/benchmark.py` and comparison plots in `README.md` to measure rendering speeds against Pandoc and Playwright.
- **Integration & Regression Testing**: Added an end-to-end integration and regression testing suite using `pypdf` for text and layout structure extraction. Converts Markdown source (incorporating headings, styled text, lists, tables, admonitions, page breaks, and footnotes) to PDF in deterministic mode, asserting correct page counts, section-based headers, footnote page-locations, and body text layout properties.

### Fixed
- **Config In-place Mutation**: Copied configuration object via `dataclasses.replace` in `convert()` to avoid mutating caller-provided options.
- **TOML Parsing Optimization**: Refactored CLI to parse config TOML only once, avoiding multiple redundant disk reads.
- **CLI Flag Overrides**: Added paired flags with `None` defaults in the CLI (e.g. `--toc/--no-toc`) to allow overriding config `true` values to `false`.
- **Dynamic Theme Reloading**: Config now automatically reloads theme configuration if `config.theme` is modified after initialization.
- **Footnote Deduplication**: Implemented document-wide footnote deduplication to prevent duplicate rendering of the same footnote.
- **Thread-Safe Flowables**: Converted class-level attributes in `ResizableImage` to thread-local properties to ensure thread safety during concurrent rendering.
- **Admonition Box Defensive Wrapping**: Added defensive validation checks to ensure `AdmonitionBox.draw()` asserts that its children have been wrapped correctly.
- **Coordinate Transform Correction**: Corrected `FootnoteFlowable` absolute positioning coordinate math under non-trivial canvas transforms.
- **Include Resolver Enhancements**: Limited path resolution to the source folder and restricted recursion depth to prevent path traversal and infinite loops.
- **Admonition Title Escaping**: HTML-escaped custom admonition titles in attributes to prevent ReportLab parsing errors.
- **Indented Footnote Definition**: Added full Markdown continuation support for multi-line indented footnote definitions.
- **Single-string Plugin Registry Support**: Added `isinstance` guard to handle single string plugin registration paths safely.
- **Plugin Load Error Warning**: Compiled and logged warnings when plugin loading fails instead of silently swallowing the error.
- **Matplotlib LaTeX Rendering Logs**: Added explicit debug logging for matplotlib LaTeX rendering attempts to ease troubleshooting.

## [0.5.1] - 2026-06-14

### Fixed
- **Thread Safety**: Stored bookmark and footnote registries in document template instances and made footnote definition parsing thread-safe to support concurrent compilation runs.
- **Robustness**: Resolved admonition styling `AttributeError` crashes by fetching settings defensively, and XML-escaped custom admonition titles to prevent ReportLab parsing crashes.
- **Ordered Lists**: Respected explicit starting index numbers in ordered lists.
- **Table Columns**: Calculated table column widths dynamically using stylesheet page width and margins instead of hardcoded margins.
- **Theme Name Validation**: Validated pre-built theme names and raised `ConfigError` for unknown themes.
- **Front Matter Parsing**: Supported CRLF and EOF scenarios in YAML front matter parsing.
- **Preprocessing Isolation**: Prevented preprocessors from modifying content inside fenced code blocks.
- **Link XML Escaping**: Escaped XML special characters in link `href` values.
- **Duplicate Headings**: Uniquified duplicate heading slugs per conversion run.
- **Dependency Management**: Added missing `pillow` and `pygments` dependencies to `pyproject.toml`.
- **File Descriptor Leak**: Replaced open-file handle reads with `Path.read_text()` in `convert()` to resolve leaks.
- **Performance**: Avoided duplicate pre-processing and parsing in the two-pass layout engine.
- **State Leaks**: Cleared metadata state between pipeline runs.
- **Registry Loading**: Copied custom registry handlers to pipeline registry and registered built-ins defensively.

## [0.5.0] - 2026-06-14

### Added
- **Cover Page Generation**: Added a `--cover` CLI flag and `cover` config setting to auto-generate and prepend a cover/title page before the Table of Contents, using `title`, `author`, and `date` YAML front-matter metadata, while automatically suppressing page headers and footers on page 1.
- **Image Captions**: Render markdown image alt-text as a small, styled, and centered caption paragraph below images in the generated PDF.
- **Pre-Built Themes**: Bundled three additional built-in themes (`academic`, `minimal`, `dark`) selectable via the `--theme`/`-t` flag or the `theme` configuration setting in `md2pdf.toml`. Added support for custom page background color rendering (`color_page_bg`), utilized by the `dark` theme to fill the canvas with a charcoal background (`#1e1e1e`).

## [0.4.3] - 2026-06-14

### Added
- **Font Path Validation**: Added pre-flight validation for `[theme]` custom font file paths (`font_file_body`, `font_file_heading`, `font_file_mono`). A new `validate_font_paths()` function in `_font_registry.py` raises a `ConfigError` with a clear message if any configured path does not exist on disk, preventing cryptic ReportLab registration crashes from surfacing mid-pipeline.
- **Emoji Download Timeout**: Replaced `urlretrieve` with a `urlopen`-based download in `_fetch_emoji_png` to support a configurable network timeout. `EmojiPreProcessor` now accepts a `timeout` parameter (default `10.0` seconds) forwarded to every download call, and `PreProcessorRegistry` exposes a matching `emoji_timeout` constructor argument. Any timeout or network error is caught and treated as a graceful fallback (original emoji character is kept).
- **Unified Documentation Manual**: Added `docs/user_manual.md` which aggregates all individual guides into a single print-ready documentation manual with a Table of Contents.
- **Example Suite**: Added `examples/` directory containing four production-grade markdown templates and rendered PDFs: `academic_paper`, `business_invoice`, `project_roadmap`, and `simple_cv`.
- **Documentation Build Tooling**: Added `scripts/build_docs.py` and a `make docs` Makefile target to automate rebuilding all docs and examples into high-resolution PDFs.
- **MIT License**: Added `LICENSE` file.
- **CI Pipeline**: Added `ci.yml` GitHub Actions workflow that runs the full test suite with branch coverage on every push and pull request to `main`, and uploads results to Codecov.
- **PyPI Metadata**: Added `license`, Python version `classifiers`, and an improved package description to `pyproject.toml` for correct shields.io badge resolution after next release.
- **`matplotlib` Test Marker**: Added `matplotlib` pytest marker to skip optional-dependency tests in environments without `pymd2pdf[matplotlib]` installed.

### Changed
- **README Overhaul**: Restructured README with a user-first perspective — installation and quick start moved to the top, architecture diagrams moved to the bottom. Added "Why md2pdf?" comparison table, Quick Start, Configuration, and Contributing sections. Fixed placeholder git clone URL.
- **Release Workflow Testing**: Added automated testing step (`uv run pytest`) to the GitHub Actions release workflow to verify code correctness before initiating packaging and release publication.

### Fixed
- **CLI Test ANSI Codes**: Fixed `test_help` failure in CI caused by typer/Rich injecting ANSI escape sequences into `result.output`. Added `strip_ansi()` helper to `test_cli.py` to sanitize output before string assertions.


## [0.4.2] - 2026-06-14

### Changed
- **Release Workflow Enhancement**: Enhanced the GitHub Actions release workflow to extract the version-specific section from `CHANGELOG.md` and populate the GitHub Release body description.

## [0.4.1] - 2026-06-14

### Added
- **GitHub CI/CD Release Workflow**: Added GitHub Actions workflow to automatically build the package, create a GitHub Release, and publish to PyPI using OIDC Trusted Publishing upon tag push (`v*`).

## [0.4.0] - 2026-06-14

### Added
- **Table Column Alignment**: Enabled parsing and styling of column-level alignments (`left`, `center`, `right`) using `:---`, `:---:`, and `---:`. TableHandler now generates dynamically aligned ParagraphStyles for cell contents and appends matching `ALIGN` commands to the ReportLab `TableStyle`.
- **Superscript & Subscript Support**: Added inline parsing support for superscript `x^2^` and subscript `H~2~O` syntax using custom mistletoe SpanTokens (with strict lookaround checks to avoid conflicts with Strikethrough or other markdown formatting) and rendering using ReportLab's native `<sup>` and `<sub>` tags.
- **Strikethrough & Highlight Support**: Added inline parsing support for `~~strikethrough~~` (renders using `<strike>` ReportLab tags) and `==highlight==` (renders using `<span backcolor="...">` ReportLab tags). Added `color_highlight` config field to `ThemeConfig` to allow custom highlight color configuration.
- **Progress Reporting**: Added stage-level compilation progress reports to `sys.stderr`. Emits details on pre-processing, includes resolving, parsing, diagram mapping and rendering, emoji assets batch download, and PDF layout passes. Added a new `--progress/--no-progress` CLI option and `progress_callback` to the top-level Python API.
- **Optional Matplotlib LaTeX Math Rendering**: Added support for offline, fast LaTeX equation rendering via `matplotlib.mathtext` (optional dependency `pymd2pdf[matplotlib]`).
- **LatexBlockPreProcessor**: Added a preprocessor to convert block math `$$ ... $$` into `latex` code fences before parsing, preventing the parser from fragmenting equations containing escaped `$` signs or nested environments.

### Changed
- **Task List Checkboxes**: Changed `ListHandler` to use a white square emoji (`U+25FB`) for unchecked tasks instead of the black ballot box emoji (`U+2610`). This ensures that unchecked tasks display correctly with the color emoji theme enabled (where only checked boxes use the specific `2611` PNG).
- **Concurrent Asset Pre-fetching**: Implemented concurrent scanning and pre-fetching of Mermaid and LaTeX assets in a thread pool of 5 workers before document mapping, drastically speeding up compilation for formula-heavy documents.
- **Kroki Error Retry & Fallback**: Added a single-retry limit for Kroki client calls (2 attempts total). Block math now falls back to showing raw LaTeX within a monospace block (`Preformatted`) instead of rendering a generic placeholder box graphic on error.

## [0.3.0] - 2026-06-13

### Added
- **Colour Emoji Support (Twemoji)**: Added `EmojiPreProcessor` (priority 35) that detects emoji codepoints in Markdown source, downloads matching PNG files from the Twemoji CDN, caches them under `~/.cache/pymd2pdf/emoji/`, and injects inline `<img>` tags so emojis render in colour in the final PDF. Handles ZWJ sequences, variation-selector-16, skin-tone modifiers, and multi-codepoint sequences as single units. Skips pure-math Unicode blocks (arrows, box-drawing, etc.) to avoid false positives. Added `emoji: bool = True` config field and `--emoji`/`--no-emoji` CLI flag.
- **Pagebreak Directive**: Added `PageBreakPreProcessor` that translates `<!-- pagebreak -->` HTML comments and `\pagebreak` backslash syntax into `PageBreak` tokens. Implemented `PageBreakHandler` which emits a ReportLab `PageBreak` flowable, giving authors explicit pagination control without touching the pipeline.
- **Admonition / Callout Blocks**: Added `AdmonitionPreProcessor` that converts MkDocs/Obsidian-style fenced containers (`:::note`, `:::warning`, `:::tip`, `:::info`, `:::caution`) and GitHub-style alerts (`> [!NOTE]`, `> [!WARNING]`, etc.) into HTML. Implemented `AdmonitionBox` flowable with a coloured left border and tinted background, and a matching `AdmonitionHandler` with distinct colour themes per severity level.
- **Inline `<br>` Tag Support**: `inline_render()` now translates escaped raw HTML `<br>` tags into ReportLab paragraph break tags, enabling hard line breaks inside paragraphs, lists, and table cells.

### Changed
- **Table / Heading Layout**: Added `KeepTogetherParts` flowable to allow tables to split across pages while keeping their preceding heading attached. `LayoutComposer` now wraps heading–table pairs in `KeepTogetherParts` instead of a strict `KeepTogether`, preventing orphaned headings without forcing entire large tables onto a new page.
- **Inline Image Handling**: `ParagraphHandler` classifies images by size threshold (≤ 32 px = inline, larger = block `ResizableImage` flowable). `_expand_inline_imgs()` helper added to `inline_render()` so emoji render inline (`valign=middle`) in headings, lists, tables, and blockquotes.

## [0.2.0] - 2026-06-13

### Added
- **Table of Contents (TOC) Generation**: Prepend a dynamically generated, A4-aligned Table of Contents page before the content by walking bookmark flowables. Added a `--toc` CLI flag and `toc` config property.
- **YAML Front-Matter PDF Metadata**: Integrated yaml front-matter parsing to extract PDF metadata (`title`, `author`, `subject`, `keywords`) and applied them to the final PDF properties. Fallbacks are set to "pymd2pdf" for author and the input filename for title.
- **Footnotes Support**: Registered FootnoteReference and FootnoteDefinition markdown tokens. Implemented `FootnoteFlowable` with eager height calculations for overlapping stack prevention, supporting internal clickable links and two-pass page resolving.
- **Running Page Headers & Section Titles**: Added configurable page headers/running titles. Supported `--header` and `--header-on-first-page` CLI options, template placeholders (`{title}`, `{section}`), and two-pass layout rendering for section titles.

### Changed
- Improved `README.md` documentation covering bookmark/unicode features, corrected project tree structure, and updated development setup instructions.

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
