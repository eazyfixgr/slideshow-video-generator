"""Unified project captions: one project caption or video/photo caption workflows."""

import copy
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .deps import Image, ImageTk
from .slide_design import (DEFAULT_PRESENTATION, INHERIT_TEMPLATE, TEMPLATES,
                           normalize_presentation)


CAPTION_STRATEGIES = {
    "Ένα κείμενο για όλο το project": "all",
    "Ξεχωριστά captions για video / φωτογραφίες": "by_type",
}
TYPE_CAPTION_MODES = {
    "Κοινό caption για όλα": "shared",
    "Caption ανά media": "individual",
    "Κοινό caption σε επιλεγμένη ομάδα": "group",
}


class CaptionsMixin:
    """One text workflow for all media, with per-type and per-item caption modes."""

    @staticmethod
    def _replace_caption_text(widget, value):
        widget.delete("1.0", tk.END)
        widget.insert("1.0", value or "")
        widget.edit_reset()

    def open_video_text(self):
        return self.open_text_captions_manager("by_type", "video")

    def open_photo_captions(self):
        return self.open_text_captions_manager("by_type", "image")

    def open_text_window(self):
        """Backward-compatible command; route it to the unified Captions window."""
        return self.open_text_captions_manager()

    def _bind_captions_text(self, widget, on_change=None):
        self._bind_text_shortcuts(widget)
        menu = tk.Menu(widget, tearoff=0)

        def text_action(action):
            self._do_text_shortcut(widget, action)
            if on_change and action in ("paste", "cut", "undo"):
                on_change()

        for label, action in (("Copy", "copy"), ("Paste", "paste"),
                              ("Cut", "cut"), ("Undo", "undo")):
            menu.add_command(label=label, command=lambda a=action: text_action(a))

        def popup(event):
            menu.tk_popup(event.x_root, event.y_root)
            return "break"
        widget.bind("<Button-3>", popup, add="+")
        if on_change:
            widget.bind("<KeyRelease>", lambda _e: on_change(), add="+")

    def _schedule_caption_preview(self, parent, canvas, item_index, media_type, global_text,
                                  status=None, edit_override=None):
        """Render the selected item asynchronously and paint it on the Tk thread."""
        if item_index is None or not (0 <= item_index < len(self.media_files)):
            return
        job = getattr(canvas, "_caption_preview_job", None)
        if job:
            try:
                parent.after_cancel(job)
            except tk.TclError:
                pass
        canvas._caption_preview_token = getattr(canvas, "_caption_preview_token", 0) + 1
        token = canvas._caption_preview_token
        _kind, path, current_edit = self.media_files[item_index]
        edit = copy.deepcopy(edit_override if edit_override is not None else current_edit)
        width, height = map(int, self.settings["resolution"].split("x"))
        if status is not None:
            status.config(text="Ενημέρωση preview…")

        def show(frame, result_token):
            if result_token != getattr(canvas, "_caption_preview_token", -1):
                return
            try:
                if not canvas.winfo_exists():
                    return
                cw, ch = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
                scale = min(cw / frame.width, ch / frame.height)
                size = (max(1, round(frame.width * scale)),
                        max(1, round(frame.height * scale)))
                ref = ImageTk.PhotoImage(frame.resize(size, Image.Resampling.LANCZOS))
                canvas.delete("all")
                canvas.create_image(cw // 2, ch // 2, image=ref)
                canvas.image_ref = ref
                if status is not None:
                    status.config(text="Preview updated")
            except tk.TclError:
                pass

        def render():
            canvas._caption_preview_job = None

            def worker():
                try:
                    if media_type == "image":
                        source = Image.open(path)
                    else:
                        start = float(edit.get("trim_start") or 0.0)
                        source = (self._video_frame_at(path, start) if start > .005 else
                                  self._video_first_frame(path))
                    source = self._apply_image_edit(source, edit, path, m_type=media_type)
                    frame = self._render_with_text(source, media_type, global_text, width,
                                                   height, edit=edit)
                    frame = self._apply_watermark_overlay(frame)
                    self._post_ui(show, frame, token)
                except Exception as exc:
                    if status is not None:
                        error = str(exc)
                        self._post_ui(status.config, text=f"Preview: {error}")

            threading.Thread(target=worker, daemon=True).start()

        canvas._caption_preview_job = parent.after(300, render)

    def open_text_captions_manager(self, initial_strategy=None, initial_media=None):
        existing = getattr(self, "_text_captions_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    change_strategy = getattr(existing, "_set_caption_strategy", None)
                    if initial_strategy and change_strategy:
                        change_strategy(initial_strategy)
                    media_tabs = getattr(existing, "_media_caption_notebook", None)
                    if initial_media and media_tabs is not None:
                        media_tabs.select(0 if initial_media == "video" else 1)
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

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

        strategy_tabs = ttk.Notebook(outer)
        strategy_tabs.grid(row=1, column=0, sticky="nsew")
        dialog._captions_notebook = strategy_tabs

        project_page = ttk.Frame(strategy_tabs, padding=10)
        separate_page = ttk.Frame(strategy_tabs, padding=8)
        strategy_tabs.add(project_page, text="  Ένα caption για όλο το project  ")
        strategy_tabs.add(separate_page, text="  Ξεχωριστά video / photo captions  ")

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
            style_fields = ("text_position", "font_family", "font_size", "text_color",
                            "panel_color", "accent_color", "panel_style")
            for _kind, _path, edit in self.media_files:
                presentation = normalize_presentation(edit.get("presentation"))
                if presentation["template"] != INHERIT_TEMPLATE:
                    presentation["template"] = INHERIT_TEMPLATE
                    changed = True
                for field in style_fields:
                    default_value = DEFAULT_PRESENTATION[field]
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
            value = whole_text.get("1.0", "end-1c").strip()
            if value != self.project_text_all:
                self.project_text_all = value
                self.project_caption_mode = "all"
                self.is_modified = True
                self._schedule_preview(450)
                schedule_project_preview()

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
                presentation = normalize_presentation(edit.get("presentation"))
                presentation["mode"] = "global"
                edit["presentation"] = presentation
            self.project_text_videos = self.project_text_all
            self.project_text_photos = self.project_text_all
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            whole_status.config(text=f"Caption appliqué à {len(self.media_files)} slides")

        # --------------------------- separated media-type caption pages
        separate_page.columnconfigure(0, weight=1)
        separate_page.rowconfigure(0, weight=1)
        media_tabs = ttk.Notebook(separate_page)
        media_tabs.grid(row=0, column=0, sticky="nsew")
        dialog._media_caption_notebook = media_tabs
        video_page = ttk.Frame(media_tabs, padding=7)
        photo_page = ttk.Frame(media_tabs, padding=7)
        media_tabs.add(video_page, text="  Video Captions  ")
        media_tabs.add(photo_page, text="  Photo Captions  ")
        video_state = self._build_media_caption_page(video_page, dialog, "video", instructions)
        photo_state = self._build_media_caption_page(photo_page, dialog, "image", instructions)

        def open_project_design():
            video_state["save_current"]()
            photo_state["save_current"]()
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
                        dialog.grab_set()
                except tk.TclError:
                    pass

            design_dialog.bind("<Destroy>", restore_caption_dialog, add="+")

        design_button.config(command=open_project_design)

        strategy_job = {"id": None}

        def set_caption_strategy(strategy):
            if strategy not in ("all", "by_type") or strategy == self.project_caption_mode:
                return
            if strategy == "all":
                video_text = (self.project_text_videos or "").strip()
                photo_text = (self.project_text_photos or "").strip()
                if not self.project_text_all:
                    # If the old project had two different shared captions,
                    # keep the video version as the starting point in this mode.
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
            schedule_project_preview()

        dialog._set_caption_strategy = set_caption_strategy

        def on_strategy_change(_event=None):
            current = strategy_tabs.index(strategy_tabs.select())
            set_caption_strategy("all" if current == 0 else "by_type")

        strategy_tabs.bind("<<NotebookTabChanged>>", on_strategy_change, add="+")
        strategy_tabs.select(0 if self.project_caption_mode == "all" else 1)
        media_tabs.select(0 if initial_media == "video" else 1 if initial_media == "image" else 0)

        # --------------------------- common close behavior
        state = {"closed": False}

        def close():
            if state["closed"]:
                return
            state["closed"] = True
            video_state["save_current"]()
            photo_state["save_current"]()
            sync_instructions()
            sync_project_caption()
            self.update_media_display()
            self._schedule_preview()
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
            media_tabs.select(0 if initial_media == "video" else 1)
        if self.project_caption_mode == "all":
            schedule_project_preview()
        return dialog

    def _build_media_caption_page(self, parent, dialog, media_type, instructions):
        """Shared/individual/group editor for one media type, with thumbnail selection."""
        label_type = "video" if media_type == "video" else "photo"
        global_attr = "project_text_videos" if media_type == "video" else "project_text_photos"
        media = [(index, path, edit) for index, (kind, path, edit) in enumerate(self.media_files)
                 if kind == media_type]
        default_mode = ("individual" if any(
            normalize_presentation(edit.get("presentation"))["mode"] in ("custom", "combine")
            for _index, _path, edit in media) else "shared")
        mode_labels = {
            "Κοινό caption για όλα τα video" if media_type == "video" else
            "Κοινό caption για όλες τις φωτογραφίες": "shared",
            "Caption ανά video" if media_type == "video" else "Caption ανά φωτογραφία": "individual",
            "Κοινό caption σε επιλεγμένη ομάδα": "group",
        }
        mode_by_value = {value: key for key, value in mode_labels.items()}
        mode_var = tk.StringVar(value=mode_by_value[default_mode])
        state = {"mode": default_mode, "current": None, "loading": False,
                 "dirty": False, "closed": False}

        page = ttk.Frame(parent)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        page.rowconfigure(1, weight=1)

        mode_row = ttk.Frame(page)
        mode_row.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(mode_row, text="Τρόπος caption", font=("Calibri", 10, "bold")).pack(side="left", padx=(0, 8))
        mode_combo = ttk.Combobox(mode_row, textvariable=mode_var, values=list(mode_labels),
                                  state="readonly", width=34)
        mode_combo.pack(side="left", fill="x", expand=True)

        body = ttk.Frame(page)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)
        tree_box = ttk.LabelFrame(
            body, text=("Videos — Ctrl/Shift για ομάδα" if media_type == "video" else
                        "Φωτογραφίες — Ctrl/Shift για ομάδα"), padding=5)
        tree_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tree_frame = ttk.Frame(tree_box)
        tree_frame.pack(fill="both", expand=True)
        style = ttk.Style(dialog)
        style.configure("CaptionMedia.Treeview", rowheight=68)
        tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse",
                            style="CaptionMedia.Treeview")
        tree.column("#0", width=285, minwidth=180, stretch=True)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        thumb_refs = {}
        for index, path, _edit in media:
            tree.insert("", "end", iid=str(index), text=Path(path).name)

        def build_thumbnail(index, path):
            if media_type == "video":
                image = self._video_first_frame(path)
            else:
                image = Image.open(path)
                image.load()
            image = image.convert("RGB")
            target_w, target_h = 100, 56
            scale = max(target_w / image.width, target_h / image.height)
            image = image.resize((round(image.width * scale), round(image.height * scale)),
                                 Image.Resampling.LANCZOS)
            left = max(0, (image.width - target_w) // 2)
            top = max(0, (image.height - target_h) // 2)
            return index, image.crop((left, top, left + target_w, top + target_h))

        def apply_thumbnail(index, image):
            if state["closed"] or image is None:
                return
            try:
                ref = ImageTk.PhotoImage(image)
                thumb_refs[index] = ref
                tree.item(str(index), image=ref)
            except tk.TclError:
                pass

        def load_thumbnails():
            for index, path, _edit in media:
                if state["closed"]:
                    return
                try:
                    frame_index, image = build_thumbnail(index, path)
                    self._post_ui(apply_thumbnail, frame_index, image)
                except Exception:
                    continue

        if media:
            threading.Thread(target=load_thumbnails, daemon=True).start()

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        shared_frame = ttk.Frame(right)
        shared_frame.grid(row=0, column=0, sticky="nsew")
        shared_frame.columnconfigure(0, weight=1)
        shared_frame.rowconfigure(1, weight=1)
        shared_initial_stored = (getattr(self, global_attr) or "").strip()
        shared_initial_display = self.get_text_for(media_type).strip()
        ttk.Label(shared_frame,
                  text=("Κοινό κείμενο για όλα τα video" if media_type == "video" else
                        "Κοινό κείμενο για όλες τις φωτογραφίες"),
                  font=("Calibri", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        shared_text = scrolledtext.ScrolledText(shared_frame, height=7, wrap=tk.WORD,
                                                undo=True, font=("Calibri", 11))
        shared_text.grid(row=1, column=0, sticky="nsew")
        shared_text.insert("1.0", shared_initial_display)
        shared_text.edit_reset()
        self._bind_text_shortcuts(shared_text)
        shared_tools = ttk.Frame(shared_frame)
        shared_tools.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        shared_status = ttk.Label(shared_tools, text="", foreground="#2d6cdf")
        shared_status.pack(side="left")
        quick = ttk.Button(shared_tools, text="Quick Paste")
        quick.pack(side="right", padx=3)
        improve = ttk.Button(shared_tools, text="Βελτίωση με AI")
        improve.pack(side="right", padx=3)
        apply_shared = ttk.Button(shared_frame,
                                  text=("Εφαρμογή κοινού caption σε ΟΛΑ τα video" if media_type == "video" else
                                        "Εφαρμογή κοινού caption σε ΟΛΕΣ τις φωτογραφίες"))
        apply_shared.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(shared_frame,
                  text="Το κοινό κείμενο ισχύει στα media με Global caption. Τα Custom captions μένουν ως overrides.",
                  foreground="#666", wraplength=640).grid(row=4, column=0, sticky="w", pady=(4, 0))

        caption_frame = ttk.Frame(right)
        caption_frame.grid(row=0, column=0, sticky="nsew")
        caption_frame.columnconfigure(1, weight=1)
        caption_frame.rowconfigure(3, weight=1)
        caption_title_label = ttk.Label(caption_frame, text="Caption ανά media",
                                        font=("Calibri", 11, "bold"))
        caption_title_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(caption_frame, text="Τίτλος", width=13).grid(row=1, column=0, sticky="w", pady=3)
        title_var = tk.StringVar()
        ttk.Entry(caption_frame, textvariable=title_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(caption_frame, text="Υπότιτλος", width=13).grid(row=2, column=0, sticky="w", pady=3)
        subtitle_var = tk.StringVar()
        ttk.Entry(caption_frame, textvariable=subtitle_var).grid(row=2, column=1, sticky="ew", pady=3)
        ttk.Label(caption_frame, text="Περιγραφή", width=13).grid(row=3, column=0, sticky="nw", pady=3)
        description = scrolledtext.ScrolledText(caption_frame, height=6, wrap=tk.WORD,
                                                undo=True, font=("Calibri", 11))
        description.grid(row=3, column=1, sticky="nsew", pady=3)
        self._bind_text_shortcuts(description)
        controls = ttk.Frame(caption_frame)
        controls.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        apply_caption = ttk.Button(controls, text="Αποθήκευση caption")
        apply_caption.pack(side="left")
        design_button = ttk.Button(controls, text="Template / σχεδίαση…")
        design_button.pack(side="right")
        hint = ttk.Label(caption_frame, text="", foreground="#666", wraplength=640)
        hint.grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 0))

        preview_box = ttk.LabelFrame(right, text="Preview επιλεγμένου media", padding=4)
        preview_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        preview_box.columnconfigure(0, weight=1)
        preview_box.rowconfigure(0, weight=1)
        preview = tk.Canvas(preview_box, bg="black", width=440, height=270,
                            highlightthickness=0)
        preview.grid(row=0, column=0, sticky="nsew")
        preview_status = ttk.Label(preview_box, text="", foreground="#666")
        preview_status.grid(row=1, column=0, sticky="w")

        def caption_values():
            return {"title": title_var.get().strip(),
                    "subtitle": subtitle_var.get().strip(),
                    "description": description.get("1.0", "end-1c").strip()}

        def write_item_caption(index, values):
            if not 0 <= index < len(self.media_files):
                return
            edit = self.media_files[index][2]
            presentation = normalize_presentation(edit.get("presentation"))
            presentation["mode"] = "custom"
            presentation.update(values)
            edit["presentation"] = normalize_presentation(
                presentation, scene_id=presentation["scene_id"])
            self.is_modified = True

        def save_current():
            index = state.get("current")
            if state["mode"] == "individual" and index is not None and state["dirty"] and \
                    not state["loading"]:
                write_item_caption(index, caption_values())
                state["dirty"] = False
                self._schedule_preview(450)

        def load_current(index):
            if not 0 <= index < len(self.media_files):
                return
            state["loading"] = True
            presentation = normalize_presentation(self.media_files[index][2].get("presentation"))
            title_var.set(presentation["title"])
            subtitle_var.set(presentation["subtitle"])
            caption_description = presentation["description"]
            if presentation["mode"] == "global" and not any((
                    presentation["title"], presentation["subtitle"], caption_description)):
                caption_description = self.get_text_for(media_type)
            description.delete("1.0", tk.END)
            description.insert("1.0", caption_description or "")
            description.edit_reset()
            state["current"] = index
            state["dirty"] = False
            state["loading"] = False
            caption_title_label.config(text=f"Caption: {Path(self.media_files[index][1]).name}")
            apply_caption.config(text="Αποθήκευση caption")
            hint.config(text="Το caption αποθηκεύεται ανά media. Το template και το crop μένουν ανεξάρτητα.")
            schedule_preview()

        def tree_selection(_event=None):
            selected_ids = list(tree.selection())
            selected_indices = [int(item_id) for item_id in selected_ids]
            if state["mode"] == "individual":
                focused = tree.focus()
                index = int(focused) if focused and focused.isdigit() else (
                    selected_indices[-1] if selected_indices else None)
                if index is not None and index != state.get("current"):
                    save_current()
                    load_current(index)
            elif state["mode"] == "group":
                hint.config(text=f"Επιλεγμένα: {len(selected_indices)}. Το caption αντιγράφεται στα media "
                                 "και μετά μπορούν να αλλάξουν ανεξάρτητα.")
                schedule_preview()
            else:
                schedule_preview()

        def schedule_preview():
            selected_ids = list(tree.selection())
            selected_indices = [int(item_id) for item_id in selected_ids]
            if state["mode"] == "individual":
                index = state.get("current") or (media[0][0] if media else None)
                edit_override = None
            elif state["mode"] == "group":
                index = selected_indices[0] if selected_indices else (media[0][0] if media else None)
                edit_override = copy.deepcopy(self.media_files[index][2]) if index is not None else None
                if edit_override is not None:
                    presentation = normalize_presentation(edit_override.get("presentation"))
                    presentation["mode"] = "custom"
                    presentation.update(caption_values())
                    edit_override["presentation"] = presentation
            else:
                index = selected_indices[0] if selected_indices else (media[0][0] if media else None)
                edit_override = copy.deepcopy(self.media_files[index][2]) if index is not None else None
                if edit_override is not None:
                    presentation = normalize_presentation(edit_override.get("presentation"))
                    presentation["mode"] = "global"
                    edit_override["presentation"] = presentation
            if index is None:
                preview.delete("all")
                preview_status.config(text="Δεν υπάρχουν media αυτού του τύπου.")
                return
            global_text = (shared_text.get("1.0", "end-1c") if state["mode"] == "shared"
                           else self.get_text_for(media_type))
            self._schedule_caption_preview(dialog, preview, index, media_type,
                                           global_text, preview_status, edit_override)

        def mode_changed(*_):
            new_mode = mode_labels.get(mode_var.get(), "shared")
            if state["mode"] == "individual":
                save_current()
            state["mode"] = new_mode
            if new_mode == "shared":
                tree.configure(selectmode="browse")
                caption_frame.grid_remove()
                shared_frame.grid()
                preview_box.config(text="Preview κοινού caption στο επιλεγμένο media")
                apply_shared.config(text=("Εφαρμογή κοινού caption σε ΟΛΑ τα video" if media_type == "video"
                                          else "Εφαρμογή κοινού caption σε ΟΛΕΣ τις φωτογραφίες"))
                apply_shared.state(["!disabled"])
            else:
                shared_frame.grid_remove()
                caption_frame.grid()
                preview_box.config(text="Preview caption επιλεγμένου media")
                tree.configure(selectmode="extended" if new_mode == "group" else "browse")
                if new_mode == "individual":
                    selected_ids = list(tree.selection())
                    index = int(selected_ids[0]) if selected_ids else (media[0][0] if media else None)
                    if index is not None:
                        tree.selection_set(str(index))
                        tree.focus(str(index))
                        load_current(index)
                    else:
                        caption_title_label.config(text="Δεν υπάρχουν media")
                        apply_caption.state(["disabled"])
                else:
                    tree.selection_remove(tree.selection())
                    state["current"] = None
                    title_var.set("")
                    subtitle_var.set("")
                    description.delete("1.0", tk.END)
                    caption_title_label.config(text="Κοινό caption σε επιλεγμένη ομάδα")
                    apply_caption.config(text="Εφαρμογή στα επιλεγμένα")
                    apply_caption.state(["!disabled"])
                    hint.config(text="Επίλεξε media με Ctrl/Shift, γράψε caption και πάτα Εφαρμογή.")
            schedule_preview()

        def sync_shared_text(_event=None, force=False):
            value = shared_text.get("1.0", "end-1c").strip()
            displayed_initial = shared_initial_display
            stored_value = (shared_initial_stored if not force and value == displayed_initial
                            else value)
            if stored_value != getattr(self, global_attr):
                setattr(self, global_attr, stored_value)
                if self.project_caption_mode == "all":
                    self.project_caption_mode = "by_type"
                self.is_modified = True
                self._schedule_preview(450)
            schedule_preview()

        def apply_shared_to_all():
            sync_shared_text(force=True)
            for index, _path, edit in media:
                presentation = normalize_presentation(edit.get("presentation"))
                presentation["mode"] = "global"
                edit["presentation"] = presentation
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            schedule_preview()
            preview_status.config(text=f"Κοινό caption εφαρμόστηκε σε {len(media)} media")

        def caption_changed(*_):
            if state["loading"]:
                return
            if state["mode"] == "individual":
                state["dirty"] = True
                save_current()
            schedule_preview()

        def apply_caption_action():
            if state["mode"] == "individual":
                index = state.get("current")
                if index is None:
                    messagebox.showinfo("Captions", "Επίλεξε πρώτα media.", parent=dialog)
                    return
                write_item_caption(index, caption_values())
                state["dirty"] = False
                preview_status.config(text="Caption αποθηκεύτηκε για αυτό το media")
            elif state["mode"] == "group":
                selected_indices = [int(item_id) for item_id in tree.selection()]
                if not selected_indices:
                    messagebox.showinfo("Captions", "Επίλεξε ένα ή περισσότερα media.", parent=dialog)
                    return
                for index in selected_indices:
                    write_item_caption(index, caption_values())
                preview_status.config(text=f"Caption εφαρμόστηκε σε {len(selected_indices)} media")
            self.update_media_display()
            self._schedule_preview()
            schedule_preview()

        shared_text.bind("<KeyRelease>", sync_shared_text, add="+")
        self._bind_captions_text(shared_text, lambda: sync_shared_text())
        mode_combo.bind("<<ComboboxSelected>>", mode_changed, add="+")
        tree.bind("<<TreeviewSelect>>", tree_selection)
        title_var.trace_add("write", caption_changed)
        subtitle_var.trace_add("write", caption_changed)
        self._bind_captions_text(description, lambda: caption_changed())
        apply_shared.config(command=apply_shared_to_all)
        apply_caption.config(command=apply_caption_action)
        improve.config(command=lambda: self.improve_text_with_ai(
            shared_text.get("1.0", "end-1c"), instructions.get("1.0", "end-1c"),
            apply_result=lambda value: (self._replace_caption_text(shared_text, value),
                                        sync_shared_text()),
            set_busy=lambda busy: (improve.config(state="disabled" if busy else "normal"),
                                   preview_status.config(text="AI γράφει..." if busy else ""))))

        def open_design():
            if state["mode"] == "individual" and state.get("current") is not None:
                self.open_presentation_editor(state["current"])
                return
            selected_indices = [int(item_id) for item_id in tree.selection()]
            if state["mode"] == "shared":
                selected_indices = [index for index, _path, _edit in media]
            if not selected_indices:
                selected_indices = [index for index, _path, _edit in media[:1]]
            self.selected_indices = set(selected_indices)
            self.open_storyboard_editor()

        design_button.config(command=open_design)

        def load_thumbnail(index, path):
            image = (self._video_first_frame(path) if media_type == "video" else Image.open(path))
            if media_type == "image":
                image.load()
            image = image.convert("RGB")
            tw, th = 100, 56
            scale = max(tw / image.width, th / image.height)
            image = image.resize((round(image.width * scale), round(image.height * scale)),
                                 Image.Resampling.LANCZOS)
            x = max(0, (image.width - tw) // 2)
            y = max(0, (image.height - th) // 2)
            return index, image.crop((x, y, x + tw, y + th))

        def install_thumbnail(index, image):
            if state["closed"] or image is None:
                return
            try:
                photo = ImageTk.PhotoImage(image)
                state.setdefault("thumbs", {})[index] = photo
                tree.item(str(index), image=photo)
            except tk.TclError:
                pass

        def thumbnail_worker():
            for index, path, _edit in media:
                if state["closed"]:
                    return
                try:
                    index, image = load_thumbnail(index, path)
                    self._post_ui(install_thumbnail, index, image)
                except Exception:
                    continue

        if media:
            threading.Thread(target=thumbnail_worker, daemon=True).start()
        mode_combo.set(mode_by_value[state["mode"]])
        if state["mode"] == "individual" and media:
            tree.selection_set(str(media[0][0]))
            tree.focus(str(media[0][0]))
            load_current(media[0][0])
        else:
            mode_changed()

        return {"frame": page, "save_current": save_current,
                "reload_shared": lambda: self._replace_caption_text(
                    shared_text, self.get_text_for(media_type)),
                "refresh_preview": schedule_preview,
                "closed": lambda: state.update(closed=True)}
