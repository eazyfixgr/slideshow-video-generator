"""The editor shell: header, three-column workspace, stage and status bar."""

import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .deps import ImageTk, DND_FILES, TKDND_AVAILABLE
from .profiles import initials
from .slide_design import TEMPLATES, normalize_presentation, normalize_template
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import (ScrollFrame, aspect_label, avatar_image, flat_button,
                         format_duration, primary_button)


class LayoutMixin:
    """The editor shell: header, three-column workspace, stage and status bar."""

    # ------------------------------------------------------------- header
    def _build_header(self):
        header = tk.Frame(self.root, bg=P["panel"], height=62,
                          highlightbackground=P["border"], highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        self.header = header

        left = tk.Frame(header, bg=P["panel"])
        left.pack(side="left", fill="y", padx=(12, 0))
        flat_button(left, "◀  Έναρξη", self.return_to_welcome,
                    background=P["panel"], foreground=P["accent"],
                    active_background=P["selected"], font=("Segoe UI", 9, "bold"),
                    padx=8, pady=6).pack(side="left", pady=15)
        tk.Frame(left, bg=P["border"], width=1, height=30).pack(
            side="left", padx=12, pady=16)

        project = tk.Frame(left, bg=P["panel"])
        project.pack(side="left", fill="y")
        tk.Label(project, text="PROJECT", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(10, 0))
        self.name_var = tk.StringVar()
        self.name_entry = tk.Entry(project, textvariable=self.name_var, bg=P["panel"],
                                   fg=P["text"], insertbackground=P["text"],
                                   selectbackground=P["selected"], relief="flat", bd=0,
                                   highlightthickness=0, font=("Segoe UI", 14, "bold"),
                                   width=28)
        self.name_entry.pack(anchor="w", pady=(0, 9))
        self.name_var.trace_add("write", lambda *_a: self._update_saved_status())

        profile = tk.Frame(header, bg=P["panel"], cursor="hand2")
        profile.pack(side="left", padx=(18, 0), pady=12)
        self.header_profile_avatar = tk.Label(profile, bg=P["panel"], bd=0)
        self.header_profile_avatar.pack(side="left")
        profile_text = tk.Frame(profile, bg=P["panel"])
        profile_text.pack(side="left", padx=(7, 0))
        self.header_profile_name = tk.Label(profile_text, text="", bg=P["panel"],
                                            fg=P["text"], font=("Segoe UI", 9, "bold"),
                                            anchor="w")
        self.header_profile_name.pack(anchor="w")
        self.header_profile_role = tk.Label(profile_text, text="", bg=P["panel"],
                                            fg=P["muted"], font=("Segoe UI", 7),
                                            anchor="w")
        self.header_profile_role.pack(anchor="w")
        for widget in (profile, profile_text, self.header_profile_avatar,
                       self.header_profile_name, self.header_profile_role):
            widget.bind("<Button-1>", lambda _e: self.open_edit_profile_dialog())

        right = tk.Frame(header, bg=P["panel"])
        right.pack(side="right", fill="y", padx=(0, 12))
        self.export_header_btn = primary_button(
            right, "Εξαγωγή", self.show_export_panel,
            font=("Segoe UI", 9, "bold"), padx=18, pady=7)
        self.export_header_btn.pack(side="right", pady=15)
        self.redo_btn = flat_button(right, "↷", self.redo, background=P["panel"],
                                    foreground=P["muted"],
                                    active_background=P["selected"],
                                    font=("Segoe UI", 13), padx=7, pady=2)
        self.redo_btn.pack(side="right", padx=(2, 6), pady=15)
        self.undo_btn = flat_button(right, "↶", self.undo, background=P["panel"],
                                    foreground=P["muted"],
                                    active_background=P["selected"],
                                    font=("Segoe UI", 13), padx=7, pady=2)
        self.undo_btn.pack(side="right", padx=2, pady=15)
        self.saved_status_var = tk.StringVar(value="")
        self.saved_status_label = tk.Label(right, textvariable=self.saved_status_var,
                                           bg=P["panel"], fg=P["muted"],
                                           font=("Segoe UI", 8))
        self.saved_status_label.pack(side="right", padx=(0, 10), pady=15)

    def _update_header_widgets(self):
        profile = self.active_profile_data
        self.header_profile_name.configure(text=profile.get("name", "Προφίλ"))
        self.header_profile_role.configure(text=profile.get("role", "") or "Προφίλ")
        image = avatar_image(initials(profile.get("name")), profile.get("color", P["accent"]),
                             34, P["panel"])
        photo = ImageTk.PhotoImage(image, master=self.root)
        self._header_avatar_photo = photo
        self.header_profile_avatar.configure(image=photo)
        self._update_saved_status()
        self._update_window_title()

    def _update_window_title(self):
        name = self.name_var.get().strip() if hasattr(self, "name_var") else ""
        profile = self.active_profile_data.get("name", "")
        title = "Slideshow Video Creator Pro"
        if name:
            title = f"{name} — {title}"
        if profile:
            title += f" · {profile}"
        try:
            self.root.title(title)
        except tk.TclError:
            pass

    def _update_saved_status(self):
        if not hasattr(self, "saved_status_var"):
            return
        if getattr(self, "is_modified", False):
            text, color = "● Μη αποθηκευμένες αλλαγές", P["accent"]
        elif hasattr(self, "name_var") and self.name_var.get().strip():
            text, color = "✓ Αποθηκευμένο", P["good"]
        else:
            text, color = "Νέο project", P["muted"]
        try:
            self.saved_status_var.set(text)
            self.saved_status_label.configure(fg=color)
            self.undo_btn.configure(state=("normal" if self._undo_stack else "disabled"),
                                    foreground=(P["text"] if self._undo_stack else P["border"]))
            self.redo_btn.configure(state=("normal" if self._redo_stack else "disabled"),
                                    foreground=(P["text"] if self._redo_stack else P["border"]))
        except tk.TclError:
            pass
        self._update_window_title()

    def _start_shell_poll(self):
        if getattr(self, "_shell_poll_job", None) is not None:
            try:
                self.root.after_cancel(self._shell_poll_job)
            except tk.TclError:
                pass
        self._shell_poll_job = self.root.after(700, self._shell_poll)

    def _shell_poll(self):
        self._shell_poll_job = None
        self._update_saved_status()
        if self.root.winfo_exists():
            self._shell_poll_job = self.root.after(700, self._shell_poll)

    # ---------------------------------------------------------- workspace
    def setup_gui(self):
        self.root.configure(bg=P["background"])
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_workspace()
        self._build_storyboard(self.root)
        self._build_status_bar()
        self._build_export_panel()

        self._update_header_widgets()
        self._refresh_stage()
        self.update_media_display()
        self._start_shell_poll()

    def _build_workspace(self):
        workspace = tk.PanedWindow(self.root, orient="horizontal", bg=P["border"],
                                   sashwidth=6, sashrelief="flat", bd=0)
        workspace.grid(row=1, column=0, sticky="nsew", padx=10, pady=(8, 6))
        self.workspace = workspace

        left = tk.Frame(workspace, bg=P["panel"], highlightbackground=P["border"],
                        highlightthickness=1)
        stage = tk.Frame(workspace, bg=P["background"])
        inspector = tk.Frame(workspace, bg=P["panel"], highlightbackground=P["border"],
                             highlightthickness=1)
        workspace.add(left, minsize=190, width=250, stretch="never")
        workspace.add(stage, minsize=420, stretch="always")
        workspace.add(inspector, minsize=270, width=330, stretch="never")
        self._build_library_panel(left)
        self._build_stage_panel(stage)
        self._build_inspector(inspector)

    def _build_library_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        header = tk.Frame(parent, bg=P["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(11, 4))
        tk.Label(header, text="ΒΙΒΛΙΟΘΗΚΗ", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.library_count_var = tk.StringVar(value="0")
        tk.Label(header, textvariable=self.library_count_var, bg=P["panel"],
                 fg=P["muted"], font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))
        primary_button(header, "+", self.import_media, font=("Segoe UI", 12, "bold"),
                       padx=8, pady=1).pack(side="right")

        filters = tk.Frame(parent, bg=P["panel"])
        filters.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 4))
        self.library_filter_var = tk.StringVar(value="all")
        self._library_filter_buttons = {}
        for key, label in (("all", "Όλα"), ("image", "Φωτογραφίες"),
                           ("video", "Βίντεο")):
            button = flat_button(filters, label,
                                 lambda value=key: self._set_library_filter(value),
                                 background=P["panel"], foreground=P["muted"],
                                 active_background=P["selected"],
                                 font=("Segoe UI", 8), padx=8, pady=3)
            button.pack(side="left", padx=(0, 3))
            self._library_filter_buttons[key] = button
        self._update_library_filter_buttons()

        scroller = ScrollFrame(parent, background=P["background"])
        scroller.grid(row=2, column=0, sticky="nsew", padx=(6, 2), pady=(0, 2))
        self.library_scroller = scroller
        self.media_canvas = scroller.canvas
        self.media_scrollbar = scroller.scrollbar
        self.thumb_frame = scroller.body
        self.canvas_window = scroller._window
        self.media_canvas.bind("<Configure>", self._debounced_resize)
        self.thumb_frame.bind(
            "<Configure>",
            lambda _e: self.media_canvas.configure(scrollregion=self.media_canvas.bbox("all")))

        footer = tk.Frame(parent, bg=P["panel"])
        footer.grid(row=3, column=0, sticky="ew", padx=10, pady=(2, 8))
        self.list_view_btn = flat_button(footer, "Λίστα", self._set_list_view,
                                         background=P["panel"], foreground=P["muted"],
                                         active_background=P["selected"],
                                         font=("Segoe UI", 8), padx=6, pady=2)
        self.list_view_btn.pack(side="right")
        self.grid_view_btn = flat_button(footer, "Πλέγμα", self._set_grid_view,
                                         background=P["panel"], foreground=P["muted"],
                                         active_background=P["selected"],
                                         font=("Segoe UI", 8), padx=6, pady=2)
        self.grid_view_btn.pack(side="right", padx=(0, 2))
        tk.Label(footer, text="Σύρε για αναδιάταξη", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 7)).pack(side="left")
        self._update_library_view_buttons()

        if TKDND_AVAILABLE:
            for target in (self.media_canvas, self.thumb_frame):
                try:
                    target.drop_target_register(DND_FILES)
                    target.dnd_bind("<<Drop>>", lambda e: self.handle_drop(e.data))
                except tk.TclError:
                    pass

    def _set_library_filter(self, value):
        self.library_filter_var.set(value)
        self._update_library_filter_buttons()
        self.update_media_display()

    def _update_library_filter_buttons(self):
        current = getattr(self, "library_filter_var", None)
        current = current.get() if current else "all"
        for key, button in getattr(self, "_library_filter_buttons", {}).items():
            try:
                active = key == current
                button.configure(background=(P["accent_faint"] if active else P["panel"]),
                                 foreground=(P["accent"] if active else P["muted"]))
            except tk.TclError:
                pass

    def _set_list_view(self):
        self.view_mode.set("list")
        self._update_library_view_buttons()
        self.update_media_display()

    def _set_grid_view(self):
        self.view_mode.set("thumbnails")
        self._update_library_view_buttons()
        self.update_media_display()

    def _update_library_view_buttons(self):
        mode = self.view_mode.get()
        for button, key in ((getattr(self, "list_view_btn", None), "list"),
                            (getattr(self, "grid_view_btn", None), "thumbnails")):
            if button is None:
                continue
            try:
                button.configure(foreground=(P["accent"] if mode == key else P["muted"]))
            except tk.TclError:
                pass

    def _build_stage_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = tk.Frame(parent, bg=P["background"])
        header.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        tk.Label(header, text="ΠΡΟΕΠΙΣΚΟΠΗΣΗ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.stage_scene_var = tk.StringVar(value="Καμία σκηνή")
        tk.Label(header, textvariable=self.stage_scene_var, bg=P["background"],
                 fg=P["text"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(8, 0))
        self.stage_aspect_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self.stage_aspect_var, bg=P["accent_faint"],
                 fg=P["accent"], font=("Segoe UI", 8, "bold"), padx=8, pady=2).pack(
            side="right")
        self.safe_guides_var = tk.BooleanVar(value=False)
        self.safe_guides_btn = flat_button(
            header, "○  Οδηγοί ασφαλείας", self._toggle_safe_guides,
            background=P["background"], foreground=P["muted"],
            active_background=P["selected"], font=("Segoe UI", 8),
            padx=7, pady=2)
        self.safe_guides_btn.pack(side="right", padx=(0, 10))

        shell = tk.Frame(parent, bg=P["stage"], highlightbackground=P["border"],
                         highlightthickness=1)
        shell.grid(row=1, column=0, sticky="nsew", padx=4)
        self.preview_canvas = tk.Canvas(shell, bg=P["stage"], highlightthickness=0, bd=0)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_video_canvas = self.preview_canvas
        self.preview_photo_canvas = self.preview_canvas
        self.preview_canvas.bind("<Button-1>", lambda _e: self._show_preview_zoom(self.preview_canvas))
        self.preview_canvas.bind("<Configure>", lambda _e: self._on_preview_configure(
            self.preview_canvas), add="+")

        transport = tk.Frame(parent, bg=P["background"])
        transport.grid(row=2, column=0, sticky="ew", padx=4, pady=(7, 4))
        flat_button(transport, "⏮", self._preview_previous, background=P["background"],
                    foreground=P["muted"], active_background=P["selected"],
                    font=("Segoe UI", 12), padx=6, pady=1).pack(side="left")
        self.play_btn = flat_button(transport, "▶", self._toggle_preview_play,
                                    background=P["raised"], foreground=P["text"],
                                    active_background=P["selected"],
                                    font=("Segoe UI", 11), padx=11, pady=2)
        self.play_btn.pack(side="left", padx=4)
        flat_button(transport, "⏭", self._preview_next, background=P["background"],
                    foreground=P["muted"], active_background=P["selected"],
                    font=("Segoe UI", 12), padx=6, pady=1).pack(side="left")
        self.seek_canvas = tk.Canvas(transport, height=18, bg=P["background"],
                                     highlightthickness=0, bd=0, cursor="hand2")
        self.seek_canvas.pack(side="left", fill="x", expand=True, padx=12)
        self.seek_canvas.bind("<Configure>", lambda _e: self._draw_scene_seek())
        self.seek_canvas.bind("<Button-1>", self._seek_press)
        self.seek_canvas.bind("<B1-Motion>", self._seek_press)
        self.scene_clock_var = tk.StringVar(value="—")
        tk.Label(transport, textvariable=self.scene_clock_var, bg=P["background"],
                 fg=P["muted"], font=("Segoe UI", 8)).pack(side="right")
        self._seek_index = 0
        self._seek_max = 0
        self._seek_guard = False
        self._preview_playing = False
        self._preview_play_job = None

    def _refresh_stage(self):
        if not hasattr(self, "stage_scene_var"):
            return
        media = getattr(self, "media_files", [])
        count = len(media)
        if not count:
            self.stage_scene_var.set("Καμία σκηνή")
            self.stage_aspect_var.set(aspect_label(self.settings.get("resolution")))
            self.scene_clock_var.set("—")
            self._set_scene_seek(0, 1)
            return
        index = self._selected_item_index()
        if index is None:
            index = 0
        item = media[index]
        self.stage_scene_var.set(f"Σκηνή {index + 1:02d} / {count:02d}")
        self.stage_aspect_var.set(
            f"{aspect_label(self.settings.get('resolution'))} · "
            f"{Path(item[1]).name}")
        self.scene_clock_var.set(f"{index + 1:02d} / {count:02d}")
        self._set_scene_seek(index, max(0, count - 1))

    def _set_scene_seek(self, value, maximum):
        if not hasattr(self, "seek_canvas"):
            return
        self._seek_index = max(0, int(value))
        self._seek_max = max(0, int(maximum))
        self._draw_scene_seek()

    def _draw_scene_seek(self):
        canvas = getattr(self, "seek_canvas", None)
        if canvas is None:
            return
        try:
            width = max(1, canvas.winfo_width())
            height = max(1, canvas.winfo_height())
            canvas.delete("all")
            y = height / 2
            left, right = 5, max(6, width - 5)
            count = len(getattr(self, "media_files", []))
            canvas.create_line(left, y, right, y, fill=P["field"], width=4,
                               capstyle="round")
            if not count:
                canvas.create_line(left, y, right, y, fill=P["border"], width=4,
                                   capstyle="round")
                return
            maximum = max(1, self._seek_max)
            fraction = min(1.0, max(0.0, self._seek_index / maximum))
            x = left + (right - left) * fraction
            canvas.create_line(left, y, x, y, fill=P["accent"], width=4,
                               capstyle="round")
            canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=P["accent"],
                               outline=P["accent"])
        except tk.TclError:
            pass

    def _seek_press(self, event):
        if not getattr(self, "media_files", None) or not hasattr(self, "seek_canvas"):
            return
        width = max(1, self.seek_canvas.winfo_width())
        fraction = (event.x - 5) / max(1, width - 10)
        index = int(round(max(0.0, min(1.0, fraction)) * max(0, len(self.media_files) - 1)))
        if index != self._selected_item_index():
            self.select_scene(index, preview=True)

    def _toggle_safe_guides(self):
        self.safe_guides_var.set(not self.safe_guides_var.get())
        self._update_safe_guides_button()
        self._draw_preview_display(self.preview_canvas)

    def _update_safe_guides_button(self):
        button = getattr(self, "safe_guides_btn", None)
        if button is None:
            return
        active = self.safe_guides_var.get()
        try:
            button.configure(text=("●  Οδηγοί ασφαλείας" if active
                                   else "○  Οδηγοί ασφαλείας"),
                             foreground=(P["accent"] if active else P["muted"]))
        except tk.TclError:
            pass

    def _selection_changed(self):
        self._refresh_stage()
        self.render_storyboard()
        if getattr(self, "inspector_view", "captions") != "captions":
            self._render_inspector()
        self._schedule_preview(150)

    def _refresh_inspector_after_media(self, force=False):
        if not hasattr(self, "inspector_content"):
            return
        if force or getattr(self, "inspector_view", "captions") != "captions":
            self._render_inspector()

    def select_scene(self, index, preview=True, sync_inspector=True):
        if not (0 <= index < len(getattr(self, "media_files", []))):
            return
        self.selected_indices = {index}
        self._sel_anchor = index
        item = self.media_files[index]
        presentation = normalize_presentation(item[2].get("presentation"))
        self._active_presentation_scene_id = presentation.get("scene_id")
        self._refresh_selection()
        self._refresh_stage()
        self.render_storyboard()
        if sync_inspector and getattr(self, "inspector_view", "captions") != "captions":
            self._render_inspector()
        if preview:
            self._schedule_preview(120)

    def _preview_previous(self):
        if not getattr(self, "media_files", None):
            return
        index = self._selected_item_index() or 0
        self.select_scene(max(0, index - 1))

    def _preview_next(self):
        if not getattr(self, "media_files", None):
            return
        index = self._selected_item_index() or 0
        self.select_scene(min(len(self.media_files) - 1, index + 1))

    def _toggle_preview_play(self):
        if getattr(self, "_preview_playing", False):
            self._stop_preview_play()
        elif getattr(self, "media_files", None):
            self._preview_playing = True
            self.play_btn.configure(text="❚❚")
            index = self._selected_item_index()
            if index is None:
                index = 0
                self.select_scene(index, preview=True, sync_inspector=False)
            seconds = self._scene_seconds(self.media_files[index])
            self._preview_play_job = self.root.after(
                max(700, min(6000, int(seconds * 1000))), self._advance_preview_play)

    def _stop_preview_play(self):
        self._preview_playing = False
        job = getattr(self, "_preview_play_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._preview_play_job = None
        if hasattr(self, "play_btn"):
            self.play_btn.configure(text="▶")

    def _advance_preview_play(self):
        self._preview_play_job = None
        if not getattr(self, "_preview_playing", False) or not self.media_files:
            self._stop_preview_play()
            return
        index = self._selected_item_index()
        if index is None:
            index = 0
        else:
            index += 1
        if index >= len(self.media_files):
            self._stop_preview_play()
            return
        self.select_scene(index, preview=True, sync_inspector=False)
        seconds = self._scene_seconds(self.media_files[index])
        self._preview_play_job = self.root.after(
            max(700, min(6000, int(seconds * 1000))), self._advance_preview_play)

    # ----------------------------------------------------------- status bar
    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=P["panel"], height=26,
                       highlightbackground=P["border"], highlightthickness=1)
        bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))
        bar.grid_propagate(False)
        self.status = tk.Label(bar, text="Ready", bg=P["panel"], fg=P["muted"],
                               font=("Segoe UI", 8), anchor="w", padx=10)
        self.status.pack(side="left", fill="x", expand=True)
        tk.Label(bar, text="Ctrl+S Αποθήκευση · Ctrl+Z Undo · F5 Preview",
                 bg=P["panel"], fg=P["border"], font=("Segoe UI", 7)).pack(
            side="right", padx=10)

    # ----------------------------------------------------- caption helpers
    def _sync_caption_template_dropdown(self):
        template_var = getattr(self, "_caption_template_var", None)
        if template_var is not None:
            template = normalize_template(getattr(self, "project_template", "legacy"))
            self.project_template = template
            template_var.set(TEMPLATES.get(template, TEMPLATES["legacy"]))

    def _remember_caption_template(self, template):
        template = normalize_template(template)
        self.settings["last_caption_template"] = template
        self.settings["last_caption_template_is_global"] = True
        self._sync_caption_template_dropdown()
        self.save_settings()
        return template

    def _on_caption_template_selected(self, _event=None):
        selected = self._caption_template_var.get()
        template = next((key for key, label in TEMPLATES.items()
                         if label == selected), "legacy")
        changed = template != self.project_template
        self.project_template = self._remember_caption_template(template)
        if not changed:
            return
        if self.media_files:
            self.update_media_display()
            self._schedule_preview()
        self.render_storyboard()
        self._refresh_stage()
        if getattr(self, "current_project", None) or self.name_var.get().strip():
            self.is_modified = True

    # --------------------------------------------------------- export ETA
    def _start_export_eta(self):
        job = getattr(self, "_export_eta_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        now = time.monotonic()
        self._export_eta_active = True
        self._export_eta_state = {
            "last_progress": float(self.progress_var.get()),
            "last_change": now,
            "seconds_per_percent": None,
        }
        self.export_eta_var.set("Estimating remaining time…")
        self._update_export_eta()

    def _on_export_progress(self, *_):
        if not getattr(self, "_export_eta_active", False):
            return
        try:
            progress = float(self.progress_var.get())
        except (tk.TclError, ValueError, TypeError):
            return
        state = self._export_eta_state
        previous = state["last_progress"]
        if progress <= previous:
            return
        now = time.monotonic()
        elapsed = now - state["last_change"]
        delta = progress - previous
        if elapsed > 0:
            sample = elapsed / delta
            old_rate = state["seconds_per_percent"]
            state["seconds_per_percent"] = (sample if old_rate is None else
                                             old_rate * 0.65 + sample * 0.35)
        state["last_progress"] = progress
        state["last_change"] = now

    def _update_export_eta(self):
        self._export_eta_job = None
        if not getattr(self, "_export_eta_active", False):
            return
        try:
            progress = max(0.0, min(100.0, float(self.progress_var.get())))
        except (tk.TclError, ValueError, TypeError):
            progress = 0.0
        state = self._export_eta_state
        seconds_per_percent = state["seconds_per_percent"]
        if progress >= 99.5:
            text = "Finishing export…"
        elif seconds_per_percent is None:
            text = "Estimating remaining time…"
        else:
            elapsed_since_update = time.monotonic() - state["last_change"]
            remaining = seconds_per_percent * (100.0 - progress) - elapsed_since_update
            text = (f"Remaining: {self.format_estimated_duration(remaining)}"
                    if remaining > 1 else "Re-estimating…")
        self.export_eta_var.set(text)
        self._export_eta_job = self.root.after(1000, self._update_export_eta)

    def _finish_export_eta(self, completed=False, cancelled=False):
        self._export_eta_active = False
        job = getattr(self, "_export_eta_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._export_eta_job = None
        if completed:
            self.export_eta_var.set("Export complete")
        elif cancelled:
            self.export_eta_var.set("Export cancelled")
        else:
            self.export_eta_var.set("Export stopped")

    # ------------------------------------------------------------- library
    def _debounced_resize(self, event):
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(200, lambda: self._on_canvas_resize(event.width))

    def _on_canvas_resize(self, width):
        self.media_canvas.itemconfig(self.canvas_window, width=width)
        self.update_media_display()
