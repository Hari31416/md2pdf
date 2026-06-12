# Phase 6: Layout Safeguards & Anti-Fail Logic

**Goal:** Implement the "anti-fail" layout rules that prevent the known failure modes: ghost pages, orphaned lines, mid-row table splits, and header-image separation.

**Depends on:** Phase 3 (handlers), Phase 4 (asset handlers)

---

## Deliverables

- `md2pdf/core/layout.py` — `LayoutComposer` that post-processes the flat flowable list and applies grouping rules
- Updated `HeadingHandler` — emits a `BookmarkFlowable` for TOC anchors
- Updated `MermaidHandler` / `LatexHandler` — wraps output in `KeepTogether` with preceding heading
- Updated `TableHandler` — enforces `splitByRow=True` + `repeatRows`
- `md2pdf/core/flowables.py` — custom flowables (left-bar for blockquote, page-number footer)
- `tests/test_layout.py`

---

## Problem → Solution Map

| Known Failure                  | Root Cause                                                  | Solution                                                              |
| ------------------------------ | ----------------------------------------------------------- | --------------------------------------------------------------------- |
| Ghost empty page after diagram | ReportLab inserts page break before large image, leaves gap | `KeepTogether([heading, image])` — moves whole block to next page     |
| Table row split mid-cell       | Default `splitByRow` behaviour                              | `Table(..., splitByRow=True)` with min-row-height enforcement         |
| Table header doesn't repeat    | Missing `repeatRows`                                        | `Table(..., repeatRows=1)`                                            |
| Orphan paragraph line          | No widow/orphan setting                                     | `ParagraphStyle(..., allowWidows=0, allowOrphans=0)`                  |
| List item stranded alone       | Same                                                        | `ListFlowable(..., bulletFontSize=10)` + `KeepWithNext` on short list |
| Section heading at page bottom | No keep-with-next                                           | `Paragraph(text, style)` + `KeepTogether([heading, first_para])`      |

---

## `LayoutComposer` (`layout.py`)

The `LayoutComposer` receives the **flat flowable list** from `Pipeline._map()` and applies grouping passes before handing off to ReportLab's `doc.build()`.

```python
from reportlab.platypus import KeepTogether, Flowable

class LayoutComposer:
    def compose(self, flowables: list[Flowable]) -> list[Flowable]:
        """Apply all layout safeguard passes in order."""
        flowables = self._bond_headings_to_next(flowables)
        flowables = self._bond_headings_to_images(flowables)
        return flowables

    def _bond_headings_to_next(self, flowables: list[Flowable]) -> list[Flowable]:
        """
        Wrap each heading with the immediately following flowable in a
        KeepTogether so headings never appear alone at the bottom of a page.
        """
        result: list[Flowable] = []
        i = 0
        while i < len(flowables):
            current = flowables[i]
            if self._is_heading(current) and i + 1 < len(flowables):
                nxt = flowables[i + 1]
                # Don't bond heading to another heading or an image block
                if not self._is_heading(nxt) and not self._is_image_block(nxt):
                    result.append(KeepTogether([current, nxt]))
                    i += 2
                    continue
            result.append(current)
            i += 1
        return result

    def _bond_headings_to_images(self, flowables: list[Flowable]) -> list[Flowable]:
        """
        When a heading is immediately followed by an image (Mermaid/LaTeX PNG),
        wrap both in KeepTogether to prevent ghost page gaps.
        """
        result: list[Flowable] = []
        i = 0
        while i < len(flowables):
            current = flowables[i]
            if self._is_heading(current) and i + 1 < len(flowables):
                nxt = flowables[i + 1]
                if self._is_image_block(nxt):
                    result.append(KeepTogether([current, nxt]))
                    i += 2
                    continue
            result.append(current)
            i += 1
        return result

    def _is_heading(self, f: Flowable) -> bool:
        from reportlab.platypus import Paragraph
        if not isinstance(f, Paragraph):
            return False
        style_name = getattr(f.style, "name", "")
        return style_name.startswith("h")

    def _is_image_block(self, f: Flowable) -> bool:
        from reportlab.platypus import Image
        return isinstance(f, Image)
```

---

## Widow/Orphan Enforcement

All paragraph styles in `DefaultStyleSheet` must include:

```python
ParagraphStyle(
    "body",
    ...,
    allowWidows=0,    # no single line left at top of page
    allowOrphans=0,   # no single line left at bottom of page
)
```

For list items, the list flowable should set `leftIndent` and the containing `ListFlowable` should use `spaceAfter` between items to prevent tight packing.

---

## Custom Flowables (`flowables.py`)

### `BlockQuoteBar`

A custom `Flowable` that draws a left vertical bar beside blockquote text (matching the visual convention of GitHub-flavored markdown blockquotes).

```python
from reportlab.platypus import Flowable
from reportlab.lib import colors

class BlockQuoteBar(Flowable):
    def __init__(self, inner_flowable, bar_color=colors.HexColor("#cccccc"),
                 bar_width=3, padding=8) -> None:
        super().__init__()
        self.inner = inner_flowable
        self.bar_color = bar_color
        self.bar_width = bar_width
        self.padding = padding
        self.width = inner_flowable.width + bar_width + padding
        self.height = inner_flowable.height

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(self.bar_color)
        c.rect(0, 0, self.bar_width, self.height, fill=1, stroke=0)
        self.inner.canv = c
        self.inner.drawOn(c, self.bar_width + self.padding, 0)
```

### `PageNumberCanvas`

Used as the `onPage` callback for `SimpleDocTemplate.build()` to draw footer with page numbers.

```python
def draw_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    page_text = f"Page {doc.page}"
    canvas.drawRightString(doc.pagesize[0] - 20, 15, page_text)
    canvas.restoreState()
```

Built-in `PageNumberPostProcessor` attaches this as the `onLaterPages` callback.

---

## PDF Document Build (`Pipeline._render()`)

```python
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

def _render(self, flowables: list) -> None:
    composer = LayoutComposer()
    safe_flowables = composer.compose(flowables)

    # Run post-processors (Phase 5)
    for pp in self._post_processors:
        safe_flowables = pp.process(self._doc, safe_flowables)

    self._doc.build(
        safe_flowables,
        onFirstPage=draw_page_number,
        onLaterPages=draw_page_number,
    )

def _build_doc(self) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        self.config.output_file,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=22*mm,
        bottomMargin=22*mm,
    )
```

---

## Acceptance Criteria

- [ ] A document with a heading immediately before a large Mermaid chart renders without an empty page between them
- [ ] `LayoutComposer._bond_headings_to_next()` correctly wraps heading+paragraph pairs
- [ ] A heading at the very end of a page is pushed to the next page together with the first line of following content
- [ ] A table with 50 rows splits cleanly between rows — no row is split across a page boundary
- [ ] Table header row appears at the top of every page the table spans
- [ ] Blockquote renders with a visible left bar
- [ ] Page numbers appear in footer on all pages
- [ ] All paragraph styles have `allowWidows=0, allowOrphans=0`
