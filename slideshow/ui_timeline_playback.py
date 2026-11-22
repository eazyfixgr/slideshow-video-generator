"""A wall-clock playhead with synchronized mixed audio and composed preview frames."""

import copy
import shutil
import subprocess
import threading
import time

from .audio_engine import FLAGS, audio_fingerprint, mix_command
from .deps import Image
from .timeline_model import source_time


def timecode(seconds):
    milliseconds = max(0, round(float(seconds) * 1000))
    minutes, rest = divmod(milliseconds, 60000)
    return f"{minutes:02d}:{rest // 1000:02d}.{rest % 1000:03d}"


class TimelinePlaybackMixin:
    def stop_timeline_playback(self):
        self._preview_playing = False
        self._preview_loading = False
        self._playback_generation = getattr(self, "_playback_generation", 0) + 1
        job = getattr(self, "_preview_play_job", None)
        if job:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._preview_play_job = None
        process = getattr(self, "_timeline_audio_process", None)
        if process is not None and process.poll() is None:
            process.terminate()
        self._timeline_audio_process = None
        if hasattr(self, "play_btn"):
            self.play_btn.configure(text="▶")

    def toggle_timeline_playback(self):
        if getattr(self, "_preview_playing", False) or getattr(self, "_preview_loading", False):
            self.stop_timeline_playback()
            return
        if not self.media_files:
            return
        self._commit_pending_caption_apply()
        layout, total = self.timeline_layout()
        position = float(getattr(self, "_playhead_seconds", 0))
        if position >= total - .02:
            position = 0.0
        self._preview_loading = True
        token = getattr(self, "_playback_generation", 0) + 1
        self._playback_generation = token
        self.status.configure(text="Προετοιμασία ήχου timeline…")
        self.play_btn.configure(text="…")

        def prepared(path=None, error=None):
            if token != getattr(self, "_playback_generation", None):
                return
            self._preview_loading = False
            if error:
                self.status.configure(text=str(error))
                self.play_btn.configure(text="▶")
                return
            self.status.configure(text="Προεπισκόπηση timeline")
            self._start_timeline_clock(position, audio_path=path)

        def worker():
            try:
                tracks = self.project_audio_plan(total)
                video_audio = self.video_sound_clips(layout)
                if not tracks and not video_audio:
                    self._post_ui(prepared)
                    return
                key = audio_fingerprint(tracks, total, video_audio)
                folder = self.temp_dir / "timeline_preview"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"mix_{key}.wav"
                if not path.exists():
                    run = subprocess.run(mix_command(tracks, total, path, video_audio), capture_output=True,
                                         timeout=180, creationflags=FLAGS)
                    if run.returncode:
                        path.unlink(missing_ok=True)
                        raise RuntimeError(run.stderr.decode(errors="replace")[-400:])
                self._post_ui(prepared, path)
            except Exception as error:
                self._post_ui(prepared, None, str(error))
        threading.Thread(target=worker, daemon=True).start()

    def _start_timeline_clock(self, position, muted=False, audio_path=None):
        self.stop_timeline_playback()
        self._playhead_seconds = max(0.0, position)
        self._playback_start_position = self._playhead_seconds
        self._playback_clock = time.monotonic()
        if audio_path and not muted:
            ffplay = shutil.which("ffplay")
            if ffplay:
                self._timeline_audio_process = subprocess.Popen(
                    [ffplay, "-nodisp", "-autoexit", "-loglevel", "error", "-ss", f"{position:.6f}", str(audio_path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=FLAGS)
        self._preview_playing = True
        self.play_btn.configure(text="❚❚")
        self._timeline_tick()

    def _timeline_tick(self):
        if not self._preview_playing:
            return
        layout, total = self.timeline_layout()
        position = self._playback_start_position + time.monotonic() - self._playback_clock
        self._playhead_seconds = min(position, total)
        active = [item for item in layout if item["start"] <= position]
        if active:
            index = active[-1]["index"]
            self.stage_scene_var.set(f"Σκηνή {index + 1:02d} / {len(layout):02d}")
        self._draw_timeline_playhead()
        self._update_timeline_clock_label(total)
        self._request_timeline_frame(self._playhead_seconds, layout)
        if position >= total:
            self.stop_timeline_playback()
            return
        self._preview_play_job = self.root.after(50, self._timeline_tick)

    def seek_timeline(self, seconds, render=True):
        if getattr(self, "_voiceover_recording", False):
            return
        self.stop_timeline_playback()
        layout, total = self.timeline_layout()
        self._playhead_seconds = min(max(0, seconds), total)
        if layout:
            index = max((item["index"] for item in layout if item["start"] <= seconds), default=0)
            self.selected_indices = {index}
            self._refresh_selection()
            self._refresh_inspector_after_media()
        self._draw_timeline_playhead()
        self._update_timeline_clock_label(total)
        if render:
            self._request_timeline_frame(self._playhead_seconds, layout)

    def _update_timeline_clock_label(self, total=None):
        if total is None:
            _layout, total = self.timeline_layout()
        position = getattr(self, "_playhead_seconds", 0)
        if hasattr(self, "scene_clock_var"):
            self.scene_clock_var.set(f"{timecode(position)} / {timecode(total)}")
            self._set_scene_seek(position, max(.01, total))
        if hasattr(self, "timeline_clock_var"):
            self.timeline_clock_var.set(f"{timecode(position)} / {timecode(total)}")

    def _request_timeline_frame(self, seconds, layout):
        if not layout:
            return
        if not hasattr(self, "_frame_event"):
            self._frame_event = threading.Event()
            self._frame_stop = threading.Event()
            self._frame_request = None
            self.root.bind("<Destroy>", lambda event: self._frame_stop.set()
                           if event.widget is self.root else None, add="+")
            threading.Thread(target=self._timeline_frame_worker, daemon=True).start()
        self._frame_request = (seconds, copy.deepcopy(layout), copy.deepcopy(self.media_files),
                               getattr(self, "_playback_generation", 0),
                               tuple(map(int, self.settings["resolution"].split("x"))))
        self._frame_event.set()

    def _timeline_frame_worker(self):
        cache = {}
        cache_token = None
        while not self._frame_stop.is_set():
            if not self._frame_event.wait(.2):
                continue
            self._frame_event.clear()
            request = self._frame_request
            if not request:
                continue
            seconds, layout, media, token, (width, height) = request
            if token != cache_token:
                cache.clear()
                cache_token = token
            try:
                active = [item for item in layout if item["start"] <= seconds < item["end"]]
                if not active:
                    active = [layout[-1]]
                frames = []
                for timing in active[-2:]:
                    item = media[timing["index"]]
                    kind, path, edit = item
                    local = max(0.0, seconds - timing["start"])
                    progress = min(1.0, local / max(.01, timing["duration"]))
                    source_at = 0.0
                    if kind == "video":
                        full = self._video_dur_cache.get(str(path)) or self._video_duration(path)
                        source_at = source_time(self.video_keep_segments(edit, full), local)
                    key = repr((path, edit, self.project_text_all, self.project_text_photos,
                                self.project_text_videos, self.project_template_name, width, height))
                    moving = self._slide_background_mode(edit.get("presentation")) == "fit_and_move"
                    if kind == "image" and not moving and key in cache:
                        frame = cache[key]
                    else:
                        frame = self._preview_frame_image(path, kind, width, height, edit, source_at, progress)
                        if kind == "image" and not moving:
                            cache[key] = frame
                            if len(cache) > 30:
                                cache.pop(next(iter(cache)))
                    frames.append(frame)
                frame = frames[-1]
                if len(frames) > 1:
                    timing = active[-1]
                    blend = min(1.0, max(0.0, (seconds - timing["start"]) / max(.01, timing["overlap"])))
                    frame = Image.blend(frames[0].convert("RGB"), frames[-1].convert("RGB"), blend)
                self._post_ui(self._display_timeline_frame, token, frame)
            except Exception as error:
                self._post_ui(self.status.configure, {"text": f"Preview: {error}"})

    def _display_timeline_frame(self, token, frame):
        if token == getattr(self, "_playback_generation", 0):
            self._show_preview(self.preview_canvas, frame)
