# Changelog

All notable changes to the `md2pdf` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

