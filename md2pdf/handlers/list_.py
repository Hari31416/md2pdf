"""ListHandler — renders ordered and unordered Markdown lists.

Supports:
- Unordered lists (bullet)
- Ordered lists (numbered)
- Arbitrarily nested lists via recursion
"""

from __future__ import annotations

import copy
import re

from reportlab.platypus import ListFlowable, ListItem, Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render

# Indentation added per nesting level (points)
_INDENT_PER_LEVEL: int = 18


def _copy_token(token: dict) -> dict:
    """Deep copy a token dict, excluding raw AST '_node' objects to avoid deepcopy issues."""
    copied = {
        "type": token.get("type", ""),
        "raw": token.get("raw", ""),
        "attrs": copy.deepcopy(token.get("attrs", {})),
    }
    if "children" in token:
        copied["children"] = [_copy_token(c) for c in token["children"]]
    return copied


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
        start_val = token.get("attrs", {}).get("start")
        is_ordered: bool = start_val is not None
        bullet_type = "1" if is_ordered else "bullet"

        kwargs = {}
        if is_ordered:
            try:
                kwargs["start"] = int(start_val)
            except (ValueError, TypeError):
                kwargs["start"] = 1

        items: list[ListItem] = []
        for child in token.get("children", []):
            item = self._render_item(child, styles, is_ordered, _depth)
            items.append(item)

        return [
            ListFlowable(
                items,
                bulletType=bullet_type,
                leftIndent=_INDENT_PER_LEVEL,
                bulletFontSize=styles.get("list_item", styles.get("body")).fontSize,
                spaceBefore=0,
                spaceAfter=styles.get("spacing_base", 8) if _depth == 0 else 0,
                **kwargs,
            )
        ]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _process_checkbox(self, item_token: dict, styles: dict) -> None:
        """Detect and rewrite GFM-style task list checkboxes [ ] and [x]."""
        children = item_token.get("children", [])
        if not children:
            return

        first_child = children[0]
        if first_child.get("type") == "List":
            return

        if first_child.get("type") == "Paragraph":
            inline_children = first_child.get("children", [])
        else:
            inline_children = children

        if not inline_children:
            return

        first_inline = inline_children[0]
        if first_inline.get("type") != "RawText":
            return

        raw_text = first_inline.get("raw", "")

        # Match [ ] or [x] or [X] at the beginning
        match = re.match(r"^\[([ xX])\](?:[ \t](.*)|$)", raw_text)
        if not match:
            return

        checked_char = match.group(1)
        remaining_text = match.group(2) or ""

        is_checked = checked_char in ("x", "X")
        config = styles.get("_config")
        emoji_enabled = getattr(config, "emoji", True) if config else True
        cache_dir = getattr(config, "cache_dir", "") if config else ""

        replacement = None
        if emoji_enabled:
            from pathlib import Path

            slug = "2611" if is_checked else "25fb"
            emoji_cache_dir = (
                Path(cache_dir) / "emoji" if cache_dir else Path.home() / ".cache/pymd2pdf/emoji"
            )

            png_path = emoji_cache_dir / f"{slug}.png"
            if png_path.exists():
                replacement = f'<img src="{png_path}" width="14" height="14"/>'

        if not replacement:
            replacement = "☑" if is_checked else "☐"

        # Update the raw text inline token
        first_inline["raw"] = f"{replacement} {remaining_text}" if remaining_text else replacement

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
        item_token = _copy_token(item_token)
        self._process_checkbox(item_token, styles)

        contents: list = []
        inline_children: list[dict] = []

        for child in item_token.get("children", []):
            child_type = child.get("type", "")

            if child_type == "List":
                # Flush buffered inline children as a Paragraph first
                if inline_children:
                    text = inline_render(inline_children, styles, parent_style="list_item")
                    contents.append(Paragraph(text, styles["list_item"]))
                    inline_children = []
                # Recurse into the nested list
                contents.extend(self.render(child, styles, _depth=depth + 1))

            elif child_type == "Paragraph":
                # Loose list items wrap their content in a Paragraph token
                text = inline_render(child.get("children", []), styles, parent_style="list_item")
                contents.append(Paragraph(text, styles["list_item"]))

            elif registry := styles.get("_registry"):
                handler = registry.get(child_type)
                if handler is not None:
                    # Flush buffered inline children first
                    if inline_children:
                        text = inline_render(inline_children, styles, parent_style="list_item")
                        contents.append(Paragraph(text, styles["list_item"]))
                        inline_children = []
                    # Render using handler
                    contents.extend(handler.render(child, styles))
                else:
                    inline_children.append(child)
            else:
                # Tight list items expose inline tokens directly
                inline_children.append(child)

        # Flush any remaining inline content
        if inline_children:
            text = inline_render(inline_children, styles, parent_style="list_item")
            contents.append(Paragraph(text, styles["list_item"]))

        # ListItem requires at least one flowable
        if not contents:
            contents.append(Paragraph("", styles["list_item"]))

        return ListItem(contents, bulletType="1" if ordered else "bullet")
