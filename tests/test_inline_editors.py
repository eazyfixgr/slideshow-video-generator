"""Regression checks for embedded editors with a real Tk interpreter."""

import copy
import tempfile
import json
import subprocess
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from slideshow.app import SlideshowApp
from slideshow.slide_design import normalize_presentation


class InlineEditorTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.storage = tempfile.TemporaryDirectory()
        self.directory = Path(self.storage.name)
        self.patch_dir = patch("slideshow.app.APP_DIR", self.directory)
        self.patch_dir.start()
        self.app = SlideshowApp(self.root, show_welcome=False)
        self.app._schedule_preview = lambda *args: None
        self.app.render_storyboard = lambda: None
        self.app.media_files = [
            ("image", "one.png", {"presentation": normalize_presentation(
                {"title": "First", "mode": "custom", "duration": 4})}),
            ("image", "two.png", {"presentation": normalize_presentation(
                {"title": "Second", "mode": "custom", "duration": 7})}),
        ]
        self.app.selected_indices = {0}
        self.app._inline_caption_scope = "Τρέχουσα σκηνή"
        self.app._set_inspector_view("captions")
        self.root.update()

    def tearDown(self):
        if hasattr(self, "root"):
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.tk.call("after", "cancel", job)
            self.root.destroy()
        if hasattr(self, "patch_dir"):
            self.patch_dir.stop()
            self.storage.cleanup()

    def widgets(self, kind):
        def walk(parent):
            for child in parent.winfo_children():
                yield child
                yield from walk(child)
        return [widget for widget in walk(self.app.inspector_content)
                if isinstance(widget, kind)]

    def title_edit(self, text):
        widget = self.widgets(tk.Text)[0]
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        self.root.update()

    def test_scene_change_flushes_pending_title_without_a_dialog(self):
        self.title_edit("Edited")
        self.app.select_scene(1)
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "Edited")
        self.assertEqual(self.app.media_files[1][2]["presentation"]["title"], "Second")
        self.assertEqual(self.widgets(tk.Text)[0].get("1.0", "end-1c"), "Second")
        self.app.open_presentation_editor(1)
        self.app.open_text_captions_manager()
        self.app.open_storyboard_editor()
        self.assertFalse(any(isinstance(w, tk.Toplevel) and w.winfo_viewable()
                             for w in self.root.winfo_children()))

    def test_group_style_preserves_content_duration_and_identity(self):
        self.app.selected_indices = {0, 1}
        self.app._inline_design_scope = "Επιλεγμένες σκηνές"
        self.app._set_inspector_view("design")
        before = copy.deepcopy(self.app.media_files)
        combos = self.widgets(__import__("tkinter").ttk.Combobox)
        template = combos[1]
        template.set("Elegant Navy & Gold")
        template.event_generate("<<ComboboxSelected>>")
        self.app._commit_pending_caption_apply()
        for old, new in zip(before, self.app.media_files):
            old_value, value = old[2]["presentation"], new[2]["presentation"]
            self.assertEqual(value["template"], "navy_gold")
            for key in ("title", "duration", "scene_id", "mode"):
                self.assertEqual(value[key], old_value[key])
        self.app.undo()
        self.assertEqual(self.app.media_files, before)

    def test_first_welcome_and_profile_restore(self):
        self.app.show_welcome_screen()
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertTrue(self.app._welcome_dialog.winfo_viewable())
        self.app.media_files = []
        self.app.is_modified = False
        profile = self.app.create_new_profile("Second profile")
        self.assertEqual(self.app.active_profile_id, profile["id"])
        self.assertEqual(self.root.state(), "withdrawn")
        data = json.loads((self.directory / "profiles.json").read_text())
        self.assertEqual(data["active_profile"], profile["id"])

    def test_embedded_caption_and_design_export(self):
        from PIL import Image
        image_path = self.directory / "image.png"
        Image.new("RGB", (320, 320), "#304050").save(image_path)
        self.app.media_files = self.app.normalize_media_list(
            [("image", str(image_path), {"presentation": {
                "mode": "custom", "title": "Render check",
                "template": "navy_gold", "duration": 0.5}})])
        self.app.settings.update(resolution="320x320", transition="none",
                                 watermark_enabled=False)
        output = self.directory / "render-check.mp4"
        self.app._export_task(output)
        self.assertTrue(output.is_file(), (self.app.temp_dir / "export_log.txt").read_text())
        result = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(output)], text=True)
        self.assertGreater(float(result), 0.3)

    def test_uncommitted_input_cannot_write_into_loaded_media(self):
        self.title_edit("Old draft")
        replacement = copy.deepcopy(self.app.media_files)
        self.app.media_files = replacement
        self.app._render_inspector()
        self.assertEqual(replacement[0][2]["presentation"]["title"], "First")

    def test_save_commits_latest_keystroke_and_round_trips(self):
        self.title_edit("Saved immediately")
        self.app.name_var.set("Inline test")
        with patch("slideshow.app.messagebox.showinfo"):
            self.assertTrue(self.app.save_project())
        path = next(self.app.projects_dir.glob("*.json"))
        self.assertTrue(self.app.load_project_file(path))
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "Saved immediately")


if __name__ == "__main__":
    unittest.main()
