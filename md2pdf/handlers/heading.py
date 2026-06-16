"""HeadingHandler — renders Markdown headings (H1–H6) to ReportLab Paragraphs."""

from __future__ import annotations

import html
import re

from reportlab.platypus import Paragraph

from md2pdf.core.flowables import BookmarkFlowable
from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render


def slugify(text: str) -> str:
    """Convert text to a URL/bookmark-friendly slug."""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    clean = clean.lower()
    # Unescape HTML entities (e.g. &amp; -> &) before processing
    clean = html.unescape(clean)
    # Replace spaces with hyphens
    clean = re.sub(r"\s", "-", clean)
    # Strip everything except letters, numbers, hyphens, and underscores
    clean = re.sub(r"[^\w-]", "", clean)
    return clean


class HeadingHandler(ElementHandler):
    """Render ``Heading`` tokens as styled ``Paragraph`` flowables with bookmark anchors.

    Heading levels above 4 fall back to the ``h4`` style since ReportLab's
    default stylesheet does not define H5/H6.
    """

    token_type = "Heading"

    def render(self, token: dict, styles: dict) -> list:
        level: int = token.get("attrs", {}).get("level", 1)
        style_key = f"h{min(level, 4)}"
        text = inline_render(token.get("children", []), styles, parent_style=style_key)

        slug = slugify(text)
        if not slug:
            import uuid

            slug = f"heading-{uuid.uuid4().hex[:8]}"

        # Uniquify slug
        seen_slugs = styles.get("_seen_slugs")
        if seen_slugs is not None:
            base_slug = slug
            counter = 2
            while slug in seen_slugs:
                slug = f"{base_slug}-{counter}"
                counter += 1
            seen_slugs.add(slug)

        # Strip HTML tags for the plain-text outline title shown in PDF viewers.
        plain_title = re.sub(r"<[^>]+>", "", text)
        plain_title = html.unescape(plain_title)
        # Outline level is 0-indexed (H1 → 0, H2 → 1, …).
        return [
            BookmarkFlowable(slug, title=plain_title, level=level - 1),
            Paragraph(text, styles[style_key]),
        ]
