# md2pdf

**Automated Programmatic Markdown-to-PDF Typesetting Engine**

`md2pdf` converts structured Markdown documents into beautiful, print-ready PDFs. Unlike other conversion tools, it does not rely on heavy dependencies like Pandoc, Node.js, or headless Chrome/Chromium browsers. It is written in pure Python and powered by ReportLab and mistletoe.

---

## Features

- **Standard Elements**: headings (H1–H6), paragraphs, lists, blockquotes, horizontal rules, and hyperlinks.
- **Multi-page Tables**: tables split cleanly across page boundaries. Headers repeat at the top of every page.
- **Diagrams & Math Blocks**: renders Mermaid diagrams and LaTeX math blocks via the Kroki API (with offline fallbacks and SHA-256 disk caching).
- **Extensible Plugin System**: load custom element handlers, text-level preprocessors, post-processors, and stylesheet/theme layers.
- **Typesetting Safeguards**: implements strict "anti-fail" layout rules including orphaned heading protection, ghost page elimination, and widow/orphan line settings.
- **DX-First Validation**: pre-render validation runs to identify nested tables, empty diagrams, or unsupported elements before rendering.

---

## Installation

Using `uv` (recommended):
```bash
uv tool install md2pdf
```

Or via standard `pip`:
```bash
pip install md2pdf
```

---

## Command Line Usage

Convert a Markdown file:
```bash
md2pdf input.md -o output.pdf
```

### Options

| Flag | Shortcut | Description |
| ---- | -------- | ----------- |
| `--output` | `-o` | Path to save the output PDF file (default: `output.pdf`). |
| `--config` | `-c` | Path to a custom `md2pdf.toml` config file. |
| `--theme` | `-t` | Name of the theme to apply (default: `default`). |
| `--offline` | | Skip external API requests (e.g. Kroki diagram rendering) and use local placeholders. |
| `--validate-only`| | Execute pre-render validation checks and exit without building a PDF. |
| `--verbose` | `-v` | Output debug-level logging to `stderr`. |
| `--help` | | Show help message. |

---

## Pre-Render Validation

You can validate a Markdown document without compiling a PDF:
```bash
md2pdf input.md --validate-only
```

The validator checks for issues like:
- `UNSUPPORTED_ELEMENT`: Element types that have no registered handlers.
- `EMPTY_TABLE`: Tables with no rows.
- `NESTED_TABLE`: Tables embedded inside other tables (which ReportLab does not support).
- `EMPTY_DIAGRAM`: Diagram syntax blocks without any source body.

If validation errors are found, the command exits with exit code `1`.

---

## Configuration (`md2pdf.toml`)

Configuration is declared in `md2pdf.toml` at the root of your project:

```toml
[md2pdf]
theme = "default"
offline = false
cache_dir = ".md2pdf_cache"

[theme]
font_body = "Helvetica"
font_heading = "Helvetica-Bold"
font_mono = "Courier"
font_size_body = 10
font_size_small = 8
color_body_text = "#333333"
color_blockquote_bar = "#cccccc"

[plugins]
handlers = [
    "my_plugin.handlers:CustomImageHandler"
]
```

---

## Developer Documentation

- [Plugin Authoring Guide](docs/plugin-authoring.md)
- [Themes and Styles System](docs/themes.md)
