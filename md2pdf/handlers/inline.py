"""Shared inline renderer for md2pdf handlers.

``inline_render`` converts a list of inline token dicts (produced by the
parser for the ``children`` of block-level tokens) into a ReportLab XML
markup string suitable for use inside a ``Paragraph(text, style)`` call.

Supported inline token types
-----------------------------
- ``RawText``   — plain text (XML-escaped)
- ``Strong``    — ``<b>...</b>``
- ``Emphasis``  — ``<i>...</i>``
- ``InlineCode``— ``<font name='Courier'>...</font>``
- ``Link``      — ``<a href="..." color="...">...</a>``
- ``Image``     — alt text only (images not embedded inline)
- ``LineBreak`` — ``<br/>``
- Anything else — raw text content, XML-escaped
"""

from __future__ import annotations

import xml.sax.saxutils as saxutils


def escape_xml(text: str) -> str:
    """Escape ``<``, ``>``, and ``&`` for use in ReportLab XML markup.

    Args:
        text: Plain text string.

    Returns:
        XML-safe string.
    """
    return saxutils.escape(text)


def inline_render(children: list[dict], styles: dict | None = None) -> str:
    """Convert inline token children to a ReportLab XML markup string.

    Args:
        children: List of inline token dicts as produced by
                  :class:`~md2pdf.core.parser.MarkdownParser`.
        styles:   Optional stylesheet dict; used to look up ``color_link``.
                  Pass ``None`` (or omit) to use the default link colour.

    Returns:
        A string of ReportLab paragraph markup, e.g.
        ``"Hello <b>world</b> — visit <a href='…'>link</a>."``.
    """
    parts: list[str] = []
    link_color: str = (styles or {}).get("color_link", "#0366d6")

    for child in children:
        t = child.get("type", "")
        raw = child.get("raw", "") or ""

        if t == "RawText":
            parts.append(escape_xml(raw))

        elif t == "Strong":
            inner = inline_render(child.get("children", []), styles)
            parts.append(f"<b>{inner}</b>")

        elif t == "Emphasis":
            inner = inline_render(child.get("children", []), styles)
            parts.append(f"<i>{inner}</i>")

        elif t == "InlineCode":
            inner = inline_render(child.get("children", []), styles) or escape_xml(raw)
            parts.append(f"<font name='Courier'>{inner}</font>")

        elif t == "Math":
            config = styles.get("_config") if styles else None
            from md2pdf.handlers.latex import get_latex_image

            path, w, h = get_latex_image(raw, config)
            if path:
                parts.append(f'<img src="{path}" width="{w}" height="{h}" valign="middle"/>')
            else:
                parts.append(escape_xml(raw))

        elif t == "Link":
            href = child.get("attrs", {}).get("target", "")
            label = inline_render(child.get("children", []), styles)
            parts.append(f'<a href="{href}" color="{link_color}">{label}</a>')

        elif t == "Image":
            # Inline images are represented by their alt text only.
            alt = child.get("attrs", {}).get("title", "") or escape_xml(raw)
            parts.append(escape_xml(alt))

        elif t == "LineBreak":
            parts.append("<br/>")

        elif t == "SoftBreak":
            parts.append(" ")

        else:
            # Fallback: render whatever raw text is available.
            if child.get("children"):
                parts.append(inline_render(child["children"], styles))
            else:
                parts.append(escape_xml(raw))

    return "".join(parts)
