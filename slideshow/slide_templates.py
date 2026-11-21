"""Live template styles, editable defaults and per-slide override resolution."""

import copy
import re

from .design_templates import read_design_templates
from .slide_design import (DEFAULT_PRESENTATION, INHERIT_TEMPLATE, TEMPLATES,
                           normalize_template)

REGISTRY_KEY = "slide_templates"
DEFAULT_KEY = "slideshow_default_template"
VERSION_KEY = "slide_template_registry_version"

STYLE_FIELDS = (
    "text_position", "text_align", "font_family", "font_size", "text_color",
    "panel_color", "accent_color", "panel_style", "panel_opacity",
    "panel_width_pct", "panel_padding_pct", "panel_min_height_pct",
    "text_layout",
)
STYLE_FIELD_LABELS = {
    "text_position": "Θέση κειμένου",
    "text_align": "Στοίχιση κειμένου",
    "font_family": "Γραμματοσειρά",
    "font_size": "Μέγεθος γραμματοσειράς",
    "text_color": "Χρώμα κειμένου",
    "panel_color": "Χρώμα πλαισίου",
    "accent_color": "Χρώμα έμφασης",
    "panel_style": "Στυλ πλαισίου",
    "panel_opacity": "Διαφάνεια πλαισίου",
    "panel_width_pct": "Πλάτος πλαισίου (%)",
    "panel_padding_pct": "Εσωτερικό padding (%)",
    "panel_min_height_pct": "Ελάχιστο ύψος πλαισίου (%)",
    "text_layout": "Τοποθέτηση κειμένου",
}
FONT_CHOICES = ("", "Calibri", "Arial", "Verdana", "Georgia")
TEXT_POSITION_CHOICES = {"Πάνω": "top", "Κέντρο": "center", "Κάτω": "bottom"}
TEXT_ALIGN_CHOICES = {"Αριστερά": "left", "Κέντρο": "center", "Δεξιά": "right"}
PANEL_STYLE_CHOICES = {"Συμπαγές": "solid", "Ημιδιαφανές": "translucent"}
TEXT_LAYOUT_CHOICES = {"Πάνω από το media (overlay)": "overlay",
                       "Κάτω από το media (below)": "below"}

BUILTIN_STYLES = {
    "legacy": {
        "text_position": "bottom", "text_align": "center",
        "font_family": "Calibri", "font_size": 32,
        "text_color": "#000000", "panel_color": "#FFFFFF",
        "accent_color": "#D6B86A", "panel_style": "solid",
        "panel_opacity": 100, "panel_width_pct": 0,
        "panel_padding_pct": 0, "panel_min_height_pct": 0,
        "text_layout": "overlay",
    },
    "navy_gold": {
        "text_position": "bottom", "text_align": "center",
        "font_family": "Calibri", "font_size": 85,
        "text_color": "#FFFFFF", "panel_color": "#111B2B",
        "accent_color": "#D6B86A", "panel_style": "solid",
        "panel_opacity": 100, "panel_width_pct": 100,
        "panel_padding_pct": 0, "panel_min_height_pct": 0,
        "text_layout": "below",
    },
    "cinematic": {
        "text_position": "bottom", "text_align": "center",
        "font_family": "Calibri", "font_size": 90,
        "text_color": "#FFFFFF", "panel_color": "#000000",
        "accent_color": "#D6B86A", "panel_style": "translucent",
        "panel_opacity": 70, "panel_width_pct": 100,
        "panel_padding_pct": 0, "panel_min_height_pct": 0,
        "text_layout": "overlay",
    },
    "lower_third": {
        "text_position": "bottom", "text_align": "center",
        "font_family": "Calibri", "font_size": 90,
        "text_color": "#FFFFFF", "panel_color": "#0C131D",
        "accent_color": "#D6B86A", "panel_style": "translucent",
        "panel_opacity": 80, "panel_width_pct": 0,
        "panel_padding_pct": 0, "panel_min_height_pct": 0,
        "text_layout": "overlay",
    },
    "intro_outro": {
        "text_position": "bottom", "text_align": "center",
        "font_family": "Calibri", "font_size": 90,
        "text_color": "#FFFFFF", "panel_color": "#111B2B",
        "accent_color": "#D6B86A", "panel_style": "solid",
        "panel_opacity": 0, "panel_width_pct": 0,
        "panel_padding_pct": 0, "panel_min_height_pct": 0,
        "text_layout": "below",
    },
}
# Values used by the pre-template-era renderer. They tell the migration which
# old presentation fields were real user choices and which were defaults.
LEGACY_STYLE_DEFAULTS = {
    "text_position": "bottom", "text_align": "center", "font_family": "",
    "text_color": "#FFFFFF", "panel_color": "#111B2B",
    "accent_color": "#D6B86A", "panel_style": "solid",
}
LABEL_FOR_BASE = {key: label for key, label in TEMPLATES.items()}
BASE_FOR_LABEL = {label: key for key, label in TEMPLATES.items()}


def _clamp_int(value, low, high, fallback):
    try:
        return max(low, min(high, int(float(value))))
    except (TypeError, ValueError):
        return fallback


def _clamp_float(value, low, high, fallback):
    try:
        return round(max(low, min(high, float(value))), 2)
    except (TypeError, ValueError):
        return fallback


def _valid_color(value, fallback):
    value = str(value or fallback)
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def normalize_style(base, value=None):
    """Return one complete, validated style dictionary."""
    base = normalize_template(base, "legacy")
    if base not in BUILTIN_STYLES:
        base = "legacy"
    defaults = BUILTIN_STYLES[base]
    source = value if isinstance(value, dict) else {}
    style = copy.deepcopy(defaults)
    for key in STYLE_FIELDS:
        if key in source:
            style[key] = source[key]
    style["font_family"] = str(style.get("font_family") or "")
    if style["font_family"] not in FONT_CHOICES:
        style["font_family"] = defaults["font_family"]
    style["font_size"] = _clamp_int(style.get("font_size"), 4, 400,
                                    defaults["font_size"])
    for key in ("text_color", "panel_color", "accent_color"):
        style[key] = _valid_color(style.get(key), defaults[key])
    style["text_position"] = (style.get("text_position")
                              if style.get("text_position") in ("top", "center", "bottom")
                              else defaults["text_position"])
    style["text_align"] = (style.get("text_align")
                           if style.get("text_align") in ("left", "center", "right")
                           else defaults["text_align"])
    if style.get("panel_style") not in ("solid", "translucent"):
        style["panel_style"] = defaults["panel_style"]
    style["panel_opacity"] = _clamp_int(style.get("panel_opacity"), 0, 100,
                                        defaults["panel_opacity"])
    style["panel_width_pct"] = _clamp_int(style.get("panel_width_pct"), 0, 100,
                                          defaults["panel_width_pct"])
    style["panel_padding_pct"] = _clamp_float(
        style.get("panel_padding_pct"), 0, 15, defaults["panel_padding_pct"])
    style["panel_min_height_pct"] = _clamp_int(
        style.get("panel_min_height_pct"), 0, 80, defaults["panel_min_height_pct"])
    if style.get("text_layout") not in ("overlay", "below"):
        style["text_layout"] = defaults["text_layout"]
    return {key: style[key] for key in STYLE_FIELDS}


def _unique_custom_name(name, reserved):
    name = str(name or "").strip()
    if not name:
        name = "Custom template"
    candidate = name
    index = 2
    while candidate in reserved:
        candidate = f"{name} {index}"
        index += 1
    return candidate


def _style_from_old_template(value):
    base = normalize_template(value.get("template", "legacy"), "legacy")
    style = normalize_style(base, value)
    return base, style


def ensure_template_settings(settings, legacy_font_size=None, legacy_font_family=None,
                             legacy_text_style=None):
    """Create the registry once and migrate old named presets/global text choices."""
    if settings.get(VERSION_KEY) == 1:
        return False
    registry = {}
    reserved = set(BASE_FOR_LABEL)
    for name, value in read_design_templates(settings).items():
        if not isinstance(value, dict):
            continue
        base, style = _style_from_old_template(value)
        custom_name = _unique_custom_name(name, reserved)
        reserved.add(custom_name)
        registry[custom_name] = {
            "base": base, "builtin": False, "style": style,
        }

    legacy_style = normalize_style("legacy")
    changed = False
    if legacy_font_size is not None:
        try:
            value = max(4, min(400, int(legacy_font_size)))
        except (TypeError, ValueError):
            value = None
        if value and value != legacy_style["font_size"]:
            legacy_style["font_size"] = value
            changed = True
    if legacy_font_family and legacy_font_family in FONT_CHOICES:
        if legacy_font_family != legacy_style["font_family"]:
            legacy_style["font_family"] = legacy_font_family
            changed = True
    if legacy_text_style and legacy_text_style != "black_box":
        legacy_style["panel_opacity"] = 0
        legacy_style["text_color"] = "#FFFFFF"
        changed = True
    if changed:
        registry[LABEL_FOR_BASE["legacy"]] = {
            "base": "legacy", "builtin": True, "style": legacy_style,
        }

    current_base = normalize_template(settings.get("last_caption_template", "legacy"),
                                      "legacy")
    default_name = settings.get(DEFAULT_KEY)
    if default_name not in BASE_FOR_LABEL and default_name not in registry:
        default_name = LABEL_FOR_BASE.get(current_base, LABEL_FOR_BASE["legacy"])
    settings[REGISTRY_KEY] = registry
    settings[DEFAULT_KEY] = default_name
    settings[VERSION_KEY] = 1
    return True


def read_template_registry(settings):
    """Return ordered entries: name -> {base, builtin, style, label}."""
    registry = {}
    for key, label in TEMPLATES.items():
        registry[label] = {
            "base": key, "builtin": True, "style": normalize_style(key),
            "label": label,
        }
    stored = settings.get(REGISTRY_KEY, {})
    if not isinstance(stored, dict):
        stored = {}
    for name, entry in stored.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(entry, dict):
            continue
        name = name.strip()
        builtin = bool(entry.get("builtin"))
        base = normalize_template(entry.get("base", "legacy"), "legacy")
        if builtin and name in registry:
            base = registry[name]["base"]
            registry[name]["style"] = normalize_style(base, entry.get("style"))
        elif not builtin and name not in BASE_FOR_LABEL:
            registry[name] = {
                "base": base, "builtin": False,
                "style": normalize_style(base, entry.get("style")),
                "label": name,
            }
    return registry


def default_template_name(settings, registry=None):
    registry = registry or read_template_registry(settings)
    name = settings.get(DEFAULT_KEY)
    if name in registry:
        return name
    legacy = settings.get("last_caption_template", "legacy")
    label = LABEL_FOR_BASE.get(normalize_template(legacy, "legacy"))
    if label in registry:
        return label
    return next(iter(registry), LABEL_FOR_BASE["legacy"])


def template_base(name, registry):
    entry = registry.get(name)
    return entry["base"] if entry else "legacy"


def template_style(name, registry):
    entry = registry.get(name)
    return copy.deepcopy(entry["style"]) if entry else normalize_style("legacy")


def legacy_style_overrides(presentation, base):
    """Work out which old style fields were genuine user overrides."""
    if isinstance(presentation.get("style_overrides"), list):
        return list(presentation["style_overrides"])
    if base == "legacy":
        return []
    source = presentation if isinstance(presentation, dict) else {}
    old_size = 85 if base == "navy_gold" else 90
    defaults = dict(LEGACY_STYLE_DEFAULTS)
    defaults["font_size"] = old_size
    overrides = []
    for key, fallback in defaults.items():
        if key not in source:
            continue
        value = source[key]
        if value != fallback:
            overrides.append(key)
    return overrides


def resolve_presentation(presentation, project_base, project_name, default_name,
                         registry):
    """Merge the selected live template with per-slide explicit overrides."""
    p = copy.deepcopy(presentation) if isinstance(presentation, dict) else {}
    base = normalize_template(p.get("template", INHERIT_TEMPLATE),
                              INHERIT_TEMPLATE)
    name = str(p.get("template_name") or "").strip()
    if not name:
        if base not in (INHERIT_TEMPLATE, "project"):
            name = LABEL_FOR_BASE.get(base, "")
        else:
            name = project_name or default_name
    if name not in registry:
        name = default_name if default_name in registry else next(iter(registry), "")
    if name not in registry:
        resolved = dict(DEFAULT_PRESENTATION)
        resolved.update(p)
        return resolved
    entry = registry[name]
    resolved_base = entry["base"]
    style = copy.deepcopy(entry["style"])
    overrides = p.get("style_overrides")
    if not isinstance(overrides, list):
        legacy_base = normalize_template(base, "legacy")
        if legacy_base == INHERIT_TEMPLATE:
            legacy_base = normalize_template(project_base, "legacy")
        overrides = legacy_style_overrides(p, legacy_base)
    for key in overrides:
        if key in STYLE_FIELDS and key in p:
            style[key] = p[key]
    resolved = copy.deepcopy(p)
    resolved["template"] = resolved_base
    resolved["template_name"] = name
    resolved["style_overrides"] = [key for key in overrides if key in STYLE_FIELDS]
    resolved.update(style)
    return resolved
