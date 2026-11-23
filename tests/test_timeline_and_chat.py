"""Real timing, mixed audio, non-destructive AI edits and project round trips."""

import copy
import faulthandler
import json
import math
import subprocess
import tempfile
import time
import tkinter as tk
import unittest
import wave
from array import array
from pathlib import Path
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
import numpy as np

from slideshow.ai_chat import apply_chat_edits, project_context
from slideshow.app import SlideshowApp
from slideshow.audio_engine import analyze_audio, automatic_music, mix_command
from slideshow.rich_text import parse_markup
from slideshow.slide_design import normalize_presentation
from slideshow.timeline_model import (audio_clip, audio_segments, cut_audio_edge,
                                      new_track, normalize_audio, remove_audio_range,
                                      scene_timing, set_audio_segments, source_time,
                                      trim_audio)
from slideshow.ui_storyboard import ORIGIN, AUDIO_TOP, LANE
from slideshow.ui_audio_tracks import AudioTracksMixin
from slideshow.voice_recording import input_devices


def tone(path, duration=1, frequency=440):
    samples = array("h", [round(5000 * math.sin(2 * math.pi * frequency * i / 48000))
                          for i in range(round(duration * 48000))])
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(samples.tobytes())


class TimelineModelTests(unittest.TestCase):
    def test_scene_offsets_include_transition_overlaps(self):
        layout, total = scene_timing([
            {"duration": 4, "transition": "global"},
            {"duration": 7, "transition": "global"},
            {"duration": 2, "transition": "none"}],
            {"transition_effect": "random", "transition_duration": .7})
        self.assertEqual([item["start"] for item in layout], [0, 3.3, 10.3])
        self.assertAlmostEqual(total, 12.3)

    def test_source_scrub_maps_across_kept_video_segments(self):
        self.assertAlmostEqual(source_time([(2, 3), (10, 4)], 3.5), 10.5)
        self.assertAlmostEqual(source_time([(2, 3), (10, 4)], 1), 3)

    def test_audio_edge_trims_are_bounded_and_non_destructive(self):
        clip = audio_clip("music.wav", 3, 4, offset=2)
        changed = trim_audio(clip, "left", -10, 9)
        self.assertEqual((changed["start"], changed["offset"], changed["duration"]), (2, 0, 5))
        changed = trim_audio(clip, "right", 100, 9)
        self.assertEqual(changed["duration"], 7)
        self.assertEqual(clip["duration"], 3)

    def test_audio_segment_cuts_remove_parts_from_start_middle_and_end(self):
        clip = audio_clip("music.wav", 5, 4, offset=2)
        self.assertTrue(set_audio_segments(clip, [[2, 3], [7, 2]], 12))
        self.assertEqual((clip["offset"], clip["duration"]), (2, 5))
        ranges = remove_audio_range(audio_segments(clip), 3, 4, 12)
        self.assertEqual(ranges, [[2, 1], [4, 1], [7, 2]])
        ranges = cut_audio_edge(ranges, "start", .5, 12)
        ranges = cut_audio_edge(ranges, "end", .5, 12)
        self.assertEqual(ranges, [[2.5, .5], [4, 1], [7, 1.5]])
        self.assertAlmostEqual(sum(length for _start, length in ranges), 3)

    def test_segmented_audio_normalization_round_trips_and_compacts(self):
        clip = audio_clip("music.wav", 5, 0, offset=0)
        set_audio_segments(clip, [[0, .2], [.8, .2]], 1)
        audio = normalize_audio({"mode": "manual", "tracks": [
            new_track("Music", clips=[clip])]})
        saved = audio["tracks"][0]["clips"][0]
        self.assertEqual([start for start, _length in saved["segments"]], [0, .8])
        self.assertEqual([round(length, 6) for _start, length in saved["segments"]],
                         [.2, .2])
        self.assertAlmostEqual(saved["duration"], .4)
        self.assertEqual(saved["offset"], 0)

    def test_mix_command_compacts_deleted_audio_ranges(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / "tone.wav", root / "mix.wav"
            tone(source)
            clip = audio_clip(str(source), .4, 0, segments=[[0, .2], [.8, .2]])
            run = subprocess.run(mix_command([new_track("Music", clips=[clip])], .4, output),
                                 capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors="replace"))
            with wave.open(str(output)) as stream:
                rate, frames = stream.getframerate(), stream.getnframes()
            self.assertAlmostEqual(frames / rate, .4, places=2)

    def test_audio_normalization_preserves_tracks_and_rejects_non_finite_numbers(self):
        clip = audio_clip("x.wav", 3, 2, volume_db=float("nan"))
        track = new_track("Music", clips=[clip], mute=True, solo=True)
        audio = normalize_audio({"mode": "manual", "tracks": [track]})
        self.assertTrue(audio["tracks"][0]["mute"])
        self.assertTrue(audio["tracks"][0]["solo"])
        self.assertEqual(audio["tracks"][0]["clips"][0]["volume_db"], 0)

    def test_mix_has_real_silence_gaps_offsets_and_track_gain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / "tone.wav", root / "mix.wav"
            tone(source)
            tracks = [new_track("Music", clips=[audio_clip(str(source), .3, 0, offset=.2)]),
                      new_track("Voice", volume_db=-6, clips=[audio_clip(str(source), .3, .6)]),
                      new_track("Muted", mute=True, clips=[audio_clip(str(source), 1, 0)])]
            run = subprocess.run(mix_command(tracks, 1, output), capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors="replace"))
            with wave.open(str(output)) as stream:
                rate, channels, frames = stream.getframerate(), stream.getnchannels(), stream.getnframes()
                data = np.frombuffer(stream.readframes(frames), dtype="<i2").reshape(-1, channels)[:, 0].astype(float)
            self.assertAlmostEqual(frames / rate, 1, places=3)
            def rms(start, end):
                block = data[round(start * rate):round(end * rate)]
                return np.sqrt(np.mean(block ** 2))
            self.assertGreater(rms(.05, .25), 1000)
            self.assertLess(rms(.4, .55), 5)
            self.assertAlmostEqual(rms(.65, .85) / rms(.05, .25), .501, delta=.04)

    def test_automatic_plan_does_not_consume_music_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "one.wav").touch()
            (root / "two.wav").touch()
            tracker = {"available_music": ["one.wav", "two.wav"], "used_music": ["one.wav"]}
            before = copy.deepcopy(tracker)
            tracks = automatic_music({"music_folder": folder, "crossfade_duration": 1}, tracker, 8,
                                     lambda *_: {"usable": 5, "offset": 0})
            self.assertEqual(Path(tracks[0]["clips"][0]["path"]).name, "two.wav")
            self.assertEqual(tracker, before)
            self.assertEqual(tracks[0]["clips"][1]["start"], 4)

    def test_windows_microphone_names_are_parsed_without_changing_unicode(self):
        output = ('[dshow] "Μικρόφωνο USB" (audio)\n[dshow] "Camera" (video)\n'
                  '[dshow] "Μικρόφωνο USB" (audio)').encode("utf-8")
        with patch("slideshow.voice_recording.subprocess.run", return_value=SimpleNamespace(stderr=output)):
            self.assertEqual(input_devices(), ["Μικρόφωνο USB"])


class ChatAndProjectTests(unittest.TestCase):
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
        self.app._queue_timeline_audio = lambda *args: None
        for name in ("one.png", "two.png", "three.png"):
            Image.new("RGB", (80, 60), "#304050").save(self.directory / name)
        self.app.media_files = [self.app._new_item("image", str(self.directory / name))
                                for name in ("one.png", "two.png", "three.png")]
        self.app.project_caption_mode = "all"
        self.app.project_text_all = "Original shared caption"
        self.app.settings["transition_effect"] = "none"
        self.app.selected_indices = {0}

    def tearDown(self):
        self.app.stop_timeline_playback()
        faulthandler.disable()
        if self.app._crash_log_file:
            self.app._crash_log_file.close()
        for job in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.tk.call("after", "cancel", job)
        self.root.destroy()
        self.patch_dir.stop()
        self.storage.cleanup()

    def test_chat_updates_group_and_preserves_other_scene_and_ids(self):
        for item in self.app.media_files[:2]:
            item[2]["group_id"] = "shared"
        context = project_context(self.app)
        ids = [scene["scene_id"] for scene in context["scenes"]]
        apply_chat_edits(self.app, {"message": "Done", "operations": [{
            "type": "update_scenes", "scene_ids": [ids[0]], "caption": "Changed",
            "duration": 4, "style": {"text_color": "#FFAA00"}}]})
        self.assertEqual([item[2]["presentation"]["description"] for item in self.app.media_files],
                         ["Changed", "Changed", "Original shared caption"])
        self.assertEqual([item[2]["presentation"]["scene_id"] for item in self.app.media_files], ids)
        self.app.undo()
        self.assertEqual(self.app.project_caption_mode, "all")

    def test_invalid_late_operation_rolls_back_all_proposed_edits(self):
        context = project_context(self.app)
        before = copy.deepcopy(self.app.media_files)
        with self.assertRaises(ValueError):
            apply_chat_edits(self.app, {"operations": [
                {"type": "update_scenes", "scene_ids": [context["scenes"][0]["scene_id"]], "caption": "bad"},
                {"type": "remove_scenes", "scene_ids": ["missing"]}]})
        self.assertEqual(self.app.media_files, before)
        self.assertEqual(self.app._undo_stack, [])

    def test_chat_preserves_visible_shared_caption_when_old_hidden_text_exists(self):
        self.app.media_files[1][2]["presentation"].update(mode="custom", description="Hidden old text")
        context = project_context(self.app)
        apply_chat_edits(self.app, {"operations": [{"type": "update_scenes",
            "scene_ids": [context["scenes"][0]["scene_id"]], "caption": "New"}]})
        self.assertEqual(self.app.media_files[1][2]["presentation"]["description"], "Original shared caption")

    def test_audio_chat_history_save_load_and_reset(self):
        self.app.project_audio = {"mode": "manual", "tracks": [new_track("Voice-over", clips=[
            audio_clip(str(self.directory / "voice.wav"), 2, 1, offset=.5, recording=True)])]}
        self.app.ai_chat_history = [{"role": "user", "content": "Change the first scene"},
                                    {"role": "assistant", "content": "Done"}]
        self.app.project_ai_brief = "A real estate advert"
        self.app.name_var.set("Timeline saved")
        with patch("slideshow.app.messagebox.showinfo"):
            self.assertTrue(self.app.save_project())
        path = self.app.current_project
        self.app.new_project()
        self.assertEqual(self.app.ai_chat_history, [])
        self.assertEqual(self.app.project_audio["mode"], "auto")
        self.app.load_project_file(path)
        self.assertEqual(len(self.app.ai_chat_history), 2)
        clip = self.app.project_audio["tracks"][0]["clips"][0]
        self.assertEqual((clip["start"], clip["offset"], clip["duration"]), (1, .5, 2))
        self.assertEqual(self.app.project_ai_brief, "A real estate advert")

    def test_scene_widths_are_proportional_to_real_durations(self):
        self.app.media_files[0][2]["presentation"]["duration"] = 4
        self.app.media_files[1][2]["presentation"]["duration"] = 8
        self.app.render_storyboard()
        canvas = self.app.storyboard_canvas
        def width(index):
            rectangle = next(item for item in canvas.find_withtag(f"scene:{index}") if canvas.type(item) == "rectangle")
            x1, _y1, x2, _y2 = canvas.coords(rectangle)
            return x2 - x1
        self.assertAlmostEqual(width(1) / width(0), 2)

    def test_audio_drag_moves_clip_in_time_and_to_another_track_with_undo(self):
        clip = audio_clip(str(self.directory / "music.wav"), 5, 1)
        self.app.project_audio = {"mode": "manual", "tracks": [
            new_track("Music", clips=[clip]), new_track("Second")]}
        self.app._timeline_fit = False
        self.app._timeline_zoom = 10
        self.app.render_storyboard()
        x, y = ORIGIN + 35, AUDIO_TOP + 22
        self.app._timeline_press(SimpleNamespace(x=x, y=y, state=0))
        self.app._timeline_motion(SimpleNamespace(x=x+20, y=y+LANE, state=0))
        self.app._timeline_release(SimpleNamespace(x=x+20, y=y+LANE, state=0))
        self.assertEqual(self.app.project_audio["tracks"][0]["clips"], [])
        self.assertEqual(self.app.project_audio["tracks"][1]["clips"][0]["start"], 3)
        self.app.undo()
        self.assertEqual(self.app.project_audio["tracks"][0]["clips"][0]["start"], 1)

    def test_preview_uses_elapsed_seconds_instead_of_a_scene_count_timer(self):
        self.app._preview_playing = True
        self.app._playback_start_position = 1
        self.app._playback_clock = 10
        with patch("slideshow.ui_timeline_playback.time.monotonic", return_value=12.5), \
                patch.object(self.app, "_request_timeline_frame"):
            self.app._timeline_tick()
        self.assertAlmostEqual(self.app._playhead_seconds, 3.5)

    def test_timeline_playback_produces_composed_preview_frames(self):
        self.app.settings["resolution"] = "320x320"
        self.app._start_timeline_clock(0, muted=True)
        deadline = time.monotonic() + 3
        while not hasattr(self.app.preview_canvas, "full_image") and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.02)
        self.app.stop_timeline_playback()
        self.assertTrue(hasattr(self.app.preview_canvas, "full_image"))
        self.assertEqual(self.app.preview_canvas.full_image.size, (320, 320))

    def test_automatic_music_is_visible_in_timeline_before_export(self):
        path = self.directory / "song.wav"
        tone(path)
        self.app.media_files = self.app.media_files[:1]
        self.app.media_files[0][2]["presentation"]["duration"] = 1
        self.app.settings.update(music_folder=str(self.directory), trim_silence=False,
                                  crossfade_duration=0)
        self.app.music_tracker = {"available_music": ["song.wav"], "used_music": []}
        self.app._queue_timeline_audio = AudioTracksMixin._queue_timeline_audio.__get__(self.app)
        self.app._timeline_audio_key = None
        self.app.render_storyboard()
        deadline = time.monotonic() + 4
        while not self.app._timeline_display_tracks and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.02)
        self.assertTrue(self.app._timeline_display_tracks)
        clip = self.app._timeline_display_tracks[0]["clips"][0]
        self.assertEqual(Path(clip["path"]), path)
        self.assertTrue(self.app.storyboard_canvas.find_withtag(f"audio:{clip['id']}"))
        self.assertEqual(self.app.music_tracker["used_music"], [])

    def test_talk_to_ai_uses_history_and_applies_mock_api_reply(self):
        context = project_context(self.app)
        scene_id = context["scenes"][0]["scene_id"]
        self.app.settings["ai_director_api_key"] = "test-only-key"
        response = {"choices": [{"message": {"content": json.dumps({"message": "Άλλαξα την πρώτη σκηνή.",
                    "operations": [{"type": "update_scenes", "scene_ids": [scene_id], "caption": "New caption"}]})}}]}
        dialog = self.app.show_ai_chat()
        def walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from walk(child)
        widgets = list(walk(dialog))
        text = [widget for widget in widgets if isinstance(widget, tk.Text)][-1]
        text.insert("1.0", "Δεν μου αρέσει η πρώτη σκηνή, άλλαξε το κείμενο.")
        with patch.object(self.app, "_ai_call", return_value=response) as api:
            next(widget for widget in widgets if isinstance(widget, ttk.Button) and widget.cget("text") == "Αποστολή").invoke()
            deadline = time.monotonic() + 4
            while (len(self.app.ai_chat_history) < 2 and time.monotonic() < deadline):
                self.root.update()
                time.sleep(.02)
            self.assertEqual(self.app.media_files[0][2]["presentation"]["description"], "New caption")
            self.assertEqual(len(self.app.ai_chat_history), 2)
            payload = api.call_args.args[1]
            self.assertNotIn("test-only-key", json.dumps(payload))
        dialog.destroy()

    def test_finished_voiceover_becomes_a_durable_timeline_clip(self):
        folder = self.app.projects_dir / "recordings"
        folder.mkdir()
        path = folder / "voice.wav"
        tone(path, .4)
        dialog = tk.Toplevel(self.root)
        self.app._voiceover_state = {
            "recorder": SimpleNamespace(path=path, stop=lambda: .4), "job": None,
            "saved": False, "start": 1.25, "dialog": dialog, "status": tk.StringVar()}
        self.app._stop_voiceover_capture(save=True)
        track = next(track for track in self.app.project_audio["tracks"] if track["name"] == "Voice-over")
        self.assertEqual(track["clips"][0]["start"], 1.25)
        self.assertTrue(track["clips"][0]["recording"])
        self.assertTrue(path.exists())
        dialog.destroy()

    def test_export_mixes_timeline_music_and_voiceover_at_their_positions(self):
        source = self.directory / "tone.wav"
        voice = self.directory / "voice.wav"
        tone(source, 1, 440)
        tone(voice, 1, 660)
        self.app.media_files = self.app.media_files[:2]
        for item in self.app.media_files:
            item[2]["presentation"]["duration"] = 1
        self.app.project_text_all = ""
        self.app.settings.update(resolution="320x320", transition_effect="none", watermark_enabled=False)
        self.app.project_audio = {"mode": "manual", "tracks": [
            new_track("Music", clips=[audio_clip(str(source), .4, .05)]),
            new_track("Voice-over", clips=[audio_clip(str(voice), .4, 1.1, recording=True)])]}
        output = self.directory / "timeline.mp4"
        callbacks = []
        with patch.object(self.app, "_post_ui", side_effect=lambda *args: callbacks.append(args)):
            self.app._export_task(output)
        self.assertTrue(output.exists(), str(callbacks))
        self.assertAlmostEqual(self.app._probe_duration(output), 2, delta=.1)
        decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
                                  "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                                 capture_output=True, timeout=30)
        data = np.frombuffer(decoded.stdout, dtype="<f4")
        def rms(start, end):
            return float(np.sqrt(np.mean(data[round(start * 48000):round(end * 48000)] ** 2)))
        self.assertGreater(rms(.1, .3), .02)
        self.assertLess(rms(.65, .85), .002)
        self.assertGreater(rms(1.2, 1.4), .02)

    def test_video_duration_is_never_probed_while_building_timeline(self):
        self.app.media_files.append(("video", str(self.directory / "remote.mp4"), {
            "presentation": normalize_presentation({"duration": 3})}))
        with patch.object(self.app, "_video_duration",
                          side_effect=AssertionError("blocked Tk thread")), \
                patch.object(self.app, "_queue_timeline_video_duration"):
            layout, total = self.app.timeline_layout()
            clips = self.app._estimate_export_clips()
        self.assertTrue(layout)
        self.assertGreater(total, 0)
        self.assertEqual(len(clips), len(self.app.media_files))

    def test_accent_after_global_size_wraps_inside_the_size_markers(self):
        widget = tk.Text(self.root)
        widget.insert("1.0", "%+3%Title\n\nContact%%\n")
        start = widget.index("1.0+11c")
        widget.tag_add(tk.SEL, start, "end-1c")
        self.app._format_rich_selection(widget, "accent")
        text = widget.get("1.0", "end-1c")
        self.assertNotIn("%%##", text)
        self.assertIn("##Contact##%%", text)
        content = next(span for span in parse_markup(text) if "Contact" in span.text)
        self.assertTrue(content.accent)
        self.assertEqual(content.size_steps, 3)
        widget.destroy()

    def test_size_change_inside_global_size_affects_only_the_selection(self):
        widget = tk.Text(self.root)
        widget.insert("1.0", "%+3%Outer word%%")
        start_off = widget.get("1.0", "end-1c").index("word")
        widget.tag_add(tk.SEL, widget.index(f"1.0+{start_off}c"),
                       widget.index(f"1.0+{start_off + 4}c"))
        self.app._format_rich_selection(widget, "size", 1)
        text = widget.get("1.0", "end-1c")
        spans = {span.text.strip(): span.size_steps for span in parse_markup(text)
                 if span.text.strip()}
        self.assertEqual(spans.get("word"), 4)
        self.assertEqual(spans.get("Outer"), 3)
        widget.destroy()

    def test_fit_and_move_photos_stay_fit_and_move_with_auto_position_photos(self):
        source = Image.new("RGB", (320, 180), "#305070")
        edit = self.app._new_item("image", str(self.directory / "photo.png"))[2]
        edit["presentation"] = normalize_presentation({
            "template": "navy_gold", "text_layout": "below", "mode": "none"})
        self.app.settings.update({
            "auto_position_photos": True,
            "auto_position_videos": False,
            "background_mode": "fit_and_move",
            "watermark_enabled": False,
        })
        presentation = self.app._presentation_for(edit)
        with patch.object(self.app, "_render_design_frame",
                          side_effect=AssertionError("auto position used")):
            preview = self.app._render_design_fitmove_preview(
                source, edit, "image", 270, 480, presentation)
        rendered, _overflow = self.app._render_design_frame(
            source, edit, "image", 270, 480)
        self.assertEqual(preview.size, rendered.size)
        self.assertNotEqual(preview.convert("RGB").tobytes(),
                            rendered.convert("RGB").tobytes())

    def test_auto_position_video_preview_matches_the_renderer(self):
        source = Image.new("RGB", (320, 180), "#305070")
        edit = self.app._new_item("video", str(self.directory / "new-video.mp4"))[2]
        edit["presentation"] = normalize_presentation({
            "template": "lower_third", "text_layout": "overlay",
            "text_position": "bottom"})
        self.app.project_text_all = ""
        self.app.settings.update({
            "auto_position_videos": True,
            "video_auto_position_fill": "blur",
            "background_mode": "fit_and_move",
            "cropping": False,
            "watermark_enabled": False,
        })
        with patch.object(self.app, "_video_first_frame", return_value=source):
            preview = self.app._preview_frame_image(
                str(self.directory / "new-video.mp4"), "video", 270, 480, edit)
        rendered, _overflow = self.app._render_design_frame(
            source, edit, "video", 270, 480)
        self.assertEqual(preview.size, rendered.size)
        self.assertEqual(preview.convert("RGB").tobytes(),
                         rendered.convert("RGB").tobytes())

    def test_automatic_music_plan_is_frozen_and_only_extended(self):
        first = self.directory / "one.wav"
        second = self.directory / "two.wav"
        third = self.directory / "three.wav"
        for index, path in enumerate((first, second, third)):
            tone(path, 1, 300 + index * 100)
        self.app.settings.update(music_folder=str(self.directory), trim_silence=False,
                                  crossfade_duration=0)
        self.app.music_tracker = {"available_music": [first.name, second.name, third.name],
                                  "used_music": []}
        self.app.project_audio = {"mode": "auto", "version": 1, "tracks": []}
        self.app._automatic_audio_cache = None
        initial = self.app.project_audio_plan(2.0)
        self.assertTrue(initial)
        first_path = Path(initial[0]["clips"][0]["path"]).name
        first_start = initial[0]["clips"][0]["start"]
        # Simulate the project remembering the plan.
        self.app.project_audio["tracks"] = copy.deepcopy(initial)
        same = self.app.project_audio_plan(1.5)
        self.assertEqual(same[0]["clips"][0]["path"], initial[0]["clips"][0]["path"])
        self.assertEqual(same[0]["clips"][0]["start"], first_start)
        extended = self.app.project_audio_plan(4.0)
        self.assertEqual(Path(extended[0]["clips"][0]["path"]).name, first_path)
        self.assertEqual(extended[0]["clips"][0]["start"], first_start)
        self.assertGreater(len(extended[0]["clips"]), len(initial[0]["clips"]))
        # Existing clips keep their old positions; only new clips are appended.
        for old, new in zip(initial[0]["clips"], extended[0]["clips"]):
            self.assertEqual((old["path"], old["start"], old["duration"]),
                             (new["path"], new["start"], new["duration"]))

    def test_auto_audio_plan_is_written_to_project_file(self):
        path = self.directory / "saved_project.json"
        path.write_text(json.dumps({"name": "x", "media_files": []}), encoding="utf-8")
        self.app.current_project = path
        self.app.project_audio = {"mode": "auto", "version": 1, "tracks": [
            new_track("Αυτόματη μουσική", id="auto-music", clips=[
                audio_clip(str(self.directory / "one.wav"), 2, 0)])]}
        self.assertTrue(self.app._persist_project_audio())
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["project_audio"]["tracks"][0]["clips"][0]["start"], 0)


if __name__ == "__main__":
    unittest.main()
