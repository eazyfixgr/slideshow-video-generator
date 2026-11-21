"""The right-hand inspector with one shared caption/design scope."""

import tkinter as tk
from tkinter import ttk

from .ui_caption_inspector import CAPTION_STRATEGIES
from .ui_inline_editors import InlineEditorsMixin
from .ui_scene_controls import SceneControlsMixin
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import ScrollFrame, flat_button, primary_button

INSPECTOR_TABS = (("captions", "Captions"), ("design", "Slide Design"))


class InspectorMixin(SceneControlsMixin, InlineEditorsMixin):
    def _build_inspector(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        header = tk.Frame(parent, bg=P["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        scope_row = tk.Frame(header, bg=P["panel"])
        scope_row.pack(fill="x")
        tk.Label(scope_row, text="Εφαρμογή σε", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        self.inspector_scope_var = tk.StringVar()
        self.inspector_scope_combo = ttk.Combobox(
            scope_row, textvariable=self.inspector_scope_var,
            values=list(CAPTION_STRATEGIES), state="readonly", width=20)
        self.inspector_scope_combo.pack(side="left", fill="x", expand=True)
        self.inspector_scope_combo.bind(
            "<<ComboboxSelected>>", lambda _e: self._set_caption_strategy(
                CAPTION_STRATEGIES[self.inspector_scope_var.get()]))
        self.inspector_title_var = tk.StringVar(value="Captions")
        tk.Label(header, textvariable=self.inspector_title_var, bg=P["panel"],
                 fg=P["text"], font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(6, 0))

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
        self._commit_pending_caption_apply()
        self.inspector_view = view if view in dict(INSPECTOR_TABS) else "captions"
        self._render_inspector()

    def _render_inspector(self):
        if not hasattr(self, "inspector_content") or getattr(self, "_inline_committing", False):
            return
        self._commit_pending_caption_apply()
        self._caption_apply_callback = None
        self.inspector_scope_var.set(next(
            label for label, mode in CAPTION_STRATEGIES.items()
            if mode == self.project_caption_mode))
        view = getattr(self, "inspector_view", "captions")
        for key, button in self._inspector_tab_buttons.items():
            button.configure(background=P["accent_faint"] if key == view else P["panel"],
                             foreground=P["accent"] if key == view else P["muted"])
        self._cancel_pending_caption_apply()
        for child in self.inspector_content.winfo_children():
            child.destroy()
        self._inspector_caption_refs = None
        scroller = ScrollFrame(self.inspector_content, background=P["panel"])
        scroller.pack(fill="both", expand=True)
        body = tk.Frame(scroller.body, bg=P["panel"], padx=14, pady=6)
        body.pack(fill="both", expand=True)
        if view == "captions":
            self._render_captions_inspector(body)
        else:
            self._render_design_inspector(body)

    def _inspector_scope_targets(self):
        if self.project_caption_mode == "all":
            return list(self.media_files)
        if self.project_caption_mode == "by_type":
            kind = getattr(self, "_design_media_type", "image")
            return [item for item in self.media_files if item[0] == kind]
        targets = [self.media_files[i] for i in self._selected()]
        _index, item = self._selected_item()
        return targets or ([item] if item is not None else [])

    def _render_design_type_selector(self, body):
        row = tk.Frame(body, bg=P["panel"])
        row.pack(fill="x", pady=(2, 6))
        kind = getattr(self, "_design_media_type", "image")

        def select(value):
            self._commit_pending_caption_apply()
            self._design_media_type = value
            self._render_inspector()

        for value, label in (("image", "Φωτογραφίες"), ("video", "Βίντεο")):
            count = sum(item[0] == value for item in self.media_files)
            flat_button(row, f"{label} ({count})", lambda v=value: select(v),
                        background=P["accent_faint"] if value == kind else P["raised"],
                        foreground=P["accent"] if value == kind else P["muted"],
                        active_background=P["selected"], font=("Segoe UI", 8)).pack(
                side="left", expand=True, fill="x", padx=(0, 3))

    def _render_design_type_selector(self, body):
        row = tk.Frame(body, bg=P["panel"])
        row.pack(fill="x", pady=(3, 6))
        current = getattr(self, "_design_media_type", "image")

        def select(kind):
            self._commit_pending_caption_apply()
            self._design_media_type = kind
            self._render_inspector()

        for kind, label in (("image", "Φωτογραφίες"), ("video", "Βίντεο")):
            flat_button(row, label, lambda k=kind: select(k),
                        background=P["selected"] if current == kind else P["raised"],
                        foreground=P["accent"] if current == kind else P["muted"],
                        active_background=P["selected"], font=("Segoe UI", 9)).pack(
                side="left", fill="x", expand=True, padx=2)

    def _selected_item_index(self):
        selected = sorted(getattr(self, "selected_indices", set()))
        if selected and 0 <= selected[0] < len(self.media_files):
            return selected[0]
        return 0 if self.media_files else None

    def _selected_item(self):
        index = self._selected_item_index()
        return (index, self.media_files[index]) if index is not None else (None, None)

    def _section(self, parent, text):
        tk.Label(parent, text=text, bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 4))

    def _empty_inspector(self, parent, text):
        box = tk.Frame(parent, bg=P["raised"], highlightbackground=P["border"],
                       highlightthickness=1, padx=12, pady=14)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text=text, bg=P["raised"], fg=P["muted"], font=("Segoe UI", 9),
                 wraplength=250, justify="left").pack(anchor="w")
        primary_button(box, "Προσθήκη media", self.import_media).pack(anchor="w", pady=(10, 0))

    def _after_scene_edit(self):
        self._schedule_preview(120)
        self.render_storyboard()
        self._refresh_stage()
        self._refresh_header()
