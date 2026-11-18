"""Persistence helpers for named, reusable slide-design templates."""

import copy

from .slide_design import DESIGN_FIELDS, normalize_presentation


def read_design_templates(settings):
    """Read named templates and include templates saved by the old preset UI."""
    merged = {}
    for key in ("slide_design_presets", "slide_design_templates"):
        values = settings.get(key, {})
        if isinstance(values, dict):
            merged.update({name: value for name, value in values.items()
                           if isinstance(name, str) and isinstance(value, dict)})
    return {
        name: {field: copy.deepcopy(normalize_presentation(value)[field])
               for field in DESIGN_FIELDS}
        for name, value in merged.items()
    }


def write_design_templates(settings, templates):
    """Save validated user-created templates without touching older settings."""
    cleaned = {}
    for name, value in templates.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(value, dict):
            continue
        presentation = normalize_presentation(value)
        cleaned[name.strip()] = {field: copy.deepcopy(presentation[field])
                                 for field in DESIGN_FIELDS}
    settings["slide_design_templates"] = cleaned
    return cleaned
