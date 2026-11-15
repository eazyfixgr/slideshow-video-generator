"""Per-media presentation editor, template preview, and batch design actions."""

import copy
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser

from .deps import Image, ImageTk
from .slide_design import (DEFAULT_PRESENTATION, TEMPLATES, compose_design_frame,
                           normalize_presentation, presentation_fields)


MODE_LABELS = {
    "Use Global Text": "global",
    "Custom Text": "custom",
    "No Text": "none",
    "Custom + Global": "combine",
}
MODE_BY_VALUE = {value: label for label, value in MODE_LABELS.items()}
DESIGN_KEYS = ("template", "text_position", "font_family", "font_size", "text_color",
               "panel_color", "accent_color", "panel_style", "duration", "logo_enabled",
               "logo_path", "compare_path", "transition", "transition_duration", "motion")
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

        def add_entry(label, key, width=40):
            row = ttk.Frame(form)
            row.pack(fill="x", padx=8, pady=3)
            ttk.Label(row, text=label, width=17).pack(side="left", anchor="n")
            var = tk.StringVar(value=draft.get(key, ""))
            entry = ttk.Entry(row, textvariable=var, width=width)
            entry.pack(side="left", fill="x", expand=True)
            vars_by_key[key] = var
            var.trace_add("write", schedule_preview)
            return entry

        def add_text(label, key, height=3):
            row = ttk.Frame(form)
            row.pack(fill="x", padx=8, pady=3)
            ttk.Label(row, text=label, width=17).pack(side="left", anchor="n", pady=4)
            widget = tk.Text(row, height=height, wrap="word", undo=True)
            widget.pack(side="left", fill="x", expand=True)
            widget.insert("1.0", draft.get(key, ""))
            widget.bind("<KeyRelease>", schedule_preview, add="+")
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
                            "Το Custom + Global προσθέτει και το κοινό κείμενο.",
                  foreground="#666", wraplength=520, justify="left").pack(
            anchor="w", padx=8, pady=(0, 6))

        ttk.Separator(form).pack(fill="x", padx=8, pady=5)
        add_entry("Τίτλος", "title")
        add_entry("Υπότιτλος", "subtitle")
        add_text("Περιγραφή", "description", 4)
        add_entry("Κατηγορία / τύπος", "category")
        add_entry("Τοποθεσία", "location")
        add_entry("Τιμή", "price")
        add_entry("Σημαντικές λεπτομέρειες", "details")
        add_entry("Call to action", "cta")
        add_entry("Επωνυμία", "business_name")
        add_entry("Τηλέφωνο", "phone")
        add_entry("Ιστότοπος", "website")
        add_entry("Ετικέτα ΠΡΙΝ", "before_label")
        add_entry("Ετικέτα ΜΕΤΑ", "after_label")

        ttk.Separator(form).pack(fill="x", padx=8, pady=6)
        template_row = ttk.Frame(form)
        template_row.pack(fill="x", padx=8, pady=3)
        ttk.Label(template_row, text="Template", width=17).pack(side="left")
        template_var = tk.StringVar(value=TEMPLATES.get(draft["template"], TEMPLATES["legacy"]))
        ttk.Combobox(template_row, textvariable=template_var, state="readonly",
                     values=list(TEMPLATES.values())).pack(side="left", fill="x", expand=True)
        template_var.trace_add("write", schedule_preview)

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
        position_var = tk.StringVar(value=draft["text_position"])
        ttk.Combobox(position_row, textvariable=position_var, state="readonly",
                     values=["template", "top", "center", "bottom"], width=12).pack(side="left")
        position_var.trace_add("write", schedule_preview)
        vars_by_key["text_position"] = position_var
        panel_style_var = tk.StringVar(value=draft["panel_style"])
        ttk.Combobox(position_row, textvariable=panel_style_var, state="readonly",
                     values=["solid", "translucent"], width=14).pack(side="left", padx=8)
        panel_style_var.trace_add("write", schedule_preview)
        vars_by_key["panel_style"] = panel_style_var

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

        images = [(str(path), f"{i + 1}. {Path(path).name}")
                  for i, (kind, path, _ed) in enumerate(self.media_files)
                  if kind == "image" and i != idx]
        compare_labels = ["— χωρίς σύγκριση —"] + [label for _path, label in images]
        compare_by_label = {label: path for path, label in images}
        current_compare_label = next((label for path, label in images
                                      if path == draft["compare_path"]), compare_labels[0])
        compare_var = tk.StringVar(value=current_compare_label)
        compare_row = ttk.Frame(form)
        compare_row.pack(fill="x", padx=8, pady=4)
        ttk.Label(compare_row, text="Φωτογραφία ΠΡΙΝ", width=17).pack(side="left")
        ttk.Combobox(compare_row, textvariable=compare_var, state="readonly",
                     values=compare_labels).pack(side="left", fill="x", expand=True)
        compare_var.trace_add("write", schedule_preview)
        ttk.Label(form, text="Το template Before / After χρησιμοποιεί την επιλεγμένη φωτογραφία "
                            "ως ΠΡΙΝ και το τρέχον media ως ΜΕΤΑ.", foreground="#666",
                  wraplength=520).pack(anchor="w", padx=8, pady=(0, 5))

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
        ttk.Button(button_row, text="↻ Πρότυπα defaults", command=lambda: reset_design()).pack(
            fill="x", pady=2)
        ttk.Button(button_row, text="Αποθήκευση preset…", command=lambda: save_preset()).pack(
            fill="x", pady=2)
        ttk.Button(button_row, text="Εφαρμογή σχεδίου στα επιλεγμένα",
                   command=lambda: apply_design_selected()).pack(fill="x", pady=2)
        ttk.Button(button_row, text="Εφαρμογή στο τρέχον slide",
                   command=lambda: apply_current()).pack(fill="x", pady=2)

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
            values["template"] = next((k for k, v in TEMPLATES.items()
                                       if v == template_var.get()), "legacy")
            values["duration"] = (numeric(duration_var, self.settings.get("slide_duration", 3))
                                   if duration_enabled.get() else None)
            values["transition"] = transition_labels.get(transition_var.get(), "global")
            values["transition_duration"] = (numeric(
                transition_duration_var, self.settings.get("transition_duration", .7))
                                               if custom_transition_duration.get() else None)
            values["font_size"] = numeric(font_size_var, 0)
            values["text_color"] = color_vars["text_color"].get()
            values["panel_color"] = color_vars["panel_color"].get()
            values["accent_color"] = color_vars["accent_color"].get()
            values["logo_enabled"] = logo_enabled.get()
            values["compare_path"] = compare_by_label.get(compare_var.get(), "")
            return normalize_presentation(values, scene_id=original["scene_id"])

        def display_preview(frame, overflow, missing_compare, token):
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
                if missing_compare:
                    warnings.append("⚠ Διάλεξε φωτογραφία «ΠΡΙΝ» για το template Before / After.")
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
            preview_status.config(text="Δημιουργώ προεπισκόπηση…")

            def worker():
                try:
                    missing_compare = (values["template"] == "before_after" and
                                       not Path(values.get("compare_path", "")).is_file())
                    if m_type == "image":
                        source = Image.open(path)
                    else:
                        start = float(media_edit.get("trim_start") or 0.0)
                        source = self._video_frame_at(path, start) if start > .005 else \
                                 self._video_first_frame(path)
                    source = self._apply_image_edit(source, media_edit, path, m_type=m_type)
                    if values["template"] == "legacy":
                        text = self._presentation_text(values, m_type, raw_global)
                        if m_type == "image":
                            frame = self._fit_image_logic(source, width, height, "image", text=text)
                            data = getattr(frame, "fit_move_data", None)
                            if data is not None:
                                overlay = self._make_text_overlay(text, width, height)
                                frame = self._render_fit_and_move_frame(
                                    frame, data, 0.0, width, height, overlay)
                            else:
                                frame = self.render_text_on_image(frame, text, width, height)
                        else:
                            frame = self._render_video_first_frame(source, width, height)
                            frame = self.render_text_on_image(frame, text, width, height)
                        overflow = False
                    else:
                        fields = presentation_fields(values, raw_global)
                        fallback = source if values["template"] != "before_after" else None
                        before = self._presentation_before_image(values, fallback=fallback)
                        frame, overflow = compose_design_frame(
                            source, width, height, values, fields, before_image=before)
                    frame = self._apply_watermark_overlay(frame)
                    self._post_ui(display_preview, frame, overflow, missing_compare, token)
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
                    template_var.set(TEMPLATES[value])
                elif key == "text_position":
                    position_var.set(value)
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
                    panel_style_var.set(value)
                elif key == "duration":
                    duration_enabled.set(False)
                elif key == "logo_enabled":
                    logo_enabled.set(False)
                elif key == "logo_path":
                    logo_var.set("")
                elif key == "compare_path":
                    compare_var.set(compare_labels[0])
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
            for key in DESIGN_KEYS:
                if key not in preset:
                    continue
                value = copy.deepcopy(preset[key])
                if key == "template":
                    template_var.set(TEMPLATES.get(value, TEMPLATES["legacy"]))
                elif key == "text_position":
                    position_var.set(value)
                elif key == "font_family":
                    font_var.set(value or self.settings.get("font_family", "Calibri"))
                elif key == "font_size":
                    font_size_var.set(value)
                elif key in color_vars:
                    color_vars[key].set(value)
                elif key == "panel_style":
                    panel_style_var.set(value)
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
                elif key == "compare_path":
                    compare_var.set(next((label for path, label in images if path == value),
                                         compare_labels[0]))
            schedule_preview()

        def apply_design_selected():
            values = current_data()
            selected = set(getattr(self, "selected_indices", set()))
            selected.add(idx)
            for selected_idx in sorted(selected):
                if not 0 <= selected_idx < len(self.media_files):
                    continue
                target = self.media_files[selected_idx][2]
                current = normalize_presentation(target.get("presentation"))
                for key in DESIGN_KEYS:
                    current[key] = copy.deepcopy(values[key])
                target["presentation"] = normalize_presentation(current,
                                                                 scene_id=current["scene_id"])
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            preview_status.config(text=f"Σχέδιο εφαρμόστηκε σε {len(selected)} επιλεγμένα media")

        def apply_current():
            values = current_data()
            target = self.media_files[idx][2]
            target["presentation"] = values
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            preview_status.config(text="Οι ρυθμίσεις του slide αποθηκεύτηκαν στο project")

        canvas.bind("<Configure>", schedule_preview, add="+")
        parent.bind("<Destroy>", lambda e: preview_state.update(closed=True)
                    if e.widget is parent else None, add="+")
        schedule_preview()
        return container
