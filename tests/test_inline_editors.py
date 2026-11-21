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
        from PIL import Image
        for name in ("one.png", "two.png"):
            Image.new("RGB", (32, 32), "#304050").save(self.directory / name)
        self.app.media_files = [
            ("image", str(self.directory / "one.png"), {"presentation": normalize_presentation(
                {"title": "First", "mode": "custom", "duration": 4})}),
            ("image", str(self.directory / "two.png"), {"presentation": normalize_presentation(
                {"title": "Second", "mode": "custom", "duration": 7})}),
        ]
        self.app.selected_indices = {0}
        self.app.project_caption_mode = "individual"
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

    def caption_edit(self, text):
        widget = self.widgets(tk.Text)[0]
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        self.root.update()

    def test_scene_change_flushes_pending_caption_without_a_dialog(self):
        self.caption_edit("Edited")
        self.app.select_scene(1)
        self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "Edited")
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "")
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
        self.app.complete_profile_onboarding("First profile", "", "#e8bd79")
        self.assertFalse(self.app._needs_profile_setup)
        self.app.show_welcome_screen()
        self.root.update()
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertTrue(self.app._welcome_dialog.winfo_viewable())
        self.app.media_files = []
        self.app.is_modified = False
        profile = self.app.create_new_profile("Second profile")
        self.assertEqual(self.app.active_profile_id, profile["id"])
        self.assertEqual(self.root.state(), "withdrawn")
        data = json.loads((self.directory / "profiles.json").read_text(encoding="utf-8"))
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
        self.caption_edit("Old draft")
        replacement = copy.deepcopy(self.app.media_files)
        self.app.media_files = replacement
        self.app._render_inspector()
        self.assertEqual(replacement[0][2]["presentation"]["title"], "First")

    def test_save_commits_latest_keystroke_and_round_trips(self):
        self.caption_edit("Saved immediately")
        self.app.name_var.set("Inline test")
        with patch("slideshow.app.messagebox.showinfo"):
            self.assertTrue(self.app.save_project())
        path = next(self.app.projects_dir.glob("*.json"))
        self.assertTrue(self.app.load_project_file(path))
        self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "Saved immediately")

    def wait_ms(self, milliseconds):
        done = tk.BooleanVar(master=self.root, value=False)
        self.root.after(milliseconds, lambda: done.set(True))
        self.root.wait_variable(done)

    def test_caption_waits_for_two_seconds_after_last_edit(self):
        self.caption_edit("Still typing")
        self.wait_ms(1100)
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "First")
        self.caption_edit("Finished")
        self.wait_ms(1100)
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "First")
        self.wait_ms(1050)
        self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "Finished")
        self.assertIsNone(self.app._caption_apply_job)

    def test_legacy_caption_is_editable_in_one_field_without_losing_text(self):
        data = self.app.media_files[0][2]["presentation"]
        data.update(subtitle="Subtitle", description="Body")
        original = copy.deepcopy(data)
        self.app._render_inspector()
        self.root.update()
        self.assertEqual(self.widgets(tk.Text)[0].get("1.0", "end-1c"),
                         "First\nSubtitle\nBody")
        self.app._commit_pending_caption_apply()
        self.assertEqual(data, original)
        labels = [widget.cget("text") for widget in self.widgets(tk.ttk.Label)]
        self.assertNotIn("Τίτλος", labels)
        self.assertNotIn("Υπότιτλος", labels)
        self.assertNotIn("Τρόπος κειμένου", labels)
        self.assertIn("Επιπλέον οδηγίες για AI", labels)
        buttons = [widget.cget("text") for widget in self.widgets(tk.ttk.Button)]
        self.assertNotIn("Εφαρμογή κειμένου", buttons)
        self.assertNotIn("Quick Paste", buttons)
        self.caption_edit("First\nSubtitle\nUpdated body")
        self.app._commit_pending_caption_apply()
        data = self.app.media_files[0][2]["presentation"]
        self.assertEqual(data["description"], "First\nSubtitle\nUpdated body")
        self.assertEqual((data["title"], data["subtitle"]), ("", ""))

    def test_ai_result_updates_the_single_caption_field(self):
        with patch.object(self.app, "improve_text_with_ai",
                          side_effect=lambda text, instructions, receive: receive("Improved")):
            button = next(widget for widget in self.widgets(tk.ttk.Button)
                          if widget.cget("text") == "Βελτίωση με AI")
            button.invoke()
        data = self.app.media_files[0][2]["presentation"]
        self.assertEqual(data["description"], "Improved")
        self.assertEqual(data["title"], "")

    def test_three_caption_strategies_and_mixed_group_round_trip(self):
        self.app.media_files.append(("video", str(self.directory / "one.png"), {
            "presentation": normalize_presentation({"mode": "global", "duration": 9})}))
        self.app._set_caption_strategy("all")
        self.assertEqual(len(self.widgets(tk.Text)), 2)
        self.caption_edit("Shared caption")
        self.app._commit_pending_caption_apply()
        for kind, _path, edit in self.app.media_files:
            effective = self.app._presentation_for(edit)
            self.assertEqual(self.app._presentation_text(effective, kind), "Shared caption")
        self.assertEqual(self.app.media_files[0][2]["presentation"]["title"], "First")
        self.app._set_caption_strategy("by_type")
        self.assertEqual(len(self.widgets(tk.Text)), 3)
        for widget, text in zip(self.widgets(tk.Text)[:2], ("Photo caption", "Video caption")):
            widget.insert("1.0", text)
        self.root.update()
        self.app._commit_pending_caption_apply()
        self.assertEqual(self.app.get_text_for("image"), "Photo caption")
        self.assertEqual(self.app.get_text_for("video"), "Video caption")
        self.app.name_var.set("Strategies")
        with patch("slideshow.app.messagebox.showinfo"):
            self.app.save_project()
        project = next(self.app.projects_dir.glob("*.json"))
        self.app.load_project_file(project)
        self.assertEqual(self.app.project_caption_mode, "by_type")
        self.app._set_caption_strategy("all")
        self.caption_edit("")
        self.app._commit_pending_caption_apply()
        with patch("slideshow.app.messagebox.showinfo"):
            self.app.save_project()
        self.app.load_project_file(project)
        self.assertEqual(self.app.get_text_for("image"), "")
        self.app._set_caption_strategy("by_type")
        self.assertEqual(self.app.get_text_for("image"), "Photo caption")
        self.assertEqual(self.app.get_text_for("video"), "Video caption")
        self.app._set_caption_strategy("individual")
        self.assertEqual(self.app.media_files[2][2]["presentation"]["description"], "Video caption")
        self.app.selected_indices = {0, 2}
        self.app._render_inspector()
        before = copy.deepcopy(self.app.media_files)
        self.caption_edit("Mixed group")
        self.app._commit_pending_caption_apply()
        for index in (0, 2):
            value = self.app.media_files[index][2]["presentation"]
            self.assertEqual(value["description"], "Mixed group")
            for key in ("scene_id", "duration", "template"):
                self.assertEqual(value[key], before[index][2]["presentation"][key])
        self.assertEqual(self.app.media_files[1], before[1])
        with patch("slideshow.app.messagebox.showinfo"):
            self.app.save_project()
        self.app.load_project_file(project)
        self.assertEqual(self.app.project_caption_mode, "individual")
        self.assertEqual(self.app.media_files[2][2]["presentation"]["description"], "Mixed group")
        self.assertEqual(self.app._new_item("image", str(self.directory / "one.png"))
                         [2]["presentation"]["mode"], "custom")

    def test_legacy_mixed_caption_migration_and_strategy_undo(self):
        video, photo, mode, shared = self.app._project_caption_values({
            "caption_mode": "all", "project_text_all": "Shared",
            "media_files": self.app.media_files})
        self.assertEqual((video, photo, mode, shared), ("Shared", "Shared", "individual", "Shared"))
        self.app._set_caption_strategy("all")
        self.app.undo()
        self.assertEqual(self.app.project_caption_mode, "individual")
        self.app.redo()
        self.assertEqual(self.app.project_caption_mode, "all")

    def test_keyboard_and_context_menu_paste_apply_without_quick_paste(self):
        widget = self.widgets(tk.Text)[0]
        widget.delete("1.0", "end")
        self.root.clipboard_clear()
        self.root.clipboard_append("Pasted caption")
        widget.event_generate("<<Paste>>")
        self.root.update()
        self.app._commit_pending_caption_apply()
        self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "Pasted caption")
        widget.delete("1.0", "end")
        menu = next(child for child in widget.winfo_children() if isinstance(child, tk.Menu))
        menu.invoke("Paste")
        self.root.update()
        self.app._commit_pending_caption_apply()
        self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "Pasted caption")

    def drag_sash(self, index, offset):
        workspace = self.app.workspace
        x, _y = workspace.sash_coord(index)
        for event, position in (("<ButtonPress-1>", x + 4),
                                ("<B1-Motion>", x + 4 + offset),
                                ("<ButtonRelease-1>", x + 4 + offset)):
            workspace.event_generate(event, x=position, y=100)
            self.root.update()
        self.root.update()

    def pane_widths(self):
        return [self.app.workspace.nametowidget(name).winfo_width()
                for name in self.app.workspace.panes()]

    def test_both_dividers_drag_and_restore_independently_for_each_profile(self):
        self.root.geometry("1250x850")
        self.root.deiconify()
        self.root.update()
        first_profile = self.app.active_profile_id
        initial = self.pane_widths()
        self.assertAlmostEqual(initial[2], 360, delta=3)
        self.drag_sash(0, 80)
        self.assertGreater(self.pane_widths()[0], initial[0] + 50)
        self.drag_sash(1, -80)
        first_widths = self.pane_widths()
        self.assertGreater(first_widths[2], initial[2] + 50,
                           (initial, first_widths, self.app.workspace.winfo_width()))
        first_settings = self.app.settings_file
        saved = json.loads(first_settings.read_text())["workspace_layout"]
        self.assertAlmostEqual(sum(saved), 1)
        self.assertNotIn("workspace_layout", self.app._capture_project_settings())
        second = self.app.create_new_profile("Layout two")
        self.root.update()
        self.drag_sash(0, 20)
        self.drag_sash(1, 40)
        second_widths = self.pane_widths()
        self.app.switch_profile(first_profile)
        self.root.update()
        for expected, actual in zip(first_widths, self.pane_widths()):
            self.assertAlmostEqual(expected, actual, delta=3)
        self.root.geometry("1000x850")
        self.root.update()
        self.root.geometry("1250x850")
        self.root.update()
        for expected, actual in zip(first_widths, self.pane_widths()):
            self.assertAlmostEqual(expected, actual, delta=3)
        self.app.switch_profile(second["id"])
        self.root.update()
        for expected, actual in zip(second_widths, self.pane_widths()):
            self.assertAlmostEqual(expected, actual, delta=3)


if __name__ == "__main__":
    unittest.main()
