"""Per-slide presentation data and reusable, resolution-independent templates.

The compositor deliberately keeps the source media separate from its graphic
layers.  A still image and an FFmpeg video frame use the same geometry and
overlay images, so previews and exports share the same design rules.
"""

import os
import re
import uuid

from PIL import Image, ImageDraw, ImageFont


TEMPLATES = {
    "legacy": "Κλασικό (παλιά εμφάνιση)",
    "navy_gold": "Elegant Navy & Gold",
    "cinematic": "Full-Screen Cinematic",
    "lower_third": "Modern Lower Third",
    "split_editorial": "Split Editorial Layout",
    "real_estate": "Real Estate Property",
    "business_service": "Business Service Card",
    "intro_outro": "Introduction / Outro",
    "before_after": "Before / After",
}
INHERIT_TEMPLATE = "project"
INHERIT_TEMPLATE_LABEL = "Use Project Default"

FONT_FILES = {
    "Calibri": ("calibri.ttf", "calibrib.ttf"),
    "Arial": ("arial.ttf", "arialbd.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf"),
}

DEFAULT_PRESENTATION = {
    "scene_id": "",
    "mode": "global",
    "template": INHERIT_TEMPLATE,
    "title": "",
    "subtitle": "",
    "description": "",
    "category": "",
    "location": "",
    "price": "",
    "details": "",
    "cta": "",
    "business_name": "",
    "phone": "",
    "website": "",
    "before_label": "ΠΡΙΝ",
    "after_label": "ΜΕΤΑ",
    "text_position": "template",
    "font_family": "",
    "font_size": 0,
    "text_color": "#FFFFFF",
    "panel_color": "#111B2B",
    "accent_color": "#D6B86A",
    "panel_style": "solid",
    "duration": None,
    "logo_enabled": False,
    "logo_path": "",
    "compare_path": "",
    "transition": "global",
    "transition_duration": None,
    "motion": {"preset": "static"},
}

_MODES = {"global", "custom", "none", "combine"}
_TEXT_POSITIONS = {"template", "top", "center", "bottom"}
_PANEL_STYLES = {"solid", "translucent"}
_TRANSITIONS = {"global", "none", "fade", "fadeblack", "fadewhite", "wipeleft",
                "wiperight", "wipeup", "wipedown", "smoothleft", "smoothright"}


def normalize_presentation(value=None, scene_id=None):
    """Return validated presentation data, preserving unknown future fields."""
    data = dict(DEFAULT_PRESENTATION)
    if isinstance(value, dict):
        data.update(value)
    data["scene_id"] = str(data.get("scene_id") or scene_id or uuid.uuid4().hex)
    if not isinstance(data.get("mode"), str) or data.get("mode") not in _MODES:
        data["mode"] = "global"
    if (not isinstance(data.get("template"), str) or
            (data.get("template") not in TEMPLATES and
             data.get("template") != INHERIT_TEMPLATE)):
        data["template"] = INHERIT_TEMPLATE
    if not isinstance(data.get("text_position"), str) or data.get("text_position") not in _TEXT_POSITIONS:
        data["text_position"] = "template"
    if not isinstance(data.get("panel_style"), str) or data.get("panel_style") not in _PANEL_STYLES:
        data["panel_style"] = "solid"
    if not isinstance(data.get("transition"), str) or data.get("transition") not in _TRANSITIONS:
        data["transition"] = "global"
    for key in ("title", "subtitle", "description", "category", "location", "price",
                "details", "cta", "business_name", "phone", "website", "logo_path",
                "compare_path", "font_family", "transition", "before_label", "after_label"):
        data[key] = str(data.get(key) or "")
    for key, fallback in (("text_color", "#FFFFFF"), ("panel_color", "#111B2B"),
                          ("accent_color", "#D6B86A")):
        value = str(data.get(key) or fallback)
        data[key] = value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback
    try:
        data["font_size"] = max(0, min(200, int(data.get("font_size") or 0)))
    except (TypeError, ValueError):
        data["font_size"] = 0
    try:
        duration = float(data.get("duration")) if data.get("duration") is not None else None
    except (TypeError, ValueError):
        duration = None
    data["duration"] = round(max(1.0, min(30.0, duration)), 2) if duration else None
    try:
        transition_duration = (float(data.get("transition_duration"))
                               if data.get("transition_duration") is not None else None)
    except (TypeError, ValueError):
        transition_duration = None
    data["transition_duration"] = (round(max(0.2, min(2.0, transition_duration)), 2)
                                   if transition_duration else None)
    data["logo_enabled"] = bool(data.get("logo_enabled"))
    motion = data.get("motion")
    data["motion"] = dict(motion) if isinstance(motion, dict) else {"preset": "static"}
    return data


def has_presentation_settings(value, project_template="legacy"):
    """Whether an item should display a presentation badge in the library."""
    data = normalize_presentation(value)
    return bool(data["mode"] != "global" or
                data["template"] not in ("legacy", INHERIT_TEMPLATE) or
                (data["template"] == INHERIT_TEMPLATE and project_template != "legacy") or
                data["duration"] is not None or data["logo_enabled"] or
                data["compare_path"] or data["transition"] != "global" or
                data["transition_duration"] is not None)


def presentation_fields(presentation, global_text=""):
    """Resolve the individual/global text modes into renderer-ready fields."""
    p = normalize_presentation(presentation)
    mode = p["mode"]
    raw_global = (global_text or "").strip()
    custom = {key: p.get(key, "").strip() for key in (
        "title", "subtitle", "description", "category", "location", "price",
        "details", "cta", "business_name", "phone", "website", "before_label",
        "after_label")}
    if mode == "none":
        return {key: "" for key in custom}
    if mode == "global":
        return _global_fields(raw_global)
    if mode == "combine" and raw_global:
        global_parts = _global_fields(raw_global)
        append_text = raw_global
        if not custom["title"]:
            custom["title"] = global_parts["title"]
            append_text = global_parts["description"]
        if custom["description"]:
            custom["description"] += "\n" + append_text if append_text else ""
        elif custom["subtitle"]:
            custom["description"] = append_text
        else:
            custom["description"] = append_text or global_parts["description"]
    return custom


def _global_fields(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return {
        "title": lines[0] if lines else "",
        "subtitle": "",
        "description": "\n".join(lines[1:]),
        "category": "", "location": "", "price": "", "details": "",
        "cta": "", "business_name": "", "phone": "", "website": "",
        "before_label": "ΠΡΙΝ", "after_label": "ΜΕΤΑ",
    }


def legacy_text(presentation, global_text=""):
    """Text for the original lower text box, preserving legacy global text."""
    p = normalize_presentation(presentation)
    if p["mode"] == "global":
        return global_text or ""
    if p["mode"] == "none":
        return ""
    fields = presentation_fields(p, global_text)
    lines = [fields[k] for k in ("title", "subtitle", "description", "location",
                                  "price", "details", "cta") if fields.get(k)]
    return "\n".join(lines)


def _even(value):
    return max(2, int(value) // 2 * 2)


def image_rect(template, width, height):
    """Dynamic media rectangle for each template, in output-pixel coordinates."""
    w, h = max(2, int(width)), max(2, int(height))
    aspect = w / h
    if template in ("cinematic", "lower_third"):
        return (0, 0, w, h)
    if template in ("navy_gold", "real_estate"):
        return (0, 0, w, _even(h * 0.60))
    if template in ("split_editorial", "business_service"):
        if aspect >= 1.25:
            rw = _even(w * (0.62 if template == "split_editorial" else 0.56))
            return (0, 0, rw, h)
        rh = _even(h * (0.60 if template == "split_editorial" else 0.58))
        return (0, 0, w, rh)
    if template == "intro_outro":
        rw, rh = _even(w * 0.72), _even(h * 0.42)
        return ((w - rw) // 2, _even(h * 0.08), rw, rh)
    if template == "before_after":
        if aspect >= 1.0:
            half = _even(w * 0.5)
            return (half, 0, w - half, h)
        half = _even(h * 0.5)
        return (0, half, w, h - half)
    return (0, 0, w, h)


def _fit_image(source, size):
    """Cover a target rectangle, centre-cropping only the excess pixels."""
    tw, th = max(1, int(size[0])), max(1, int(size[1]))
    source = source.convert("RGB")
    scale = max(tw / source.width, th / source.height)
    resized = source.resize((max(tw, round(source.width * scale)),
                             max(th, round(source.height * scale))), Image.Resampling.LANCZOS)
    x = max(0, (resized.width - tw) // 2)
    y = max(0, (resized.height - th) // 2)
    return resized.crop((x, y, x + tw, y + th))


def _font(family, size, bold=False):
    family = family if family in FONT_FILES else "Calibri"
    filename = FONT_FILES[family][1 if bold else 0]
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    try:
        return ImageFont.truetype(os.path.join(fonts_dir, filename), max(8, int(size)))
    except Exception:
        try:
            return ImageFont.truetype("arial.ttf", max(8, int(size)))
        except Exception:
            try:
                return ImageFont.load_default(size=max(8, int(size)))
            except TypeError:
                return ImageFont.load_default()


def _text_width(font, text):
    try:
        return font.getlength(text)
    except Exception:
        return font.getbbox(text)[2]


def _wrap(text, font, max_width):
    lines = []
    for paragraph in (text or "").splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            if _text_width(font, word) > max_width:
                if current:
                    lines.append(current)
                    current = ""
                piece = ""
                piece_width = 0.0
                for char in word:
                    char_width = _text_width(font, char)
                    if piece and piece_width + char_width > max_width:
                        lines.append(piece)
                        piece = char
                        piece_width = char_width
                    else:
                        piece += char
                        piece_width += char_width
                current = piece
                continue
            candidate = word if not current else current + " " + word
            if _text_width(font, candidate) <= max_width or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _color_rgba(hex_color, alpha=255):
    rgb = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (*rgb, max(0, min(255, int(alpha))))


def _place_logo(overlay, presentation, fonts, bounds, accent):
    path = presentation.get("logo_path", "")
    if not presentation.get("logo_enabled") or not path or not os.path.isfile(path):
        return
    try:
        logo = Image.open(path).convert("RGBA")
        max_w = max(20, int(bounds[2] * 0.18))
        max_h = max(20, int(bounds[3] * 0.13))
        logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        x = bounds[0] + max(0, bounds[2] - logo.width)
        y = bounds[1] + max(0, bounds[3] - logo.height)
        overlay.alpha_composite(logo, (x, y))
    except Exception:
        return


def render_design_layers(width, height, presentation, fields, before_image=None):
    """Return (base, overlay, image_rect, overflow) for a professional template.

    ``base`` contains opaque panels and a static Before image where needed.
    ``overlay`` contains all typography and decoration. The main media remains
    its own layer and is painted into ``image_rect`` by the caller.
    """
    p = normalize_presentation(presentation)
    template = p["template"]
    w, h = max(2, int(width)), max(2, int(height))
    panel = p["panel_color"]
    accent = p["accent_color"]
    white = p["text_color"]
    base = Image.new("RGB", (w, h), panel if template != "cinematic" else "#101010")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rect = image_rect(template, w, h)
    x, y, rw, rh = rect
    margin = max(18, int(min(w, h) * 0.055))
    text_box = None

    if template == "navy_gold":
        yline = rh
        draw.rectangle((0, yline, w, min(h, yline + max(3, int(h * 0.004))),), fill=accent)
        text_box = (margin, min(h - margin, yline + margin), w - margin * 2,
                    max(0, h - yline - margin * 2))
    elif template == "real_estate":
        draw.rectangle((0, rh, w, min(h, rh + max(4, int(h * 0.005))),), fill=accent)
        text_box = (margin, rh + margin, w - margin * 2, max(0, h - rh - margin * 2))
    elif template == "split_editorial":
        if w / h >= 1.25:
            draw.rectangle((rw, 0, min(w, rw + max(3, int(w * 0.004))), h), fill=accent)
            text_box = (rw + margin, margin, max(0, w - rw - margin * 2), h - margin * 2)
        else:
            draw.rectangle((0, rh, w, min(h, rh + max(3, int(h * 0.004))),), fill=accent)
            text_box = (margin, rh + margin, w - margin * 2, max(0, h - rh - margin * 2))
    elif template == "business_service":
        if w / h >= 1.25:
            text_box = (rw + margin, margin, max(0, w - rw - margin * 2), h - margin * 2)
        else:
            draw.rectangle((0, rh, w, min(h, rh + max(3, int(h * 0.004))),), fill=accent)
            text_box = (margin, rh + margin, w - margin * 2, max(0, h - rh - margin * 2))
    elif template == "cinematic":
        alpha = 178 if p["panel_style"] == "solid" else 132
        top = int(h * 0.53)
        for gy in range(top, h):
            a = int(alpha * (gy - top) / max(1, h - top))
            draw.line((0, gy, w, gy), fill=(0, 0, 0, a))
        text_box = (margin, int(h * 0.62), w - margin * 2, int(h * 0.34))
    elif template == "lower_third":
        alpha = 205 if p["panel_style"] == "solid" else 145
        box_h = int(h * 0.31)
        box_y = h - box_h - max(12, int(h * 0.025))
        draw.rounded_rectangle((margin // 2, box_y, w - margin // 2, h - margin // 2),
                               radius=max(8, margin // 3), fill=(12, 19, 29, alpha),
                               outline=_color_rgba(accent, 220), width=max(1, int(h * 0.002)))
        text_box = (margin, box_y + margin // 2, w - margin * 2,
                    box_h - margin)
    elif template == "intro_outro":
        draw.rectangle((0, 0, w, max(2, int(h * 0.018))), fill=accent)
        draw.rectangle((0, h - max(2, int(h * 0.018)), w, h), fill=accent)
        text_box = (margin * 2, y + rh + margin, w - margin * 4,
                    max(0, h - y - rh - margin * 2))
    elif template == "before_after":
        if before_image is not None:
            before_rect = (0, 0, x, h) if w / h >= 1.0 else (0, 0, w, y)
            bx, by, bw, bh = before_rect
            if bw > 0 and bh > 0:
                base.paste(_fit_image(before_image, (bw, bh)), (bx, by))
        else:
            before_rect = (0, 0, x, h) if w / h >= 1.0 else (0, 0, w, y)
            bx, by, bw, bh = before_rect
            label_font = _font(p["font_family"], max(12, int(min(w, h) * .022)), True)
            label = "ΕΠΙΛΕΞΕ ΦΩΤΟΓΡΑΦΙΑ ΠΡΙΝ"
            label_w = _text_width(label_font, label)
            placeholder = ImageDraw.Draw(base)
            placeholder.text((bx + max(0, (bw - label_w) // 2),
                              by + max(0, (bh - label_font.size) // 2)),
                             label, font=label_font, fill="#B7C0CC")
        split_x = x if w / h >= 1.0 else w
        split_y = y if w / h < 1.0 else h
        if w / h >= 1.0:
            draw.rectangle((split_x - 2, 0, split_x + 2, h), fill=accent)
            draw.rectangle((0, 0, max(100, int(w * .20)), max(34, int(h * .06))),
                           fill=(9, 15, 24, 220))
            draw.text((margin // 2, margin // 3), fields.get("before_label") or "ΠΡΙΝ",
                      font=_font(p["font_family"], max(12, int(min(w, h) * .025)), True), fill=white)
            draw.rectangle((split_x, 0, min(w, split_x + int(w * .20)), max(34, int(h * .06))),
                           fill=(9, 15, 24, 220))
            draw.text((split_x + margin // 2, margin // 3), fields.get("after_label") or "ΜΕΤΑ",
                      font=_font(p["font_family"], max(12, int(min(w, h) * .025)), True), fill=white)
        else:
            draw.rectangle((0, split_y - 2, w, split_y + 2), fill=accent)
            label_font = _font(p["font_family"], max(12, int(min(w, h) * .025)), True)
            draw.rectangle((0, 0, int(w * .22), max(34, int(h * .06))), fill=(9, 15, 24, 220))
            draw.text((margin // 2, margin // 3), fields.get("before_label") or "ΠΡΙΝ",
                      font=label_font, fill=white)
            draw.rectangle((0, split_y, int(w * .22), split_y + max(34, int(h * .06))), fill=(9, 15, 24, 220))
            draw.text((margin // 2, split_y + margin // 3), fields.get("after_label") or "ΜΕΤΑ",
                      font=label_font, fill=white)
        overlay_draw = ImageDraw.Draw(overlay, "RGBA")
        overlay_draw.rectangle((0, int(h * .79), w, h), fill=(8, 14, 22, 175))
        text_box = (margin, int(h * .81), w - margin * 2, int(h * .17))
    else:
        return base, overlay, rect, False

    logo_bounds = text_box
    if (text_box and p.get("logo_enabled") and p.get("logo_path") and
            os.path.isfile(p["logo_path"])):
        tx, ty, tw, th = text_box
        text_box = (tx, ty, tw, max(0, th - int(th * 0.15)))

    overflow = False
    if text_box:
        overflow = _draw_content(draw, text_box, fields, p, accent, white, margin)
    _place_logo(overlay, p, None,
                logo_bounds or (margin, margin, w - margin * 2, h - margin * 2), accent)
    return base, overlay, rect, overflow


def _draw_content(draw, box, fields, p, accent, white, margin):
    x, y, bw, bh = box
    box_y = y
    if bw < 1 or bh < 1:
        return bool(any(fields.values()))
    family = p.get("font_family") or "Calibri"
    min_side = min(draw._image.size) if getattr(draw, "_image", None) else min(bw, bh)
    auto_title = max(22, min(96, int(min_side * (0.065 if p["template"] != "lower_third" else 0.052))))
    title_size = p["font_size"] or auto_title
    title_size = min(title_size, max(18, int(bh * .31)))
    title = fields.get("title", "") or ""
    subtitle = fields.get("subtitle", "") or ""
    description = fields.get("description", "") or ""
    metadata = [fields.get(k, "") for k in ("location", "price", "details") if fields.get(k)]
    business = fields.get("business_name", "") or ""
    contact = "  •  ".join(v for v in (fields.get("phone", ""), fields.get("website", "")) if v)
    category = fields.get("category", "") or (
        "PROPERTY" if p["template"] == "real_estate" else
        ("FEATURED" if p["template"] == "navy_gold" else ""))
    cta = fields.get("cta", "") or ""
    scale = 1.0
    parts = []
    for _ in range(18):
        parts = []
        cursor = y
        if category:
            size = max(10, int(min_side * .021 * scale))
            font = _font(family, size, True)
            lines = _wrap(category.upper(), font, bw)
            parts.append(("category", lines, font, accent, size + 3))
            cursor += len(lines) * (size + 3) + max(4, margin // 5)
        if title:
            size = max(9, int(title_size * scale))
            font = _font(family, size, True)
            lines = _wrap(title, font, bw)
            parts.append(("title", lines, font, white, int(size * 1.15)))
            cursor += len(lines) * int(size * 1.15) + max(3, margin // 6)
        if subtitle:
            size = max(9, int(title_size * .52 * scale))
            font = _font(family, size, False)
            lines = _wrap(subtitle, font, bw)
            parts.append(("subtitle", lines, font, white, int(size * 1.22)))
            cursor += len(lines) * int(size * 1.22) + max(3, margin // 7)
        for value in metadata:
            size = max(9, int(title_size * .42 * scale))
            font = _font(family, size, True)
            lines = _wrap(value, font, bw)
            parts.append(("metadata", lines, font, accent if value in (fields.get("location"), fields.get("price")) else white, int(size * 1.2)))
            cursor += len(lines) * int(size * 1.2) + max(2, margin // 8)
        if description:
            size = max(8, int(title_size * .36 * scale))
            font = _font(family, size, False)
            lines = _wrap(description, font, bw)
            parts.append(("description", lines, font, white, int(size * 1.3)))
            cursor += len(lines) * int(size * 1.3) + max(2, margin // 8)
        if cta:
            size = max(9, int(title_size * .37 * scale))
            font = _font(family, size, True)
            lines = _wrap(cta, font, bw)
            parts.append(("cta", lines, font, accent, int(size * 1.25)))
            cursor += len(lines) * int(size * 1.25) + max(2, margin // 8)
        if business or contact:
            size = max(8, int(title_size * .25 * scale))
            font = _font(family, size, False)
            footer = "  •  ".join(v for v in (business, contact) if v)
            lines = _wrap(footer, font, bw)
            parts.append(("footer", lines, font, white, int(size * 1.2)))
            cursor += len(lines) * int(size * 1.2)
        if cursor <= y + bh:
            break
        scale *= .86
    overflow = bool(parts and cursor > y + bh)
    content_height = max(0, cursor - y)
    position = p.get("text_position", "template")
    if position == "center":
        y = box_y + max(0, (bh - content_height) // 2)
    elif position == "bottom":
        y = box_y + max(0, bh - content_height)
    else:
        y = box_y
    cursor = y
    for name, lines, font, color, line_h in parts:
        if name == "category" and p["template"] in ("navy_gold", "real_estate"):
            line = lines[0] if lines else ""
            draw.rounded_rectangle((x, cursor, x + max(1, _text_width(font, line) + 16), cursor + line_h + 5),
                                   radius=max(2, line_h // 4), fill=_color_rgba(accent, 36),
                                   outline=_color_rgba(accent, 170), width=1)
            draw.text((x + 8, cursor + 2), line, font=font, fill=color)
            cursor += line_h + max(7, margin // 5)
            continue
        for line in lines:
            draw.text((x, cursor), line, font=font, fill=color)
            cursor += line_h
        cursor += max(2, margin // 8)
    return overflow


def compose_design_frame(source, width, height, presentation, fields, before_image=None):
    """Compose one actual media frame using the same reusable template layers."""
    base, overlay, rect, overflow = render_design_layers(
        width, height, presentation, fields, before_image=before_image)
    result = base.copy()
    x, y, rw, rh = rect
    if source is not None and rw > 0 and rh > 0:
        result.paste(_fit_image(source, (rw, rh)), (x, y))
    result = Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")
    return result, overflow
