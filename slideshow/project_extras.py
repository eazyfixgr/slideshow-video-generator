"""Per-project timeline/chat state, reset and persistence helpers."""

import copy
import uuid

from .timeline_model import empty_audio, normalize_audio


class ProjectExtrasMixin:
    def _reset_project_extras(self):
        if hasattr(self, "_stop_voiceover_capture"):
            self._stop_voiceover_capture(save=True)
        self.project_audio = empty_audio()
        self.ai_chat_history = []
        self.project_ai_brief = ""
        self._session_id = uuid.uuid4().hex
        self._automatic_audio_cache = None
        self._timeline_audio_key = None
        self._timeline_display_tracks = []
        self._timeline_waveforms = {}
        self._timeline_duration_pending = set()
        self._timeline_duration_attempted = set()
        self._playhead_seconds = 0.0
        self._refresh_chat_history()

    def _load_project_extras(self, data):
        self._reset_project_extras()
        self.project_audio = normalize_audio(data.get("project_audio"))
        self.project_ai_brief = str(data.get("ai_director_brief") or "")
        history = data.get("ai_chat_history")
        if not isinstance(history, list):
            history = []
        self.ai_chat_history = [
            {"role": item["role"], "content": str(item.get("content") or "")[:16000]}
            for item in history
            if isinstance(item, dict) and item.get("role") in ("user", "assistant")][-200:]
        self._refresh_chat_history()

    def _project_extra_data(self):
        audio = normalize_audio(getattr(self, "project_audio", empty_audio()))
        cache = getattr(self, "_automatic_audio_cache", None)
        if audio["mode"] == "auto" and not audio.get("tracks") and cache:
            audio["tracks"] = copy.deepcopy(cache["tracks"])
        return {"project_audio": audio,
                "ai_chat_history": copy.deepcopy(getattr(self, "ai_chat_history", []))[-200:],
                "ai_director_brief": getattr(self, "project_ai_brief", "")}

    def _refresh_chat_history(self):
        callback = getattr(self, "_chat_refresh_callback", None)
        if callback:
            try:
                callback()
            except Exception:
                self._chat_refresh_callback = None
