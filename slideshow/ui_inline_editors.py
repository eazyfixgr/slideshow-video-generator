"""Full caption and slide-design controls embedded in the inspector."""

import copy
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser

from .slide_design import (TEMPLATES, DESIGN_FIELDS, normalize_presentation,
                           INHERIT_TEMPLATE, INHERIT_TEMPLATE_LABEL)
from .ui_caption_inspector import CaptionInspectorMixin
from .design_templates import (read_design_templates, write_design_templates,
                               design_template_choices)

STYLE_FIELDS = tuple(key for key in DESIGN_FIELDS
                     if key not in ("duration", "transition", "transition_duration"))


class InlineEditorsMixin(CaptionInspectorMixin):
    """Persist pending input before the inspector changes its scene or context."""

    def _cancel_pending_caption_apply(self):
        job = getattr(self, "_caption_apply_job", None)
        self._caption_apply_job = None
        if job:
            self.root.after_cancel(job)

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

    def _render_design_inspector(self, body):
        self.inspector_title_var.set("Slide Design")
        index, item = self._selected_item()
        if item is None:
            self._empty_inspector(body, "Πρόσθεσε media για να επεξεργαστείς την εμφάνιση.")
            return
        scope = self._inline_scope(body, ("Τρέχουσα σκηνή", "Επιλεγμένες σκηνές", "Όλες οι σκηνές"),
                                   "_inline_design_scope", "Τρέχουσα σκηνή")
        media = self.media_files
        targets = ([item] if scope == "Τρέχουσα σκηνή" else
                   [media[i] for i in self._selected()] if scope == "Επιλεγμένες σκηνές" else list(media))
        original = normalize_presentation(item[2].get("presentation"), project_template=self.project_template)
        draft = copy.deepcopy(original)
        saved = read_design_templates(self.settings)
        dirty = {"value": False, "loading": False}
        variables = {}
        choice_values = {}
        status = tk.StringVar()

        def changed():
            if not dirty["loading"]:
                dirty["value"] = True
                self._inline_changed()

        def field(label, key, choices=None):
            value = draft[key]
            if isinstance(choices, dict):
                choice_values[key] = choices
                value = next(label for label, stored in choices.items() if stored == value)
            var, widget = self._inline_field(body, label, value, changed, choices)
            variables[key] = var
            return widget

        def fill_variables():
            for key, var in variables.items():
                value = draft[key]
                if key in choice_values:
                    value = next(label for label, stored in choice_values[key].items()
                                 if stored == value)
                var.set(value)

        labels = {INHERIT_TEMPLATE_LABEL: INHERIT_TEMPLATE, **{v: k for k, v in TEMPLATES.items()}}
        template_name = next(label for label, key in labels.items() if key == original["template"])
        template, template_combo = self._inline_field(body, "Template", template_name, changed,
            design_template_choices(saved, TEMPLATES.values(), INHERIT_TEMPLATE_LABEL))

        def choose_template(_event):
            if template.get() in saved:
                dirty["loading"] = True
                draft.update(copy.deepcopy(saved[template.get()]))
                fill_variables()
                dirty["loading"] = False
            changed()
        template_combo.bind("<<ComboboxSelected>>", choose_template)
        field("Θέση κειμένου", "text_position", {"Πάνω": "top", "Κέντρο": "center", "Κάτω": "bottom"})
        field("Στοίχιση κειμένου", "text_align", {"Αριστερά": "left", "Κέντρο": "center", "Δεξιά": "right"})
        field("Γραμματοσειρά", "font_family", ("", "Calibri", "Arial", "Verdana", "Georgia"))
        field("Μέγεθος γραμματοσειράς", "font_size")
        field("Πλαίσιο", "panel_style", {"Συμπαγές": "solid", "Ημιδιαφανές": "translucent"})
        for key, label in (("text_color", "Χρώμα κειμένου"), ("panel_color", "Χρώμα πλαισίου"),
                           ("accent_color", "Χρώμα έμφασης")):
            field(label, key)
            def choose(k=key):
                result = colorchooser.askcolor(variables[k].get(), parent=self.root)[1]
                if result:
                    variables[k].set(result)
            ttk.Button(body, text="Επιλογή χρώματος", command=choose).pack(anchor="e", pady=2)
        for key, label in (("featured_enabled", "Εμφάνιση badge"), ("logo_enabled", "Λογότυπο")):
            var = tk.BooleanVar(value=draft[key])
            variables[key] = var
            ttk.Checkbutton(body, text=label, variable=var, command=changed).pack(anchor="w", pady=6)
        field("Κείμενο badge", "featured_text")
        field("Αρχείο λογότυπου", "logo_path")
        def choose_logo():
            path = filedialog.askopenfilename(parent=self.root, filetypes=[("Logo", "*.png *.jpg *.jpeg")])
            if path:
                variables["logo_path"].set(path)
        ttk.Button(body, text="Επιλογή λογότυπου", command=choose_logo).pack(fill="x", pady=3)

        def current():
            result = copy.deepcopy(draft)
            for key, var in variables.items():
                result[key] = choice_values[key][var.get()] if key in choice_values else var.get()
            try:
                result["font_size"] = int(result["font_size"])
            except ValueError:
                status.set("Γράψε έγκυρο μέγεθος γραμματοσειράς.")
                return None
            for key in ("text_color", "panel_color", "accent_color"):
                try:
                    self.root.winfo_rgb(result[key])
                except tk.TclError:
                    status.set("Γράψε έγκυρο χρώμα.")
                    return None
            result["template"] = (saved[template.get()]["template"] if template.get() in saved
                                    else labels.get(template.get(), "legacy"))
            return normalize_presentation(result, scene_id=original["scene_id"])

        def apply():
            if not dirty["value"] or self.media_files is not media or not body.winfo_exists():
                return False
            result = current()
            if result is None:
                return False
            valid = [target for target in targets if any(target is entry for entry in media)]
            if not valid:
                return False
            self.push_undo()
            for target in valid:
                value = normalize_presentation(target[2].get("presentation"))
                for key in STYLE_FIELDS:
                    value[key] = copy.deepcopy(result[key])
                target[2]["presentation"] = value
            dirty["value"] = False
            status.set("Η εμφάνιση εφαρμόστηκε.")
            self._inline_refresh()
            return True
        self._caption_apply_callback = apply
        ttk.Button(body, text="Εφαρμογή εμφάνισης", command=self._commit_pending_caption_apply).pack(fill="x", pady=8)
        status_label = self._inline_label(body)
        status_label.configure(textvariable=status)
        default_label = TEMPLATES.get(self.project_template, TEMPLATES["legacy"])
        default, combo = self._inline_field(body, "Προεπιλεγμένο template project", default_label,
                                            lambda: None, TEMPLATES.values())
        def project_default(_event):
            self._commit_pending_caption_apply()
            self.project_template = next(key for key, label in TEMPLATES.items() if label == default.get())
            self._remember_caption_template(self.project_template)
            self._inline_refresh()
        combo.bind("<<ComboboxSelected>>", project_default)
        name, _entry = self._inline_field(body, "Όνομα template για αποθήκευση", "", lambda: None)
        def save_template():
            value = current()
            title = name.get().strip()
            if value is None or not title or title in labels:
                status.set("Γράψε ένα μοναδικό όνομα template.")
                return
            saved[title] = {key: copy.deepcopy(value[key]) for key in DESIGN_FIELDS}
            write_design_templates(self.settings, saved)
            self.save_settings()
            template_combo.configure(values=design_template_choices(saved, TEMPLATES.values(), INHERIT_TEMPLATE_LABEL))
            status.set("Το template αποθηκεύτηκε στο προφίλ.")
        ttk.Button(body, text="Αποθήκευση / ενημέρωση\ntemplate", command=save_template).pack(fill="x", pady=4)
        def reset():
            dirty["loading"] = True
            fresh = normalize_presentation({"template": labels.get(template.get(), "legacy")},
                                           project_template=self.project_template)
            draft.update(saved.get(template.get(), fresh))
            fill_variables()
            dirty["loading"] = False
            changed()
        ttk.Button(body, text="Επαναφορά template", command=reset).pack(fill="x", pady=4)
