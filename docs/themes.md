# Themes & Styling System in md2pdf

`md2pdf` uses a centralized theme system to control colors, fonts, and spacing across all document elements. The stylesheet registry compiles layers of styles into a single unified stylesheet dictionary before rendering.

---

## Built-In Themes

`md2pdf` bundles several pre-built themes selectable via the CLI `--theme` / `-t` flag or the `theme` configuration setting in `md2pdf.toml`:

* **`default`**: The standard layout using DejaVu fonts, a corporate dark-blue table header, gray grid, and default spacing metrics.
* **`academic`**: A formal serif layout using `Times-Roman` and `Times-Bold` fonts, `Courier` for code, slightly larger font sizes/spacing, and formal dark table styling.
* **`minimal`**: A clean, modern sans-serif layout using `Helvetica` and `Helvetica-Bold` fonts, generous line margins, thick black blockquote accent bar, black hyperlinks, and plain white table styling.
* **`dark`**: A dark mode layout painting a dark charcoal background (`#1e1e1e`) across all pages, light-gray body text, soft-blue hyperlinks, dark table structures, and pygments syntax highlighting styled via `monokai`.

---

## The `ThemeConfig` Dataclass

The styling system is parameterized by `ThemeConfig`, which is the single source of truth for colors and fonts. Sensible defaults are provided so the theme section is completely optional.

Here is the default schema with its default settings:

```toml
[theme]
# --- Typography ---
font_body             = "Helvetica"
font_heading          = "Helvetica-Bold"
font_mono             = "Courier"
font_size_body        = 10
font_size_small       = 9
spacing_base          = 8

# --- Prose Colors ---
color_body_text       = "#000000"
color_blockquote_text = "#555555"
color_link            = "#0366d6"
color_hr              = "#cccccc"

# --- Table Colors ---
color_table_header_bg = "#2c3e50"
color_table_header_text= "#ffffff"
color_table_grid      = "#cccccc"
color_table_row_odd   = "#ffffff"
color_table_row_even  = "#f5f5f5"

# --- Blockquote Accent Bar ---
color_blockquote_bar  = "#cccccc"

# --- Code Highlighting ---
color_code_bg         = "#f5f5f5"
syntax_style          = "default"

# --- Page Background ---
color_page_bg         = "#ffffff"
```

---

## Base Stylesheet Keys

The default base stylesheet built from `ThemeConfig` contains the following keys, which map to ReportLab `ParagraphStyle` objects or raw scalar values:

| Key                    | Type             | Description                                                |
| ---------------------- | ---------------- | ---------------------------------------------------------- |
| `h1`                   | `ParagraphStyle` | Large document heading style (H1).                         |
| `h2`                   | `ParagraphStyle` | Section heading style (H2).                                |
| `h3`                   | `ParagraphStyle` | Subsection heading style (H3).                             |
| `h4`                   | `ParagraphStyle` | Minor heading style (H4).                                  |
| `body`                 | `ParagraphStyle` | Normal body paragraphs.                                    |
| `blockquote`           | `ParagraphStyle` | Indented text for blockquotes.                             |
| `list_item`            | `ParagraphStyle` | Text within lists.                                         |
| `code_inline`          | `ParagraphStyle` | Monospace inline code fragments.                           |
| `table_header`         | `ParagraphStyle` | Bold column headers inside tables.                         |
| `table_cell`           | `ParagraphStyle` | Normal text inside table cells.                            |
| `table_style`          | `list`           | ReportLab table styles (backgrounds, padding, grid lines). |
| `color_hr`             | `HexColor`       | Color for `<hr>` thematic breaks.                          |
| `color_link`           | `str`            | Color for hyperlinks (used in XML markup tag rendering).   |
| `color_blockquote_bar` | `HexColor`       | Left vertical rule color for blockquotes.                  |
| `code_block`           | `ParagraphStyle` | Multi-line syntax-highlighted code block style.            |
| `footnote`             | `ParagraphStyle` | Text style for footnote definitions.                       |
| `color_code_bg`        | `HexColor`       | Background color for code blocks.                          |
| `syntax_style`         | `str`            | Name of Pygments syntax highlighting theme.                |
| `spacing_base`         | `int`            | Base spacing metric in points.                             |
| `color_page_bg`        | `HexColor`       | Background color for document pages.                       |

All paragraph styles include:
- `allowWidows = 0`
- `allowOrphans = 0`

These ensure that single lines of paragraphs are never orphaned at the top or bottom of page boundaries.

---

## Styling Override Plugins

You can register styling layers by implementing a class with a `get_stylesheet()` method and registering it under the `md2pdf.stylesheets` entry-point group.

A style layer returns a partial dictionary. Later layers are merged with earlier layers, overriding keys:

```python
class ElegantLawTheme:
    def get_stylesheet(self) -> dict:
        return {
            "font_body": "Times-Roman",
            "font_heading": "Times-Bold",
            "color_body_text": "#1a1a1a",
            "color_link": "#000080",
        }
```

Register this layer in your plugin package's `pyproject.toml`:

```toml
[project.entry-points."md2pdf.stylesheets"]
law_theme = "my_plugin.themes:ElegantLawTheme"
```
