"""ListHandler — renders ordered and unordered Markdown lists.

Supports:
- Unordered lists (bullet)
- Ordered lists (numbered)
- Arbitrarily nested lists via recursion
"""

from __future__ import annotations

from reportlab.platypus import ListFlowable, ListItem, Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render

# Indentation added per nesting level (points)
_INDENT_PER_LEVEL: int = 18


class ListHandler(ElementHandler):
    """Render ``List`` tokens as ``ListFlowable`` flowables.

    Nested lists are rendered recursively: child ``List`` tokens found
    inside a ``ListItem`` produce an inner ``ListFlowable`` that is
    appended after the item's paragraph content.
    """

    token_type = "List"

    def render(self, token: dict, styles: dict, _depth: int = 0) -> list:
        """Render a list token and return a list containing one ``ListFlowable``.

        Args:
            token:  Normalised list token dict.
            styles: Stylesheet dict from the pipeline.
            _depth: Current nesting depth (0 = top-level).  Used internally
                    for recursive rendering to increase indentation.
        """
        is_ordered: bool = token.get("attrs", {}).get("start") is not None
        bullet_type = "1" if is_ordered else "bullet"

        items: list[ListItem] = []
        for child in token.get("children", []):
            item = self._render_item(child, styles, is_ordered, _depth)
            items.append(item)

        return [
            ListFlowable(
                items,
                bulletType=bullet_type,
                leftIndent=_INDENT_PER_LEVEL * (_depth + 1),
                bulletFontSize=styles.get("list_item", styles.get("body")).fontSize,
                spaceBefore=0,
                spaceAfter=styles.get("spacing_base", 8) if _depth == 0 else 0,
            )
        ]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _render_item(
        self,
        item_token: dict,
        styles: dict,
        ordered: bool,
        depth: int,
    ) -> ListItem:
        """Convert a ``ListItem`` token to a ``ListItem`` flowable.

        A list item may contain:
        - Inline text children  → rendered as a ``Paragraph``
        - Nested ``List`` tokens → rendered recursively and appended after
          the paragraph
        """
        contents: list = []
        inline_children: list[dict] = []

        for child in item_token.get("children", []):
            child_type = child.get("type", "")

            if child_type == "List":
                # Flush buffered inline children as a Paragraph first
                if inline_children:
                    text = inline_render(inline_children, styles)
                    contents.append(Paragraph(text, styles["list_item"]))
                    inline_children = []
                # Recurse into the nested list
                contents.extend(self.render(child, styles, _depth=depth + 1))

            elif child_type == "Paragraph":
                # Loose list items wrap their content in a Paragraph token
                text = inline_render(child.get("children", []), styles)
                contents.append(Paragraph(text, styles["list_item"]))

            else:
                # Tight list items expose inline tokens directly
                inline_children.append(child)

        # Flush any remaining inline content
        if inline_children:
            text = inline_render(inline_children, styles)
            contents.append(Paragraph(text, styles["list_item"]))

        # ListItem requires at least one flowable
        if not contents:
            contents.append(Paragraph("", styles["list_item"]))

        return ListItem(contents, bulletType="1" if ordered else "bullet")
