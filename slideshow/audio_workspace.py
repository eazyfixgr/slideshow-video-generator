"""Shared project music plan, audio analysis cache and source-video audio."""

import copy
import json
import os
import threading
from pathlib import Path

from .audio_engine import analyze_audio, automatic_music, extend_music
from .timeline_model import audio_clip, empty_audio, normalize_audio, scene_timing


class AudioWorkspaceMixin:
    def timeline_layout(self):
        return scene_timing(self._timeline_media_clips(), self.settings)

    def _timeline_media_clips(self):
        """Never probe a video on the Tk thread while opening/rendering a project."""
        default = float(self.settings.get("slide_duration", 3) or 3)
        clips = []
        for kind, path, edit in self.media_files:
            presentation = self._presentation_for(edit)
            if kind == "image":
                duration = presentation["duration"] or default
            else:
                full = self._video_dur_cache.get(str(path))
                if full:
                    kept = sum(length for _start, length in
                               self.video_keep_segments(edit, full))
                    duration = min(kept, presentation["duration"]) if presentation["duration"] else kept
                else:
                    duration = presentation["duration"] or default
                    self._queue_timeline_video_duration(path)
            clips.append({"type": "video" if kind == "video" else "image",
                          "duration": max(.1, float(duration or default)),
                          "transition": presentation.get("transition", "global"),
                          "transition_duration": presentation.get("transition_duration")})
        return clips

    def _queue_timeline_video_duration(self, path):
        key = str(path)
        if not hasattr(self, "_timeline_duration_pending"):
            self._timeline_duration_pending = set()
            self._timeline_duration_attempted = set()
        if key in self._timeline_duration_pending or key in self._timeline_duration_attempted:
            return
        self._timeline_duration_pending.add(key)
        token = getattr(self, "_session_id", None)

        def worker():
            try:
                duration = self._video_duration(key)
            except Exception:
                duration = 0
            self._post_ui(self._timeline_duration_ready, token, key, duration)
        threading.Thread(target=worker, daemon=True).start()

    def _timeline_duration_ready(self, token, path, duration):
        self._timeline_duration_pending.discard(path)
        self._timeline_duration_attempted.add(path)
        if token != getattr(self, "_session_id", None):
            return
        if duration and duration > 0:
            self._video_dur_cache[path] = duration
            self._timeline_audio_key = None
            if hasattr(self, "storyboard_canvas"):
                self.render_storyboard()
            refresh = getattr(self, "_refresh_export_estimate", None)
            if refresh:
                refresh()

    def _analyze_project_audio(self, path, trim=False):
        path = Path(path)
        key = (str(path), path.stat().st_mtime_ns)
        if not hasattr(self, "_audio_analysis_cache"):
            self._audio_analysis_cache = {}
            self._audio_analysis_lock = threading.Lock()
        with self._audio_analysis_lock:
            if key not in self._audio_analysis_cache:
                self._audio_analysis_cache[key] = analyze_audio(path, True)
            information = self._audio_analysis_cache[key]
            return information if trim else {**information, "offset": 0.0, "usable": information["duration"]}

    def project_audio_plan(self, duration):
        audio = getattr(self, "project_audio", empty_audio())
        if audio["mode"] == "manual":
            return copy.deepcopy(audio["tracks"])
        if audio.get("tracks"):
            coverage = max((clip["start"] + clip["duration"] for track in audio["tracks"]
                            for clip in track["clips"]), default=0)
            if coverage >= duration - .05:
                return copy.deepcopy(audio["tracks"])
            token = getattr(self, "_session_id", None)
            extended = extend_music(audio["tracks"], self.settings, self.music_tracker,
                                    duration, self._analyze_project_audio)
            if token == getattr(self, "_session_id", None):
                self._automatic_audio_cache = {"key": "project-plan",
                                               "duration": duration, "tracks": extended}
            return extended
        cached = getattr(self, "_automatic_audio_cache", None)
        if cached and cached.get("duration", 0) >= duration - .05:
            return copy.deepcopy(cached["tracks"])
        token = getattr(self, "_session_id", None)
        tracks = automatic_music(self.settings, self.music_tracker, duration,
                                 self._analyze_project_audio) if duration > 0 else []
        if token == getattr(self, "_session_id", None):
            self._automatic_audio_cache = {"key": "project-plan", "duration": duration,
                                           "tracks": tracks}
        return copy.deepcopy(tracks)

    def _manual_audio(self):
        if not hasattr(self, "project_audio"):
            self.project_audio = empty_audio()
        if self.project_audio["mode"] == "auto":
            _layout, duration = self.timeline_layout()
            self.project_audio = {"version": 1, "mode": "manual",
                                  "tracks": self.project_audio_plan(duration)}
        return self.project_audio

    def _persist_project_audio(self):
        """Remember the automatic song plan without overwriting unsaved edits."""
        path = getattr(self, "current_project", None)
        if not path:
            return False
        path = Path(path)
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                return False
            data["project_audio"] = normalize_audio(
                getattr(self, "project_audio", empty_audio()))
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
            return True
        except (OSError, ValueError, TypeError):
            return False

    def _audio_changed(self):
        self.is_modified = True
        self._stop_preview_play()
        self.render_storyboard()
        self._refresh_header()

    def video_sound_clips(self, layout):
        result = []
        for timing, item in zip(layout, self.media_files):
            kind, path, edit = item
            enabled = edit.get("audio")
            if enabled is None:
                enabled = bool(self.settings.get("video_audio", False))
            if kind != "video" or not enabled or not self._video_has_audio(path):
                continue
            full = self._video_dur_cache.get(str(path)) or self._video_duration(path)
            segments = self.video_keep_segments(edit, full)
            remaining, local = timing["duration"], 0.0
            for offset, length in segments:
                length = min(length, remaining)
                if length <= 0:
                    break
                result.append(audio_clip(str(path), length, timing["start"] + local,
                                          offset=offset,
                                          volume_db=float(self.settings.get("video_audio_volume_db", 0))))
                local += length
                remaining -= length
        return result
