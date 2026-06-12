# Phase 3: Built-in Element Handlers

**Goal:** Implement all built-in `ElementHandler` subclasses that cover standard Markdown elements. These are the handlers the engine ships with — users and plugins can override any of them.

**Depends on:** Phase 1 (registry), Phase 2 (token types)

---

## Deliverables

- `md2pdf/handlers/heading.py` — `HeadingHandler`
- `md2pdf/handlers/paragraph.py` — `ParagraphHandler`
- `md2pdf/handlers/list_.py` — `ListHandler` (ordered + unordered, nested)
- `md2pdf/handlers/blockquote.py` — `BlockQuoteHandler`
- `md2pdf/handlers/table.py` — `TableHandler` (multi-page, repeating header)
- `md2pdf/handlers/thematic_break.py` — `ThematicBreakHandler`
- `md2pdf/handlers/inline.py` — inline span renderer (shared utility, not a handler)
- `md2pdf/styles/theme.py` — `ThemeConfig` dataclass (user-editable color/font palette)
- `md2pdf/styles/default.py` — `build_default_stylesheet(theme)` (all paragraph/table styles)
- Updated `Pipeline._map()` — dispatches tokens to registry, collects flowables
- `tests/test_handlers.py`
- `tests/test_theme.py`

---

## ThemeConfig (`md2pdf/styles/theme.py`)

`ThemeConfig` is a plain dataclass whose fields map 1:1 to entries in `md2pdf.toml`. It is the **single source of truth for all colors, fonts, and spacing** — no hex literals anywhere else in the codebase.

```python
from dataclasses import dataclass, field

@dataclass
class ThemeConfig:
    # --- Typography ---
    font_body: str = "Helvetica"
    font_heading: str = "Helvetica-Bold"
    font_mono: str = "Courier"
    font_size_body: int = 10
    font_size_small: int = 9

    # --- Body colors ---
    color_body_text: str = "#000000"
    color_blockquote_text: str = "#555555"
    color_link: str = "#0366d6"
    color_hr: str = "#cccccc"

    # --- Table colors ---
    color_table_header_bg: str = "#2c3e50"
    color_table_header_text: str = "#ffffff"
    color_table_grid: str = "#cccccc"
    color_table_row_odd: str = "#ffffff"
    color_table_row_even: str = "#f5f5f5"

    # --- Blockquote bar ---
    color_blockquote_bar: str = "#cccccc"

    @classmethod
    def from_dict(cls, data: dict) -> "ThemeConfig":
        """Build from a [theme] TOML table; unknown keys are ignored."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def hex(self, attr: str):
        """Return a reportlab HexColor for the named attribute."""
        from reportlab.lib import colors
        return colors.HexColor(getattr(self, attr))
```

### User-facing TOML section (`md2pdf.toml`)

All fields have defaults, so the `[theme]` section is entirely optional. Users only need to set what they want to change:

```toml
[theme]
# Typography
font_body    = "Helvetica"
font_heading = "Helvetica-Bold"
font_mono    = "Courier"

# Body
color_body_text       = "#000000"
color_blockquote_text = "#555555"
color_link            = "#0366d6"
color_hr              = "#cccccc"

# Table
color_table_header_bg   = "#2c3e50"
color_table_header_text = "#ffffff"
color_table_grid        = "#cccccc"
color_table_row_odd     = "#ffffff"
color_table_row_even    = "#f5f5f5"

# Blockquote left bar
color_blockquote_bar = "#cccccc"
```

> **Note:** `ThemeConfig` is loaded inside `Config.from_toml()` (Phase 1) by passing the `[theme]` sub-table to `ThemeConfig.from_dict()`. The constructed `ThemeConfig` is stored on `Config.theme_config` and passed into `build_default_stylesheet()`.

---

## StyleSheet (`md2pdf/styles/default.py`)

`build_default_stylesheet()` now accepts a `ThemeConfig` and reads all colors and fonts from it. No hex literals remain in this file.

```python
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from md2pdf.styles.theme import ThemeConfig

def build_default_stylesheet(theme: ThemeConfig | None = None) -> dict:
    if theme is None:
        theme = ThemeConfig()   # all defaults
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"],
                             fontName=theme.font_heading, fontSize=20, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=base["Heading2"],
                             fontName=theme.font_heading, fontSize=16, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"],
                             fontName=theme.font_heading, fontSize=13, spaceAfter=3),
        "h4": ParagraphStyle("h4", parent=base["Heading4"],
                             fontName=theme.font_heading, fontSize=11, spaceAfter=2),
        "body": ParagraphStyle("body", parent=base["Normal"],
                               fontName=theme.font_body,
                               fontSize=theme.font_size_body, leading=14),
        "blockquote": ParagraphStyle(
            "blockquote", parent=base["Normal"],
            fontName=theme.font_body,
            leftIndent=12, textColor=theme.hex("color_blockquote_text"),
            borderPad=4, fontSize=theme.font_size_body, leading=14,
        ),
        "list_item": ParagraphStyle("list_item", parent=base["Normal"],
                                    fontName=theme.font_body,
                                    fontSize=theme.font_size_body, leading=13),
        "code_inline": ParagraphStyle(
            "code_inline", parent=base["Code"],
            fontName=theme.font_mono, fontSize=theme.font_size_small,
        ),
        "table_header": ParagraphStyle(
            "table_header", parent=base["Normal"],
            fontName=theme.font_heading, fontSize=theme.font_size_small,
            textColor=theme.hex("color_table_header_text"),
        ),
        "table_cell": ParagraphStyle("table_cell", parent=base["Normal"],
                                     fontName=theme.font_body,
                                     fontSize=theme.font_size_small, leading=12),
        # --- Raw TableStyle command list (used by TableHandler) ---
        "table_style": [
            ("BACKGROUND",    (0, 0), (-1, 0),  theme.hex("color_table_header_bg")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  theme.hex("color_table_header_text")),
            ("GRID",          (0, 0), (-1, -1), 0.5, theme.hex("color_table_grid")),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [theme.hex("color_table_row_odd"), theme.hex("color_table_row_even")]),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ],
        # --- Scalar values consumed by non-Paragraph handlers ---
        "color_hr":             theme.hex("color_hr"),
        "color_link":           theme.color_link,          # raw string for XML attr
        "color_blockquote_bar": theme.hex("color_blockquote_bar"),
    }
```

**Key design points:**
- `ThemeConfig` defaults match the originals, so removing the `[theme]` section produces an identical PDF.
- `theme.hex(attr)` is a small helper that converts the stored hex string to a ReportLab `HexColor` on demand — avoids repeated `colors.HexColor(...)` calls at the call site.
- `color_link` is stored as a plain string because it's used in ReportLab XML `<a href="..." color="{color_link}">` markup, not as a `HexColor` object.

---

## Handler Implementations

### `HeadingHandler`

```python
class HeadingHandler(ElementHandler):
    token_type = "Heading"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        level = token["attrs"].get("level", 1)
        style_key = f"h{min(level, 4)}"
        text = inline_render(token["children"])   # shared inline renderer
        return [Paragraph(text, styles[style_key])]
```

### `ParagraphHandler`

```python
class ParagraphHandler(ElementHandler):
    token_type = "Paragraph"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        text = inline_render(token["children"])
        return [Paragraph(text, styles["body"])]
```

### `ListHandler`

- Recursively renders nested lists using `ListFlowable` / `ListItem`
- Supports ordered (`ol`) and unordered (`ul`) by checking `token["attrs"]["start"]`
- Nested lists: recursively call `ListHandler.render()` on child `List` tokens

```python
class ListHandler(ElementHandler):
    token_type = "List"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        is_ordered = token["attrs"].get("start") is not None
        items = []
        for child in token["children"]:
            items.append(self._render_item(child, styles, is_ordered))
        return [ListFlowable(items, bulletType="1" if is_ordered else "bullet")]

    def _render_item(self, item_token: dict, styles: dict, ordered: bool) -> ListItem:
        # Render paragraph children, recurse into nested lists
        ...
```

### `BlockQuoteHandler`

```python
class BlockQuoteHandler(ElementHandler):
    token_type = "BlockQuote"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        # Wrap children in blockquote style; add left bar via a custom Flowable or leftIndent
        ...
```

### `TableHandler`

Key concerns:
- `repeatRows=1` on `Table(...)` ensures header row repeats across page breaks
- Cell content is `Paragraph(text, styles["table_cell"])` — allows text wrapping
- Column widths: auto-computed from page width minus margins, evenly distributed unless overridden

```python
class TableHandler(ElementHandler):
    token_type = "Table"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        node = token["_node"]
        header_row = [
            Paragraph(cell_text, styles["table_header"])
            for cell_text in self._extract_header(node)
        ]
        data_rows = [
            [Paragraph(c, styles["table_cell"]) for c in row]
            for row in self._extract_rows(node)
        ]
        all_rows = [header_row] + data_rows
        col_widths = self._compute_col_widths(len(header_row))
        tbl = Table(all_rows, colWidths=col_widths, repeatRows=1,
                    splitByRow=True)
        tbl.setStyle(TableStyle(styles["table_style"]))
        return [tbl]
```

### `ThematicBreakHandler`

```python
class ThematicBreakHandler(ElementHandler):
    token_type = "ThematicBreak"

    def render(self, token: dict, styles: dict) -> list[Flowable]:
        from reportlab.platypus import HRFlowable
        # color_hr comes from styles dict (ultimately from ThemeConfig)
        return [HRFlowable(width="100%", thickness=0.5,
                           color=styles.get("color_hr", colors.grey), spaceAfter=6)]
```

---

## Shared Inline Renderer (`inline.py`)

Inline elements (bold, italic, code, links) are rendered to ReportLab XML markup strings used inside `Paragraph(text, style)`.

```python
def inline_render(children: list[dict]) -> str:
    """Convert inline token children to ReportLab XML markup string."""
    parts = []
    for child in children:
        t = child["type"]
        raw = child.get("raw", "")
        if t == "RawText":
            parts.append(escape_xml(raw))
        elif t == "Strong":
            parts.append(f"<b>{inline_render(child['children'])}</b>")
        elif t == "Emphasis":
            parts.append(f"<i>{inline_render(child['children'])}</i>")
        elif t == "InlineCode":
            parts.append(f"<font name='Courier'>{escape_xml(raw)}</font>")
        elif t == "Link":
            href = child["attrs"].get("target", "")
            label = inline_render(child["children"])
            # color_link comes from styles dict (ultimately from ThemeConfig)
            link_color = styles.get("color_link", "#0366d6") if styles else "#0366d6"
            parts.append(f'<a href="{href}" color="{link_color}">{label}</a>')
        else:
            parts.append(escape_xml(raw))
    return "".join(parts)
```

---

## Updated `Pipeline._map()`

```python
def _map(self, tokens: list[dict]) -> list[Flowable]:
    flowables = []
    for token in tokens:
        handler = self.registry.get(token["type"])
        if handler:
            flowables.extend(handler.render(token, self._styles))
        else:
            logging.warning("No handler for token type: %s", token["type"])
    return flowables
```

---

## Handler Registration in `pyproject.toml`

```toml
[project.entry-points."md2pdf.handlers"]
Heading       = "md2pdf.handlers.heading:HeadingHandler"
Paragraph     = "md2pdf.handlers.paragraph:ParagraphHandler"
List          = "md2pdf.handlers.list_:ListHandler"
BlockQuote    = "md2pdf.handlers.blockquote:BlockQuoteHandler"
Table         = "md2pdf.handlers.table:TableHandler"
ThematicBreak = "md2pdf.handlers.thematic_break:ThematicBreakHandler"
```

---

## Acceptance Criteria

- [ ] All handler unit tests produce valid `Flowable` instances (no exceptions)
- [ ] `TableHandler` produces a `Table` with `repeatRows=1`
- [ ] `ListHandler` correctly renders a 2-level nested list
- [ ] `inline_render` correctly escapes XML special chars and renders bold/italic/link markup
- [ ] A sample markdown with all element types renders to a non-empty PDF without errors
- [ ] `ThemeConfig()` (no args) produces identical output to the previously hard-coded defaults
- [ ] Setting `color_table_header_bg = "#c0392b"` in `md2pdf.toml` produces a red table header (visual check)
- [ ] `ThemeConfig.from_dict({"color_link": "#e74c3c", "unknown_key": "x"})` ignores the unknown key without error
- [ ] No `colors.HexColor("#...")` literals remain in `default.py` or any handler file
