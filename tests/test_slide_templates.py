"""Pure tests for live template styles and override resolution."""

import unittest

from slideshow.slide_design import INHERIT_TEMPLATE, normalize_presentation
from slideshow.slide_templates import (DEFAULT_KEY, REGISTRY_KEY, VERSION_KEY,
                                       ensure_template_settings, normalize_style,
                                       read_template_registry, resolve_presentation,
                                       legacy_style_overrides)


class TemplateRegistryTests(unittest.TestCase):
    def test_first_run_creates_generic_default_and_migrates_legacy_font(self):
        settings = {
            "font_size": 44, "font_family": "Arial", "text_style": "black_box",
            "last_caption_template": "navy_gold",
        }
        self.assertTrue(ensure_template_settings(
            settings, legacy_font_size=44, legacy_font_family="Arial",
            legacy_text_style="black_box"))
        self.assertEqual(settings[VERSION_KEY], 1)
        self.assertEqual(settings[DEFAULT_KEY], "Elegant Navy & Gold")
        registry = read_template_registry(settings)
        self.assertEqual(registry["Απλό"]["style"]["font_size"], 44)
        self.assertEqual(registry["Απλό"]["style"]["font_family"], "Arial")

    def test_old_named_presets_become_custom_templates(self):
        settings = {
            "last_caption_template": "legacy",
            "slide_design_templates": {
                "My Look": {
                    "template": "lower_third", "font_size": 77,
                    "text_color": "#123456", "panel_color": "#0A0B0C",
                    "accent_color": "#ABCDEF", "text_position": "top",
                    "text_align": "left", "font_family": "Georgia",
                    "panel_style": "translucent",
                }
            },
        }
        ensure_template_settings(settings)
        registry = read_template_registry(settings)
        self.assertIn("My Look", registry)
        self.assertFalse(registry["My Look"]["builtin"])
        self.assertEqual(registry["My Look"]["base"], "lower_third")
        self.assertEqual(registry["My Look"]["style"]["font_size"], 77)

    def test_live_builtin_override_updates_every_slide_without_overrides(self):
        settings = {"last_caption_template": "navy_gold"}
        ensure_template_settings(settings)
        settings[REGISTRY_KEY]["Elegant Navy & Gold"] = {
            "base": "navy_gold", "builtin": True,
            "style": dict(normalize_style("navy_gold"), font_size=120),
        }
        registry = read_template_registry(settings)
        resolved = resolve_presentation(
            {"template": INHERIT_TEMPLATE, "style_overrides": []},
            "navy_gold", "", "Elegant Navy & Gold", registry)
        self.assertEqual(resolved["template"], "navy_gold")
        self.assertEqual(resolved["font_size"], 120)
        self.assertEqual(resolved["template_name"], "Elegant Navy & Gold")

    def test_explicit_slide_override_wins_over_template(self):
        settings = {"last_caption_template": "cinematic"}
        ensure_template_settings(settings)
        registry = read_template_registry(settings)
        resolved = resolve_presentation(
            {"template": INHERIT_TEMPLATE, "style_overrides": ["font_size"],
             "font_size": 33},
            "cinematic", "", "Υπότιτλος", registry)
        self.assertEqual(resolved["font_size"], 33)
        self.assertEqual(resolved["template"], "cinematic")

    def test_custom_template_resolves_to_its_base(self):
        settings = {"last_caption_template": "legacy"}
        ensure_template_settings(settings)
        settings[REGISTRY_KEY]["Bright"] = {
            "base": "lower_third", "builtin": False,
            "style": dict(normalize_style("lower_third"), text_color="#00FF00"),
        }
        registry = read_template_registry(settings)
        resolved = resolve_presentation(
            {"template": "lower_third", "template_name": "Bright",
             "style_overrides": []},
            "legacy", "", "Απλό", registry)
        self.assertEqual(resolved["template"], "lower_third")
        self.assertEqual(resolved["template_name"], "Bright")
        self.assertEqual(resolved["text_color"], "#00FF00")

    def test_old_style_values_only_become_overrides_when_different(self):
        presentation = {
            "template": "navy_gold", "font_size": 85, "font_family": "",
            "text_color": "#FFFFFF", "panel_color": "#111B2B",
            "accent_color": "#D6B86A", "text_position": "bottom",
            "text_align": "center", "panel_style": "solid",
        }
        self.assertEqual(legacy_style_overrides(presentation, "navy_gold"), [])
        presentation["font_size"] = 111
        self.assertEqual(legacy_style_overrides(presentation, "navy_gold"),
                         ["font_size"])

    def test_presentation_normalizes_new_style_fields(self):
        presentation = normalize_presentation({
            "template": "navy_gold", "template_name": "My template",
            "style_overrides": ["font_size", "font_size"],
            "text_layout": "below", "panel_opacity": 42,
            "panel_width_pct": 60, "panel_padding_pct": 2.5,
            "panel_min_height_pct": 12,
        })
        self.assertEqual(presentation["template_name"], "My template")
        self.assertEqual(presentation["style_overrides"], ["font_size", "font_size"])
        self.assertEqual(presentation["text_layout"], "below")
        self.assertEqual(presentation["panel_opacity"], 42)
        self.assertEqual(presentation["panel_width_pct"], 60)
        self.assertEqual(presentation["panel_padding_pct"], 2.5)
        self.assertEqual(presentation["panel_min_height_pct"], 12)


if __name__ == "__main__":
    unittest.main()
