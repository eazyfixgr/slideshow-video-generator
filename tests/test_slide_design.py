import json
import unittest

from PIL import Image

from slideshow.slide_design import (
    TEMPLATES,
    _font,
    _wrap_rich,
    compose_design_frame,
    image_rect,
    legacy_text,
    normalize_presentation,
    presentation_fields,
    render_design_layers,
)
from slideshow.media_edit import MediaEditMixin
from slideshow.export import ExportMixin
from slideshow.render import RenderMixin
from slideshow.app import SlideshowApp


class PresentationModelTests(unittest.TestCase):
    def test_legacy_project_keeps_global_text_behavior(self):
        old_project_edit = {"crop": None, "brightness": 1.0, "color": 1.0}
        presentation = normalize_presentation(old_project_edit.get("presentation"))
        self.assertEqual(presentation["mode"], "global")
        self.assertEqual(presentation["template"], "project")
        self.assertEqual(legacy_text(presentation, "Πωλείται\nΔιαμέρισμα"),
                         "Πωλείται\nΔιαμέρισμα")
        self.assertTrue(presentation["scene_id"])

    def test_custom_text_does_not_replace_other_global_text(self):
        custom = normalize_presentation({
            "mode": "custom", "title": "Διαμέρισμα", "description": "Κοντά στο μετρό",
            "template": "navy_gold",
        })
        fields = presentation_fields(custom, "Κοινό κείμενο")
        self.assertEqual(fields["title"], "Διαμέρισμα")
        self.assertEqual(fields["description"], "Κοντά στο μετρό")
        self.assertEqual(legacy_text(custom, "Κοινό κείμενο"), "Διαμέρισμα\nΚοντά στο μετρό")

    def test_global_multiline_copy_uses_one_body_scale(self):
        fields = presentation_fields(normalize_presentation(), "Μεγάλη πρώτη γραμμή\nΜικρότερη τελευταία γραμμή")
        self.assertEqual(fields["title"], "")
        self.assertEqual(fields["description"], "Μεγάλη πρώτη γραμμή\nΜικρότερη τελευταία γραμμή")

    def test_invalid_values_are_safely_normalized(self):
        presentation = normalize_presentation({
            "mode": "unexpected", "template": "missing", "duration": "999",
            "transition": "bad;ffmpeg-command", "text_color": "red",
        })
        self.assertEqual(presentation["mode"], "global")
        self.assertEqual(presentation["template"], "project")
        self.assertEqual(presentation["duration"], 30.0)
        self.assertEqual(presentation["transition"], "global")
        self.assertEqual(presentation["text_color"], "#FFFFFF")

    def test_presentation_round_trips_as_project_json(self):
        presentation = normalize_presentation({
            "mode": "custom", "template": "real_estate", "title": "Ακίνητο",
            "duration": 7.5, "transition": "fadeblack", "transition_duration": 1.2,
        })
        encoded = json.dumps({"media_files": [["image", "photo.jpg", {
            "presentation": presentation,
        }]]}, ensure_ascii=False)
        restored = json.loads(encoded)["media_files"][0][2]["presentation"]
        self.assertEqual(restored["scene_id"], presentation["scene_id"])
        self.assertEqual(restored["title"], "Ακίνητο")
        self.assertEqual(restored["duration"], 7.5)

    def test_legacy_media_normalization_adds_stable_scene_id(self):
        old_item = MediaEditMixin.normalize_item(["image", "photo.jpg", {"crop": None}])
        first_id = old_item[2]["presentation"]["scene_id"]
        saved = json.loads(json.dumps(old_item, ensure_ascii=False))
        loaded = MediaEditMixin.normalize_item(saved)
        self.assertEqual(loaded[2]["presentation"]["scene_id"], first_id)

    def test_combined_mode_adds_global_text_once(self):
        presentation = normalize_presentation({
            "mode": "combine", "title": "Μοναδικός τίτλος", "description": "Κείμενο slide",
        })
        fields = presentation_fields(presentation, "Επωνυμία\nΤηλέφωνο")
        self.assertEqual(fields["title"], "Μοναδικός τίτλος")
        self.assertEqual(fields["description"], "Κείμενο slide\nΕπωνυμία\nΤηλέφωνο")

    def test_markdown_bold_wraps_without_leaking_asterisks(self):
        lines = _wrap_rich("Κανονικό **έντονο κείμενο**\nΤελευταία γραμμή",
                           _font("Calibri", 18), "Calibri", 260)
        segments = [segment for line in lines for segment in line]
        self.assertTrue(any(is_bold for is_bold, _text in segments))
        self.assertNotIn("**", "".join(text for _is_bold, text in segments))
        self.assertGreaterEqual(len(lines), 2)

    def test_audio_offsets_match_mixed_transition_overlaps(self):
        offsets = ExportMixin._clip_offsets(
            None, [2.0, 3.0, 4.0], transitions=[("none", 0.0), ("fade", 0.5), ("none", 0.0)])
        self.assertEqual(offsets, [0.0, 1.5, 4.5])

    def test_project_template_is_inherited_unless_slide_overrides_it(self):
        class ProjectRenderer(RenderMixin):
            project_template = "navy_gold"

        inherited = ProjectRenderer._presentation_for(
            object.__new__(ProjectRenderer), {"presentation": normalize_presentation()})
        explicit = ProjectRenderer._presentation_for(
            object.__new__(ProjectRenderer), {
                "presentation": normalize_presentation({"template": "real_estate"})})
        self.assertEqual(inherited["template"], "navy_gold")
        self.assertEqual(explicit["template"], "real_estate")

        renderer = object.__new__(ProjectRenderer)
        stored = normalize_presentation({"scene_id": "slide-1", "template": "legacy"})
        renderer._presentation_preview_drafts = {
            "slide-1": normalize_presentation({"scene_id": "slide-1", "template": "navy_gold"})
        }
        live = ProjectRenderer._presentation_for(renderer, {"presentation": stored})
        self.assertEqual(live["template"], "navy_gold")

    def test_project_caption_strategy_selects_shared_or_media_type_text(self):
        class CaptionRenderer(RenderMixin):
            project_caption_mode = "all"
            project_text_all = "Shared"
            project_text_videos = "Video"
            project_text_photos = "Photo"

        app = object.__new__(CaptionRenderer)
        self.assertEqual(app.get_text_for("image"), "Shared")
        self.assertEqual(app.get_text_for("video"), "Shared")
        app.project_caption_mode = "by_type"
        self.assertEqual(app.get_text_for("image"), "Photo")
        self.assertEqual(app.get_text_for("video"), "Video")
        app.project_text_photos = ""
        self.assertEqual(app.get_text_for("image"), "")

    def test_legacy_project_settings_are_not_silently_overridden(self):
        self.assertEqual(SlideshowApp._normalize_project_settings({}), {})
        normalized = SlideshowApp._normalize_project_settings({
            "resolution": "invalid", "slide_duration": 999,
            "transition_effect": "random", "transition_duration": 0.05,
        })
        self.assertEqual(normalized["slide_duration"], 30)
        self.assertEqual(normalized["transition_effect"], "random")
        self.assertEqual(normalized["transition_duration"], 0.2)
        self.assertNotIn("resolution", normalized)

    def test_old_caption_text_loads_even_when_new_project_metadata_exists(self):
        video, photo, mode, shared = SlideshowApp._project_caption_values({
            "project_template": "navy_gold",
            "project_settings": {"resolution": "1080x1920"},
            "text_videos": "Old shared caption",
            "text_photos": "",
        })
        self.assertEqual(video, "Old shared caption")
        self.assertEqual(photo, "")
        self.assertEqual(mode, "all")
        self.assertEqual(shared, "Old shared caption")


class TemplateRendererTests(unittest.TestCase):
    def test_templates_render_at_portrait_landscape_and_square_sizes(self):
        source = Image.new("RGB", (1200, 800), "#6789AB")
        before = Image.new("RGB", (800, 1200), "#345678")
        fields = {
            "title": "Πολυτελής κατοικία",
            "subtitle": "Νέος Κόσμος",
            "description": "Φωτεινό ακίνητο κοντά σε μέσα μεταφοράς και αγορά.",
            "category": "ΠΡΟΣ ΠΩΛΗΣΗ",
            "location": "Αθήνα",
            "price": "€250.000",
            "details": "3 υπνοδωμάτια • 2 μπάνια",
            "cta": "Κλείστε ραντεβού",
            "business_name": "Τεχνικό Γραφείο",
            "phone": "210 1234567",
            "website": "example.gr",
            "before_label": "BEFORE",
            "after_label": "AFTER",
        }
        for template in TEMPLATES:
            if template == "legacy":
                continue
            presentation = normalize_presentation({"template": template, "mode": "custom"})
            for size in ((1080, 1920), (1920, 1080), (1080, 1080)):
                with self.subTest(template=template, size=size):
                    frame, overflow = compose_design_frame(
                        source, *size, presentation, fields, before_image=before)
                    self.assertEqual(frame.size, size)
                    self.assertEqual(frame.mode, "RGB")
                    rect = image_rect(template, *size)
                    self.assertGreater(rect[2], 0)
                    self.assertGreater(rect[3], 0)
                    self.assertLessEqual(rect[0] + rect[2], size[0])
                    self.assertLessEqual(rect[1] + rect[3], size[1])
                    self.assertIsInstance(overflow, bool)

    def test_extremely_long_content_is_reported_as_overflow(self):
        source = Image.new("RGB", (320, 240), "#456789")
        fields = {"title": "Listing", "description": "X" * 12000}
        presentation = normalize_presentation({"template": "lower_third", "mode": "custom"})
        frame, overflow = compose_design_frame(source, 360, 640, presentation, fields)
        self.assertEqual(frame.size, (360, 640))
        self.assertTrue(overflow)

    def test_lower_third_panel_fits_short_text_and_moves_top_or_bottom(self):
        fields = {"title": "Short title"}
        template = {"template": "lower_third", "mode": "custom"}
        _, bottom_overlay, _, _ = render_design_layers(
            360, 640, normalize_presentation(template), fields)
        bottom_box = bottom_overlay.getchannel("A").getbbox()
        self.assertIsNotNone(bottom_box)
        self.assertLess(bottom_box[2] - bottom_box[0], 300)
        self.assertLess(bottom_box[3] - bottom_box[1], 210)

        template["text_position"] = "top"
        _, top_overlay, _, _ = render_design_layers(
            360, 640, normalize_presentation(template), fields)
        top_box = top_overlay.getchannel("A").getbbox()
        self.assertIsNotNone(top_box)
        self.assertLess(top_box[1], 80)

    def test_navy_gold_gives_more_photo_area_to_short_copy(self):
        presentation = normalize_presentation({"template": "navy_gold", "mode": "custom"})
        short = {"title": "Short title", "description": "One short sentence."}
        long = {"title": "Property overview", "description": "A detailed property description. " * 70}
        _base, _overlay, short_rect, _overflow = render_design_layers(
            720, 1280, presentation, short)
        _base, _overlay, long_rect, _overflow = render_design_layers(
            720, 1280, presentation, long)
        self.assertGreater(short_rect[3], long_rect[3])


if __name__ == "__main__":
    unittest.main()
