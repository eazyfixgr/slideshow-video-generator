"""Per-slide presentation data and reusable, resolution-independent templates.

The compositor deliberately keeps the source media separate from its graphic
layers.  A still image and an FFmpeg video frame use the same geometry and
overlay images, so previews and exports share the same design rules.
"""

import os
import re
import uuid

from PIL import Image, ImageDraw, ImageFilter, ImageFont


TEMPLATES = {
    "legacy": "Απλό",
    "navy_gold": "Elegant Navy & Gold",
    "cinematic": "Υπότιτλος",
    "lower_third": "Navy & Gold Transparent",
    "intro_outro": "Introduction / Outro",
}
INHERIT_TEMPLATE = "project"
INHERIT_TEMPLATE_LABEL = "Use Project Default"
TEMPLATE_ALIASES = {
    "real_estate": "navy_gold",
    "split_editorial": "navy_gold",
    "business_service": "navy_gold",
    "before_after": "navy_gold",
}


def normalize_template(value, fallback="legacy"):
    """Resolve removed template names while keeping old projects renderable."""
    if value == INHERIT_TEMPLATE:
        return INHERIT_TEMPLATE
    if not isinstance(value, str):
        return fallback
    value = TEMPLATE_ALIASES.get(value, value)
    return value if value in TEMPLATES else fallback

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
    "template_name": "",
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
    "text_position": "bottom",
    "text_align": "center",
    "font_family": "",
    "font_size": 90,
    "text_color": "#FFFFFF",
    "panel_color": "#111B2B",
    "accent_color": "#D6B86A",
    "panel_style": "solid",
    "panel_opacity": None,
    "panel_width_pct": 0,
    "panel_padding_pct": 0,
    "panel_min_height_pct": 0,
    "text_layout": None,
    "featured_enabled": False,
    "featured_text": "FEATURED",
    "duration": None,
    "logo_enabled": False,
    "logo_path": "",
    "compare_path": "",
    "transition": "global",
    "transition_duration": None,
    "motion": {"preset": "static"},
}
DESIGN_FIELDS = (
    "template", "text_position", "text_align", "featured_enabled", "featured_text",
    "font_family", "font_size", "text_color", "panel_color", "accent_color",
    "panel_style", "panel_opacity", "panel_width_pct", "panel_padding_pct",
    "panel_min_height_pct", "text_layout", "duration", "logo_enabled", "logo_path",
    "transition", "transition_duration", "motion",
)

_MODES = {"global", "custom", "none", "combine"}
_TEXT_POSITIONS = {"top", "center", "bottom"}
_TEXT_ALIGNMENTS = {"left", "center", "right"}
_PANEL_STYLES = {"solid", "translucent"}
_TRANSITIONS = {"global", "none", "fade", "fadeblack", "fadewhite", "wipeleft",
                "wiperight", "wipeup", "wipedown", "smoothleft", "smoothright"}


def normalize_presentation(value=None, scene_id=None, project_template=None):
    """Return validated presentation data, preserving unknown future fields."""
    data = dict(DEFAULT_PRESENTATION)
    source = value if isinstance(value, dict) else {}
    data.update(source)
    data["scene_id"] = str(data.get("scene_id") or scene_id or uuid.uuid4().hex)
    if not isinstance(data.get("mode"), str) or data.get("mode") not in _MODES:
        data["mode"] = "global"
    old_template = source.get("template")
    data["template"] = normalize_template(data.get("template"), INHERIT_TEMPLATE)
    data["template_name"] = str(data.get("template_name") or "").strip()
    if isinstance(source.get("style_overrides"), list):
        data["style_overrides"] = [str(key) for key in source["style_overrides"]
                                   if isinstance(key, str)]
    else:
        data.pop("style_overrides", None)
    if "font_size" not in source:
        default_template = data["template"]
        if default_template == INHERIT_TEMPLATE and project_template:
            default_template = normalize_template(project_template)
        if default_template == "navy_gold":
            data["font_size"] = 85
    if old_template == "real_estate" and "featured_text" not in source:
        data["featured_text"] = str(source.get("category") or "PROPERTY")
    elif (isinstance(old_template, str) and old_template in TEMPLATE_ALIASES and
          "featured_enabled" not in source):
        data["featured_enabled"] = False
        if "featured_text" not in source:
            data["featured_text"] = ""
    if (data.get("text_position") == "template" or
            not isinstance(data.get("text_position"), str) or
            data.get("text_position") not in _TEXT_POSITIONS):
        data["text_position"] = "bottom"
    if not isinstance(data.get("text_align"), str) or data.get("text_align") not in _TEXT_ALIGNMENTS:
        data["text_align"] = "center"
    if not isinstance(data.get("panel_style"), str) or data.get("panel_style") not in _PANEL_STYLES:
        data["panel_style"] = "solid"
    if not isinstance(data.get("transition"), str) or data.get("transition") not in _TRANSITIONS:
        data["transition"] = "global"
    for key in ("title", "subtitle", "description", "category", "location", "price",
                "details", "cta", "business_name", "phone", "website", "logo_path",
                "compare_path", "font_family", "transition", "before_label", "after_label",
                "featured_text"):
        data[key] = str(data.get(key) or "")
    for key, fallback in (("text_color", "#FFFFFF"), ("panel_color", "#111B2B"),
                          ("accent_color", "#D6B86A")):
        value = str(data.get(key) or fallback)
        data[key] = value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback
    try:
        data["font_size"] = max(0, min(400, int(data.get("font_size") or 0)))
    except (TypeError, ValueError):
        data["font_size"] = 0
    opacity = data.get("panel_opacity")
    if opacity is None:
        data["panel_opacity"] = None
    else:
        try:
            data["panel_opacity"] = max(0, min(100, int(float(opacity))))
        except (TypeError, ValueError):
            data["panel_opacity"] = None
    try:
        data["panel_width_pct"] = max(0, min(100, int(data.get("panel_width_pct") or 0)))
    except (TypeError, ValueError):
        data["panel_width_pct"] = 0
    try:
        data["panel_padding_pct"] = round(max(
            0.0, min(15.0, float(data.get("panel_padding_pct") or 0))), 2)
    except (TypeError, ValueError):
        data["panel_padding_pct"] = 0
    try:
        data["panel_min_height_pct"] = max(
            0, min(80, int(data.get("panel_min_height_pct") or 0)))
    except (TypeError, ValueError):
        data["panel_min_height_pct"] = 0
    if data.get("text_layout") not in ("overlay", "below"):
        data["text_layout"] = None
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
    data["featured_enabled"] = bool(data.get("featured_enabled"))
    motion = data.get("motion")
    data["motion"] = dict(motion) if isinstance(motion, dict) else {"preset": "static"}
    return data


def has_presentation_settings(value, project_template="legacy"):
    """Whether an item should display a presentation badge in the library."""
    data = normalize_presentation(value)
    return bool(data["mode"] != "global" or
                data["template"] not in ("legacy", INHERIT_TEMPLATE) or
                (data["template"] == INHERIT_TEMPLATE and project_template != "legacy") or
                data.get("template_name") or data.get("style_overrides") or
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
    return {
        # Shared legacy text is unstructured copy, not a guaranteed title plus
        # body. Keep it at one body scale so a short final line does not appear
        # as an oversized heading followed by tiny copy in new templates.
        "title": "",
        "subtitle": "",
        "description": (text or "").strip(),
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


def _contain_image(source, size):
    """Fit all of the media inside a rectangle without cropping its edges."""
    tw, th = max(1, int(size[0])), max(1, int(size[1]))
    source = source.convert("RGB")
    scale = min(tw / source.width, th / source.height)
    resized = source.resize((max(1, round(source.width * scale)),
                             max(1, round(source.height * scale))), Image.Resampling.LANCZOS)
    return resized


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


def _line_width(line, font, family):
    if isinstance(line, str):
        return _text_width(font, line)
    bold = _font(family, getattr(font, "size", 12), True)
    return sum(_text_width(bold if is_bold else font, text) for is_bold, text in line)


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


def _wrap_rich(text, font, family, max_width):
    """Word-wrap a description while retaining the app's **bold** markers."""
    bold_font = _font(family, getattr(font, "size", 12), True)
    spans = []
    cursor = 0
    for match in re.finditer(r"\*\*(.+?)\*\*", text or "", flags=re.DOTALL):
        if match.start() > cursor:
            spans.append((False, text[cursor:match.start()]))
        spans.append((True, match.group(1)))
        cursor = match.end()
    if cursor < len(text or ""):
        spans.append((False, (text or "")[cursor:]))
    if not spans:
        spans = [(False, text or "")]

    lines, line, line_width = [], [], 0.0

    def flush(force_empty=False):
        nonlocal line, line_width
        if line or force_empty:
            lines.append(line)
        line, line_width = [], 0.0

    for is_bold, span in spans:
        chosen_font = bold_font if is_bold else font
        paragraphs = span.split("\n")
        for paragraph_index, paragraph in enumerate(paragraphs):
            if paragraph_index:
                flush(force_empty=True)
            for word in paragraph.split():
                pieces = _wrap(word, chosen_font, max_width)
                for piece_index, piece in enumerate(pieces):
                    token = piece + (" " if piece_index == len(pieces) - 1 else "")
                    piece_width = _text_width(chosen_font, token)
                    if line and line_width + piece_width > max_width:
                        flush()
                    line.append((is_bold, token))
                    line_width += piece_width
    flush()
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


def render_design_layers(width, height, presentation, fields, before_image=None,
                         auto_position_video=False, video_fill_mode="panel", video_source=None):
    """Return (base, overlay, image_rect, overflow) for a professional template.

    ``base`` contains opaque panels and a static Before image where needed.
    ``overlay`` contains all typography and decoration. The main media remains
    its own layer and is painted into ``image_rect`` by the caller.
    """
    p = normalize_presentation(presentation)
    if auto_position_video and not p.get("text_layout"):
        p["text_position"] = "bottom"
    template = p["template"]
    w, h = max(2, int(width)), max(2, int(height))
    panel = p["panel_color"]
    accent = p["accent_color"]
    white = p["text_color"]
    layout = p.get("text_layout") or {
        "navy_gold": "below", "intro_outro": "below",
        "cinematic": "overlay", "lower_third": "overlay", "legacy": "overlay",
    }.get(template, "overlay")
    below_media = bool(auto_position_video or layout == "below")
    opacity = p.get("panel_opacity")
    panel_alpha = None if opacity is None else max(0, min(255, round(float(opacity) * 2.55)))
    width_pct = int(p.get("panel_width_pct") or 0)
    padding_pct = float(p.get("panel_padding_pct") or 0)
    min_height_pct = int(p.get("panel_min_height_pct") or 0)
    base = Image.new("RGB", (w, h), panel if template != "cinematic" else "#101010")
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rect = image_rect(template, w, h)
    x, y, rw, rh = rect
    # Keep safe areas generous enough for mobile UI overlays without wasting
    # the large blank bands the original design left around short captions.
    margin = max(12, int(min(w, h) * 0.0275))
    text_box = None
    logo_area = None

    if template == "navy_gold":
        pad = max(12, int(min(w, h) * .025),
                  int(min(w, h) * padding_pct / 100))
        logo_reserve = max(24, int(min(w, h) * .075)) if (
            p.get("logo_enabled") and p.get("logo_path") and os.path.isfile(p["logo_path"])) else 0
        probe = ImageDraw.Draw(Image.new("RGBA", (w, h)))
        _overflow, content_h, _content_w = _draw_content(
            probe, (0, 0, w - margin * 2, int(h * .45)), fields, p,
            accent, white, margin, measure_only=True)
        panel_h = min(int(h * .48), max(int(h * .12), content_h + 2 * pad + logo_reserve))
        if min_height_pct:
            panel_h = min(int(h * .85), max(panel_h, int(h * min_height_pct / 100)))
        if below_media:
            panel_y = h - panel_h
        elif p["text_position"] == "top":
            panel_y = 0
        elif p["text_position"] == "center":
            panel_y = max(0, (h - panel_h) // 2)
        else:
            panel_y = h - panel_h
        panel_x, panel_w = 0, w
        if 0 < width_pct < 100:
            panel_w = max(int(w * .2), int(w * width_pct / 100))
            panel_x = (w - panel_w) // 2
        if below_media:
            rect = (0, 0, w, h - panel_h)
        else:
            rect = (0, 0, w, h)
            alpha = (panel_alpha if panel_alpha is not None else 255)
            if alpha > 0:
                draw.rounded_rectangle(
                    (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
                    radius=max(8, margin // 2),
                    fill=_color_rgba(panel, alpha))
        divider_y = panel_h if panel_y == 0 else panel_y
        draw.rectangle((panel_x, divider_y, panel_x + panel_w,
                        min(h, divider_y + max(3, int(h * 0.004))),), fill=accent)
        text_box = (panel_x + pad, panel_y + pad,
                    max(0, panel_w - 2 * pad),
                    max(0, panel_h - 2 * pad - logo_reserve))
        logo_area = (panel_x, panel_y, panel_w, panel_h)
    elif template == "real_estate":
        pad = max(12, int(min(w, h) * .025))
        logo_reserve = max(24, int(min(w, h) * .075)) if (
            p.get("logo_enabled") and p.get("logo_path") and os.path.isfile(p["logo_path"])) else 0
        probe = ImageDraw.Draw(Image.new("RGBA", (w, h)))
        _overflow, content_h, _content_w = _draw_content(
            probe, (0, 0, w - margin * 2, int(h * .45)), fields, p,
            accent, white, margin, measure_only=True)
        panel_h = min(int(h * .48), max(int(h * .12), content_h + 2 * pad + logo_reserve))
        panel_y = 0 if p["text_position"] == "top" else h - panel_h
        image_y = panel_h if panel_y == 0 else 0
        rect = (0, image_y, w, h - panel_h)
        divider_y = panel_h if panel_y == 0 else panel_y
        draw.rectangle((0, divider_y, w, min(h, divider_y + max(4, int(h * 0.005))),),
                       fill=accent)
        text_box = (margin, panel_y + pad, w - margin * 2,
                    max(0, panel_h - 2 * pad - logo_reserve))
        logo_area = (0, panel_y, w, panel_h)
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
        alpha = (panel_alpha if panel_alpha is not None else
                 (178 if p["panel_style"] == "solid" else 132))
        top = int(h * 0.53)
        for gy in range(top, h):
            a = int(alpha * (gy - top) / max(1, h - top))
            draw.line((0, gy, w, gy), fill=_color_rgba(panel, a))
        box_w = int(w * width_pct / 100) if 0 < width_pct < 100 else w - margin * 2
        box_x = (w - box_w) // 2
        pad = max(0, int(min(w, h) * padding_pct / 100))
        text_box = (box_x + pad, int(h * 0.62) + pad,
                    max(1, box_w - pad * 2), max(1, int(h * 0.34) - pad * 2))
        if below_media:
            rect = (0, 0, w, int(h * 0.60))
    elif template == "lower_third":
        visible_text_keys = ("title", "subtitle", "description", "category", "location",
                             "price", "details", "cta", "business_name", "phone", "website")
        if any(str(fields.get(key, "")).strip() for key in visible_text_keys):
            content_width = max(1, w - margin * 2)
            content_limit = max(1, int(h * 0.70))
            probe = ImageDraw.Draw(Image.new("RGBA", (w, h)))
            _overflow, content_h, content_w = _draw_content(
                probe, (0, 0, content_width, content_limit), fields, p,
                accent, white, margin, measure_only=True)
            pad = max(14, int(min(w, h) * 0.026),
                      int(min(w, h) * padding_pct / 100))
            has_logo = bool(p.get("logo_enabled") and p.get("logo_path") and
                            os.path.isfile(p["logo_path"]))
            logo_reserve = max(24, int(min(w, h) * 0.075)) if has_logo else 0
            panel_h = min(h - margin * 2,
                          max(2 * pad + logo_reserve + 1, content_h + 2 * pad + logo_reserve))
            if min_height_pct:
                panel_h = min(h - margin * 2,
                              max(panel_h, int(h * min_height_pct / 100)))
            panel_w = min(w - margin * 2,
                          max(int(w * 0.22), int(content_w + 2 * pad)))
            if width_pct:
                panel_w = max(int(w * 0.2), min(w - margin * 2,
                                                int(w * width_pct / 100)))
            panel_x = (w - panel_w) // 2
            position = p.get("text_position", "bottom")
            if below_media:
                panel_y = h - panel_h - margin
            elif position == "top":
                panel_y = margin
            elif position == "center":
                panel_y = max(margin, (h - panel_h) // 2)
            else:
                panel_y = h - panel_h - margin
            alpha = (panel_alpha if panel_alpha is not None else
                     (205 if p["panel_style"] == "solid" else 145))
            draw.rounded_rectangle((panel_x, panel_y, panel_x + panel_w, panel_y + panel_h),
                                   radius=max(8, margin // 3),
                                   fill=_color_rgba(panel, alpha),
                                   outline=_color_rgba(accent, 220),
                                   width=max(1, int(h * 0.002)))
            text_box = (panel_x + pad, panel_y + pad,
                        max(1, panel_w - 2 * pad), max(1, content_h))
            logo_area = (panel_x, panel_y, panel_w, panel_h)
            if below_media:
                rect = (0, 0, w, max(2, panel_y))
    elif template == "intro_outro":
        draw.rectangle((0, 0, w, max(2, int(h * 0.018))), fill=accent)
        draw.rectangle((0, h - max(2, int(h * 0.018)), w, h), fill=accent)
        box_w = int(w * width_pct / 100) if 0 < width_pct < 100 else w - margin * 4
        box_x = (w - box_w) // 2
        pad = max(0, int(min(w, h) * padding_pct / 100))
        if below_media:
            text_box = (box_x + pad, y + rh + margin + pad,
                        max(1, box_w - pad * 2),
                        max(0, h - y - rh - margin * 2 - pad * 2))
        else:
            rect = (0, 0, w, h)
            text_box = (box_x + pad, int(h * 0.62) + pad,
                        max(1, box_w - pad * 2),
                        max(1, int(h * 0.34) - pad * 2))
        alpha = (panel_alpha if panel_alpha is not None else 0)
        if alpha > 0:
            draw.rounded_rectangle((text_box[0] - pad, text_box[1] - pad,
                                    text_box[0] + text_box[2] + pad,
                                    text_box[1] + text_box[3] + pad),
                                   radius=max(8, margin // 3),
                                   fill=_color_rgba(panel, alpha))
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

    if auto_position_video and rect[2] > 0 and rect[3] > 0:
        rx, ry, rw, rh = rect
        if video_fill_mode == "blur" and video_source is not None:
            fill = _fit_image(video_source, (rw, rh)).filter(
                ImageFilter.GaussianBlur(max(8, int(min(rw, rh) * .035))))
        else:
            fill = Image.new("RGB", (rw, rh), panel)
        base.paste(fill, (rx, ry))

    logo_bounds = logo_area or text_box
    if (text_box and p.get("logo_enabled") and p.get("logo_path") and
            os.path.isfile(p["logo_path"]) and template != "lower_third"):
        tx, ty, tw, th = text_box
        text_box = (tx, ty, tw, max(0, th - int(th * 0.15)))

    overflow = False
    if text_box:
        overflow = _draw_content(draw, text_box, fields, p, accent, white, margin)
    _place_logo(overlay, p, None,
                logo_bounds or (margin, margin, w - margin * 2, h - margin * 2), accent)
    return base, overlay, rect, overflow


def _draw_content(draw, box, fields, p, accent, white, margin, measure_only=False):
    x, y, bw, bh = box
    box_y = y
    if bw < 1 or bh < 1:
        return bool(any(fields.values()))
    family = p.get("font_family") or "Calibri"
    min_side = min(draw._image.size) if getattr(draw, "_image", None) else min(bw, bh)
    auto_title = max(22, min(96, int(min_side * 0.065)))
    title_size = (max(9, round(p["font_size"] * min_side / 1080))
                  if p["font_size"] else auto_title)
    title = fields.get("title", "") or ""
    subtitle = fields.get("subtitle", "") or ""
    description = fields.get("description", "") or ""
    metadata = [fields.get(k, "") for k in ("location", "price", "details") if fields.get(k)]
    business = fields.get("business_name", "") or ""
    contact = "  •  ".join(v for v in (fields.get("phone", ""), fields.get("website", "")) if v)
    category = fields.get("category", "")
    if p["template"] == "navy_gold":
        category = ((p["featured_text"] or category) if p["featured_enabled"] else "")
    cta = fields.get("cta", "") or ""
    scale = 1.0
    parts = []
    for _ in range(18):
        parts = []
        cursor = y
        if category:
            size = max(10, int(min_side * .021 * scale))
            font = _font(family, size, True)
            lines = _wrap(category, font, bw)
            parts.append(("category", lines, font, accent, size + 3))
            cursor += len(lines) * (size + 3) + max(4, margin // 5)
        if title:
            size = max(9, int(title_size * scale))
            font = _font(family, size, True)
            lines = _wrap_rich(title, font, family, bw)
            parts.append(("title", lines, font, white, int(size * 1.15)))
            cursor += len(lines) * int(size * 1.15) + max(3, margin // 6)
        if subtitle:
            size = max(9, int(title_size * .52 * scale))
            font = _font(family, size, False)
            lines = _wrap_rich(subtitle, font, family, bw)
            parts.append(("subtitle", lines, font, white, int(size * 1.22)))
            cursor += len(lines) * int(size * 1.22) + max(3, margin // 7)
        for value in metadata:
            size = max(9, int(title_size * .42 * scale))
            font = _font(family, size, True)
            lines = _wrap_rich(value, font, family, bw)
            parts.append(("metadata", lines, font, accent if value in (fields.get("location"), fields.get("price")) else white, int(size * 1.2)))
            cursor += len(lines) * int(size * 1.2) + max(2, margin // 8)
        if description:
            size = max(8, int(title_size * .36 * scale))
            font = _font(family, size, False)
            lines = _wrap_rich(description, font, family, bw)
            parts.append(("description", lines, font, white, int(size * 1.3)))
            cursor += len(lines) * int(size * 1.3) + max(2, margin // 8)
        if cta:
            size = max(9, int(title_size * .37 * scale))
            font = _font(family, size, True)
            lines = _wrap_rich(cta, font, family, bw)
            parts.append(("cta", lines, font, accent, int(size * 1.25)))
            cursor += len(lines) * int(size * 1.25) + max(2, margin // 8)
        if business or contact:
            size = max(8, int(title_size * .25 * scale))
            font = _font(family, size, False)
            footer = "  •  ".join(v for v in (business, contact) if v)
            lines = _wrap_rich(footer, font, family, bw)
            parts.append(("footer", lines, font, white, int(size * 1.2)))
            cursor += len(lines) * int(size * 1.2)
        if cursor <= y + bh:
            break
        scale *= .86
    overflow = bool(parts and cursor > y + bh)
    content_height = max(0, cursor - y)
    max_line_width = max((int(_line_width(line, font, family))
                          for _name, lines, font, _color, _line_h in parts
                          for line in lines), default=0)
    if measure_only:
        return overflow, content_height, max_line_width
    position = p.get("text_position", "bottom")
    if position == "center":
        y = box_y + max(0, (bh - content_height) // 2)
    elif position == "bottom":
        y = box_y + max(0, bh - content_height)
    else:
        y = box_y
    cursor = y
    text_align = p["text_align"]

    def aligned_x(line_width):
        if text_align == "center":
            return x + max(0, (bw - line_width) // 2)
        if text_align == "right":
            return x + max(0, bw - line_width)
        return x

    for name, lines, font, color, line_h in parts:
        if name == "category" and p["template"] == "navy_gold":
            line = lines[0] if lines else ""
            line_width = int(_line_width(line, font, family))
            category_x = aligned_x(line_width + 16)
            draw.rounded_rectangle((category_x, cursor,
                                    category_x + max(1, line_width + 16), cursor + line_h + 5),
                                   radius=max(2, line_h // 4), fill=_color_rgba(accent, 36),
                                   outline=_color_rgba(accent, 170), width=1)
            draw.text((category_x + 8, cursor + 2), line, font=font, fill=color)
            cursor += line_h + max(7, margin // 5)
            continue
        stroke_width = (max(1, round(getattr(font, "size", 12) * .035))
                        if p["template"] == "cinematic" else 0)
        for line in lines:
            line_x = aligned_x(int(_line_width(line, font, family)))
            if isinstance(line, str):
                draw.text((line_x, cursor), line, font=font, fill=color,
                          stroke_width=stroke_width,
                          stroke_fill="#000000" if stroke_width else None)
            else:
                text_x = line_x
                bold_font = _font(family, getattr(font, "size", 12), True)
                for is_bold, segment in line:
                    segment_font = bold_font if is_bold else font
                    draw.text((text_x, cursor), segment, font=segment_font, fill=color,
                              stroke_width=stroke_width,
                              stroke_fill="#000000" if stroke_width else None)
                    text_x += _text_width(segment_font, segment)
            cursor += line_h
        cursor += max(2, margin // 8)
    return overflow


def compose_design_frame(source, width, height, presentation, fields, before_image=None,
                         auto_position_video=False, video_fill_mode="panel"):
    """Compose one actual media frame using the same reusable template layers."""
    base, overlay, rect, overflow = render_design_layers(
        width, height, presentation, fields, before_image=before_image,
        auto_position_video=auto_position_video, video_fill_mode=video_fill_mode,
        video_source=source if auto_position_video else None)
    result = base.copy()
    x, y, rw, rh = rect
    if source is not None and rw > 0 and rh > 0:
        fitted = (_contain_image(source, (rw, rh)) if auto_position_video else
                  _fit_image(source, (rw, rh)))
        px = x + max(0, (rw - fitted.width) // 2)
        py = (y if auto_position_video else
              y + max(0, (rh - fitted.height) // 2))
        result.paste(fitted, (px, py))
    result = Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")
    return result, overflow
