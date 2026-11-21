"""Scoped scene timing and the project format dialog."""

import math
import tkinter as tk
from tkinter import ttk

from .slide_design import normalize_presentation
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import aspect_label, resolution_for_aspect, primary_button

TRANSITIONS = {
    "Προεπιλογή project": "global", "Χωρίς εφέ": "none", "Fade": "fade",
    "Fade to black": "fadeblack", "Fade to white": "fadewhite",
    "Wipe left": "wipeleft", "Wipe right": "wiperight",
    "Smooth left": "smoothleft", "Smooth right": "smoothright",
}


class SceneControlsMixin:
    def _render_slide_project_controls(self, body, targets, project_scope):
        self._section(body, "ΔΙΑΡΚΕΙΑ ΣΚΗΝΗΣ")
        presentation = normalize_presentation(
            targets[0][2].get("presentation") if targets else None)
        seconds = (self.settings.get("slide_duration", 3) if project_scope
                   else presentation.get("duration"))
        duration = tk.StringVar(value="" if seconds is None else f"{float(seconds):g}")
        self._inline_label(body, "Χρόνος προβολής σκηνής (δευτερόλεπτα)")
        duration_spin = ttk.Spinbox(body, from_=1, to=30, increment=0.5,
                                    textvariable=duration)
        duration_spin.pack(fill="x", pady=(2, 3))
        self._inline_label(body, "Κενό: προεπιλογή για φωτογραφίες, πλήρης διάρκεια βίντεο.")
        self._inline_label(body, "Στα βίντεο λειτουργεί ως μέγιστος χρόνος προβολής.")

        self._section(body, "ΕΦΕ ΜΕΤΑΒΑΣΗΣ")
        effect = (self.settings.get("transition_effect", "fade") if project_scope
                  else presentation.get("transition", "global"))
        effect_var = tk.StringVar(value=next(
            (label for label, value in TRANSITIONS.items() if value == effect),
            "Προεπιλογή project"))
        self._inline_label(body, "Εφέ ανάμεσα στις σκηνές")
        choices = {label: value for label, value in TRANSITIONS.items()
                   if not project_scope or value != "global"}
        if project_scope and effect not in choices.values():
            effect = "fade"
            effect_var.set("Fade")
        effect_combo = ttk.Combobox(body, textvariable=effect_var,
                                    values=list(choices), state="readonly")
        effect_combo.pack(fill="x", pady=(2, 6))
        tr_seconds = (self.settings.get("transition_duration", 0.7) if project_scope
                      else presentation.get("transition_duration"))
        transition_duration = tk.StringVar(
            value="" if tr_seconds is None else f"{float(tr_seconds):g}")
        self._inline_label(body, "Διάρκεια εφέ μετάβασης (δευτερόλεπτα)")
        effect_spin = ttk.Spinbox(body, from_=0.2, to=2, increment=0.1,
                                 textvariable=transition_duration)
        effect_spin.pack(fill="x", pady=(2, 3))
        self._inline_label(body, "Κενό: διάρκεια εφέ από τις προεπιλογές του project.")
        status = tk.StringVar()

        def apply():
            try:
                raw = duration.get().strip()
                value = float(raw) if raw else None
                raw_tr = transition_duration.get().strip()
                tr_value = float(raw_tr) if raw_tr else None
                if value is not None and (not math.isfinite(value) or not 1 <= value <= 30):
                    raise ValueError("Διάρκεια σκηνής: από 1 έως 30 δευτερόλεπτα.")
                if tr_value is not None and (not math.isfinite(tr_value) or not 0.2 <= tr_value <= 2):
                    raise ValueError("Διάρκεια εφέ: από 0,2 έως 2 δευτερόλεπτα.")
            except ValueError as error:
                status.set(str(error) if str(error).startswith("Διάρκεια")
                           else "Γράψε έγκυρο αριθμό δευτερολέπτων (π.χ. 3 ή 0.7).")
                return
            self._commit_pending_caption_apply()
            self.push_undo()
            chosen_effect = TRANSITIONS[effect_var.get()]
            if project_scope:
                if value is not None:
                    self.settings["slide_duration"] = value
                self.settings["transition_effect"] = chosen_effect
                if tr_value is not None:
                    self.settings["transition_duration"] = tr_value
            for _kind, _path, edit in targets:
                data = normalize_presentation(edit.get("presentation"))
                data["duration"] = value
                data["transition"] = "global" if project_scope else chosen_effect
                data["transition_duration"] = None if project_scope else tr_value
                edit["presentation"] = data
            self.is_modified = True
            self._after_scene_edit()
            status.set("Η διάρκεια σκηνής και το εφέ εφαρμόστηκαν στην επιλογή σου.")

        ttk.Button(body, text="Εφαρμογή διάρκειας και εφέ", command=apply).pack(
            fill="x", pady=(8, 2))
        self._inline_label(body).configure(textvariable=status)
        duration_spin.bind("<Return>", lambda _e: apply())
        effect_spin.bind("<Return>", lambda _e: apply())
        self._section(body, "ΕΜΦΑΝΙΣΗ ΚΕΙΜΕΝΟΥ & ΠΛΑΙΣΙΟΥ")

    def show_project_format(self):
        self._commit_pending_caption_apply()
        existing = getattr(self, "_project_format_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return
        dialog = tk.Toplevel(self.root)
        self._project_format_dialog = dialog
        dialog.title("Μορφή project")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Μορφή project", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        aspect = tk.StringVar(value=aspect_label(self.settings.get("resolution")))
        for ratio, label in (("9:16", "Κάθετο"), ("4:5", "Portrait"),
                             ("1:1", "Τετράγωνο"), ("16:9", "Οριζόντιο")):
            ttk.Radiobutton(body, text=f"{ratio} — {label}", variable=aspect,
                            value=ratio).pack(anchor="w", pady=6)

        def apply():
            resolution = resolution_for_aspect(aspect.get())
            if aspect.get() != aspect_label(self.settings.get("resolution")):
                self.settings["resolution"] = resolution
                self.project_settings = self._capture_project_settings()
                self._active_project_settings = True
                self.is_modified = True
                self._after_scene_edit()
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Ακύρωση", command=dialog.destroy).pack(side="right")
        primary_button(buttons, "Εφαρμογή μορφής", apply).pack(side="right", padx=(0, 8))
