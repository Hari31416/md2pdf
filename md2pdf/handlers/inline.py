"""Shared inline renderer for md2pdf handlers.

``inline_render`` converts a list of inline token dicts (produced by the
parser for the ``children`` of block-level tokens) into a ReportLab XML
markup string suitable for use inside a ``Paragraph(text, style)`` call.

Supported inline token types
-----------------------------
- ``RawText``   — plain text (XML-escaped); small ``<img>`` tags (≤32 px)
                  are rendered as inline ReportLab images automatically.
- ``InlineXML`` — pre-built ReportLab XML, emitted verbatim.
- ``Strong``    — ``<b>...</b>``
- ``Emphasis``  — ``<i>...</i>``
- ``InlineCode``— ``<font name='Courier'>...</font>``
- ``Link``      — ``<a href="..." color="...">...</a>``
- ``Image``     — alt text only (large images not embedded inline)
- ``LineBreak`` — ``<br/>``
- Anything else — raw text content, XML-escaped
"""

from __future__ import annotations

import re
import xml.sax.saxutils as saxutils
from typing import Any

# ---------------------------------------------------------------------------
# Inline-image helpers (used for emoji substitution)
# ---------------------------------------------------------------------------

# Max dimension (px) at which an <img> tag is treated as inline rather than block.
_INLINE_IMG_MAX_PX: int = 32

_IMG_TAG_RE = re.compile(r"(<img\s+[^>]*?>)", re.IGNORECASE)
_IMG_ATTR_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)


def _parse_img_attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for m in _IMG_ATTR_RE.finditer(tag):
        attrs[m.group(1).lower()] = m.group(2) or m.group(3) or ""
    return attrs


def _is_small_img(attrs: dict[str, str]) -> bool:
    """Return True when both width and height are present and ≤ ``_INLINE_IMG_MAX_PX``."""
    for dim in ("width", "height"):
        val = attrs.get(dim, "").strip()
        if not val:
            return False
        try:
            if float(val) > _INLINE_IMG_MAX_PX:
                return False
        except ValueError:
            return False
    return True


def _expand_inline_imgs(raw: str) -> str:
    """Split *raw* on ``<img>`` tags; keep small ones as ReportLab inline images.

    Large images and tags without a ``src`` attribute are XML-escaped so they
    appear as literal text (which is the safe fallback for non-paragraph contexts).
    """
    out: list[str] = []
    for part in _IMG_TAG_RE.split(raw):
        if part.lower().startswith("<img"):
            attrs = _parse_img_attrs(part)
            src = attrs.get("src", "")
            if src and _is_small_img(attrs):
                w = attrs.get("width", "14")
                h = attrs.get("height", "14")
                out.append(f'<img src="{src}" width="{w}" height="{h}" valign="middle"/>')
            else:
                # Large or malformed img — escape so it shows as text rather than crashing.
                out.append(escape_xml(part))
        else:
            out.append(escape_xml(part))
    return "".join(out)


def escape_xml(text: str) -> str:
    """Escape ``<``, ``>``, and ``&`` for use in ReportLab XML markup.

    Args:
        text: Plain text string.

    Returns:
        XML-safe string.
    """
    return saxutils.escape(text)


def inline_render(
    children: list[dict],
    styles: dict | None = None,
    parent_style: Any | None = None,
) -> str:
    """Convert inline token children to a ReportLab XML markup string.

    Args:
        children: List of inline token dicts as produced by
                  :class:`~md2pdf.core.parser.MarkdownParser`.
        styles:   Optional stylesheet dict; used to look up ``color_link``.
                  Pass ``None`` (or omit) to use the default link colour.
        parent_style: The stylesheet paragraph style (or style name) of the
                      containing block.

    Returns:
        A string of ReportLab paragraph markup, e.g.
        ``"Hello <b>world</b> — visit <a href='…'>link</a>."``.
    """
    parts: list[str] = []
    link_color: str = (styles or {}).get("color_link", "#0366d6")

    for child in children:
        t = child.get("type", "")
        raw = child.get("raw", "") or ""

        if t == "InlineXML":
            # Pre-built ReportLab paragraph XML — emit verbatim, no escaping.
            parts.append(raw)

        elif t == "RawText":
            if "<img" in raw.lower():
                # May contain emoji <img> tags — expand small ones inline.
                parts.append(_expand_inline_imgs(raw))
            else:
                parts.append(escape_xml(raw))

        elif t == "Strong":
            inner = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f"<b>{inner}</b>")

        elif t == "Emphasis":
            inner = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f"<i>{inner}</i>")

        elif t == "Strikethrough":
            inner = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f"<strike>{inner}</strike>")

        elif t == "Highlight":
            inner = inline_render(child.get("children", []), styles, parent_style)
            highlight_color = (styles or {}).get("color_highlight", "#ffff00")
            parts.append(f'<span backcolor="{highlight_color}">{inner}</span>')

        elif t == "Superscript":
            inner = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f"<sup>{inner}</sup>")

        elif t == "Subscript":
            inner = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f"<sub>{inner}</sub>")

        elif t == "InlineCode":
            inner = inline_render(child.get("children", []), styles, parent_style) or escape_xml(
                raw
            )
            parts.append(f"<font name='Courier'>{inner}</font>")

        elif t == "Math":
            config = styles.get("_config") if styles else None
            from md2pdf.handlers.latex import get_latex_image

            fontsize = 10
            if parent_style:
                if isinstance(parent_style, str) and styles and parent_style in styles:
                    fontsize = getattr(styles[parent_style], "fontSize", 10)
                elif hasattr(parent_style, "fontSize"):
                    fontsize = getattr(parent_style, "fontSize", 10)
            elif styles and "body" in styles:
                fontsize = getattr(styles["body"], "fontSize", 10)

            path, w, h, depth = get_latex_image(raw, config, fontsize=fontsize)
            if path:
                valign = -depth
                parts.append(f'<img src="{path}" width="{w}" height="{h}" valign="{valign}"/>')
            else:
                parts.append(escape_xml(raw))

        elif t == "Link":
            href = child.get("attrs", {}).get("target", "")
            label = inline_render(child.get("children", []), styles, parent_style)
            parts.append(f'<a href="{href}" color="{link_color}">{label}</a>')

        elif t == "Image":
            # Inline images are represented by their alt text only.
            alt = child.get("attrs", {}).get("title", "") or escape_xml(raw)
            parts.append(escape_xml(alt))

        elif t == "FootnoteReference":
            parts.append(f'<sup><a href="#fn-{raw}" color="{link_color}">{raw}</a></sup>')

        elif t == "LineBreak":
            parts.append("<br/>")

        elif t == "SoftBreak":
            parts.append(" ")

        else:
            # Fallback: render whatever raw text is available.
            if child.get("children"):
                parts.append(inline_render(child["children"], styles, parent_style))
            else:
                parts.append(escape_xml(raw))

    rendered = "".join(parts)

    rendered = re.sub(r"&lt;[Bb][Rr]\s*/?&gt;", "<br/>", rendered)
    return rendered
