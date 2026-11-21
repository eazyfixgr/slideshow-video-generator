"""Full caption and slide-design controls embedded in the inspector."""

import copy
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox

from .slide_design import INHERIT_TEMPLATE, normalize_presentation
from .slide_templates import (FONT_CHOICES, PANEL_STYLE_CHOICES, STYLE_FIELDS,
                              TEXT_ALIGN_CHOICES, TEXT_LAYOUT_CHOICES,
                              TEXT_POSITION_CHOICES, read_template_registry,
                              template_base, template_style)
from .ui_caption_inspector import CaptionInspectorMixin
from .ui_theme import MODERN_PALETTE as P

DESIGN_SCOPES = ("Όλο το project", "Τρέχουσα σκηνή", "Επιλεγμένες σκηνές",
                 "Όλες οι σκηνές")


class InlineEditorsMixin(CaptionInspectorMixin):
    """Persist pending input before the inspector changes its scene or context."""

    def _cancel_pending_caption_apply(self):
        job = getattr(self, "_caption_apply_job", None)
        self._caption_apply_job = None
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    def _commit_pending_caption_apply(self):
        if getattr(self, "_inline_committing", False):
            return False
        self._cancel_pending_caption_apply()
        callback = getattr(self, "_caption_apply_callback", None)
        if callback is None:
            return False
        self._inline_committing = True
        try:
            return callback()
        finally:
            self._inline_committing = False

    def _inline_changed(self, delay_ms=450):
        self._cancel_pending_caption_apply()
        self._caption_apply_job = self.root.after(delay_ms, self._commit_pending_caption_apply)

    def _inline_refresh(self):
        self.is_modified = True
        self._schedule_preview(100)
        self.render_storyboard()
        self._refresh_header()

    def _inline_label(self, parent, text=None, **kwargs):
        label = ttk.Label(parent, text=text, wraplength=280)
        label.pack(fill="x", **kwargs)
        label.bind("<Configure>", lambda event: label.configure(
            wraplength=max(100, event.width)), add="+")
        return label

    def _inline_field(self, parent, label, value, changed, choices=None):
        self._inline_label(parent, label, pady=(7, 2))
        var = tk.StringVar(value=value)
        if choices:
            widget = ttk.Combobox(parent, textvariable=var, values=list(choices),
                                  state="readonly", width=18)
        else:
            widget = ttk.Entry(parent, textvariable=var, width=18)
        widget.pack(fill="x")
        var.trace_add("write", lambda *_: changed())
        return var, widget

    def _inline_slider(self, parent, label, value, changed, low=0, high=100,
                       suffix="%", invert=False):
        self._inline_label(parent, label, pady=(7, 2))
        row = tk.Frame(parent, bg=self._inline_bg(parent))
        row.pack(fill="x")
        value_lbl = tk.Label(row, width=7, anchor="e",
                             bg=self._inline_bg(parent), fg="#9da9b9",
                             font=("Segoe UI", 8))
        value_lbl.pack(side="right")

        def update_display(number):
            number = int(float(number))
            value_lbl.configure(text="Auto" if number == 0 and suffix != "%"
                                else f"{number}{suffix}")

        initial = int(value or 0)
        initial_display = (high - initial) if invert else initial

        def on_command(number):
            update_display(number)
            if int(float(number)) != initial_display:
                changed()

        scale = tk.Scale(row, from_=low, to=high, orient="horizontal",
                         bg=self._inline_bg(parent), fg="#f1f3f7",
                         troughcolor="#12161d", highlightthickness=0,
                         activebackground="#e8bd79", showvalue=False,
                         command=on_command)
        scale.pack(side="left", fill="x", expand=True)
        scale.set(initial_display)
        update_display(scale.get())
        return scale

    @staticmethod
    def _inline_bg(_widget):
        return "#171b22"

    def _inline_text(self, parent, label, value, changed, height=3):
        self._inline_label(parent, label, pady=(7, 2))
        widget = tk.Text(parent, height=height, width=18, wrap="word", undo=True)
        widget.pack(fill="x")
        widget.insert("1.0", value)
        widget.edit_reset()
        self._bind_captions_text(widget, changed)
        widget.bind("<<Modified>>", lambda _e: modified(), add="+")

        def modified():
            if widget.edit_modified():
                widget.edit_modified(False)
                changed()
        widget.edit_modified(False)
        return widget

    def _inline_scope(self, body, values, attribute, fallback):
        current = getattr(self, attribute, fallback)
        if current not in values:
            current = fallback
        scope, combo = self._inline_field(body, "Εφαρμογή σε", current,
                                           lambda: None, choices=values)

        def select(_event):
            self._commit_pending_caption_apply()
            setattr(self, attribute, scope.get())
            self._render_inspector()
        combo.bind("<<ComboboxSelected>>", select)
        return current

    # ----------------------------------------------------------- design panel
    def _render_design_inspector(self, body):
        self.inspector_title_var.set("Slide Design")
        registry = read_template_registry(self.settings)
        names = list(registry)
        default_name = self._default_template_name(registry)
        scope = self._inline_scope(body, DESIGN_SCOPES, "_inline_design_scope",
                                   "Όλο το project")
        index, item = self._selected_item()
        project_scope = scope == "Όλο το project"
        if scope == "Τρέχουσα σκηνή":
            targets = [item] if item is not None else []
        elif scope == "Επιλεγμένες σκηνές":
            targets = [self.media_files[i] for i in self._selected()]
        elif scope == "Όλες οι σκηνές":
            targets = list(self.media_files)
        else:
            targets = list(self.media_files)

        if not project_scope and not targets:
            self._empty_inspector(body, "Διάλεξε μια σκηνή ή μια ομάδα media για να "
                                        "αλλάξεις την εμφάνισή τους.")
            return

        if project_scope:
            current_name = self._effective_project_template_name(registry)
            draft = template_style(current_name, registry)
        else:
            resolved = self._resolve_presentation_style(
                normalize_presentation(targets[0][2].get("presentation"),
                                       project_template=self.project_template))
            current_name = resolved.get("template_name") or default_name
            if current_name not in registry:
                current_name = default_name
            draft = {key: resolved[key] for key in STYLE_FIELDS}
        dirty = {"value": False, "loading": False}
        status = tk.StringVar(value="")
        variables = {}
        choice_values = {}

        def changed():
            if not dirty["loading"]:
                dirty["value"] = True
                status.set("Πάτησε «Εφαρμογή εμφάνισης» για το project.")

        self._inline_label(
            body, "Οι αλλαγές εδώ είναι overrides του project. Για μόνιμες αλλαγές "
                  "template: Settings → Slideshow Settings.", pady=(10, 2))

        def template_changed(_event=None):
            name = template_var.get()
            if name not in registry:
                return
            entry = registry[name]
            if project_scope:
                self.set_project_template(name)
                return
            self.push_undo()
            for target in targets:
                edit = target[2]
                current = normalize_presentation(edit.get("presentation"))
                current["template"] = entry["base"]
                current["template_name"] = name
                current["style_overrides"] = []
                current.pop("style_overrides", None)
                current["style_overrides"] = []
                edit["presentation"] = current
            self.is_modified = True
            self._inline_refresh()
            self._render_inspector()

        template_var, template_combo = self._inline_field(
            body, "Template", current_name, lambda: None,
            [f"{name}{'  (default)' if name == default_name else ''}" for name in names])
        # Strip the display suffix before applying.
        template_combo.configure(values=names)
        template_var.set(current_name)
        template_combo.bind("<<ComboboxSelected>>", template_changed, add="+")
        self._render_slide_project_controls(body)
        dirty["loading"] = True

        def field(label, key, choices=None):
            value = draft[key]
            var, widget = self._inline_field(body, label, value, changed, choices)
            variables[key] = var
            return widget

        def label_for(choices, value):
            return next((label for label, stored in choices.items() if stored == value),
                        next(iter(choices), ""))

        field("Γραμματοσειρά", "font_family", FONT_CHOICES)
        field("Μέγεθος γραμματοσειράς", "font_size")
        var, widget = self._inline_field(
            body, "Θέση κειμένου", label_for(TEXT_POSITION_CHOICES,
                                             draft["text_position"]),
            changed, TEXT_POSITION_CHOICES)
        variables["text_position"] = var
        choice_values["text_position"] = TEXT_POSITION_CHOICES
        var, widget = self._inline_field(
            body, "Στοίχιση κειμένου", label_for(TEXT_ALIGN_CHOICES,
                                                 draft["text_align"]),
            changed, TEXT_ALIGN_CHOICES)
        variables["text_align"] = var
        choice_values["text_align"] = TEXT_ALIGN_CHOICES
        var, widget = self._inline_field(
            body, "Τοποθέτηση", label_for(TEXT_LAYOUT_CHOICES, draft["text_layout"]),
            changed, TEXT_LAYOUT_CHOICES)
        variables["text_layout"] = var
        choice_values["text_layout"] = TEXT_LAYOUT_CHOICES

        for key, label in (("text_color", "Χρώμα κειμένου"),
                           ("panel_color", "Χρώμα πλαισίου"),
                           ("accent_color", "Χρώμα έμφασης")):
            self._inline_label(body, label, pady=(7, 2))
            row = tk.Frame(body, bg=self._inline_bg(body))
            row.pack(fill="x")
            var = tk.StringVar(value=draft[key])
            variables[key] = var
            swatch = tk.Button(row, bg=draft[key], width=4, relief="flat", bd=0,
                               highlightthickness=1, highlightbackground="#2a313d",
                               cursor="hand2")
            swatch.pack(side="left")
            entry = ttk.Entry(row, textvariable=var, width=12)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 0))

            def choose(k=key, s=swatch, v=var):
                color = colorchooser.askcolor(v.get(), parent=self.root)[1]
                if color:
                    v.set(color)
                    s.configure(bg=color)
            swatch.configure(command=choose)
            var.trace_add("write", lambda *_a, s=swatch, v=var: (
                s.configure(bg=v.get()) if len(v.get()) == 7 else None))

        slider_specs = (
            ("panel_opacity", "Διαφάνεια πλαισίου (0 = συμπαγές)", 0, 100, True),
            ("panel_width_pct", "Πλάτος πλαισίου (0 = Auto)", 0, 100, False),
            ("panel_padding_pct", "Padding πλαισίου (0 = Auto)", 0, 15, False),
            ("panel_min_height_pct", "Ελάχιστο ύψος (0 = Auto)", 0, 80, False),
        )
        slider_widgets = {}
        for key, label, low, high, invert in slider_specs:
            slider_widgets[key] = self._inline_slider(
                body, label, draft.get(key, 0), changed, low, high,
                invert=invert)

        def current_style():
            style = dict(draft)
            try:
                style["font_size"] = int(float(variables["font_size"].get()))
            except (ValueError, tk.TclError):
                status.set("Γράψε έγκυρο μέγεθος γραμματοσειράς.")
                return None
            for key in ("text_color", "panel_color", "accent_color"):
                try:
                    self.root.winfo_rgb(variables[key].get())
                    style[key] = variables[key].get()
                except tk.TclError:
                    status.set("Γράψε έγκυρο χρώμα.")
                    return None
            for key in choice_values:
                style[key] = choice_values[key][variables[key].get()]
            for key, scale in slider_widgets.items():
                display = int(scale.get())
                style[key] = (100 - display) if key == "panel_opacity" else display
            style["panel_style"] = ("solid" if style["panel_opacity"] >= 60
                                    else "translucent")
            return style

        def apply():
            if not body.winfo_exists() or not dirty["value"]:
                return False
            style = current_style()
            if style is None:
                return False
            template_name = template_var.get()
            if template_name not in registry:
                return False
            template_entry = registry[template_name]
            template_style_values = template_entry["style"]
            overrides = [key for key in STYLE_FIELDS
                         if style.get(key) != template_style_values.get(key)]
            if project_scope and not targets:
                status.set("Δεν υπάρχουν media για overrides. Το template project "
                           "αλλάζει από το παραπάνω picker.")
                return False
            self.push_undo()
            for target in targets:
                current = normalize_presentation(target[2].get("presentation"))
                current["template"] = template_entry["base"]
                current["template_name"] = template_name
                current["style_overrides"] = overrides
                for key in STYLE_FIELDS:
                    current[key] = copy.deepcopy(style[key])
                target[2]["presentation"] = current
            dirty["value"] = False
            self.is_modified = True
            self._inline_refresh()
            status.set("Η εμφάνιση εφαρμόστηκε ως override του project.")
            return True

        self._caption_apply_callback = apply
        button_row = tk.Frame(body, bg=self._inline_bg(body))
        button_row.pack(fill="x", pady=(10, 2))
        from .ui_widgets import primary_button
        primary_button(button_row, "Εφαρμογή εμφάνισης",
                       lambda: self._commit_pending_caption_apply()).pack(
            side="left", fill="x", expand=True)
        ttk.Button(button_row, text="Επαναφορά",
                   command=lambda: self._reset_design_scope(scope, targets,
                                                           project_scope)).pack(
            side="right", padx=(6, 0))
        self._inline_label(body)
        body.winfo_children()[-1].configure(textvariable=status)

        # A per-slide badge/logo remains useful and does not belong to templates.
        advanced = ttk.LabelFrame(body, text="Badge / Λογότυπο", padding=5)
        advanced.pack(fill="x", pady=(10, 2))
        featured = tk.BooleanVar(value=bool(draft.get("featured_enabled")))
        logo = tk.BooleanVar(value=bool(draft.get("logo_enabled")))
        featured_text = tk.StringVar(value=str(draft.get("featured_text", "")))
        logo_path = tk.StringVar(value=str(draft.get("logo_path", "")))
        tk.Checkbutton(advanced, text="Εμφάνιση badge", variable=featured,
                       indicatoron=False, bg=P["raised"], fg=P["text"],
                       selectcolor=P["accent_faint"], activebackground=P["selected"],
                       activeforeground=P["text"], relief="flat", bd=0, anchor="w",
                       padx=8, pady=4, font=("Segoe UI", 8)).pack(fill="x")
        ttk.Entry(advanced, textvariable=featured_text).pack(fill="x", pady=(2, 4))
        tk.Checkbutton(advanced, text="Εμφάνιση λογοτύπου", variable=logo,
                       indicatoron=False, bg=P["raised"], fg=P["text"],
                       selectcolor=P["accent_faint"], activebackground=P["selected"],
                       activeforeground=P["text"], relief="flat", bd=0, anchor="w",
                       padx=8, pady=4, font=("Segoe UI", 8)).pack(fill="x")
        path_row = tk.Frame(advanced)
        path_row.pack(fill="x", pady=(2, 0))
        ttk.Entry(path_row, textvariable=logo_path).pack(side="left", fill="x", expand=True)

        def browse_logo():
            path = filedialog.askopenfilename(
                parent=self.root, filetypes=[("Logo", "*.png *.jpg *.jpeg")])
            if path:
                logo_path.set(path)
        ttk.Button(path_row, text="…", width=3, command=browse_logo).pack(side="left")
        ttk.Button(advanced, text="Εφαρμογή badge/logo",
                   command=lambda: self._apply_design_extra(
                       targets, featured.get(), featured_text.get(),
                       logo.get(), logo_path.get())).pack(fill="x", pady=(4, 0))
        dirty["loading"] = False

    def _reset_design_scope(self, scope, targets, project_scope):
        if not messagebox.askyesno(
                "Επαναφορά",
                "Να επαναφερθεί η εμφάνιση στο default template των ρυθμίσεων;",
                parent=self.root):
            return
        if project_scope:
            self.reset_project_template(mark_modified=False)
            for _kind, _path, edit in self.media_files:
                current = normalize_presentation(edit.get("presentation"))
                current["template"] = INHERIT_TEMPLATE
                current["template_name"] = ""
                current["style_overrides"] = []
                edit["presentation"] = current
        else:
            for target in targets:
                current = normalize_presentation(target[2].get("presentation"))
                current["template"] = INHERIT_TEMPLATE
                current["template_name"] = ""
                current["style_overrides"] = []
                target[2]["presentation"] = current
        self.is_modified = True
        self._inline_refresh()
        self._render_inspector()

    def _apply_design_extra(self, targets, featured, featured_text, logo, logo_path):
        self.push_undo()
        for target in targets:
            current = normalize_presentation(target[2].get("presentation"))
            current["featured_enabled"] = bool(featured)
            current["featured_text"] = str(featured_text or "")
            current["logo_enabled"] = bool(logo)
            current["logo_path"] = str(logo_path or "")
            target[2]["presentation"] = current
        self.is_modified = True
        self._inline_refresh()
