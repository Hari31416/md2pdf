import os
import re

from reportlab.platypus import Paragraph

from md2pdf.core.registry import ElementHandler
from md2pdf.handlers.inline import inline_render


class ParagraphHandler(ElementHandler):
    """Render ``Paragraph`` tokens as styled ``Paragraph`` flowables, extracting images."""

    token_type = "Paragraph"

    def render(self, token: dict, styles: dict) -> list:
        img_tag_pattern = re.compile(r"(<img\s+[^>]*?>)", re.IGNORECASE)
        attr_pattern = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)

        def parse_attributes(tag_str: str) -> dict[str, str]:
            attrs = {}
            for m in attr_pattern.finditer(tag_str):
                name = m.group(1).lower()
                val = m.group(2) or m.group(3) or ""
                attrs[name] = val
            return attrs

        virtual_children = []
        for child in token.get("children", []):
            t = child.get("type", "")
            raw = child.get("raw", "") or ""
            if t == "RawText" and "<img" in raw.lower():
                parts = img_tag_pattern.split(raw)
                for part in parts:
                    if part.lower().startswith("<img"):
                        attrs = parse_attributes(part)
                        if "src" in attrs:
                            virtual_children.append(
                                {
                                    "type": "HTMLImage",
                                    "attrs": {
                                        "target": attrs["src"],
                                        "alt": attrs.get("alt", ""),
                                        "width": attrs.get("width", ""),
                                        "height": attrs.get("height", ""),
                                    },
                                }
                            )
                    elif part:
                        virtual_children.append({"type": "RawText", "raw": part})
            elif t == "Image":
                target = child.get("attrs", {}).get("target", "")
                alt = inline_render(child.get("children", []), styles)
                virtual_children.append(
                    {
                        "type": "MarkdownImage",
                        "attrs": {"target": target, "alt": alt},
                    }
                )
            else:
                virtual_children.append(child)

        flowables = []
        current_text_run = []

        def flush_text_run() -> None:
            if current_text_run:
                text = inline_render(current_text_run, styles)
                if text.strip():
                    flowables.append(Paragraph(text, styles["body"]))
                current_text_run.clear()

        for child in virtual_children:
            ct = child.get("type", "")
            if ct in ("HTMLImage", "MarkdownImage"):
                flush_text_run()

                target = child["attrs"]["target"]

                # Resolve relative path using _config.input_file
                config = styles.get("_config")
                input_file = config.input_file if config else ""
                if input_file and not os.path.isabs(target):
                    base_dir = os.path.dirname(os.path.abspath(input_file))
                    resolved_path = os.path.join(base_dir, target)
                else:
                    resolved_path = target

                # Verify if file exists on disk
                if not os.path.isfile(resolved_path):
                    from md2pdf.assets.fallback import PlaceholderBox

                    box = PlaceholderBox("image", f"Missing: {target}", width=400, height=80)
                    box.hAlign = "CENTER"
                    flowables.append(box)
                    continue

                # Load image dimensions using PIL
                from PIL import Image as PILImage

                from md2pdf.core.flowables import ResizableImage

                try:
                    with PILImage.open(resolved_path) as pil_img:
                        orig_w, orig_h = pil_img.size
                except Exception:
                    from md2pdf.assets.fallback import PlaceholderBox

                    box = PlaceholderBox("image", f"Corrupt: {target}", width=400, height=80)
                    box.hAlign = "CENTER"
                    flowables.append(box)
                    continue

                # Determine display size
                custom_width_str = child["attrs"].get("width", "")
                custom_height_str = child["attrs"].get("height", "")

                display_width = None
                display_height = None
                max_avail_width = 450.0

                if custom_width_str:
                    if "%" in custom_width_str:
                        try:
                            pct = float(custom_width_str.replace("%", "").strip()) / 100.0
                            display_width = max_avail_width * pct
                        except ValueError:
                            pass
                    else:
                        try:
                            display_width = float(custom_width_str.replace("px", "").strip())
                        except ValueError:
                            pass

                if custom_height_str:
                    if "%" in custom_height_str:
                        try:
                            pct = float(custom_height_str.replace("%", "").strip()) / 100.0
                            display_height = 600.0 * pct
                        except ValueError:
                            pass
                    else:
                        try:
                            display_height = float(custom_height_str.replace("px", "").strip())
                        except ValueError:
                            pass

                pts_width = orig_w * 0.75
                pts_height = orig_h * 0.75

                if display_width is not None and display_height is not None:
                    pass
                elif display_width is not None:
                    display_height = pts_height * (display_width / pts_width)
                elif display_height is not None:
                    display_width = pts_width * (display_height / pts_height)
                else:
                    display_width = min(400.0, pts_width)
                    scale_ratio = display_width / pts_width
                    display_height = pts_height * scale_ratio

                # Cap height
                max_height = 600.0
                if display_height > max_height:
                    height_scale = max_height / display_height
                    display_height = max_height
                    display_width = display_width * height_scale

                img = ResizableImage(resolved_path, width=display_width, height=display_height)
                img.hAlign = "CENTER"
                flowables.append(img)
            else:
                current_text_run.append(child)

        flush_text_run()

        if not flowables:
            return [Paragraph("", styles["body"])]

        return flowables
