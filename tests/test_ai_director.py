"""AI Director validation/apply and welcome-folder helpers."""

import faulthandler
import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from slideshow.ai_director import (apply_plan, ensure_inventory, parse_plan,
                                   validate_plan)
from slideshow.app import SlideshowApp


class AIDirectorTests(unittest.TestCase):
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
        for name in ("one.png", "two.png"):
            Image.new("RGB", (32, 32), "#304050").save(self.directory / name)
        self.app.library_media = [
            self.app._new_item("image", str(self.directory / "one.png")),
            self.app._new_item("image", str(self.directory / "two.png")),
        ]
        self.app._ensure_library_ids()

    def tearDown(self):
        if hasattr(self, "app"):
            faulthandler.disable()
            if self.app._crash_log_file is not None:
                self.app._crash_log_file.close()
        if hasattr(self, "root"):
            for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
                self.root.tk.call("after", "cancel", job)
            self.root.destroy()
        if hasattr(self, "patch_dir"):
            self.patch_dir.stop()
            self.storage.cleanup()

    def _plan(self):
        inventory = ensure_inventory(self.app)
        plan = validate_plan(
            {"title": "Θάλασσα", "aspect": "4:5", "target_duration": 12,
             "scenes": [
                 {"source_id": inventory[0]["id"], "duration": 3,
                  "caption": "**Πρώτη** εικόνα", "background_mode": "blur"},
                 {"source_id": inventory[1]["id"], "duration": 4,
                  "caption": "##Δεύτερη## εικόνα"},
             ]},
            inventory, "9:16", self.app.template_registry())
        return plan, inventory

    def test_plan_is_validated_and_applied_with_undo(self):
        plan, inventory = self._plan()
        self.assertEqual(plan["aspect"], "4:5")
        self.assertEqual(len(plan["scenes"]), 2)
        original = list(self.app.media_files)
        applied = apply_plan(self.app, plan)
        self.assertEqual(len(applied), 2)
        self.assertEqual(self.app.project_caption_mode, "individual")
        self.assertEqual(self.app.settings["resolution"], "1080x1350")
        first = self.app.media_files[0]
        self.assertEqual(first[2]["presentation"]["description"], "**Πρώτη** εικόνα")
        self.assertEqual(first[2]["presentation"]["background_mode"], "blur")
        self.assertEqual(self.app.media_files[1][2]["presentation"]["duration"], 4)
        self.app.undo()
        self.assertEqual(self.app.media_files, original)
        self.assertEqual(self.app.settings["resolution"], "1080x1080")

    def test_invalid_media_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan({"scenes": [{"source_id": "missing", "duration": 3}]},
                          ensure_inventory(self.app), "9:16", {})

    def test_fenced_json_is_accepted(self):
        plan = parse_plan('```json\n{"title":"x","scenes":[]}\n```')
        self.assertEqual(plan["title"], "x")

    def test_director_dialog_opens_with_library_media(self):
        dialog = self.app.show_ai_director()
        self.root.update()
        self.assertTrue(dialog.winfo_exists())
        dialog.destroy()

    def test_welcome_delete_removes_project_not_media(self):
        media = self.directory / "keep.jpg"
        media.write_bytes(b"x")
        project = self.app.projects_dir / "DeleteMe.json"
        project.write_text(json.dumps({"name": "DeleteMe", "media_files": [
            ["image", str(media), {}]]}), encoding="utf-8")
        with patch("slideshow.ui_welcome.messagebox.askyesno", return_value=True), \
                patch.object(self.app, "_finish_welcome"), \
                patch.object(self.app, "show_welcome_screen"):
            self.app._delete_project_from_welcome(project)
        self.assertFalse(project.exists())
        self.assertTrue(media.exists())

    def test_welcome_media_folder_uses_common_parent(self):
        project_folder = self.directory / "Sale" / "RECS 1172"
        video_folder = project_folder / "ΒΙΝΤΕΟ"
        photo_folder = project_folder / "photos"
        video_folder.mkdir(parents=True)
        photo_folder.mkdir()
        video = video_folder / "one.mp4"
        photo = photo_folder / "one.jpg"
        video.write_bytes(b"")
        photo.write_bytes(b"")
        project = self.directory / "project.json"
        project.write_text(json.dumps({"media_files": [
            ["video", str(video), {}], ["image", str(photo), {}]]}),
            encoding="utf-8")
        self.assertEqual(self.app._project_media_folder(project), project_folder)


if __name__ == "__main__":
    unittest.main()
