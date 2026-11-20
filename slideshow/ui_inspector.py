"""The right-hand inspector: scene settings, captions and slide design."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .slide_design import (DEFAULT_PRESENTATION, TEMPLATES, normalize_presentation,
                           normalize_template)
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import (ASPECTS, ScrollFrame, chip, flat_button, format_duration,
                         primary_button, resolution_for_aspect, aspect_label)

TRANSITIONS = {
    "Από το project": "global",
    "Καμία": "none",
    "Fade": "fade",
    "Fade to black": "fadeblack",
    "Fade to white": "fadewhite",
    "Wipe left": "wipeleft",
    "Wipe right": "wiperight",
    "Smooth left": "smoothleft",
    "Smooth right": "smoothright",
}
TRANSITION_BY_VALUE = {value: label for label, value in TRANSITIONS.items()}
INSPECTOR_TABS = (("captions", "Captions"), ("story", "Storyboard"),
                  ("design", "Slide Design"))


class InspectorMixin:
    """The right-hand inspector: scene settings, captions and slide design."""

    def _build_inspector(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        header = tk.Frame(parent, bg=P["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        tk.Label(header, text="ΙΔΙΟΤΗΤΕΣ", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.inspector_title_var = tk.StringVar(value="Επιλεγμένη σκηνή")
        tk.Label(header, textvariable=self.inspector_title_var, bg=P["panel"],
                 fg=P["text"], font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(1, 0))

        tabbar = tk.Frame(parent, bg=P["panel"])
        tabbar.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 6))
        self._inspector_tab_buttons = {}
        for key, label in INSPECTOR_TABS:
            button = flat_button(tabbar, label, lambda k=key: self._set_inspector_view(k),
                                 background=P["panel"], foreground=P["muted"],
                                 active_background=P["selected"], font=("Segoe UI", 8),
                                 padx=7, pady=5)
            button.pack(side="left", padx=(0, 2))
            self._inspector_tab_buttons[key] = button

        self.inspector_content = tk.Frame(parent, bg=P["panel"])
        self.inspector_content.grid(row=2, column=0, sticky="nsew")
        self.inspector_view = getattr(self, "inspector_view", "captions")
        self._render_inspector()

    def _set_inspector_view(self, view):
        self.inspector_view = view if view in dict(INSPECTOR_TABS) else "story"
        self._render_inspector()

    def _render_inspector(self):
        if not hasattr(self, "inspector_content"):
            return
        view = getattr(self, "inspector_view", "captions")
        for key, button in getattr(self, "_inspector_tab_buttons", {}).items():
            try:
                button.configure(background=(P["accent_faint"] if key == view else P["panel"]),
                                 foreground=(P["accent"] if key == view else P["muted"]))
            except tk.TclError:
                pass
        for child in self.inspector_content.winfo_children():
            child.destroy()
        self._inspector_caption_refs = None
        scroller = ScrollFrame(self.inspector_content, background=P["panel"])
        scroller.pack(fill="both", expand=True)
        body = tk.Frame(scroller.body, bg=P["panel"], padx=14, pady=6)
        body.pack(fill="both", expand=True)
        if view == "captions":
            self._render_captions_inspector(body)
        elif view == "design":
            self._render_design_inspector(body)
        else:
            self._render_story_inspector(body)

    def _selected_item_index(self):
        selected = sorted(getattr(self, "selected_indices", set()))
        if selected:
            index = selected[0]
            if 0 <= index < len(getattr(self, "media_files", [])):
                return index
        return 0 if getattr(self, "media_files", None) else None

    def _selected_item(self):
        index = self._selected_item_index()
        return (index, self.media_files[index]) if index is not None else (None, None)

    def _section(self, parent, text):
        tk.Label(parent, text=text, bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 4))

    def _empty_inspector(self, parent, text):
        box = tk.Frame(parent, bg=P["raised"], highlightthickness=1,
                       highlightbackground=P["border"], padx=12, pady=14)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text=text, bg=P["raised"], fg=P["muted"], font=("Segoe UI", 9),
                 wraplength=250, justify="left").pack(anchor="w")
        primary_button(box, "Προσθήκη media", self.import_media).pack(anchor="w", pady=(10, 0))

    def _sync_captions_inspector(self):
        """Push changes made in the full captions editor into the side panel."""
        refs = getattr(self, "_inspector_caption_refs", None)
        if not refs:
            return
        mode = getattr(self, "project_caption_mode", "all")
        try:
            refs["mode_var"].set(mode)
            refs["set_mode"](mode)
            values = {
                "all": getattr(self, "project_text_all", "") or "",
                "video": getattr(self, "project_text_videos", "") or "",
                "photo": getattr(self, "project_text_photos", "") or "",
            }
            for key, value in values.items():
                widget = refs.get(key)
                if widget is None or not widget.winfo_exists():
                    continue
                widget.delete("1.0", "end")
                widget.insert("1.0", value)
                widget.edit_reset()
        except tk.TclError:
            pass

    def _render_story_inspector(self, body):
        index, item = self._selected_item()
        if item is None:
            self.inspector_title_var.set("Καμία σκηνή")
            self._empty_inspector(body, "Πρόσθεσε φωτογραφίες ή βίντεο για να ρυθμίσεις "
                                        "διάρκεια, μετάβαση και μορφή.")
            return
        path, kind, edit = item[1], item[0], item[2]
        presentation = normalize_presentation(edit.get("presentation"))
        self.inspector_title_var.set(f"Σκηνή {index + 1:02d}")
        summary = tk.Frame(body, bg=P["raised"], highlightthickness=1,
                           highlightbackground=P["border"], padx=10, pady=9)
        summary.pack(fill="x", pady=(4, 0))
        tk.Label(summary, text=("▶ ΒΙΝΤΕΟ" if kind == "video" else "▦ ΦΩΤΟΓΡΑΦΙΑ"),
                 bg=P["raised"], fg=P["accent"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(summary, text=Path(path).name, bg=P["raised"], fg=P["text"],
                 font=("Segoe UI", 9, "bold"), wraplength=250, justify="left").pack(
            anchor="w", pady=(2, 0))
        tk.Label(summary, text=f"{aspect_label(self.settings.get('resolution'))} · "
                              f"{format_duration(self._scene_seconds(item))}",
                 bg=P["raised"], fg=P["muted"], font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        self._section(body, "ΔΙΑΡΚΕΙΑ ΣΚΗΝΗΣ")
        duration_row = tk.Frame(body, bg=P["panel"])
        duration_row.pack(fill="x")
        current_duration = presentation.get("duration")
        duration_var = tk.StringVar(value=("" if current_duration is None
                                           else f"{float(current_duration):g}"))
        spin = ttk.Spinbox(duration_row, from_=0.5, to=60, increment=0.5, width=9,
                           textvariable=duration_var)
        spin.pack(side="left")
        tk.Label(duration_row, text="δευτ. (κενό = προεπιλογή project)",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8)).pack(
            side="left", padx=(8, 0))

        def apply_duration():
            value = duration_var.get().strip()
            try:
                seconds = None if not value else max(0.2, min(600.0, float(value)))
            except ValueError:
                return
            self.push_undo()
            data = normalize_presentation(edit.get("presentation"))
            data["duration"] = seconds
            edit["presentation"] = data
            self.is_modified = True
            self._after_scene_edit()

        apply = flat_button(duration_row, "OK", apply_duration, background=P["panel"],
                            foreground=P["accent"], active_background=P["selected"],
                            font=("Segoe UI", 8, "bold"), padx=6, pady=2)
        apply.pack(side="left", padx=(8, 0))
        spin.bind("<Return>", lambda _e: apply_duration())

        self._section(body, "ΜΕΤΑΒΑΣΗ")
        transition_var = tk.StringVar(value=TRANSITION_BY_VALUE.get(
            presentation.get("transition", "global"), "Από το project"))
        transition_combo = ttk.Combobox(body, textvariable=transition_var,
                                        values=list(TRANSITIONS), state="readonly")
        transition_combo.pack(fill="x")
        transition_duration = tk.StringVar(
            value="" if presentation.get("transition_duration") is None
            else f"{float(presentation['transition_duration']):g}")
        tr_row = tk.Frame(body, bg=P["panel"])
        tr_row.pack(fill="x", pady=(6, 0))
        tk.Label(tr_row, text="Διάρκεια", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8)).pack(side="left")
        ttk.Spinbox(tr_row, from_=0.2, to=2.0, increment=0.1, width=7,
                    textvariable=transition_duration).pack(side="left", padx=(6, 0))
        tk.Label(tr_row, text="δευτ. (κενό = project)", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))

        def apply_transition(*_event):
            self.push_undo()
            data = normalize_presentation(edit.get("presentation"))
            data["transition"] = TRANSITIONS.get(transition_var.get(), "global")
            raw = transition_duration.get().strip()
            try:
                data["transition_duration"] = (None if not raw else
                                                max(0.2, min(2.0, float(raw))))
            except ValueError:
                data["transition_duration"] = None
            edit["presentation"] = data
            self.is_modified = True
            self._after_scene_edit()

        transition_combo.bind("<<ComboboxSelected>>", apply_transition)
        tr_row.winfo_children()[1].bind("<Return>", lambda _e: apply_transition())

        self._section(body, "ΜΟΡΦΗ PROJECT")
        resolution_var = tk.StringVar(value=aspect_label(self.settings.get("resolution")))
        aspect_combo = ttk.Combobox(body, textvariable=resolution_var,
                                    values=("9:16", "4:5", "1:1", "16:9"),
                                    state="readonly")
        aspect_combo.pack(fill="x")

        def apply_resolution(_event=None):
            resolution = resolution_for_aspect(resolution_var.get())
            if resolution == self.settings.get("resolution"):
                return
            self.settings["resolution"] = resolution
            self.is_modified = True
            self.save_settings()
            self._refresh_stage()
            self._schedule_preview(150)
            self.render_storyboard()

        aspect_combo.bind("<<ComboboxSelected>>", apply_resolution)

        project_duration = tk.StringVar(value=str(self.settings.get("slide_duration", 3)))
        project_row = tk.Frame(body, bg=P["panel"])
        project_row.pack(fill="x", pady=(6, 0))
        tk.Label(project_row, text="Προεπιλογή διάρκειας", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8)).pack(side="left")
        ttk.Spinbox(project_row, from_=1, to=60, increment=1, width=6,
                    textvariable=project_duration).pack(side="left", padx=(6, 0))

        def apply_project_duration():
            try:
                value = max(1, min(60, int(float(project_duration.get()))))
            except ValueError:
                return
            self.settings["slide_duration"] = value
            self.is_modified = True
            self.save_settings()
            self._schedule_preview(150)
            self.render_storyboard()

        project_row.winfo_children()[1].bind("<Return>",
                                             lambda _e: apply_project_duration())

        self._section(body, "ΕΝΕΡΓΕΙΕΣ")
        primary_button(body, "Presentation / Slide Design",
                       lambda: self.open_presentation_editor(index)).pack(fill="x", pady=(2, 4))
        flat_button(body, "Storyboard editor", self.open_storyboard_editor,
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"]).pack(fill="x", pady=2)
        flat_button(body, "Διαγραφή σκηνής",
                    lambda: self.delete_media(index), background=P["raised"],
                    foreground=P["danger"], active_background=P["selected"]).pack(
            fill="x", pady=2)

    def _render_captions_inspector(self, body):
        self.inspector_title_var.set("Κείμενα project")
        self._section(body, "ΣΤΡΑΤΗΓΙΚΗ")
        mode_var = tk.StringVar(value=getattr(self, "project_caption_mode", "all"))
        ttk.Radiobutton(body, text="Ένα κοινό κείμενο για όλες τις σκηνές",
                        variable=mode_var, value="all", style="Panel.TRadiobutton",
                        command=lambda: set_mode("all")).pack(anchor="w")
        ttk.Radiobutton(body, text="Ξεχωριστό κείμενο για φωτογραφίες / βίντεο",
                        variable=mode_var, value="by_type", style="Panel.TRadiobutton",
                        command=lambda: set_mode("by_type")).pack(anchor="w")

        text_holder = tk.Frame(body, bg=P["panel"])
        text_holder.pack(fill="x", pady=(6, 0))
        all_box = tk.Frame(text_holder, bg=P["panel"])
        by_type_box = tk.Frame(text_holder, bg=P["panel"])
        all_text = tk.Text(all_box, height=5, wrap="word", bg=P["field"],
                           fg=P["text"], insertbackground=P["text"],
                           highlightthickness=1, highlightbackground=P["border"],
                           font=("Segoe UI", 9), relief="flat", padx=8, pady=6)
        all_text.pack(fill="x")
        all_text.insert("1.0", getattr(self, "project_text_all", "") or "")

        video_text = tk.Text(by_type_box, height=4, wrap="word", bg=P["field"],
                             fg=P["text"], insertbackground=P["text"],
                             highlightthickness=1, highlightbackground=P["border"],
                             font=("Segoe UI", 9), relief="flat", padx=8, pady=6)
        video_text.pack(fill="x", pady=(0, 6))
        video_text.insert("1.0", getattr(self, "project_text_videos", "") or "")
        photo_text = tk.Text(by_type_box, height=4, wrap="word", bg=P["field"],
                             fg=P["text"], insertbackground=P["text"],
                             highlightthickness=1, highlightbackground=P["border"],
                             font=("Segoe UI", 9), relief="flat", padx=8, pady=6)
        photo_text.pack(fill="x")
        photo_text.insert("1.0", getattr(self, "project_text_photos", "") or "")
        tk.Label(by_type_box, text="Πάνω: βίντεο · Κάτω: φωτογραφίες",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8)).pack(
            anchor="w", pady=(3, 0))

        def set_mode(value):
            self.project_caption_mode = value
            if value == "all":
                by_type_box.pack_forget()
                all_box.pack(fill="x", pady=(6, 0))
            else:
                all_box.pack_forget()
                by_type_box.pack(fill="x", pady=(6, 0))

        set_mode(getattr(self, "project_caption_mode", "all"))

        def apply_text(*_event):
            self.project_caption_mode = mode_var.get()
            if self.project_caption_mode == "all":
                self.project_text_all = all_text.get("1.0", "end-1c").strip()
                self.project_text_videos = self.project_text_all
                self.project_text_photos = self.project_text_all
            else:
                self.project_text_videos = video_text.get("1.0", "end-1c").strip()
                self.project_text_photos = photo_text.get("1.0", "end-1c").strip()
            self.is_modified = True
            self._schedule_preview(200)

        clear_buttons = tk.Frame(body, bg=P["panel"])
        clear_buttons.pack(fill="x", pady=(6, 0))
        flat_button(clear_buttons, "Εφαρμογή κειμένου", apply_text,
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"], font=("Segoe UI", 8, "bold"),
                    padx=8, pady=4).pack(side="left")
        flat_button(clear_buttons, "Καθαρισμός",
                    lambda: (all_text.delete("1.0", "end"),
                             video_text.delete("1.0", "end"),
                             photo_text.delete("1.0", "end"),
                             apply_text()),
                    background=P["raised"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8),
                    padx=8, pady=4).pack(side="left", padx=(4, 0))

        self._section(body, "TEMPLATE ΚΕΙΜΕΝΟΥ")
        template_var = getattr(self, "_caption_template_var", None)
        if template_var is None:
            self._caption_template_var = template_var = tk.StringVar()
        self._sync_caption_template_dropdown()
        combo = ttk.Combobox(body, textvariable=template_var,
                             values=list(TEMPLATES.values()), state="readonly")
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", self._on_caption_template_selected, add="+")

        def open_full_editor():
            apply_text()
            self.open_text_captions_manager(
                initial_strategy=getattr(self, "project_caption_mode", "all"))

        self._section(body, "ΠΕΡΙΣΣΟΤΕΡΑ")
        primary_button(body, "Πλήρης επεξεργασία κειμένων",
                       open_full_editor).pack(fill="x", pady=(2, 4))
        primary_button(body, "Presentation / Slide Design",
                       lambda: self.open_presentation_editor(self._selected_item_index())
                       if self._selected_item_index() is not None else None).pack(fill="x", pady=2)

        self._inspector_caption_refs = {
            "mode_var": mode_var,
            "set_mode": set_mode,
            "all": all_text,
            "video": video_text,
            "photo": photo_text,
        }

    def _render_design_inspector(self, body):
        self.inspector_title_var.set("Slide Design")
        self._section(body, "PROJECT DEFAULT TEMPLATE")
        template_var = tk.StringVar(value=TEMPLATES.get(
            normalize_template(getattr(self, "project_template", "legacy")),
            TEMPLATES["legacy"]))
        combo = ttk.Combobox(body, textvariable=template_var,
                             values=list(TEMPLATES.values()), state="readonly")
        combo.pack(fill="x")

        def apply_default(_event=None):
            key = next((name for name, label in TEMPLATES.items()
                        if label == template_var.get()), "legacy")
            self.project_template = self._remember_caption_template(key)
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview(150)
            self.render_storyboard()

        combo.bind("<<ComboboxSelected>>", apply_default, add="+")

        self._section(body, "TEMPLATES")
        grid = tk.Frame(body, bg=P["panel"])
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="template")
        grid.columnconfigure(1, weight=1, uniform="template")
        descriptions = {
            "legacy": "Απλό · καθαρό κείμενο",
            "navy_gold": "Navy & Gold editorial",
            "cinematic": "Σινεματικός υπότιτλος",
            "lower_third": "Διαφανές lower third",
            "intro_outro": "Introduction / Outro",
        }
        index, item = self._selected_item()
        for position, (key, label) in enumerate(TEMPLATES.items()):
            card = tk.Frame(grid, bg=P["raised"], highlightthickness=1,
                            highlightbackground=P["border"], padx=8, pady=7,
                            cursor="hand2")
            card.grid(row=position // 2, column=position % 2, sticky="nsew",
                      padx=(0 if position % 2 == 0 else 4, 0), pady=4)
            tk.Label(card, text="Aa", bg=P["raised"], fg=P["accent"],
                     font=("Segoe UI", 14, "bold")).pack(anchor="w")
            tk.Label(card, text=label, bg=P["raised"], fg=P["text"],
                     font=("Segoe UI", 8, "bold"), wraplength=120,
                     justify="left").pack(anchor="w")
            tk.Label(card, text=descriptions.get(key, ""), bg=P["raised"],
                     fg=P["muted"], font=("Segoe UI", 7), wraplength=120,
                     justify="left").pack(anchor="w", pady=(2, 0))
            if key == normalize_template(getattr(self, "project_template", "legacy")):
                card.configure(highlightbackground=P["accent"], highlightthickness=2)
            if index is not None:
                card.bind("<Button-1>", lambda _e, k=key, i=index:
                          self._apply_template_to_scene(i, k))
                for child in card.winfo_children():
                    child.bind("<Button-1>", lambda _e, k=key, i=index:
                               self._apply_template_to_scene(i, k))

        self._section(body, "ΕΦΑΡΜΟΓΗ")
        tk.Label(body, text="Κλικ σε template για την επιλεγμένη σκηνή. "
                           "Οι πλήρεις ρυθμίσεις ανοίγουν στον editor.",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8),
                 wraplength=255, justify="left").pack(anchor="w", pady=(0, 6))
        if index is None:
            self._empty_inspector(body, "Διάλεξε ή πρόσθεσε μια σκηνή για να εφαρμόσεις template.")
            return
        primary_button(body, "Presentation / Slide Design",
                       lambda: self.open_presentation_editor(index)).pack(fill="x", pady=2)
        flat_button(body, "Εφαρμογή σε όλες τις σκηνές",
                    lambda: self._apply_template_to_all(
                        normalize_template(getattr(self, "project_template", "legacy"))),
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"]).pack(fill="x", pady=2)
        flat_button(body, "Slide Design / Project Templates",
                    self.open_storyboard_editor, background=P["raised"],
                    foreground=P["text"], active_background=P["selected"]).pack(
            fill="x", pady=2)

    def _after_scene_edit(self):
        self._schedule_preview(120)
        self.render_storyboard()
        self._refresh_stage()
        self._refresh_header()

    def _apply_template_to_scene(self, index, template):
        if not (0 <= index < len(self.media_files)):
            return
        edit = self.media_files[index][2]
        self.push_undo()
        data = normalize_presentation(edit.get("presentation"))
        data["template"] = template
        edit["presentation"] = data
        self.is_modified = True
        self._after_scene_edit()
        self._render_inspector()

    def _apply_template_to_all(self, template):
        if not self.media_files:
            return
        self.push_undo()
        for _kind, _path, edit in self.media_files:
            data = normalize_presentation(edit.get("presentation"))
            data["template"] = template
            edit["presentation"] = data
        self.is_modified = True
        self.update_media_display()
        self._schedule_preview(150)
        self.render_storyboard()
        self._refresh_stage()
