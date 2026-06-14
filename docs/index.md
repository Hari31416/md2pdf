# md2pdf Documentation Index

Welcome to the `md2pdf` documentation! `md2pdf` is an automated programmatic Markdown-to-PDF typesetting engine written in pure Python. It compiles standard Markdown and advanced elements directly to print-ready PDFs without headless browser dependencies.

Use the guides below to learn about installing, configuring, styling, and extending the engine:

---

## 📖 Available Guides

### 1. [User Guide & Feature Reference](./user-guide.md)
Learn about all supported Markdown structures, features, and configuration parameters including:
* **YAML Front Matter**: Metadata extraction to PDF properties.
* **Cover Page**: Auto-generating and prepending cover/title pages using YAML metadata.
* **Table of Contents (TOC)**: Auto-generating clickable tables of contents.
* **Running Headers & Section Titles**: Document headers, templates, and page number footers.
* **Colour Emoji (Twemoji)**: Automatically substituting emoji characters with high-res colour Twemoji images.
* **Task Lists**: GFM-style checklists (`- [ ]` / `- [x]`) rendered using Twemoji images or Unicode symbols.
* **Footnotes**: Reference link maps and automatic page layout positioning.
* **Inline Formatting**: Support for `~~strikethrough~~`, `==highlight==`, superscript `x^2^`, and subscript `H~2~O` spans.
* **Tables**: Automatic column alignment parsing (`:---`, `:---:`, `---:`) and layout styling.
* **Admonitions & GitHub Alerts**: Fenced admonition blocks and inline markdown alerts with distinct color themes.
* **Page Breaks**: Manual pagination using comment directives and backslash syntax.
* **Mermaid & LaTeX**: Diagram and math rendering via the Kroki API, with concurrent pre-fetching, local caching, offline fallbacks, and optional fast local rendering via Matplotlib.

### 2. [Styling & Themes](./themes.md)
Understand how to customize fonts, colors, and layout metrics using `ThemeConfig` blocks inside your configuration files, and how to write stylesheet override plugins.

### 3. [Plugin Authoring Guide](./plugin-authoring.md)
Explore the extension API of `md2pdf` to hook into the conversion lifecycle:
* **Stage 1 (Preprocessors)**: Intercepting and transforming raw Markdown text.
* **Stage 3 (Element Handlers)**: Mapping Markdown AST tokens to custom ReportLab flowables.
* **Stage 4 (Postprocessors)**: Mutating and rearranging flowables lists before the final PDF compilation.
* **Stylesheet Overrides**: Merging custom theme overrides into the styling pipeline.

### 4. [Visual Feature Showcase](./showcase.md)
View the primary rendering test document that demonstrates all supported elements, vertical spacing rules, and layout features. Compiling this document (`md2pdf docs/showcase.md -o docs/showcase.pdf`) serves as an end-to-end regression test for changes to the layout engine.
