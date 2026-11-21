"""SlideshowApp — the application shell: settings, projects, music, lifecycle.

The feature code lives in mixins; this class just composes them, so every
`self.<method>` keeps working exactly as it did in the single-file version.
"""

import faulthandler
import copy
import json
import os
import queue
import re
import sys
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
from typing import Dict, List, Optional

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .media_edit import MediaEditMixin
from .render import RenderMixin
from .export import ExportMixin
from .ui_library import LibraryMixin
from .media_recovery import MediaRecoveryMixin
from .ui_editors import EditorsMixin
from .ui_photo_editor import PhotoEditorMixin
from .ui_erase import EraseSettingsMixin
from .ui_timeline import TimelineMixin
from .ui_settings import SettingsMixin
from .ui_layout import LayoutMixin
from .ui_storyboard import StoryboardMixin
from .ui_inspector import InspectorMixin
from .ui_export_panel import ExportPanelMixin
from .ui_profile_dialogs import ProfileDialogsMixin
from .ui_preview import PreviewMixin
from .ui_text import TextInputMixin
from .ui_ai_text import AITextMixin, DEFAULT_BASE_URL
from .ui_ai_settings import AISettingsMixin
from .ui_ai_director import AIDirectorMixin
from .ui_presentation import PresentationMixin
from .ui_captions import CaptionsMixin
from .slide_design import normalize_template, normalize_presentation
from .slide_templates import (DEFAULT_KEY, LABEL_FOR_BASE, ensure_template_settings,
                              default_template_name, read_template_registry,
                              resolve_presentation, template_base)
from .ui_welcome import WelcomeMixin
from .ui_slideshow_settings import SlideshowSettingsMixin
from .ui_theme import ThemeMixin
from .profiles import (active_profile as registry_active_profile, create_profile,
                       ensure_profile_paths, get_profile, last_project_path,
                       load_registry, save_registry, set_active,
                       set_last_project as registry_set_last_project, update_profile)


# Where settings.json, projects/, music/, temp/ and models/ live.
# - normal run: the folder that holds the launcher (parent of this package)
# - frozen .exe: the folder that holds the .exe, so the build is portable
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent.parent

PROJECT_SETTING_KEYS = (
    "resolution", "background_mode", "cropping", "slide_duration",
    "transition_effect", "transition_duration", "random_transitions",
    "auto_position_photos",
)
PROJECT_RESOLUTIONS = {"1080x1080", "1920x1080", "1080x1920", "1080x1350", "720x1280"}
PROJECT_BACKGROUNDS = {"white", "black", "blur", "fit_and_move"}
PROJECT_TRANSITIONS = {"none", "fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                       "wipeup", "wipedown", "smoothleft", "smoothright", "random"}


class SlideshowApp(MediaEditMixin, RenderMixin, ExportMixin, LibraryMixin, StoryboardMixin, MediaRecoveryMixin, EditorsMixin, PhotoEditorMixin, EraseSettingsMixin, TimelineMixin, PresentationMixin, ProfileDialogsMixin, WelcomeMixin, ThemeMixin, SlideshowSettingsMixin, SettingsMixin, InspectorMixin, ExportPanelMixin, LayoutMixin, PreviewMixin, CaptionsMixin, TextInputMixin, AITextMixin, AISettingsMixin, AIDirectorMixin):
    """Composes every mixin above into the one application object."""

    def __init__(self, root, show_welcome=True):
        self.root = root
        if show_welcome:
            try:
                self.root.withdraw()
            except tk.TclError:
                pass
        self.root.title("Slideshow Video Creator Pro")
        self.root.geometry("1550x950")

        self.app_dir = APP_DIR
        self._use_local_ffmpeg()
        legacy_data = ((self.app_dir / "settings.json").exists() or
                       (self.app_dir / "music_tracker.json").exists() or
                       any((self.app_dir / "projects").glob("*.json")))
        self.profiles_data = load_registry(self.app_dir, legacy_data=legacy_data)
        self.active_profile_id = self.profiles_data["active_profile"]
        self.active_profile_data = registry_active_profile(self.profiles_data)
        self._needs_profile_setup = not bool(
            self.active_profile_data.get("onboarded", True))
        self._profile_setup_dialog = None
        self._apply_profile_paths()
        try:
            self._root_hidden_until_welcome = (show_welcome or
                                               self.root.state() == "withdrawn")
        except tk.TclError:
            self._root_hidden_until_welcome = bool(show_welcome)
        self._shell_poll_job = None

        # Tkinter is single-threaded: worker threads must never touch widgets or
        # call `after()` directly (that can crash the whole interpreter). They
        # enqueue callables here and the main thread drains the queue.
        self._ui_queue = queue.Queue()
        self._ui_pump_job = None
        self._crash_log_file = None
        self._enable_crash_logging()

        self.current_project = None
        self.project_template = "legacy"
        self.project_settings = {}
        self._active_project_settings = False
        self.project_caption_mode = "all"
        self.project_text_all = ""
        self.media_files = []
        self.library_media = []
        self.is_modified = False
        self.thumbnails = []
        self.view_mode = tk.StringVar(value="thumbnails")
        self.project_text_videos = ""
        self.project_text_photos = ""
        self.project_ai_instructions = ""
        self._resize_timer = None
        self._preview_job = None
        self._export_cancel = False
        self._export_proc = None
        self._video_frame_cache = {}  # first-frame per video path (rotation-corrected)
        self._video_dur_cache = {}    # duration per video path (library display)
        self.selected_indices = set()  # project/storyboard selection
        self.library_selected_indices = set()  # available-media selection
        self._sel_anchor = None
        self._library_anchor = None
        self._active_media_panel = "project"
        self._undo_stack = []
        self._redo_stack = []
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }

        self.load_settings()
        if ensure_template_settings(
                self.settings, legacy_font_size=self.settings.get("font_size"),
                legacy_font_family=self.settings.get("font_family"),
                legacy_text_style=self.settings.get("text_style")):
            self.save_settings()
        self._drop_legacy_text_settings()
        self._template_registry_cache = None
        self._init_project_template_state()
        self._global_settings = copy.deepcopy(self.settings)
        self.apply_ui_theme()
        self.view_mode.set(self.settings.get("view_mode", "thumbnails"))
        self.load_music_tracker()
        self.setup_menu()
        self.setup_gui()
        self.apply_ui_theme()
        self.setup_shortcuts()
        self._restore_window_state()

        # Warm the LaMa erase model in the background: creating its ONNX
        # session costs ~20s, and doing it at startup means the user's first
        # erase is instant instead of a 20s freeze.
        try:
            self._erase_engine().prewarm()
        except Exception:
            pass

        self.root.report_callback_exception = self._report_callback_exception
        self._ui_pump_job = self.root.after(25, self._pump_ui_queue)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        if show_welcome:
            self.root.after(120, self.show_welcome_screen)


    def _enable_crash_logging(self):
        """Keep a native traceback in crash.log if the process dies hard."""
        try:
            self._crash_log_file = open(self.app_dir / "crash.log", "a",
                                        encoding="utf-8", buffering=1)
            faulthandler.enable(file=self._crash_log_file, all_threads=True)
        except Exception:
            self._crash_log_file = None


    def _report_callback_exception(self, exc, val, tb):
        """Log Tk callback errors instead of dying silently (frozen builds)."""
        try:
            if self._crash_log_file is not None:
                self._crash_log_file.write("\n--- Tkinter callback error ---\n")
                traceback.print_exception(exc, val, tb, file=self._crash_log_file)
        except Exception:
            pass
        try:
            messagebox.showerror("Error", f"{exc.__name__}: {val}")
        except Exception:
            pass


    def _post_ui(self, func, *args, **kwargs):
        """Run ``func`` on the Tk main thread from any thread (thread-safe)."""
        self._ui_queue.put((func, args, kwargs))


    def _pump_ui_queue(self):
        self._ui_pump_job = None
        while True:
            try:
                func, args, kwargs = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                func(*args, **kwargs)
            except Exception:
                try:
                    traceback.print_exc()
                except Exception:
                    pass
                if self._crash_log_file is not None:
                    try:
                        traceback.print_exc(file=self._crash_log_file)
                    except Exception:
                        pass
        try:
            self._ui_pump_job = self.root.after(25, self._pump_ui_queue)
        except tk.TclError:
            self._ui_pump_job = None


    def setup_shortcuts(self):
        """Keyboard shortcuts for the most common actions."""
        self.root.bind("<Control-s>", lambda e: self._shortcut(self.save_project))
        self.root.bind("<Control-S>", lambda e: self._shortcut(self.save_project))
        self.root.bind("<Control-o>", lambda e: self._shortcut(self.load_project))
        self.root.bind("<Control-O>", lambda e: self._shortcut(self.load_project))
        self.root.bind("<Control-n>", lambda e: self._shortcut(self.new_project))
        self.root.bind("<Control-N>", lambda e: self._shortcut(self.new_project))
        self.root.bind("<Control-z>", lambda e: self._shortcut(self.undo))
        self.root.bind("<Control-Z>", lambda e: self._shortcut(self.undo))
        self.root.bind("<Control-y>", lambda e: self._shortcut(self.redo))
        self.root.bind("<Control-Y>", lambda e: self._shortcut(self.redo))
        self.root.bind("<Delete>", self._on_delete_key)
        self.root.bind("<F5>", lambda e: self._shortcut(self.generate_preview))

    @staticmethod
    def _is_text_widget(widget):
        return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox))

    def _shortcut(self, func):
        # Never steal Ctrl combos while the user types in an entry/text box.
        if self._is_text_widget(self.root.focus_get()):
            return None
        func()
        return "break"

    def _on_delete_key(self, event):
        if self._is_text_widget(self.root.focus_get()):
            return None
        if getattr(self, "_active_media_panel", "project") == "library":
            self.delete_library_selected()
        else:
            self.delete_selected()
        return "break"


    def _restore_window_state(self):
        """Restore geometry, but never map the editor behind the welcome screen."""
        try:
            hidden = self.root.state() == "withdrawn"
        except tk.TclError:
            hidden = True
        geo = self.settings.get("window_geometry")
        if geo:
            try:
                self.root.geometry(geo)
            except tk.TclError:
                pass
        if hidden:
            self._start_maximized = True
            return
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass


    def _save_window_state(self):
        try:
            if self.root.state() == "normal":
                self.settings["window_geometry"] = self.root.geometry()
        except tk.TclError:
            pass
        self.settings["view_mode"] = self.view_mode.get()



    def _apply_profile_paths(self):
        """Point the whole app at the active profile's workspace."""
        paths = ensure_profile_paths(self.app_dir, self.active_profile_data)
        self.profile_paths = paths
        self.settings_file = paths["settings"]
        self.projects_dir = paths["projects"]
        self.music_tracker_file = paths["music_tracker"]
        self.temp_dir = paths["temp"]

    def _default_music_folder(self):
        return self.profile_paths["music"]

    def _default_output_folder(self):
        return self.profile_paths["output"]

    def _drop_legacy_text_settings(self):
        """Font size/family now live inside each template, not in global settings."""
        changed = False
        for key in ("font_size", "font_family"):
            if key in self.settings:
                self.settings.pop(key, None)
                changed = True
        if changed:
            self.save_settings()

    def template_registry(self, refresh=False):
        cache = getattr(self, "_template_registry_cache", None)
        if refresh or cache is None:
            cache = read_template_registry(self.settings)
            self._template_registry_cache = cache
        return cache

    def _default_template_name(self, registry=None):
        return default_template_name(self.settings, registry or self.template_registry())

    def _init_project_template_state(self):
        registry = self.template_registry(refresh=True)
        name = self._default_template_name(registry)
        self.project_template_name = name
        self.project_template_override = False
        self.project_template = template_base(name, registry)

    def _effective_project_template_name(self, registry=None):
        registry = registry or self.template_registry()
        if (getattr(self, "project_template_override", False) and
                getattr(self, "project_template_name", "") in registry):
            return self.project_template_name
        return self._default_template_name(registry)

    def _effective_project_template(self, registry=None):
        registry = registry or self.template_registry()
        name = self._effective_project_template_name(registry)
        return name, template_base(name, registry)

    def set_project_template(self, name, mark_modified=True):
        registry = self.template_registry()
        if name not in registry:
            return False
        self.project_template_name = name
        self.project_template_override = True
        self.project_template = template_base(name, registry)
        if mark_modified:
            self.is_modified = True
        self._refresh_after_template_change()
        return True

    def reset_project_template(self, mark_modified=True):
        registry = self.template_registry(refresh=True)
        self.project_template_override = False
        self.project_template_name = self._default_template_name(registry)
        self.project_template = template_base(self.project_template_name, registry)
        if mark_modified:
            self.is_modified = True
        self._refresh_after_template_change()
        return True

    def set_default_template(self, name):
        registry = self.template_registry()
        if name not in registry:
            return False
        self.settings[DEFAULT_KEY] = name
        self.settings["last_caption_template"] = template_base(name, registry)
        self.settings["last_caption_template_is_global"] = True
        self.save_settings()
        self._template_registry_cache = None
        if not getattr(self, "project_template_override", False):
            registry = self.template_registry(refresh=True)
            self.project_template_name = self._default_template_name(registry)
            self.project_template = template_base(self.project_template_name, registry)
        self._refresh_after_template_change()
        return True

    def _refresh_after_template_change(self):
        registry = self.template_registry()
        self.project_template_name = self._effective_project_template_name(registry)
        self.project_template = template_base(self.project_template_name, registry)
        self._template_registry_cache = registry
        if hasattr(self, "media_canvas"):
            self.update_media_display()
        if hasattr(self, "inspector_content"):
            self._render_inspector()
        if hasattr(self, "preview_canvas"):
            self._schedule_preview(80)
        if hasattr(self, "storyboard_inner"):
            self.render_storyboard()
        self._refresh_header()

    def _resolve_presentation_style(self, presentation):
        registry = self.template_registry()
        project_name = (self.project_template_name
                        if getattr(self, "project_template_override", False) else "")
        return resolve_presentation(
            presentation, getattr(self, "project_template", "legacy"),
            project_name, self._default_template_name(registry), registry)

    def get_active_profile(self):
        return self.active_profile_data

    def save_profile_registry(self):
        save_registry(self.app_dir, self.profiles_data)

    def complete_profile_onboarding(self, name, role="", color=None):
        profile = self.active_profile_data
        update_profile(self.profiles_data, profile["id"], name=name, role=role,
                       color=color or profile.get("color"), onboarded=True)
        self.save_profile_registry()
        self.active_profile_data = get_profile(
            self.profiles_data, self.active_profile_id) or profile
        self._needs_profile_setup = False
        self._refresh_header()
        return self.active_profile_data

    def switch_profile(self, profile_id):
        """Save the current profile and reopen the app on another workspace."""
        self._commit_pending_caption_apply()
        if profile_id == self.active_profile_id:
            return True
        profile = get_profile(self.profiles_data, profile_id)
        if profile is None:
            return False
        self._remember_workspace_layout()
        try:
            self.save_settings()
            self.save_music_tracker()
        except Exception:
            pass
        if not set_active(self.profiles_data, profile_id):
            return False
        self.save_profile_registry()
        self.active_profile_id = profile_id
        self.active_profile_data = profile
        self._active_project_settings = False
        self.project_settings = {}
        self._apply_profile_paths()
        self.load_settings()
        if ensure_template_settings(
                self.settings, legacy_font_size=self.settings.get("font_size"),
                legacy_font_family=self.settings.get("font_family"),
                legacy_text_style=self.settings.get("text_style")):
            self.save_settings()
        self._drop_legacy_text_settings()
        self._template_registry_cache = None
        self._init_project_template_state()
        self._load_profile_workspace_layout()
        self._global_settings = copy.deepcopy(self.settings)
        self.apply_ui_theme()
        self.load_music_tracker()
        stop_play = getattr(self, "_stop_preview_play", None)
        if stop_play:
            stop_play()
        self.current_project = None
        self.media_files = []
        self.library_media = []
        self.selected_indices = set()
        self.library_selected_indices = set()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.is_modified = False
        self._active_presentation_scene_id = None
        if hasattr(self, "name_var"):
            self.name_var.set("")
            self.out_var.set(self.settings.get("output_folder", ""))
        self.project_caption_mode = "all"
        self.project_text_all = ""
        self.project_text_photos = ""
        self.project_text_videos = ""
        self.project_ai_instructions = ""
        self._sync_caption_template_dropdown()
        if hasattr(self, "thumb_frame"):
            self.update_media_display()
        self._refresh_inspector_after_media(force=True)
        self._refresh_header()
        return True

    def create_new_profile(self, name, role="", color=None):
        profile = create_profile(self.profiles_data, self.app_dir, name, role, color)
        self.switch_profile(profile["id"])
        return profile

    def set_last_project(self, project_path):
        try:
            registry_set_last_project(self.app_dir, self.profiles_data,
                                      self.active_profile_id, project_path)
            self.active_profile_data = get_profile(
                self.profiles_data, self.active_profile_id) or self.active_profile_data
        except Exception:
            pass

    def get_last_project(self):
        return last_project_path(self.app_dir, self.active_profile_data,
                                 self.projects_dir)

    def _refresh_header(self):
        refresh = getattr(self, "_update_header_widgets", None)
        if refresh:
            try:
                refresh()
            except tk.TclError:
                pass

    def return_to_welcome(self):
        """Hide the editor and show the profile / recent-project screen."""
        commit_captions = getattr(self, "_commit_pending_caption_apply", None)
        if commit_captions:
            commit_captions()
        if self.is_modified:
            answer = messagebox.askyesnocancel(
                "Έναρξη",
                "Έχεις μη αποθηκευμένες αλλαγές στο project.\n\n"
                "Πάτα 'Yes' για αποθήκευση και επιστροφή,\n"
                "'No' για επιστροφή χωρίς αποθήκευση,\n"
                "'Cancel' για να μείνεις στον editor.")
            if answer is None:
                return False
            if answer and not self.save_project():
                return False
            if not answer:
                self.is_modified = False
        self._remember_workspace_layout()
        self._save_window_state()
        try:
            self.save_settings()
        except Exception:
            pass
        stop_play = getattr(self, "_stop_preview_play", None)
        if stop_play:
            stop_play()
        export_window = getattr(self, "export_window", None)
        if export_window is not None:
            try:
                export_window.withdraw()
            except tk.TclError:
                pass
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        self.show_welcome_screen()
        return True

    def _use_local_ffmpeg(self):
        """Prefer a bundled FFmpeg placed next to the app by install.ps1.

        The installer drops ffmpeg.exe / ffprobe.exe in an ``ffmpeg`` folder so
        the app works on a PC without FFmpeg in the system PATH. Prepending the
        folder here means every ``subprocess`` call finds it first.
        """
        local = self.app_dir / "ffmpeg"
        if (local / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(local) + os.pathsep + os.environ.get("PATH", "")
            return
        # A frozen build can also carry ffmpeg inside its bundle.
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle and (Path(bundle) / "ffmpeg" / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(Path(bundle) / "ffmpeg") + os.pathsep + os.environ.get("PATH", "")


    def load_settings(self):
        default_settings = {
            "ui_theme": "modern",
            "volume_db": 0, "resolution": "1080x1080", "background_mode": "blur",
            "cropping": False,
            "text_style": "black_box", "auto_position_photos": False,
            "auto_position_videos": False, "mute_video_audio": True,
            "output_folder": str(self._default_output_folder()), "slide_duration": 3,
            "export_quality": "high", "facebook_target_mb": 95,
            "last_caption_template": "legacy",
            "last_caption_template_is_global": False,
            "auto_position_videos_is_global": False,
            "render_live_preview": False,
            "music_folder": str(self._default_music_folder()), "crossfade_duration": 3,
            "trim_silence": True,
            "transition_effect": "fade", "transition_duration": 0.7, "random_transitions": [],
            "watermark_enabled": False, "watermark_path": "", "watermark_position": "bottom_right",
            "watermark_size_pct": 15, "watermark_opacity": 80,
            # Text watermark (e.g. name / phone) - independent of the image logo.
            "watermark_text_enabled": False, "watermark_text": "",
            "watermark_text_position": "bottom_left",
            "watermark_text_size_pct": 6, "watermark_text_opacity": 90,
            "watermark_text_color": "#ffffff",
            # Remembered size of the photo/video Edit dialogs.
            "edit_fullscreen": False,
            # Global brightness / saturation applied to every photo or video,
            # on top of each item's own Edit values (they multiply).
            "photo_brightness": 1.0, "photo_color": 1.0,
            "video_brightness": 1.0, "video_color": 1.0,
            # Whether the sound of the source videos is heard at all (mixed under
            # the music). Each video can override this from its Edit dialog.
            "video_audio": False,
            "video_audio_volume_db": 0,
            "video_auto_position_fill": "panel",
            # Inpainting model for object erasing ("lama" or "migan").
            "erase_model": "lama",
            # Optional AI text improvement (inert until a key is stored here;
            # the per-project instructions live in the project JSON instead).
            # ai_provider: "deepseek" (cloud, needs a key) or "local" (an
            # OpenAI-compatible server on this PC, e.g. Ollama / llama.cpp).
            "ai_enabled": False, "ai_api_key": "", "ai_model": "deepseek-chat",
            "ai_base_url": DEFAULT_BASE_URL, "ai_global_instructions": "",
            "ai_provider": "deepseek",
            "ai_local_url": "http://localhost:11434/v1",
            "ai_local_model": "llama3.1",
            "ai_director_provider": "deepseek",
            "ai_director_api_key": "",
            "ai_director_base_url": DEFAULT_BASE_URL,
            "ai_director_model": "deepseek-chat",
            "ai_director_vision": False,
            "ai_director_vision_model": "",
            "ai_director_max_images": 8,
            "ai_director_style": "",
        }
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self.settings = {**default_settings, **json.load(f)}
            except:
                self.settings = default_settings
        else:
            self.settings = default_settings
            self.save_settings()
        for key in ("music_folder", "output_folder"):
            value = self.settings.get(key)
            if isinstance(value, str) and value:
                try:
                    os.makedirs(value, exist_ok=True)
                except OSError:
                    pass


    def save_settings(self):
        if self._active_project_settings and hasattr(self, "_global_settings"):
            current_project_settings = self._capture_project_settings()
            if current_project_settings != self.project_settings:
                self.is_modified = True
            self.project_settings = current_project_settings
            stored = copy.deepcopy(self._global_settings)
            for key, value in self.settings.items():
                if key not in PROJECT_SETTING_KEYS:
                    stored[key] = copy.deepcopy(value)
            self._global_settings = copy.deepcopy(stored)
        else:
            stored = self.settings
            self._global_settings = copy.deepcopy(self.settings)
        temp_file = self.settings_file.with_name(self.settings_file.name + ".tmp")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(stored, f, indent=2)
        os.replace(temp_file, self.settings_file)
        self._template_registry_cache = None


    def _capture_project_settings(self):
        return {key: copy.deepcopy(self.settings[key]) for key in PROJECT_SETTING_KEYS
                if key in self.settings}


    @staticmethod
    def _normalize_project_settings(value):
        if not isinstance(value, dict):
            return {}
        out = {}
        resolution = value.get("resolution")
        if isinstance(resolution, str) and resolution in PROJECT_RESOLUTIONS:
            out["resolution"] = resolution
        background = value.get("background_mode")
        if isinstance(background, str) and background in PROJECT_BACKGROUNDS:
            out["background_mode"] = background
        if isinstance(value.get("cropping"), bool):
            out["cropping"] = value["cropping"]
        if "slide_duration" in value:
            try:
                out["slide_duration"] = max(1, min(30, int(value["slide_duration"])))
            except (TypeError, ValueError):
                pass
        transition = value.get("transition_effect")
        if isinstance(transition, str) and transition in PROJECT_TRANSITIONS:
            out["transition_effect"] = transition
        if "transition_duration" in value:
            try:
                duration = float(value["transition_duration"])
                out["transition_duration"] = max(0.2, min(2.0, duration))
            except (TypeError, ValueError):
                pass
        random_transitions = value.get("random_transitions")
        if isinstance(random_transitions, list):
            out["random_transitions"] = list(dict.fromkeys(
                transition for transition in random_transitions
                if isinstance(transition, str) and transition in PROJECT_TRANSITIONS and
                transition != "random"))
        if isinstance(value.get("auto_position_photos"), bool):
            out["auto_position_photos"] = value["auto_position_photos"]
        return out


    def _migrate_global_video_position(self, legacy_project_settings):
        """Promote a legacy project's video-position settings to app-wide defaults."""
        if (self.settings.get("auto_position_videos_is_global") or
                not isinstance(legacy_project_settings, dict)):
            return
        found = False
        old_enabled = legacy_project_settings.get("auto_position_videos")
        if isinstance(old_enabled, bool):
            found = True
            self.settings["auto_position_videos"] = (
                bool(self.settings.get("auto_position_videos")) or old_enabled)
        old_fill = legacy_project_settings.get("video_auto_position_fill")
        if old_fill in ("panel", "blur"):
            found = True
            if (self.settings.get("video_auto_position_fill", "panel") == "panel" and
                    old_fill == "blur"):
                self.settings["video_auto_position_fill"] = old_fill
        if found:
            self.settings["auto_position_videos_is_global"] = True


    def _resolve_project_template_default(self, project_data):
        """Use the remembered template across projects, migrating a legacy choice once."""
        preferred = normalize_template(self.settings.get("last_caption_template", "legacy"))
        global_choice = bool(self.settings.get("last_caption_template_is_global"))
        if not global_choice and preferred != "legacy":
            global_choice = True
            self.settings["last_caption_template_is_global"] = True
        if not global_choice:
            saved_choice = normalize_template(project_data.get("project_template", "legacy"))
            if saved_choice != "legacy":
                preferred = saved_choice
                self.settings["last_caption_template"] = preferred
                self.settings["last_caption_template_is_global"] = True
                global_choice = True
        return preferred if global_choice else normalize_template(
            project_data.get("project_template", preferred))


    @staticmethod
    def _project_caption_values(data):
        """Preserve older mixed captions while migrating to three explicit strategies."""
        old_text = data.get("text", "")
        video_text = data.get("text_videos", old_text) or ""
        photo_text = data.get("text_photos", "") or ""
        mode = data.get("caption_mode")
        shared = str(data.get("project_text_all") or "")
        if mode not in ("all", "by_type", "individual"):
            mode = ("by_type" if video_text.strip() and photo_text.strip()
                    and video_text.strip() != photo_text.strip() else "all")
        if mode == "all" and not shared and not data.get("caption_strategy_version"):
            shared = video_text or photo_text
        if not data.get("caption_strategy_version"):
            media = data.get("media_files", data.get("media", []))
            individual = any(
                isinstance(item, (list, tuple)) and len(item) > 2 and
                isinstance(item[2], dict) and
                normalize_presentation(item[2].get("presentation"))["mode"] != "global"
                for item in media or [])
            if individual:
                if mode == "all":
                    video_text = photo_text = shared
                mode = "individual"
        return video_text, photo_text, mode, shared


    def load_music_tracker(self):
        if self.music_tracker_file.exists():
            try:
                with open(self.music_tracker_file, 'r', encoding='utf-8') as f:
                    self.music_tracker = json.load(f)
            except:
                self.music_tracker = {"used_music": [], "available_music": []}
        else:
            self.music_tracker = {"used_music": [], "available_music": []}
            self.refresh_music_list(silent=True)


    def save_music_tracker(self):
        temp_file = self.music_tracker_file.with_name(self.music_tracker_file.name + ".tmp")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.music_tracker, f, indent=2)
        os.replace(temp_file, self.music_tracker_file)


    def refresh_music_list(self, silent=False):
        music_path = Path(self.settings["music_folder"])
        if not music_path.exists():
            self.music_tracker["available_music"] = []
        else:
            self.music_tracker["available_music"] = sorted([str(f.name) for f in music_path.glob("*.mp4")])
        self.save_music_tracker()
        if not silent:
            messagebox.showinfo("Success", f"Found {len(self.music_tracker['available_music'])} music files")


    def get_next_music(self) -> Optional[str]:
        available = self.music_tracker.get("available_music", [])
        used = self.music_tracker.get("used_music", [])
        music_path = Path(self.settings["music_folder"])
        unused = [m for m in available if m not in used]
        if not unused:
            self.music_tracker["used_music"] = []
            unused = available
        if unused:
            return str(music_path / unused[0])
        return None


    def mark_music_used(self, music_file: str):
        name = Path(music_file).name
        if "used_music" not in self.music_tracker:
            self.music_tracker["used_music"] = []
        if name not in self.music_tracker["used_music"]:
            self.music_tracker["used_music"].append(name)


    def reset_music_tracker(self):
        self.music_tracker["used_music"] = []
        self.save_music_tracker()
        messagebox.showinfo("Reset", "Music tracker reset. All songs are available again.")


    def new_project(self):
        self._commit_pending_caption_apply()
        stop_play = getattr(self, "_stop_preview_play", None)
        if stop_play:
            stop_play()
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
        self.media_files = []
        self.library_media = []
        self.project_template_override = False
        self.project_template_name = self._default_template_name()
        self.project_template = template_base(self.project_template_name,
                                              self.template_registry())
        self._sync_caption_template_dropdown()
        self.project_caption_mode = "all"
        self.project_text_all = ""
        self.project_text_videos = ""
        self.project_text_photos = ""
        self.project_ai_instructions = ""
        self.project_watermark = {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        }
        self._video_frame_cache.clear()
        self._video_dur_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.selected_indices = set()
        self.library_selected_indices = set()
        self.is_modified = False
        self.update_media_display()
        self._refresh_inspector_after_media(force=True)
        self._refresh_header()


    def _migrate_image_exif(self):
        """Remember EXIF orientation for projects saved before auto-rotation."""
        for kind, path, edit in getattr(self, "media_files", []):
            if kind != "image" or not isinstance(edit, dict):
                continue
            if edit.get("exif_orientation"):
                continue
            try:
                rotate = int(edit.get("rotate", 0) or 0) % 360
            except (TypeError, ValueError):
                rotate = 0
            if rotate:
                continue
            orientation = self.read_exif_orientation(path)
            if orientation != 1:
                edit["exif_orientation"] = orientation

    def save_project(self):
        """Save the project. Returns True when it was saved, False otherwise.

        A project without a name is refused (that used to create a stray
        ``.json`` file and an empty entry in the Load list) and the name field
        is focused so the user can fix it.
        """
        commit_captions = getattr(self, "_commit_pending_caption_apply", None)
        if commit_captions:
            commit_captions()
        n = self.name_var.get().strip()
        if not n:
            messagebox.showwarning(
                "Λείπει το όνομα",
                "Γράψε πρώτα ένα όνομα για το project (πεδίο «Project Name», πάνω-δεξιά) "
                "και μετά πάτα Αποθήκευση.")
            self._focus_name_entry()
            return False

        safe = re.sub(r'\W+', '_', n).strip('_')
        if not safe:
            messagebox.showwarning(
                "Μη έγκυρο όνομα",
                "Το όνομα πρέπει να περιέχει τουλάχιστον ένα γράμμα ή αριθμό.")
            self._focus_name_entry()
            return False

        data = {
            "name": n,
            "media_files": self.media_files,
            "library_media": self.library_media,
            "text": (self.project_text_all if self.project_caption_mode == "all"
                     else self.project_text_videos),
            "text_videos": self.project_text_videos,
            "text_photos": self.project_text_photos,
            "ai_instructions": self.project_ai_instructions,
            "out": self.out_var.get(),
            "project_watermark": self.project_watermark,
            "project_template": self.project_template,
            "project_template_name": self.project_template_name,
            "project_template_override": bool(self.project_template_override),
            "project_settings": self._capture_project_settings(),
            "caption_mode": self.project_caption_mode,
            "caption_strategy_version": 1,
            "project_text_all": self.project_text_all,
        }
        p = self.projects_dir / f"{safe}.json"
        try:
            temp_file = p.with_name(p.name + ".tmp")
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, p)
        except OSError as e:
            messagebox.showerror("Σφάλμα", f"Δεν μπόρεσα να αποθηκεύσω το project:\n{e}")
            return False
        self.project_settings = copy.deepcopy(data["project_settings"])
        self._active_project_settings = bool(self.project_settings)
        self.is_modified = False
        self.current_project = p
        self.set_last_project(p)
        self._refresh_header()
        messagebox.showinfo("Saved", "Project saved.")
        return True


    def _focus_name_entry(self):
        entry = getattr(self, "name_entry", None)
        if entry is None:
            return
        try:
            entry.focus_set()
            entry.selection_range(0, tk.END)
        except tk.TclError:
            pass


    def load_project(self, on_loaded=None, project_path=None):
        if project_path is not None:
            return self.load_project_file(project_path, on_loaded=on_loaded)
        d = tk.Toplevel(self.root)
        d.title("Load Project")
        d.geometry("400x500")
        d.transient(getattr(self, "_welcome_dialog", None) or self.root)
        d.grab_set()
        
        # Search field at the top
        search_frame = ttk.Frame(d)
        search_frame.pack(fill='x', padx=10, pady=(10, 5))
        ttk.Label(search_frame, text="🔍 Αναζήτηση:").pack(side='left', padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side='left', fill='x', expand=True)
        search_entry.focus_set()
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(d)
        list_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        lb = tk.Listbox(list_frame, width=50)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=scrollbar.set)
        lb.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        pfs = sorted(list(self.projects_dir.glob("*.json")), key=os.path.getmtime, reverse=True)

        def display_name(p):
            # A project saved without a name (older bug) has an empty stem.
            return p.stem or "(χωρίς όνομα)"

        for p in pfs:
            lb.insert(tk.END, display_name(p))
        
        def filter_projects(*args):
            search_text = search_var.get().lower()
            lb.delete(0, tk.END)
            for p in pfs:
                if search_text in display_name(p).lower():
                    lb.insert(tk.END, display_name(p))
            # Reset the scroll position after rebuilding the list: otherwise a
            # list scrolled to the bottom shows a blank area when the filter
            # returns only a few results, and the project looks "missing".
            if lb.size():
                lb.yview_moveto(0)
                lb.selection_clear(0, tk.END)
                lb.selection_set(0)
                lb.activate(0)
        
        search_var.trace_add('write', filter_projects)
        
        def do_load():
            if not lb.curselection():
                if not lb.size():
                    return
                lb.selection_set(0)
            # Find the actual index in pfs matching the selected display name
            selected_name = lb.get(lb.curselection()[0])
            for idx, p in enumerate(pfs):
                if display_name(p) == selected_name:
                    if self.load_project_file(p):
                        d.destroy()
                        if on_loaded:
                            on_loaded()
                    break
        
        def do_duplicate():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for old_path in pfs:
                if display_name(old_path) == selected_name:
                    with open(old_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    data["name"] = data.get("name", "") + " -copy"
                    new_filename = re.sub(r'\W+', '_', data["name"]) + ".json"
                    new_path = self.projects_dir / new_filename
                    if new_path.exists():
                        messagebox.showerror("Duplicate",
                                             f"Υπάρχει ήδη project με το όνομα '{data['name']}'. "
                                             "Διάλεξε άλλο όνομα ή διέγραψε το υπάρχον.")
                        break
                    with open(new_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    messagebox.showinfo("Success", f"Project duplicated as: {data['name']}")
                    pfs.append(new_path)
                    # Re-apply filter to update list
                    filter_projects()
                    break
        
        def do_rename():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for idx, old_path in enumerate(pfs):
                if display_name(old_path) == selected_name:
                    current_name = old_path.stem.replace('_', ' ')
                    new_name = simpledialog.askstring("Rename Project", "New name:", initialvalue=current_name)
                    if new_name:
                        with open(old_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        data["name"] = new_name
                        new_filename = re.sub(r'\W+', '_', new_name) + ".json"
                        new_path = self.projects_dir / new_filename
                        # The sanitized name may map back to the same file (e.g. the
                        # prefilled name, "_" vs space, case changes). In that case we
                        # rewrite in place and must NOT delete the file afterwards.
                        same_file = os.path.normcase(str(old_path.resolve())) == os.path.normcase(str(new_path.resolve()))
                        if not same_file and new_path.exists():
                            messagebox.showerror("Rename",
                                                 f"Υπάρχει ήδη project με το όνομα '{new_name}'. Διάλεξε άλλο όνομα.")
                            break
                        with open(new_path, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                        if not same_file:
                            old_path.unlink()
                        messagebox.showinfo("Success", f"Project renamed to: {new_name}")
                        pfs[idx] = new_path
                        # Re-apply filter to update list
                        filter_projects()
                    break
        
        def do_delete():
            if not lb.curselection():
                return
            selected_name = lb.get(lb.curselection()[0])
            for old_path in pfs:
                if display_name(old_path) == selected_name:
                    if messagebox.askyesno("Delete Project", f"Delete project '{selected_name}'? This cannot be undone."):
                        old_path.unlink()
                        pfs.remove(old_path)
                        filter_projects()
                        messagebox.showinfo("Success", "Project deleted.")
                    break
        
        def show_context_menu(event):
            idx = lb.nearest(event.y)
            if idx < 0:
                return
            lb.selection_clear(0, tk.END)
            lb.selection_set(idx)
            lb.see(idx)
            cm = tk.Menu(self.root, tearoff=0)
            cm.add_command(label="Load", command=do_load)
            cm.add_command(label="Duplicate (-copy)", command=do_duplicate)
            cm.add_command(label="Rename", command=do_rename)
            cm.add_command(label="Delete", command=do_delete)
            cm.tk_popup(event.x_root, event.y_root)
        
        lb.bind("<Button-3>", show_context_menu)
        ttk.Button(d, text="Load", command=do_load).pack(pady=5)
        return d


    def load_project_file(self, project_path, on_loaded=None):
        """Load one project directly; used by the welcome screen's recent cards."""
        self._commit_pending_caption_apply()
        path = Path(project_path)
        try:
            with open(path, "r", encoding="utf-8-sig") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError("Το αρχείο δεν είναι έγκυρο project.")
        except Exception as exc:
            messagebox.showerror("Load Project",
                                 f"Δεν μπόρεσα να φορτώσω το project '{path.stem}':\n{exc}")
            return False

        stop_play = getattr(self, "_stop_preview_play", None)
        if stop_play:
            stop_play()
        if hasattr(self, "_global_settings"):
            for key in PROJECT_SETTING_KEYS:
                if key in self._global_settings:
                    self.settings[key] = copy.deepcopy(self._global_settings[key])
        self._migrate_global_video_position(data.get("project_settings", {}))
        had_project_template = "project_template" in data
        registry = self.template_registry()
        explicit = data.get("project_template_override")
        if explicit is None:
            explicit = (bool(data.get("project_template_name")) or
                        had_project_template)
        if explicit:
            name = str(data.get("project_template_name") or "").strip()
            if name not in registry:
                old_base = normalize_template(data.get("project_template", "legacy"),
                                              "legacy")
                name = LABEL_FOR_BASE.get(old_base, self._default_template_name(registry))
            self.project_template_name = name
            self.project_template = template_base(name, registry)
            self.project_template_override = True
        else:
            self.project_template_override = False
            self.project_template_name = self._default_template_name(registry)
            self.project_template = template_base(self.project_template_name, registry)
        self._sync_caption_template_dropdown()
        self.project_settings = self._normalize_project_settings(
            data.get("project_settings", {}))
        self._active_project_settings = bool(self.project_settings)
        self.settings.update(self.project_settings)
        self.name_var.set(data.get("name", ""))
        self.media_files = self.normalize_media_list(
            data.get("media_files", data.get("media", [])))
        raw_library = data.get("library_media")
        if raw_library is None:
            raw_library = data.get("media_files", data.get("media", []))
        self.library_media = []
        for kind, path, saved_edit in self.normalize_media_list(raw_library):
            item = self._new_item(kind, path)
            for key in ("library_id", "ai_description"):
                if saved_edit.get(key):
                    item[2][key] = saved_edit[key]
            self.library_media.append(item)
        self._ensure_library_ids()
        self._migrate_image_exif()
        if not had_project_template:
            # Previous releases wrote "legacy" for the default appearance.
            for item in self.media_files:
                if item[2]["presentation"]["template"] == "legacy":
                    item[2]["presentation"]["template"] = "project"
        (self.project_text_videos, self.project_text_photos,
         self.project_caption_mode, self.project_text_all) = self._project_caption_values(data)
        self.project_ai_instructions = data.get("ai_instructions", "")
        self.out_var.set(data.get("out", ""))
        self.project_watermark = data.get("project_watermark", {
            "enabled": False, "path": "", "position": "bottom_right",
            "size_pct": 15, "opacity": 80
        })
        self.is_modified = False
        self._video_frame_cache.clear()
        self._video_dur_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.selected_indices = set()
        self.library_selected_indices = set()
        missing_media = self._resolve_existing_project_media(project_path)
        self.current_project = path
        self.set_last_project(path)
        self._refresh_header()
        if missing_media:
            self._refresh_inspector_after_media(force=True)
            if on_loaded:
                on_loaded()
            self._show_missing_media_recovery(missing_media)
            return True
        self.update_media_display()
        self._refresh_inspector_after_media(force=True)
        if on_loaded:
            on_loaded()
        return True


    def on_closing(self):
        commit_captions = getattr(self, "_commit_pending_caption_apply", None)
        if commit_captions:
            commit_captions()
        self._remember_workspace_layout()
        self._save_window_state()
        try:
            self.save_settings()
            self.save_music_tracker()
            self.save_profile_registry()
        except Exception:
            pass
        if not self.is_modified:
            self.root.destroy()
            return
        answer = messagebox.askyesnocancel(
            "Έξοδος",
            "Έχεις αποθηκεύσει το project;\n\nΠάτα 'Yes' για να αποθηκεύσεις και να βγεις,\n'No' για να βγεις χωρίς αποθήκευση,\n'Cancel' για να μείνεις."
        )
        if answer is None:
            # Cancel - μην κλείσεις
            return
        elif answer:
            # Yes - αποθήκευσε και κλείσε (αν λείπει όνομα, μείνε ανοιχτό)
            if not self.save_project():
                return
            self.root.destroy()
        else:
            # No - κλείσε χωρίς αποθήκευση
            self.root.destroy()

