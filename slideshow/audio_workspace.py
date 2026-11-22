"""Shared project music plan, audio analysis cache and source-video audio."""

import copy
import json
import threading
from pathlib import Path

from .audio_engine import analyze_audio, automatic_music
from .timeline_model import audio_clip, empty_audio, scene_timing


class AudioWorkspaceMixin:
    def timeline_layout(self):
        return scene_timing(self._estimate_export_clips(), self.settings)

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
        settings_key = json.dumps({key: self.settings.get(key) for key in (
            "music_folder", "volume_db", "crossfade_duration", "trim_silence")}, sort_keys=True)
        cached = getattr(self, "_automatic_audio_cache", None)
        if cached and cached["key"] == settings_key and cached["duration"] >= duration - .05:
            return copy.deepcopy(cached["tracks"])
        token = getattr(self, "_session_id", None)
        tracks = automatic_music(self.settings, self.music_tracker, duration,
                                 self._analyze_project_audio) if duration > 0 else []
        if token == getattr(self, "_session_id", None):
            self._automatic_audio_cache = {"key": settings_key, "duration": duration, "tracks": tracks}
        return copy.deepcopy(tracks)

    def _manual_audio(self):
        if not hasattr(self, "project_audio"):
            self.project_audio = empty_audio()
        if self.project_audio["mode"] == "auto":
            _layout, duration = self.timeline_layout()
            self.project_audio = {"version": 1, "mode": "manual",
                                  "tracks": self.project_audio_plan(duration)}
        return self.project_audio

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
