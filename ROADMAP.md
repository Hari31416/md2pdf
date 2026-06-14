# Roadmap

Planned features and known limitations for future releases. Items are loosely ordered by priority.

---

## 🗺️ Future Roadmap

### Short-Term (Target: v0.5.0)

- **Font Path Validation** — Perform pre-flight validation on user-configured font paths in `[theme]`. Raise a clear `ConfigError` if a font file is missing, preventing cryptic ReportLab crashes during registration.
- **Emoji Download Timeout** — Implement a timeout for download requests in `EmojiPreProcessor` to prevent the compilation pipeline from hanging indefinitely on network issues.
- **Structured JSON Validation Output** — Introduce a `--format json` CLI option for the `--validate-only` command to output structured validation results, making CI/CD automation integration easier.
- **Page-Size & Orientation Configuration** — Expose page sizing (e.g., A4, Letter, A3) and page orientation (landscape/portrait) as configuration options in `md2pdf.toml` and as CLI flags.
- **Image Captions** — Render image alt-text (`![Caption](image.png)`) as a small, styled, and centered caption paragraph below images, matching academic and technical document conventions.

---

### Medium-Term (Target: v0.6.0)

- **Cover Page Generation** — Add a `--cover` CLI flag to auto-generate and prepend a cover/title page using YAML front-matter metadata (`title`, `author`, `date`) before the table of contents.
- **Watch Mode** — Support live editing with `md2pdf --watch input.md`, automatically re-rendering the output PDF whenever changes are detected in the source file.
- **Pre-Built Themes** — Bundle additional built-in themes (e.g., `academic`, `minimal`, `dark`) selectable via the `--theme` flag.
- **Encoding Detection** — Add an `--encoding` CLI flag to support reading non-UTF-8 source files, along with optional auto-detection.
- **Deterministic PDF Output** — Introduce a `--deterministic` flag to pin document creation timestamps and ID hashes, enabling byte-identical builds for CI caching.
- **Integration & Regression Testing** — Create end-to-end regression tests converting reference Markdown files to PDF and asserting text correctness (via PDF text extraction) to prevent visual or layout regressions.

---

### Longer-Term / Exploratory

- **Multi-Column Layouts** — Support newsletter or paper-style documents with multi-column text flows. This will involve moving from `SimpleDocTemplate` to custom multi-frame `BaseDocTemplate` layouts.
- **Right-to-Left (RTL) Text** — Integrate a BiDi text-ordering pre-processor to support Arabic, Hebrew, and other RTL language scripts.
- **HTML Snapshot Output** — Support compiling to styled HTML (`--format html`) alongside PDF output using the same underlying pipeline.
- **Pipeline Dry Run** — Add a `--dry-run` CLI flag to output matched pre-processors, dispatched handlers, and metadata without generating the PDF.

---

## 🏛️ Completed Milestones

| Version    | Feature                   | Description                                                                                                     |
| :--------- | :------------------------ | :-------------------------------------------------------------------------------------------------------------- |
| **v0.4.0** | Table Column Alignment    | Enabled column alignment parsing (`:---`, `:---:`, `---:`) mapping to ReportLab table cell styles.              |
|            | Superscript & Subscript   | Support for inline `x^2^` and `H~2~O` syntax using native ReportLab `<sup>` and `<sub>` tags.                   |
|            | Strikethrough & Highlight | Support for `~~strikethrough~~` (`<strike>`) and `==highlight==` (`<span backcolor="...">`) with custom colors. |
|            | Offline Math Rendering    | Optional fast LaTeX equation math rendering via `matplotlib.mathtext`.                                          |
|            | LaTeX Pre-processing      | Added block math pre-processing (`$$...$$`) to prevent fragmentation during parsing.                            |
|            | Concurrent Pre-fetching   | Parallel scanning and pre-fetching of Kroki/LaTeX assets in a thread pool.                                      |
|            | Progress Reporting        | Stage-level compilation progress outputs on stderr with `--no-progress` flag.                                   |
| **v0.3.0** | Color Emoji Support       | Pre-processing of emoji codepoints using Twemoji CDN images and local disk caching.                             |
|            | Page Breaks               | Support for `<!-- pagebreak -->` comments and `\pagebreak` directives.                                          |
|            | Admonitions / Callouts    | Support for fenced admonitions (`:::note`) and GitHub-style blockquotes (`> [!NOTE]`).                          |
|            | Keep Heading with Table   | Visual layout safeguard to keep tables attached to their preceding section header.                              |
| **v0.2.0** | Table of Contents (TOC)   | Dynamic Table of Contents generation prepended to the PDF using bookmark flowables.                             |
|            | YAML Front-Matter         | Extraction of PDF metadata properties (`title`, `author`, etc.) from YAML blocks.                               |
|            | Footnotes Support         | Clickable footnotes with height calculation safeguards to prevent rendering overlaps.                           |
|            | Page Headers / Footers    | Running headers/footers with dynamic section/page placeholders.                                                 |
| **v0.1.4** | Bookmarks & Outlines      | PDF outline entry registration to show headings in PDF viewer navigation panels.                                |
| **v0.1.3** | Unicode Fonts             | Bundled DejaVu Sans TrueType fonts for out-of-the-box multi-language support.                                   |
| **v0.1.2** | Math & Diagrams           | Kroki.io integration for LaTeX TikZ and Mermaid diagrams.                                                       |
|            | File Inclusion            | Recursive markdown file imports with relative path resolution and loop detection.                               |
| **v0.1.1** | Image Auto-scaling        | Handling of inline and block images with dimensions, aspect-ratio scaling, and missing placeholders.            |
| **v0.1.0** | Initial Release           | Core linear typesetting pipeline using ReportLab and mistletoe.                                                 |
