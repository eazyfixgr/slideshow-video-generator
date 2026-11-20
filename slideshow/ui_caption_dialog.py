"""Caption mode selection and project-wide caption editor."""

import copy

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .slide_design import INHERIT_TEMPLATE, TEMPLATES, normalize_presentation
from .ui_caption_media import MediaCaptionMixin


CAPTION_STRATEGIES = {
    "Ένα κείμενο για όλο το project": "all",
    "Ξεχωριστά captions για video / φωτογραφίες": "by_type",
}


class CaptionsMixin(MediaCaptionMixin):
    """One text workflow for all media, with per-type and per-item caption modes."""

    @staticmethod
    def _replace_caption_text(widget, value):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value or "")
        widget.edit_reset()

    def _project_has_caption_content(self):
        project_texts = (getattr(self, "project_text_all", ""),
                         getattr(self, "project_text_videos", ""),
                         getattr(self, "project_text_photos", ""))
        if any(str(value or "").strip() for value in project_texts):
            return True
        caption_fields = ("title", "subtitle", "description", "category", "location",
                          "price", "details", "cta", "business_name", "phone", "website")
        for item in getattr(self, "media_files", []):
            presentation = item[2].get("presentation") if len(item) > 2 else None
            if isinstance(presentation, dict) and any(
                    str(presentation.get(field) or "").strip() for field in caption_fields):
                return True
        return False

    def open_video_text(self):
        return self.open_text_captions_manager("by_type", "video")

    def open_photo_captions(self):
        return self.open_text_captions_manager("by_type", "image")

    def open_text_window(self):
        """Backward-compatible command; route it to the unified Captions window."""
        return self.open_text_captions_manager()

    def open_text_captions_manager(self, initial_strategy=None, initial_media=None):
        existing = getattr(self, "_text_captions_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    change_strategy = getattr(existing, "_set_caption_strategy", None)
                    if initial_strategy and change_strategy:
                        change_strategy(initial_strategy)
                    focus_media = getattr(existing, "_focus_caption_media", None)
                    if initial_media and focus_media:
                        focus_media(initial_media)
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

        if initial_strategy is None and self._project_has_caption_content():
            current_strategy = (self.project_caption_mode
                                if self.project_caption_mode in ("all", "by_type") else "all")
            current_label = CAPTION_STRATEGIES[
                "Ένα κείμενο για όλο το project" if current_strategy == "all" else
                "Ξεχωριστά captions για video / φωτογραφίες"]
            keep_current = messagebox.askyesnocancel(
                "Υπάρχουν ήδη captions",
                f"Το project έχει ήδη captions με τρόπο: {current_label}.\n\n"
                "Ναι: συνέχισε με τον υπάρχοντα τρόπο.\n"
                "Όχι: άλλαξε στον άλλο τρόπο captions.\n"
                "Άκυρο: μην ανοίξεις τον editor.",
                parent=self.root)
            if keep_current is None:
                return None
            initial_strategy = (current_strategy if keep_current else
                                ("by_type" if current_strategy == "all" else "all"))

        dialog = tk.Toplevel(self.root)
        self._text_captions_dialog = dialog
        dialog.title("Captions — Video & Photos")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        dialog.geometry(f"{min(1380, max(1000, int(sw * .92)))}x"
                        f"{min(1100, max(620, int(sh * .96)))}")
        dialog.minsize(min(920, sw - 80), min(620, sh - 80))
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ttk.Frame(dialog, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        style_bar = ttk.LabelFrame(outer, text="Σχεδίαση caption για όλο το project", padding=6)
        style_bar.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        style_bar.columnconfigure(1, weight=1)
        ttk.Label(style_bar, text="Template για video και φωτογραφίες:").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        project_template_var = tk.StringVar(
            value=TEMPLATES.get(self.project_template, TEMPLATES["legacy"]))
        project_template_combo = ttk.Combobox(
            style_bar, textvariable=project_template_var, state="readonly",
            values=list(TEMPLATES.values()), width=31)
        project_template_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        style_status = ttk.Label(style_bar, text="", foreground="#2d6cdf")
        style_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        design_button = ttk.Button(style_bar, text="Σχεδίαση")
        design_button.grid(row=0, column=2, rowspan=2, padx=(0, 2))

        chooser_page = ttk.Frame(outer, padding=24)
        chooser_page.grid(row=1, column=0, sticky="nsew")
        chooser_page.columnconfigure(0, weight=1)
        chooser_page.columnconfigure(1, weight=1)
        chooser_page.rowconfigure(1, weight=1)
        ttk.Label(chooser_page, text="Πώς θέλεις να ορίσεις τα captions;",
                  font=("Calibri", 18, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(20, 24))
        project_choice = ttk.LabelFrame(chooser_page, text="Ένα caption για όλο το project",
                                        padding=18)
        project_choice.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(project_choice, text="Το ίδιο κείμενο θα χρησιμοποιείται σε όλα τα video "
                                      "και τις φωτογραφίες.", wraplength=400,
                  justify="center").pack(expand=True, pady=20)
        project_choice_button = ttk.Button(project_choice, text="ΕΝΑ ΚΕΙΜΕΝΟ ΓΙΑ ΟΛΟ ΤΟ PROJECT")
        project_choice_button.pack(fill="x", ipady=12)
        separate_choice = ttk.LabelFrame(chooser_page,
                                         text="Ξεχωριστά captions για video και φωτογραφίες",
                                         padding=18)
        separate_choice.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        ttk.Label(separate_choice, text="Ορίζεις διαφορετικό κείμενο για video και φωτογραφίες, "
                                       "ή captions ανά media/group.", wraplength=400,
                  justify="center").pack(expand=True, pady=20)
        separate_choice_button = ttk.Button(
            separate_choice, text="ΞΕΧΩΡΙΣΤΑ VIDEO / PHOTO CAPTIONS")
        separate_choice_button.pack(fill="x", ipady=12)

        editor_shell = ttk.Frame(outer)
        editor_shell.grid(row=1, column=0, sticky="nsew")
        editor_shell.columnconfigure(0, weight=1)
        editor_shell.rowconfigure(1, weight=1)
        editor_header = ttk.Frame(editor_shell)
        editor_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        editor_mode_label = ttk.Label(editor_header, text="", font=("Calibri", 12, "bold"))
        editor_mode_label.pack(side="left", fill="x", expand=True)
        back_to_choices = ttk.Button(editor_header, text="← Επιλογές captions")
        back_to_choices.pack(side="right")
        editor_pages = ttk.Frame(editor_shell)
        editor_pages.grid(row=1, column=0, sticky="nsew")
        editor_pages.columnconfigure(0, weight=1)
        editor_pages.rowconfigure(0, weight=1)
        project_page = ttk.Frame(editor_pages, padding=10)
        separate_page = ttk.Frame(editor_pages, padding=8)
        project_page.grid(row=0, column=0, sticky="nsew")
        separate_page.grid(row=0, column=0, sticky="nsew")
        editor_shell.grid_remove()

        # Shared AI instructions are available to both caption strategies.
        ai_frame = ttk.LabelFrame(outer, text="Οδηγίες για AI (προαιρετικές)", padding=5)
        ai_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ai_frame.columnconfigure(0, weight=1)
        instructions = scrolledtext.ScrolledText(ai_frame, height=2, wrap=tk.WORD,
                                                 undo=True, font=("Calibri", 10))
        instructions.grid(row=0, column=0, sticky="ew")
        instructions.insert("1.0", self.project_ai_instructions)
        instructions.edit_reset()
        self._bind_text_shortcuts(instructions)

        bottom = ttk.Frame(outer)
        bottom.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(bottom, text="Οι αλλαγές αποθηκεύονται στο project· Ctrl+S γράφει το project στο δίσκο.",
                  foreground="#666").pack(side="left")
        close_button = ttk.Button(bottom, text="Κλείσιμο")
        close_button.pack(side="right")

        def replace_text(widget, value):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value or "")
            widget.edit_reset()

        def bind_text(widget, on_change=None):
            self._bind_captions_text(widget, on_change)

        def sync_instructions(_event=None):
            value = instructions.get("1.0", "end-1c").strip()
            if value != self.project_ai_instructions:
                self.project_ai_instructions = value
                self.is_modified = True

        instructions.bind("<KeyRelease>", sync_instructions, add="+")

        # --------------------------- project-wide caption
        project_page.columnconfigure(0, weight=3)
        project_page.columnconfigure(1, weight=2)
        project_page.rowconfigure(0, weight=1)
        whole_text_frame = ttk.LabelFrame(project_page, text="Ένα κοινό caption για video και φωτογραφίες",
                                          padding=8)
        whole_text_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        whole_text_frame.columnconfigure(0, weight=1)
        whole_text_frame.rowconfigure(1, weight=1)
        whole_toolbar = ttk.Frame(whole_text_frame)
        whole_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(whole_toolbar, text="Το ίδιο κείμενο χρησιμοποιείται σε όλο το project.",
                  foreground="#666").pack(side="left")
        whole_text = scrolledtext.ScrolledText(whole_text_frame, height=12, wrap=tk.WORD,
                                               undo=True, font=("Calibri", 12))
        whole_text.grid(row=1, column=0, sticky="nsew")
        whole_initial = (self.project_text_all or self.project_text_videos or
                         self.project_text_photos or "")
        whole_text.insert("1.0", whole_initial)
        whole_text.edit_reset()
        bind_text(whole_text)
        whole_status = ttk.Label(whole_text_frame, text="", foreground="#2d6cdf")
        whole_status.grid(row=2, column=0, sticky="w", pady=(5, 0))

        project_preview = ttk.LabelFrame(project_page, text="Preview project caption", padding=5)
        project_preview.grid(row=0, column=1, sticky="nsew")
        project_preview.columnconfigure(0, weight=1)
        project_preview.rowconfigure(0, weight=1)
        project_preview.rowconfigure(1, weight=1)
        whole_video_canvas = tk.Canvas(project_preview, bg="black", width=280, height=220,
                                       highlightthickness=1, highlightbackground="#666")
        whole_video_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        whole_photo_canvas = tk.Canvas(project_preview, bg="black", width=280, height=220,
                                       highlightthickness=1, highlightbackground="#666")
        whole_photo_canvas.grid(row=1, column=0, sticky="nsew")
        whole_controls = ttk.Frame(whole_text_frame)
        whole_controls.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        whole_controls.columnconfigure(0, weight=1)
        whole_ai_button = ttk.Button(whole_controls, text="Βελτίωση με AI")
        whole_ai_button.grid(row=0, column=0, sticky="w")
        ttk.Button(whole_controls, text="Εφαρμογή caption σε ΟΛΑ τα media",
                   command=lambda: apply_project_caption_to_all()).grid(
            row=0, column=1, sticky="e")

        def apply_project_template_to_all():
            template = next((key for key, label in TEMPLATES.items()
                             if label == project_template_var.get()), "legacy")
            changed = template != self.project_template
            self.project_template = template
            self._remember_caption_template(template)
            project_defaults = normalize_presentation(project_template=template)
            style_fields = ("text_position", "text_align", "font_family", "font_size",
                            "text_color", "panel_color", "accent_color", "panel_style",
                            "featured_enabled", "featured_text")
            for _kind, _path, edit in self.media_files:
                presentation = normalize_presentation(
                    edit.get("presentation"), project_template=template)
                if presentation["template"] != INHERIT_TEMPLATE:
                    presentation["template"] = INHERIT_TEMPLATE
                    changed = True
                for field in style_fields:
                    default_value = project_defaults[field]
                    if presentation[field] != default_value:
                        presentation[field] = copy.deepcopy(default_value)
                        changed = True
                edit["presentation"] = presentation
            if changed:
                self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            schedule_project_preview()
            video_state["refresh_preview"]()
            photo_state["refresh_preview"]()
            style_status.config(
                text=f"{TEMPLATES[template]} εφαρμόστηκε σε {len(self.media_files)} media. "
                     "Τα captions διατηρήθηκαν.")

        project_template_combo.bind(
            "<<ComboboxSelected>>", lambda _event: apply_project_template_to_all(), add="+")

        project_preview_job = {"id": None}

        def schedule_project_preview():
            if project_preview_job["id"]:
                try:
                    dialog.after_cancel(project_preview_job["id"])
                except tk.TclError:
                    pass
            project_preview_job["id"] = dialog.after(
                400, lambda: self._render_text_dialog_previews(
                    whole_video_canvas, whole_photo_canvas, whole_text.get("1.0", "end-1c"),
                    whole_text.get("1.0", "end-1c"),
                    *map(int, self.settings["resolution"].split("x"))))

        def sync_project_caption(_event=None, force=False):
            if self.project_caption_mode != "all":
                return
            value = whole_text.get("1.0", "end-1c").strip()
            if value != self.project_text_all:
                self.project_text_all = value
                self.is_modified = True
                self._schedule_preview(450)
                schedule_project_preview()
                self._sync_captions_inspector()

        whole_text.bind("<KeyRelease>", sync_project_caption, add="+")
        bind_text(whole_text, lambda: sync_project_caption())

        def set_whole_ai_busy(busy):
            whole_ai_button.config(state="disabled" if busy else "normal")
            whole_status.config(text="Το AI γράφει..." if busy else "")

        def improve_whole_caption():
            self.improve_text_with_ai(
                whole_text.get("1.0", "end-1c"), instructions.get("1.0", "end-1c"),
                apply_result=lambda value: (replace_text(whole_text, value),
                                            sync_project_caption()),
                set_busy=set_whole_ai_busy)

        whole_ai_button.config(command=improve_whole_caption)

        def apply_project_caption_to_all():
            sync_project_caption(force=True)
            self.project_caption_mode = "all"
            for _kind, _path, edit in self.media_files:
                presentation = normalize_presentation(
                    edit.get("presentation"), project_template=self.project_template)
                presentation["mode"] = "global"
                edit["presentation"] = presentation
            self.project_text_videos = self.project_text_all
            self.project_text_photos = self.project_text_all
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            self._sync_captions_inspector()
            whole_status.config(text=f"Caption appliqué à {len(self.media_files)} slides")

        # --------------------------- separated media-type caption pages
        separate_page.columnconfigure(0, weight=1, uniform="media-caption")
        separate_page.columnconfigure(1, weight=1, uniform="media-caption")
        separate_page.rowconfigure(0, weight=1)
        video_page = ttk.LabelFrame(separate_page, text="Video captions", padding=5)
        video_page.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        photo_page = ttk.LabelFrame(separate_page, text="Photo captions", padding=5)
        photo_page.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        video_state = self._build_media_caption_page(video_page, dialog, "video", instructions)
        photo_state = self._build_media_caption_page(photo_page, dialog, "image", instructions)
        dialog._focus_caption_media = lambda media_type: (
            video_state["focus"]() if media_type == "video" else photo_state["focus"]())

        def open_project_design():
            video_state["save_current"]()
            photo_state["save_current"]()
            if self.project_caption_mode == "all":
                sync_project_caption()
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            design_dialog = self.open_storyboard_editor()

            def restore_caption_dialog(event):
                if event.widget is not design_dialog:
                    return
                try:
                    if dialog.winfo_exists():
                        project_template_var.set(
                            TEMPLATES.get(self.project_template, TEMPLATES["legacy"]))
                        schedule_project_preview()
                        video_state["refresh_preview"]()
                        photo_state["refresh_preview"]()
                        video_state["refresh_templates"]()
                        photo_state["refresh_templates"]()
                        dialog.grab_set()
                except tk.TclError:
                    pass

            design_dialog.bind("<Destroy>", restore_caption_dialog, add="+")

        design_button.config(command=open_project_design)

        def set_caption_strategy(strategy):
            if strategy not in ("all", "by_type"):
                return
            if strategy != self.project_caption_mode:
                if strategy == "all":
                    video_text = (self.project_text_videos or "").strip()
                    photo_text = (self.project_text_photos or "").strip()
                    # Use active type captions; project_text_all may be stale from an earlier mode.
                    self.project_text_all = video_text or photo_text
                    replace_text(whole_text, self.project_text_all)
                    self.project_caption_mode = "all"
                else:
                    if self.project_text_all:
                        self.project_text_videos = self.project_text_all
                        self.project_text_photos = self.project_text_all
                    self.project_caption_mode = "by_type"
                    video_state["reload_shared"]()
                    photo_state["reload_shared"]()
                self.is_modified = True
                self.update_media_display()
                self._schedule_preview()
            self._sync_captions_inspector()

            editor_mode_label.config(
                text=("Ένα caption για όλο το project" if strategy == "all" else
                      "Ξεχωριστά captions — video και φωτογραφίες"))
            project_page.grid() if strategy == "all" else project_page.grid_remove()
            separate_page.grid() if strategy == "by_type" else separate_page.grid_remove()
            chooser_page.grid_remove()
            style_bar.grid()
            editor_shell.grid()
            ai_frame.grid()
            bottom.grid()
            dialog._caption_mode = strategy
            if strategy == "all":
                schedule_project_preview()

        dialog._set_caption_strategy = set_caption_strategy

        def show_caption_choices():
            for page_state in (video_state, photo_state):
                page_state["save_current"]()
            sync_instructions()
            if self.project_caption_mode == "all":
                sync_project_caption()
            editor_shell.grid_remove()
            style_bar.grid_remove()
            ai_frame.grid_remove()
            bottom.grid_remove()
            chooser_page.grid()

        project_choice_button.config(command=lambda: set_caption_strategy("all"))
        separate_choice_button.config(command=lambda: set_caption_strategy("by_type"))
        back_to_choices.config(command=show_caption_choices)

        # --------------------------- common close behavior
        state = {"closed": False}

        def close():
            if state["closed"]:
                return
            state["closed"] = True
            video_state["save_current"]()
            photo_state["save_current"]()
            video_state["shutdown"]()
            photo_state["shutdown"]()
            if project_preview_job["id"]:
                try:
                    dialog.after_cancel(project_preview_job["id"])
                except tk.TclError:
                    pass
            sync_instructions()
            if self.project_caption_mode == "all":
                sync_project_caption()
            self.update_media_display()
            self._schedule_preview()
            self._sync_captions_inspector()
            self._text_captions_dialog = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        close_button.config(command=close)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])

        if initial_media in ("video", "image"):
            set_caption_strategy("by_type")
            dialog._focus_caption_media(initial_media)
        elif initial_strategy in ("all", "by_type"):
            set_caption_strategy(initial_strategy)
        else:
            show_caption_choices()
        return dialog
