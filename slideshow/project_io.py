"""Project lifecycle and atomic JSON persistence (including chat and audio)."""

import copy
import json
import os
import re
from pathlib import Path
from tkinter import messagebox

from .project_extras import ProjectExtrasMixin
from .slide_design import normalize_template
from .slide_templates import LABEL_FOR_BASE, template_base

PROJECT_SETTING_KEYS = (
    "resolution", "background_mode", "cropping", "slide_duration",
    "transition_effect", "transition_duration", "random_transitions", "auto_position_photos",
)


class ProjectIOMixin(ProjectExtrasMixin):
    def new_project(self):
        self._commit_pending_caption_apply()
        self._stop_preview_play()
        self._reset_project_extras()
        if hasattr(self, "_global_settings"):
            for key in PROJECT_SETTING_KEYS:
                if key in self._global_settings:
                    self.settings[key] = copy.deepcopy(self._global_settings[key])
        self._active_project_settings = False
        self.project_settings = {}
        self.current_project = None
        self._active_presentation_scene_id = None
        self.name_var.set("")
        self.out_var.set(self.settings.get("output_folder", ""))
        self.media_files, self.library_media = [], []
        self.project_template_override = False
        self.project_template_name = self._default_template_name()
        self.project_template = template_base(self.project_template_name, self.template_registry())
        self._sync_caption_template_dropdown()
        self.project_caption_mode = "all"
        self.project_text_all = self.project_text_videos = self.project_text_photos = ""
        self.project_ai_instructions = ""
        self.project_watermark = {"enabled": False, "path": "", "position": "bottom_right",
                                  "size_pct": 15, "opacity": 80}
        self._video_frame_cache.clear()
        self._video_dur_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.selected_indices, self.library_selected_indices = set(), set()
        self.is_modified = False
        self.update_media_display()
        self._refresh_inspector_after_media(force=True)
        self._refresh_header()

    def save_project(self):
        self._stop_voiceover_capture(save=True)
        self._commit_pending_caption_apply()
        name = self.name_var.get().strip()
        safe = re.sub(r"\W+", "_", name).strip("_")
        if not name or not safe:
            messagebox.showwarning("Λείπει το όνομα", "Γράψε έγκυρο όνομα για το project πριν την αποθήκευση.")
            self._focus_name_entry()
            return False
        data = {
            "name": name, "media_files": self.media_files, "library_media": self.library_media,
            "text": self.project_text_all if self.project_caption_mode == "all" else self.project_text_videos,
            "text_videos": self.project_text_videos, "text_photos": self.project_text_photos,
            "ai_instructions": self.project_ai_instructions, "out": self.out_var.get(),
            "project_watermark": self.project_watermark, "project_template": self.project_template,
            "project_template_name": self.project_template_name,
            "project_template_override": bool(self.project_template_override),
            "project_settings": self._capture_project_settings(),
            "caption_mode": self.project_caption_mode, "caption_strategy_version": 1,
            "project_text_all": self.project_text_all, **self._project_extra_data(),
        }
        path = self.projects_dir / f"{safe}.json"
        try:
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(temporary, path)
        except OSError as error:
            messagebox.showerror("Σφάλμα", f"Δεν μπόρεσα να αποθηκεύσω το project:\n{error}")
            return False
        self.project_settings = copy.deepcopy(data["project_settings"])
        self._active_project_settings = bool(self.project_settings)
        self.is_modified = False
        self.current_project = path
        self.set_last_project(path)
        self._refresh_header()
        messagebox.showinfo("Saved", "Project saved.")
        return True

    def load_project_file(self, project_path, on_loaded=None):
        self._commit_pending_caption_apply()
        path = Path(project_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("Το αρχείο δεν είναι έγκυρο project.")
        except Exception as error:
            messagebox.showerror("Load Project", f"Δεν μπόρεσα να φορτώσω '{path.stem}':\n{error}")
            return False
        self._stop_preview_play()
        self._stop_voiceover_capture(save=True)
        if hasattr(self, "_global_settings"):
            for key in PROJECT_SETTING_KEYS:
                if key in self._global_settings:
                    self.settings[key] = copy.deepcopy(self._global_settings[key])
        self._migrate_global_video_position(data.get("project_settings", {}))
        had_template = "project_template" in data
        registry = self.template_registry()
        explicit = data.get("project_template_override")
        if explicit is None:
            explicit = bool(data.get("project_template_name")) or had_template
        name = str(data.get("project_template_name") or "").strip() if explicit else self._default_template_name(registry)
        if name not in registry:
            old = normalize_template(data.get("project_template", "legacy"), "legacy")
            name = LABEL_FOR_BASE.get(old, self._default_template_name(registry))
        self.project_template_name = name
        self.project_template = template_base(name, registry)
        self.project_template_override = bool(explicit)
        self._sync_caption_template_dropdown()
        self.project_settings = self._normalize_project_settings(data.get("project_settings", {}))
        self._active_project_settings = bool(self.project_settings)
        self.settings.update(self.project_settings)
        self.name_var.set(data.get("name", ""))
        self.media_files = self.normalize_media_list(data.get("media_files", data.get("media", [])))
        raw = data.get("library_media")
        if raw is None:
            raw = data.get("media_files", data.get("media", []))
        self.library_media = []
        for kind, source, saved in self.normalize_media_list(raw):
            item = self._new_item(kind, source)
            for key in ("library_id", "ai_description"):
                if saved.get(key):
                    item[2][key] = saved[key]
            self.library_media.append(item)
        self._ensure_library_ids()
        self._migrate_image_exif()
        if not had_template:
            for item in self.media_files:
                if item[2]["presentation"]["template"] == "legacy":
                    item[2]["presentation"]["template"] = "project"
        (self.project_text_videos, self.project_text_photos,
         self.project_caption_mode, self.project_text_all) = self._project_caption_values(data)
        self.project_ai_instructions = data.get("ai_instructions", "")
        self.out_var.set(data.get("out", ""))
        self.project_watermark = data.get("project_watermark", {
            "enabled": False, "path": "", "position": "bottom_right", "size_pct": 15, "opacity": 80})
        self._load_project_extras(data)
        self.is_modified = False
        self._video_frame_cache.clear()
        self._video_dur_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.selected_indices, self.library_selected_indices = set(), set()
        missing = self._resolve_existing_project_media(project_path)
        self.current_project = path
        self.set_last_project(path)
        self._refresh_header()
        if not missing:
            self.update_media_display()
        self._refresh_inspector_after_media(force=True)
        if on_loaded:
            on_loaded()
        if missing:
            self._show_missing_media_recovery(missing)
        return True

    def on_closing(self):
        self._stop_voiceover_capture(save=True)
        self._stop_preview_play()
        self._commit_pending_caption_apply()
        self._remember_workspace_layout()
        self._save_window_state()
        try:
            self.save_settings()
            self.save_music_tracker()
            self.save_profile_registry()
        except Exception:
            pass
        if self.is_modified:
            answer = messagebox.askyesnocancel("Έξοδος", "Να αποθηκευτεί το project πριν την έξοδο;")
            if answer is None or (answer and not self.save_project()):
                return
        self.root.destroy()
