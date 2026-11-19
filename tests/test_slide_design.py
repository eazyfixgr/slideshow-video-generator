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
from slideshow.deps import np
from slideshow.design_templates import (design_template_choices, read_design_templates,
                                        write_design_templates)


class PresentationModelTests(unittest.TestCase):
    def test_main_window_starts_maximized_and_keeps_saved_geometry(self):
        class Root:
            geometry_value = None
            state_value = None

            def geometry(self, value):
                self.geometry_value = value

            def state(self, value):
                self.state_value = value

        app = object.__new__(SlideshowApp)
        app.root = Root()
        app.settings = {"window_geometry": "1550x950+10+20"}
        app._restore_window_state()
        self.assertEqual(app.root.geometry_value, "1550x950+10+20")
        self.assertEqual(app.root.state_value, "zoomed")

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
            "mode": "custom", "template": "navy_gold", "title": "Ακίνητο",
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

    def test_ffmpeg_video_filter_chain_separates_color_and_scale_filters(self):
        chain = MediaEditMixin.join_ffmpeg_filters(
            "transpose=1,", "crop=iw*.8:ih*.8,scale=trunc(iw/2)*2:trunc(ih/2)*2,",
            "colorlevels=rimin=0:rimax=.95,eq=saturation=1.0619",
            "scale=1080:1068:force_original_aspect_ratio=increase,crop=1080:1068")
        self.assertIn("eq=saturation=1.0619,scale=1080:1068", chain)
        self.assertNotIn("saturation=1.0619scale", chain)

    def test_facebook_quality_allocates_less_bitrate_to_longer_projects(self):
        short = ExportMixin.facebook_video_bitrate(95, 120)
        long = ExportMixin.facebook_video_bitrate(95, 480)
        self.assertGreater(short, long)
        self.assertGreaterEqual(long, 16_000)
        self.assertLess(long, 2_000_000)
        self.assertAlmostEqual(long + 128_000, 95_000_000 * 8 / 480, delta=1)
        exporter = object.__new__(ExportMixin)
        exporter.settings = {"export_quality": "facebook"}
        exporter._export_video_bitrate = long
        options = exporter.video_encode_options()
        self.assertIn("-maxrate", options)
        self.assertNotIn("-crf", options)

    def test_export_size_estimate_tracks_quality_and_duration(self):
        def estimator(quality, duration=60):
            app = object.__new__(ExportMixin)
            app.settings = {
                "slide_duration": duration,
                "resolution": "1920x1080",
                "export_quality": quality,
                "facebook_target_mb": 25,
            }
            app.media_files = [("image", "slide.png", {})]
            app._presentation_for = lambda edit: normalize_presentation(
                edit.get("presentation"))
            return app

        high_duration, high_size = estimator("high").estimate_export_metrics()
        balanced_duration, balanced_size = estimator("balanced").estimate_export_metrics()
        compact_duration, compact_size = estimator("compact").estimate_export_metrics()
        facebook_duration, facebook_size = estimator("facebook").estimate_export_metrics()

        self.assertEqual(high_duration, 60)
        self.assertEqual(balanced_duration, 60)
        self.assertEqual(compact_duration, 60)
        self.assertEqual(facebook_duration, 60)
        self.assertGreater(high_size, balanced_size)
        self.assertGreater(balanced_size, compact_size)
        self.assertAlmostEqual(facebook_size, 25, delta=0.1)
        self.assertEqual(ExportMixin.format_estimated_duration(65), "01:05")

        two_slides = estimator("high", duration=3)
        two_slides.media_files *= 2
        self.assertAlmostEqual(two_slides.estimate_export_duration(), 5.3)

    def test_named_design_templates_migrate_old_presets(self):
        settings = {"slide_design_presets": {
            "My Navy": {"template": "real_estate", "featured_text": "FOR SALE",
                         "text_align": "right"},
        }}
        templates = read_design_templates(settings)
        self.assertEqual(templates["My Navy"]["template"], "navy_gold")
        self.assertEqual(templates["My Navy"]["featured_text"], "FOR SALE")
        self.assertEqual(templates["My Navy"]["text_align"], "right")
        write_design_templates(settings, templates)
        self.assertIn("My Navy", settings["slide_design_templates"])

    def test_custom_design_templates_are_listed_after_builtins(self):
        choices = design_template_choices(
            {"Zulu": {}, "Elegant Navy & Gold": {}, "Amber": {}},
            ["Απλό", "Elegant Navy & Gold", "Υπότιτλος"], "Use Project Default")
        self.assertEqual(choices, ["Use Project Default", "Απλό", "Elegant Navy & Gold",
                                   "Υπότιτλος", "Amber", "Zulu"])

    def test_project_template_is_inherited_unless_slide_overrides_it(self):
        class ProjectRenderer(RenderMixin):
            project_template = "navy_gold"

        inherited = ProjectRenderer._presentation_for(
            object.__new__(ProjectRenderer), {"presentation": normalize_presentation()})
        explicit = ProjectRenderer._presentation_for(
            object.__new__(ProjectRenderer), {
                "presentation": normalize_presentation({"template": "cinematic"})})
        self.assertEqual(inherited["template"], "navy_gold")
        self.assertEqual(explicit["template"], "cinematic")

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
        video_settings = SlideshowApp._normalize_project_settings({
            "auto_position_videos": True,
            "video_auto_position_fill": "blur",
            "invalid_video_fill": "blur",
        })
        self.assertTrue(video_settings["auto_position_videos"])
        self.assertEqual(video_settings["video_auto_position_fill"], "blur")
        self.assertNotIn("invalid_video_fill", video_settings)

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

    def test_template_choices_aliases_and_defaults(self):
        self.assertEqual(TEMPLATES["legacy"], "Απλό")
        self.assertEqual(TEMPLATES["cinematic"], "Υπότιτλος")
        self.assertEqual(TEMPLATES["lower_third"], "Navy & Gold Transparent")
        self.assertEqual(normalize_presentation({"template": "navy_gold"})["font_size"], 90)
        for removed in ("real_estate", "split_editorial", "business_service", "before_after"):
            self.assertNotIn(removed, TEMPLATES)
            self.assertEqual(normalize_presentation({"template": removed})["template"],
                             "navy_gold")
        old_real_estate = normalize_presentation({"template": "real_estate"})
        self.assertFalse(old_real_estate["featured_enabled"])
        self.assertEqual(old_real_estate["featured_text"], "PROPERTY")
        self.assertEqual(old_real_estate["text_position"], "bottom")
        self.assertEqual(old_real_estate["text_align"], "center")
        self.assertFalse(normalize_presentation({"template": "navy_gold"})["featured_enabled"])
        self.assertFalse(normalize_presentation({
            "template": "business_service"})["featured_enabled"])
        self.assertEqual(normalize_presentation({
            "text_position": "template", "text_align": "justify"})["text_position"], "bottom")
        self.assertEqual(normalize_presentation({"text_align": "justify"})["text_align"], "center")
        for template in TEMPLATES:
            self.assertEqual(normalize_presentation({"template": template})["text_align"],
                             "center")

    def test_navy_gold_featured_badge_can_be_disabled_or_renamed(self):
        source = Image.new("RGB", (640, 800), "#52677A")
        fields = {"title": "Bright apartment"}
        default_badge = normalize_presentation({
            "template": "navy_gold", "mode": "custom", "featured_enabled": True,
            "featured_text": "FEATURED",
        })
        custom_badge = normalize_presentation({
            "template": "navy_gold", "mode": "custom", "featured_enabled": True,
            "featured_text": "JUST LISTED",
        })
        hidden_badge = normalize_presentation({
            "template": "navy_gold", "mode": "custom", "featured_enabled": False,
        })
        default_frame, _ = compose_design_frame(source, 720, 1280, default_badge, fields)
        custom_frame, _ = compose_design_frame(source, 720, 1280, custom_badge, fields)
        hidden_frame, _ = compose_design_frame(source, 720, 1280, hidden_badge, fields)
        self.assertNotEqual(default_frame.tobytes(), custom_frame.tobytes())
        self.assertNotEqual(default_frame.tobytes(), hidden_frame.tobytes())

    def test_subtitle_template_uses_black_outline_and_bottom_default(self):
        self.assertEqual(normalize_presentation()["text_position"], "bottom")
        presentation = normalize_presentation({"template": "cinematic", "mode": "custom"})
        _base, overlay, _rect, _overflow = render_design_layers(
            720, 1280, presentation, {"title": "Movie subtitle"})
        pixels = overlay.load()
        black_outline_pixels = sum(
            1 for y in range(overlay.height) for x in range(overlay.width)
            if pixels[x, y][3] == 255 and pixels[x, y][:3] == (0, 0, 0))
        self.assertGreater(black_outline_pixels, 0)

    def test_non_legacy_text_alignment_changes_template_layout(self):
        source = Image.new("RGB", (640, 800), "#52677A")
        fields = {"title": "Bright home", "description": "Natural light and open spaces."}
        left = normalize_presentation({"template": "navy_gold", "text_align": "left"})
        right = normalize_presentation({"template": "navy_gold", "text_align": "right"})
        left_frame, _ = compose_design_frame(source, 720, 1280, left, fields)
        right_frame, _ = compose_design_frame(source, 720, 1280, right, fields)
        self.assertNotEqual(left_frame.tobytes(), right_frame.tobytes())

    def test_transparent_template_respects_large_font_size(self):
        source = Image.new("RGB", (800, 600), "#52677A")
        fields = {"title": "PROPERTY TITLE"}

        def bright_text_pixels(size):
            presentation = normalize_presentation({
                "template": "lower_third", "mode": "custom", "font_size": size,
            })
            _base, overlay, _rect, _overflow = render_design_layers(
                720, 1280, presentation, fields)
            pixels = np.asarray(overlay)
            return int(np.count_nonzero((pixels[:, :, :3].min(axis=2) > 245) &
                                        (pixels[:, :, 3] > 0)))

        self.assertGreater(bright_text_pixels(90), bright_text_pixels(0))

    def test_auto_position_video_fills_portrait_gaps_with_panel_or_blur(self):
        source = Image.new("RGB", (320, 560), "#D02030")
        presentation = normalize_presentation({"template": "navy_gold", "mode": "custom"})
        panel, _ = compose_design_frame(
            source, 360, 640, presentation, {}, auto_position_video=True,
            video_fill_mode="panel")
        blur, _ = compose_design_frame(
            source, 360, 640, presentation, {}, auto_position_video=True,
            video_fill_mode="blur")
        self.assertEqual(panel.getpixel((1, 100)), (17, 27, 43))
        self.assertEqual(blur.getpixel((1, 100)), (208, 32, 48))

    def test_auto_position_video_starts_at_top_of_media_area(self):
        source = Image.new("RGB", (560, 320), "#D02030")
        presentation = normalize_presentation({"template": "navy_gold", "mode": "custom"})
        frame, _ = compose_design_frame(
            source, 360, 640, presentation, {}, auto_position_video=True,
            video_fill_mode="panel")
        self.assertEqual(frame.getpixel((180, 20)), (208, 32, 48))
        self.assertEqual(frame.getpixel((180, 300)), (17, 27, 43))

    def test_legacy_template_alignment_defaults_center_and_can_be_changed(self):
        class ClassicRenderer(RenderMixin):
            settings = {"font_size": 24, "font_family": "Arial", "text_style": "black_box"}

        renderer = object.__new__(ClassicRenderer)
        source = Image.new("RGBA", (400, 240), (0, 0, 0, 0))
        center = renderer.render_text_on_image(source, "Classic caption", 400, 240)
        right = renderer.render_text_on_image(source, "Classic caption", 400, 240,
                                              align="right")
        center_box = center.getchannel("A").getbbox()
        self.assertGreater(center_box[0], 0)
        self.assertLess(center_box[2], 400)
        self.assertAlmostEqual((center_box[0] + center_box[2]) / 2, 200, delta=10)
        self.assertEqual(right.getchannel("A").getbbox()[2], 400)


if __name__ == "__main__":
    unittest.main()
