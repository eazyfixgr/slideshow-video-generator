"""Per-media presentation editor, template preview, and batch design actions."""

import copy
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser

from .deps import Image, ImageTk
from .slide_design import (DEFAULT_PRESENTATION, TEMPLATES, compose_design_frame,
                           INHERIT_TEMPLATE, INHERIT_TEMPLATE_LABEL,
                           has_presentation_settings, normalize_presentation,
                           normalize_template, presentation_fields)


MODE_LABELS = {
    "Use Global Text": "global",
    "Custom Text": "custom",
    "No Text": "none",
    "Custom + Global": "combine",
}
MODE_BY_VALUE = {value: label for label, value in MODE_LABELS.items()}
POSITION_LABELS = {"Πάνω": "top", "Κέντρο": "center", "Κάτω": "bottom"}
ALIGNMENT_LABELS = {"Αριστερά": "left", "Κέντρο": "center", "Δεξιά": "right"}
PANEL_STYLE_LABELS = {"Συμπαγές": "solid", "Ημιδιαφανές": "translucent"}
DESIGN_KEYS = ("template", "text_position", "text_align", "featured_enabled", "featured_text",
               "font_family", "font_size", "text_color", "panel_color", "accent_color",
               "panel_style", "duration", "logo_enabled", "logo_path",
               "transition", "transition_duration", "motion")
class PresentationMixin:
    """Build the Presentation tab used by both photo and video editors."""

    def open_presentation_editor(self, idx):
        if not (0 <= idx < len(self.media_files)):
            return
        path = self.media_files[idx][1]
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Presentation / Slide Design — {Path(path).name}")
        dialog.geometry("1120x780")
        dialog.minsize(850, 600)
        dialog.transient(self.root)
        dialog.grab_set()
        tab = ttk.Frame(dialog)
        tab.pack(fill="both", expand=True)
        self._build_presentation_tab(tab, idx)
        ttk.Button(dialog, text="Κλείσιμο", command=dialog.destroy).pack(
            side="bottom", anchor="e", padx=12, pady=8)
        return dialog

    def open_storyboard_editor(self):
        """Open one persistent editor for captions across the full project."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Storyboard / Slide Content Manager")
        dialog.geometry("1420x860")
        dialog.minsize(1050, 680)
        dialog.transient(self.root)
        dialog.grab_set()

        body = ttk.Frame(dialog)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(body, text="Slides στο project")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        default_row = ttk.Frame(left)
        default_row.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(default_row, text="Project default template").pack(anchor="w")
        default_template_var = tk.StringVar(
            value=TEMPLATES.get(self.project_template, TEMPLATES["legacy"]))
        default_template_combo = ttk.Combobox(
            default_row, textvariable=default_template_var, state="readonly",
            values=list(TEMPLATES.values()), width=31)
        default_template_combo.pack(fill="x", pady=(2, 0))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True, padx=6, pady=6)
        items = tk.Listbox(list_frame, width=34, exportselection=False)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=items.yview)
        items.configure(yscrollcommand=scrollbar.set)
        items.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        ttk.Label(left, text="Η εφαρμογή αποθηκεύει τις αλλαγές του τρέχοντος slide "
                            "όταν επιλέγεις άλλο.", foreground="#666", wraplength=250,
                  justify="left").pack(fill="x", padx=8, pady=(0, 8))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        active = {"index": None, "panel": None, "holder": None}

        def label_for(index):
            kind, path, edit = self.media_files[index]
            icon = "▶" if kind == "video" else "▦"
            presentation = normalize_presentation(edit.get("presentation"))
            custom = " ✦" if has_presentation_settings(
                presentation, self.project_template) else ""
            return f"{index + 1:02d}. {icon} {Path(path).name}{custom}"

        def refresh_items():
            items.delete(0, tk.END)
            for index in range(len(self.media_files)):
                items.insert(tk.END, label_for(index))

        def set_project_template(*_):
            template = next((key for key, label in TEMPLATES.items()
                             if label == default_template_var.get()), "legacy")
            if template == self.project_template:
                return
            self.project_template = template
            self.is_modified = True
            refresh_items()
            self.update_media_display()
            panel = active.get("panel")
            refresh = getattr(panel, "refresh_presentation_preview", None) if panel else None
            if refresh:
                refresh()
            refresh_badge = getattr(panel, "refresh_featured_controls", None) if panel else None
            if refresh_badge:
                refresh_badge()

        default_template_var.trace_add("write", set_project_template)

        def select_item(index):
            if not 0 <= index < len(self.media_files):
                return
            if active["index"] == index:
                return
            panel = active.get("panel")
            if panel is not None:
                apply = getattr(panel, "apply_presentation", None)
                if apply:
                    apply()
                refresh_items()
            holder = active.get("holder")
            if holder is not None:
                holder.destroy()
            active["index"] = index
            items.selection_clear(0, tk.END)
            items.selection_set(index)
            items.activate(index)
            items.see(index)
            panel = ttk.Frame(right)
            panel.pack(fill="both", expand=True)
            active["holder"] = panel
            active["panel"] = self._build_presentation_tab(panel, index)
            dialog.title(f"Storyboard / Slide Content Manager — {Path(self.media_files[index][1]).name}")

        def on_select(_event=None):
            choice = items.curselection()
            if choice:
                select_item(choice[0])

        def close():
            panel = active.get("panel")
            if panel is not None:
                apply = getattr(panel, "apply_presentation", None)
                if apply:
                    apply()
            dialog.destroy()

        refresh_items()
        items.bind("<<ListboxSelect>>", on_select)
        items.bind("<Double-Button-1>", on_select)
        if self.media_files:
            select_item(0)
        else:
            ttk.Label(right, text="Πρόσθεσε media στο project για να επεξεργαστείς slides.",
                      foreground="#666").pack(expand=True)
        dialog.protocol("WM_DELETE_WINDOW", close)
        ttk.Button(dialog, text="Κλείσιμο και εφαρμογή αλλαγών", command=close).pack(
            side="bottom", anchor="e", padx=12, pady=(0, 10))
        return dialog

    def _build_presentation_tab(self, parent, idx):
        if not (0 <= idx < len(self.media_files)):
            return
        edit = self.media_files[idx][2]
        original = normalize_presentation(edit.get("presentation"))
        draft = copy.deepcopy(original)

        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        container.columnconfigure(0, weight=3)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        # ---------------------------- scrollable controls
        controls = ttk.Frame(container)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        controls.rowconfigure(0, weight=1)
        controls.columnconfigure(0, weight=1)
        form_canvas = tk.Canvas(controls, highlightthickness=0)
        form_scroll = ttk.Scrollbar(controls, orient="vertical", command=form_canvas.yview)
        form = ttk.Frame(form_canvas)
        form_window = form_canvas.create_window((0, 0), window=form, anchor="nw")
        form_canvas.configure(yscrollcommand=form_scroll.set)
        form_canvas.grid(row=0, column=0, sticky="nsew")
        form_scroll.grid(row=0, column=1, sticky="ns")
        form.bind("<Configure>", lambda _e: form_canvas.configure(
            scrollregion=form_canvas.bbox("all")))
        form_canvas.bind("<Configure>", lambda e: form_canvas.itemconfigure(
            form_window, width=e.width))

        vars_by_key = {}
        text_widgets = {}
        preview_state = {"job": None, "closed": False, "token": 0}

        def schedule_preview(*_):
            if preview_state["closed"]:
                return
            if preview_state["job"]:
                try:
                    parent.after_cancel(preview_state["job"])
                except Exception:
                    pass
            preview_state["job"] = parent.after(350, render_preview)

        def content_changed(*_):
            if mode_var.get() == "Use Global Text":
                mode_var.set("Custom Text")
            schedule_preview()

        def add_entry(label, key, width=40, parent_frame=None):
            row = ttk.Frame(parent_frame or form)
            row.pack(fill="x", padx=8, pady=3)
            ttk.Label(row, text=label, width=17).pack(side="left", anchor="n")
            var = tk.StringVar(value=draft.get(key, ""))
            entry = ttk.Entry(row, textvariable=var, width=width)
            entry.pack(side="left", fill="x", expand=True)
            vars_by_key[key] = var
            var.trace_add("write", content_changed)
            return entry

        def add_text(label, key, height=3):
            row = ttk.Frame(form)
            row.pack(fill="x", padx=8, pady=3)
            ttk.Label(row, text=label, width=17).pack(side="left", anchor="n", pady=4)
            widget = tk.Text(row, height=height, wrap="word", undo=True)
            widget.pack(side="left", fill="x", expand=True)
            widget.insert("1.0", draft.get(key, ""))
            widget.bind("<KeyRelease>", content_changed, add="+")
            text_widgets[key] = widget
            return widget

        ttk.Label(form, text="Presentation / Slide Design",
                  font=("Calibri", 13, "bold")).pack(anchor="w", padx=8, pady=(4, 8))
        mode_row = ttk.Frame(form)
        mode_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(mode_row, text="Κείμενο", width=17).pack(side="left")
        mode_var = tk.StringVar(value=MODE_BY_VALUE.get(draft["mode"], "Use Global Text"))
        ttk.Combobox(mode_row, textvariable=mode_var, state="readonly",
                     values=list(MODE_LABELS), width=25).pack(side="left", fill="x", expand=True)
        mode_var.trace_add("write", schedule_preview)
        vars_by_key["mode"] = mode_var
        ttk.Label(form, text="Το Global χρησιμοποιεί το υπάρχον κείμενο Φωτογραφιών/Βίντεο. "
                            "Το Custom + Global προσθέτει και το κοινό κείμενο. "
                            "Αν γράψεις σε πεδίο κειμένου ενώ είναι Global, επιλέγεται αυτόματα Custom.",
                  foreground="#666", wraplength=520, justify="left").pack(
            anchor="w", padx=8, pady=(0, 6))

        ttk.Separator(form).pack(fill="x", padx=8, pady=5)
        add_entry("Τίτλος", "title")
        add_entry("Υπότιτλος", "subtitle")
        add_text("Περιγραφή", "description", 4)

        advanced_fields = ("category", "location", "price", "details", "cta", "business_name",
                           "phone", "website")
        advanced_open = {"value": any(draft.get(key) and
                                       draft.get(key) != DEFAULT_PRESENTATION.get(key)
                                       for key in advanced_fields)}
        advanced_frame = ttk.LabelFrame(form, text="Προαιρετικές πληροφορίες", padding=4)

        def toggle_advanced():
            if advanced_open["value"]:
                advanced_frame.pack_forget()
                advanced_open["value"] = False
                advanced_button.config(text="＋ Περισσότερα πεδία")
            else:
                advanced_frame.pack(fill="x", padx=8, pady=(2, 6))
                advanced_open["value"] = True
                advanced_button.config(text="− Λιγότερα πεδία")

        advanced_button = ttk.Button(form, text="− Λιγότερα πεδία" if advanced_open["value"]
                                     else "＋ Περισσότερα πεδία", command=toggle_advanced)
        advanced_button.pack(anchor="w", padx=8, pady=(4, 2))
        if advanced_open["value"]:
            advanced_frame.pack(fill="x", padx=8, pady=(2, 6))
        add_entry("Κατηγορία / τύπος", "category", parent_frame=advanced_frame)
        add_entry("Τοποθεσία", "location", parent_frame=advanced_frame)
        add_entry("Τιμή", "price", parent_frame=advanced_frame)
        add_entry("Σημαντικές λεπτομέρειες", "details", parent_frame=advanced_frame)
        add_entry("Call to action", "cta", parent_frame=advanced_frame)
        add_entry("Επωνυμία", "business_name", parent_frame=advanced_frame)
        add_entry("Τηλέφωνο", "phone", parent_frame=advanced_frame)
        add_entry("Ιστότοπος", "website", parent_frame=advanced_frame)

        ttk.Separator(form).pack(fill="x", padx=8, pady=6)
        template_row = ttk.Frame(form)
        template_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(template_row, text="Template", width=17).pack(side="left")
        template_label = (INHERIT_TEMPLATE_LABEL if draft["template"] == INHERIT_TEMPLATE
                          else TEMPLATES.get(draft["template"], TEMPLATES["legacy"]))
        template_var = tk.StringVar(value=template_label)
        ttk.Combobox(template_row, textvariable=template_var, state="readonly",
                     values=[INHERIT_TEMPLATE_LABEL, *TEMPLATES.values()]).pack(
            side="left", fill="x", expand=True)
        template_var.trace_add("write", schedule_preview)

        featured_row = ttk.Frame(form)
        featured_row.pack(fill="x", padx=8, pady=3)
        featured_enabled_var = tk.BooleanVar(value=draft["featured_enabled"])
        featured_check = ttk.Checkbutton(featured_row, text="Εμφάνιση Featured badge",
                                         variable=featured_enabled_var)
        featured_check.pack(side="left")
        featured_text_var = tk.StringVar(value=draft["featured_text"])
        ttk.Label(featured_row, text="Κείμενο badge:").pack(side="left", padx=(8, 3))
        featured_entry = ttk.Entry(featured_row, textvariable=featured_text_var, width=20)
        featured_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(form, text="Το badge χρησιμοποιείται στο Elegant Navy & Gold.",
                  foreground="#666").pack(anchor="w", padx=8)

        def selected_template_key():
            if template_var.get() == INHERIT_TEMPLATE_LABEL:
                return self.project_template
            return next((key for key, label in TEMPLATES.items()
                         if label == template_var.get()), "legacy")

        def update_featured_controls(*_):
            active = selected_template_key() == "navy_gold"
            featured_check.config(state="normal" if active else "disabled")
            featured_entry.config(state=("normal" if active and featured_enabled_var.get()
                                         else "disabled"))

        featured_enabled_var.trace_add("write", schedule_preview)
        featured_enabled_var.trace_add("write", update_featured_controls)
        featured_text_var.trace_add("write", schedule_preview)
        template_var.trace_add("write", update_featured_controls)
        update_featured_controls()

        preset_row = ttk.Frame(form)
        preset_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(preset_row, text="Design preset", width=17).pack(side="left")
        preset_var = tk.StringVar()
        saved_presets = self.settings.get("slide_design_presets", {})
        if not isinstance(saved_presets, dict):
            saved_presets = {}
        preset_combo = ttk.Combobox(
            preset_row, textvariable=preset_var, state="readonly",
            values=sorted(saved_presets.keys()))
        preset_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(preset_row, text="Φόρτωση", command=lambda: load_preset()).pack(side="left", padx=4)

        duration_row = ttk.Frame(form)
        duration_row.pack(fill="x", padx=8, pady=4)
        duration_enabled = tk.BooleanVar(value=draft["duration"] is not None)
        ttk.Checkbutton(duration_row, text="Ατομική διάρκεια slide (δευτ.)",
                        variable=duration_enabled, command=schedule_preview).pack(side="left")
        duration_var = tk.DoubleVar(value=draft["duration"] or
                                    self.settings.get("slide_duration", 3))
        duration_spin = ttk.Spinbox(duration_row, from_=1, to=30, increment=0.5,
                                    textvariable=duration_var, width=7)
        duration_spin.pack(side="left", padx=6)
        duration_var.trace_add("write", schedule_preview)
        ttk.Label(form, text="Στα βίντεο η ατομική διάρκεια είναι μέγιστος χρόνος αναπαραγωγής.",
                  foreground="#666", wraplength=520).pack(anchor="w", padx=8)

        transition_row = ttk.Frame(form)
        transition_row.pack(fill="x", padx=8, pady=4)
        ttk.Label(transition_row, text="Μετάβαση προς slide", width=17).pack(side="left")
        transition_labels = {
            "Παγκόσμια ρύθμιση": "global", "Καμία": "none", "Fade": "fade",
            "Fade to Black": "fadeblack", "Fade to White": "fadewhite",
            "Wipe Left": "wipeleft", "Wipe Right": "wiperight", "Wipe Up": "wipeup",
            "Wipe Down": "wipedown", "Smooth Left": "smoothleft",
            "Smooth Right": "smoothright",
        }
        transition_var = tk.StringVar(value=next(
            (label for label, value in transition_labels.items() if value == draft["transition"]),
            "Παγκόσμια ρύθμιση"))
        ttk.Combobox(transition_row, textvariable=transition_var, state="readonly",
                     values=list(transition_labels), width=20).pack(side="left", fill="x", expand=True)
        transition_var.trace_add("write", schedule_preview)
        custom_transition_duration = tk.BooleanVar(value=draft["transition_duration"] is not None)
        ttk.Checkbutton(transition_row, text="Διάρκεια", variable=custom_transition_duration,
                        command=schedule_preview).pack(side="left", padx=(8, 3))
        transition_duration_var = tk.DoubleVar(value=draft["transition_duration"] or
                                               self.settings.get("transition_duration", .7))
        ttk.Spinbox(transition_row, from_=.2, to=2.0, increment=.1,
                    textvariable=transition_duration_var, width=5).pack(side="left")
        transition_duration_var.trace_add("write", schedule_preview)

        design_row = ttk.Frame(form)
        design_row.pack(fill="x", padx=8, pady=4)
        ttk.Label(design_row, text="Γραμματοσειρά", width=17).pack(side="left")
        font_var = tk.StringVar(value=draft["font_family"] or self.settings.get("font_family", "Calibri"))
        ttk.Combobox(design_row, textvariable=font_var, state="readonly",
                     values=["Calibri", "Arial", "Verdana", "Georgia"], width=14).pack(side="left")
        font_var.trace_add("write", schedule_preview)
        vars_by_key["font_family"] = font_var
        ttk.Label(design_row, text="Μέγεθος").pack(side="left", padx=(12, 3))
        font_size_var = tk.IntVar(value=draft["font_size"])
        ttk.Spinbox(design_row, from_=0, to=200, textvariable=font_size_var, width=6).pack(side="left")
        font_size_var.trace_add("write", schedule_preview)

        position_row = ttk.Frame(form)
        position_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(position_row, text="Θέση / panel", width=17).pack(side="left")
        position_var = tk.StringVar(value=next(
            (label for label, value in POSITION_LABELS.items() if value == draft["text_position"]),
            "Κάτω"))
        ttk.Combobox(position_row, textvariable=position_var, state="readonly",
                     values=list(POSITION_LABELS), width=15).pack(side="left")
        position_var.trace_add("write", schedule_preview)
        vars_by_key["text_position"] = position_var
        panel_style_var = tk.StringVar(value=next(
            (label for label, value in PANEL_STYLE_LABELS.items() if value == draft["panel_style"]),
            "Συμπαγές"))
        ttk.Combobox(position_row, textvariable=panel_style_var, state="readonly",
                     values=list(PANEL_STYLE_LABELS), width=15).pack(side="left", padx=8)
        panel_style_var.trace_add("write", schedule_preview)
        vars_by_key["panel_style"] = panel_style_var
        ttk.Label(form, text="Στο Navy & Gold Transparent, η θέση μετακινεί ολόκληρο το πλαίσιο.",
                  foreground="#666", wraplength=520).pack(anchor="w", padx=8, pady=(0, 4))

        alignment_row = ttk.Frame(form)
        alignment_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(alignment_row, text="Στοίχιση κειμένου", width=17).pack(side="left")
        alignment_var = tk.StringVar(value=next(
            (label for label, value in ALIGNMENT_LABELS.items()
             if value == draft["text_align"]), "Αριστερά"))
        ttk.Combobox(alignment_row, textvariable=alignment_var, state="readonly",
                     values=list(ALIGNMENT_LABELS)).pack(side="left", fill="x", expand=True)
        alignment_var.trace_add("write", schedule_preview)

        color_row = ttk.Frame(form)
        color_row.pack(fill="x", padx=8, pady=4)
        color_vars = {}
        color_labels = {"text_color": "Κείμενο", "panel_color": "Panel", "accent_color": "Accent"}
        for key, label in color_labels.items():
            cell = ttk.Frame(color_row)
            cell.pack(side="left", padx=(0, 12))
            ttk.Label(cell, text=label).pack(anchor="w")
            var = tk.StringVar(value=draft[key])
            color_vars[key] = var
            chip = tk.Label(cell, text="      ", bg=var.get(), relief="solid", borderwidth=1)
            chip.pack(side="left", padx=(0, 3))

            def choose_color(k=key, v=var, c=chip):
                chosen = colorchooser.askcolor(color=v.get(), parent=parent.winfo_toplevel())
                if chosen and chosen[1]:
                    v.set(chosen[1])
                    c.config(bg=chosen[1])
                    schedule_preview()
            ttk.Button(cell, text="Αλλαγή", command=choose_color).pack(side="left")
            var.trace_add("write", schedule_preview)

        logo_row = ttk.Frame(form)
        logo_row.pack(fill="x", padx=8, pady=4)
        logo_enabled = tk.BooleanVar(value=draft["logo_enabled"])
        ttk.Checkbutton(logo_row, text="Λογότυπο σε αυτό το slide", variable=logo_enabled,
                        command=schedule_preview).pack(side="left")
        logo_var = tk.StringVar(value=draft["logo_path"])
        vars_by_key["logo_path"] = logo_var
        logo_entry = ttk.Entry(form, textvariable=logo_var)
        logo_entry.pack(fill="x", padx=8, pady=(0, 3))
        logo_var.trace_add("write", schedule_preview)
        ttk.Button(form, text="Επιλογή λογότυπου…", command=lambda: choose_logo()).pack(
            anchor="w", padx=8)

        # ---------------------------- preview and actions
        preview = ttk.LabelFrame(container, text="Προεπισκόπηση του slide")
        preview.grid(row=0, column=1, sticky="nsew")
        preview.rowconfigure(0, weight=1)
        preview.columnconfigure(0, weight=1)
        canvas = tk.Canvas(preview, bg="#161616", highlightthickness=0, width=360, height=520)
        canvas.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        warning = ttk.Label(preview, text="", foreground="#b35400", wraplength=340,
                            justify="left")
        warning.grid(row=1, column=0, sticky="ew", padx=8)
        preview_status = ttk.Label(preview, text="Αυτόματη προεπισκόπηση", foreground="#666")
        preview_status.grid(row=2, column=0, sticky="w", padx=8, pady=(2, 6))

        button_row = ttk.Frame(preview)
        button_row.grid(row=3, column=0, sticky="ew", padx=6, pady=6)
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)
        ttk.Button(button_row, text="↻ Πρότυπα defaults", command=lambda: reset_design()).grid(
            row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Αποθήκευση preset…", command=lambda: save_preset()).grid(
            row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Template → επιλεγμένα (Ctrl/Shift)",
                   command=lambda: apply_template_selected()).grid(
            row=1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Template → ΟΛΑ",
                   command=lambda: apply_template_all()).grid(
            row=1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Πλήρες σχέδιο → επιλεγμένα",
                   command=lambda: apply_design_selected()).grid(
            row=2, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Εφαρμογή τρέχοντος slide",
                   command=lambda: apply_current()).grid(
            row=2, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(button_row, text="Πλήρες σχέδιο → ΟΛΑ τα media",
                   command=lambda: apply_design_all()).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=2, pady=2)

        def choose_logo():
            path = filedialog.askopenfilename(
                parent=parent.winfo_toplevel(),
                filetypes=[("Logo image", "*.png *.jpg *.jpeg *.bmp")])
            if path:
                logo_var.set(path)

        def current_data():
            def numeric(var, fallback):
                try:
                    return var.get()
                except (tk.TclError, ValueError, TypeError):
                    return fallback

            values = copy.deepcopy(draft)
            for key, var in vars_by_key.items():
                if key == "mode":
                    values[key] = MODE_LABELS.get(var.get(), "global")
                else:
                    values[key] = var.get()
            for key, widget in text_widgets.items():
                values[key] = widget.get("1.0", "end-1c")
            values["template"] = (INHERIT_TEMPLATE if template_var.get() == INHERIT_TEMPLATE_LABEL
                                   else next((k for k, v in TEMPLATES.items()
                                              if v == template_var.get()), "legacy"))
            values["text_position"] = POSITION_LABELS.get(position_var.get(), "bottom")
            values["text_align"] = ALIGNMENT_LABELS.get(alignment_var.get(), "left")
            values["featured_enabled"] = featured_enabled_var.get()
            values["featured_text"] = featured_text_var.get()
            values["panel_style"] = PANEL_STYLE_LABELS.get(panel_style_var.get(), "solid")
            values["duration"] = (numeric(duration_var, self.settings.get("slide_duration", 3))
                                   if duration_enabled.get() else None)
            values["transition"] = transition_labels.get(transition_var.get(), "global")
            values["transition_duration"] = (numeric(
                transition_duration_var, self.settings.get("transition_duration", .7))
                                               if custom_transition_duration.get() else None)
            values["font_size"] = numeric(font_size_var, 0)
            if (not original["font_family"] and
                    values["font_family"] == self.settings.get("font_family", "Calibri")):
                values["font_family"] = ""
            values["text_color"] = color_vars["text_color"].get()
            values["panel_color"] = color_vars["panel_color"].get()
            values["accent_color"] = color_vars["accent_color"].get()
            values["logo_enabled"] = logo_enabled.get()
            values["compare_path"] = ""
            return normalize_presentation(values, scene_id=original["scene_id"])

        def display_preview(frame, overflow, token):
            if preview_state["closed"] or token != preview_state["token"]:
                return
            try:
                cw, ch = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
                scale = min(cw / frame.width, ch / frame.height)
                size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
                image = ImageTk.PhotoImage(frame.resize(size, Image.Resampling.LANCZOS))
                canvas.delete("all")
                canvas.create_image(cw // 2, ch // 2, image=image)
                canvas.image_ref = image
                warnings = []
                if overflow:
                    warnings.append("⚠ Το κείμενο υπερβαίνει τον ασφαλή χώρο· μείωσέ το ή διάλεξε άλλο template.")
                warning.config(text="\n".join(warnings))
                preview_status.config(text="Προεπισκόπηση ενημερώθηκε")
            except tk.TclError:
                pass

        def render_preview():
            preview_state["job"] = None
            if preview_state["closed"]:
                return
            preview_state["token"] += 1
            token = preview_state["token"]
            values = current_data()
            m_type, path, media_edit = self.media_files[idx]
            raw_global = self.get_text_for(m_type)
            width, height = map(int, self.settings["resolution"].split("x"))
            effective_values = self._effective_presentation(values)
            self._set_presentation_preview_draft(values)
            preview_status.config(text="Δημιουργώ προεπισκόπηση…")

            def worker():
                try:
                    if m_type == "image":
                        source = Image.open(path)
                    else:
                        start = float(media_edit.get("trim_start") or 0.0)
                        source = self._video_frame_at(path, start) if start > .005 else \
                                 self._video_first_frame(path)
                    source = self._apply_image_edit(source, media_edit, path, m_type=m_type)
                    if effective_values["template"] == "legacy":
                        text = self._presentation_text(values, m_type, raw_global)
                        if m_type == "image":
                            frame = self._fit_image_logic(source, width, height, "image", text=text)
                            data = getattr(frame, "fit_move_data", None)
                            if data is not None:
                                overlay = self._make_text_overlay(
                                    text, width, height, align=effective_values["text_align"])
                                frame = self._render_fit_and_move_frame(
                                    frame, data, 0.0, width, height, overlay)
                            else:
                                frame = self.render_text_on_image(
                                    frame, text, width, height,
                                    align=effective_values["text_align"])
                        else:
                            frame = self._render_video_first_frame(source, width, height)
                            frame = self.render_text_on_image(
                                frame, text, width, height,
                                align=effective_values["text_align"])
                        overflow = False
                    else:
                        fields = presentation_fields(values, raw_global)
                        before = self._presentation_before_image(values, fallback=source)
                        frame, overflow = compose_design_frame(
                            source, width, height, effective_values, fields, before_image=before)
                    frame = self._apply_watermark_overlay(frame)
                    self._post_ui(display_preview, frame, overflow, token)
                except Exception as exc:
                    error = str(exc)
                    self._post_ui(preview_status.config, text=f"Preview error: {error}")
            threading.Thread(target=worker, daemon=True).start()

        def reset_design():
            fresh = normalize_presentation({"scene_id": original["scene_id"]})
            for key in DESIGN_KEYS:
                if key == "font_family":
                    value = self.settings.get("font_family", "Calibri")
                else:
                    value = fresh.get(key, DEFAULT_PRESENTATION.get(key))
                if key == "template":
                    template_var.set(INHERIT_TEMPLATE_LABEL if value == INHERIT_TEMPLATE else
                                     TEMPLATES[normalize_template(value)])
                elif key == "text_position":
                    position_var.set(next((label for label, item in POSITION_LABELS.items()
                                           if item == value), "Κάτω"))
                elif key == "text_align":
                    alignment_var.set(next((label for label, item in ALIGNMENT_LABELS.items()
                                            if item == value), "Αριστερά"))
                elif key == "featured_enabled":
                    featured_enabled_var.set(value)
                elif key == "featured_text":
                    featured_text_var.set(value)
                elif key == "font_family":
                    font_var.set(value)
                elif key == "font_size":
                    font_size_var.set(value)
                elif key == "text_color":
                    color_vars[key].set(value)
                elif key == "panel_color":
                    color_vars[key].set(value)
                elif key == "accent_color":
                    color_vars[key].set(value)
                elif key == "panel_style":
                    panel_style_var.set(next((label for label, item in PANEL_STYLE_LABELS.items()
                                              if item == value), "Συμπαγές"))
                elif key == "duration":
                    duration_enabled.set(False)
                elif key == "logo_enabled":
                    logo_enabled.set(False)
                elif key == "logo_path":
                    logo_var.set("")
                elif key == "transition":
                    transition_var.set("Παγκόσμια ρύθμιση")
                elif key == "transition_duration":
                    custom_transition_duration.set(False)
            schedule_preview()

        def save_preset():
            name = simpledialog.askstring("Design preset", "Όνομα preset:",
                                          parent=parent.winfo_toplevel())
            if not name or not name.strip():
                return
            values = current_data()
            preset = {key: copy.deepcopy(values[key]) for key in DESIGN_KEYS}
            presets = self.settings.get("slide_design_presets")
            if not isinstance(presets, dict):
                presets = {}
                self.settings["slide_design_presets"] = presets
            if name.strip() in presets and not messagebox.askyesno(
                    "Design preset", f"Να αντικατασταθεί το preset «{name.strip()}»;",
                    parent=parent.winfo_toplevel()):
                return
            presets[name.strip()] = preset
            self.save_settings()
            preset_combo.configure(values=sorted(presets))
            preset_var.set(name.strip())
            messagebox.showinfo("Design preset", f"Αποθηκεύτηκε το preset «{name.strip()}».",
                                parent=parent.winfo_toplevel())

        def load_preset():
            all_presets = self.settings.get("slide_design_presets", {})
            if not isinstance(all_presets, dict):
                return
            preset = all_presets.get(preset_var.get())
            if not isinstance(preset, dict):
                return
            preset = normalize_presentation(preset)
            for key in DESIGN_KEYS:
                value = copy.deepcopy(preset[key])
                if key == "template":
                    template_var.set(INHERIT_TEMPLATE_LABEL if value == INHERIT_TEMPLATE else
                                     TEMPLATES[normalize_template(value)])
                elif key == "text_position":
                    position_var.set(next((label for label, item in POSITION_LABELS.items()
                                           if item == value), "Κάτω"))
                elif key == "text_align":
                    alignment_var.set(next((label for label, item in ALIGNMENT_LABELS.items()
                                            if item == value), "Αριστερά"))
                elif key == "featured_enabled":
                    featured_enabled_var.set(bool(value))
                elif key == "featured_text":
                    featured_text_var.set(value or "")
                elif key == "font_family":
                    font_var.set(value or self.settings.get("font_family", "Calibri"))
                elif key == "font_size":
                    font_size_var.set(value)
                elif key in color_vars:
                    color_vars[key].set(value)
                elif key == "panel_style":
                    panel_style_var.set(next((label for label, item in PANEL_STYLE_LABELS.items()
                                              if item == value), "Συμπαγές"))
                elif key == "duration":
                    duration_enabled.set(value is not None)
                    if value is not None:
                        duration_var.set(value)
                elif key == "transition":
                    transition_var.set(next((label for label, item in transition_labels.items()
                                             if item == value), "Παγκόσμια ρύθμιση"))
                elif key == "transition_duration":
                    custom_transition_duration.set(value is not None)
                    if value is not None:
                        transition_duration_var.set(value)
                elif key == "logo_enabled":
                    logo_enabled.set(bool(value))
                elif key == "logo_path":
                    logo_var.set(value or "")
            schedule_preview()

        def apply_design_to(indices, status_text):
            values = current_data()
            applied = 0
            for selected_idx in sorted(set(indices)):
                if not 0 <= selected_idx < len(self.media_files):
                    continue
                target = self.media_files[selected_idx][2]
                current = normalize_presentation(target.get("presentation"))
                for key in DESIGN_KEYS:
                    current[key] = copy.deepcopy(values[key])
                target["presentation"] = normalize_presentation(current,
                                                                  scene_id=current["scene_id"])
                applied += 1
            if applied:
                self.is_modified = True
                self.update_media_display()
                self._schedule_preview()
            preview_status.config(text=status_text.format(count=applied))

        def apply_design_selected():
            selected = set(getattr(self, "selected_indices", set()))
            selected.add(idx)
            apply_design_to(selected, "Πλήρες σχέδιο εφαρμόστηκε σε {count} επιλεγμένα media")

        def apply_design_all():
            apply_design_to(range(len(self.media_files)),
                            "Πλήρες σχέδιο εφαρμόστηκε σε {count} media")

        def apply_template_to(indices):
            template = current_data()["template"]
            changed = 0
            for selected_idx in sorted(set(indices)):
                if not 0 <= selected_idx < len(self.media_files):
                    continue
                target = self.media_files[selected_idx][2]
                current = normalize_presentation(target.get("presentation"))
                if current["template"] == template:
                    continue
                current["template"] = template
                target["presentation"] = normalize_presentation(
                    current, scene_id=current["scene_id"])
                changed += 1
            if changed:
                self.is_modified = True
                self.update_media_display()
                self._schedule_preview()
            preview_status.config(text=f"Template εφαρμόστηκε σε {changed} slide(s) — το κείμενο διατηρήθηκε")

        def apply_template_selected():
            selected = set(getattr(self, "selected_indices", set()))
            selected.add(idx)
            apply_template_to(selected)

        def apply_template_all():
            apply_template_to(range(len(self.media_files)))

        def apply_current():
            values = current_data()
            target = self.media_files[idx][2]
            if normalize_presentation(target.get("presentation")) == values:
                self._clear_presentation_preview_draft(original["scene_id"])
                preview_status.config(text="Δεν υπάρχουν αλλαγές στο slide")
                return
            target["presentation"] = values
            self._clear_presentation_preview_draft(original["scene_id"])
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            preview_status.config(text="Οι ρυθμίσεις του slide αποθηκεύτηκαν στο project")

        canvas.bind("<Configure>", schedule_preview, add="+")
        def on_parent_destroy(event):
            if event.widget is parent:
                preview_state["closed"] = True
                self._clear_presentation_preview_draft(original["scene_id"], clear_active=True)
        parent.bind("<Destroy>", on_parent_destroy, add="+")
        schedule_preview()
        container.apply_presentation = apply_current
        container.refresh_presentation_preview = schedule_preview
        container.refresh_featured_controls = update_featured_controls
        return container
