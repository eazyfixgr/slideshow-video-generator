"""Three caption strategies with automatic scene and group editing."""

import tkinter as tk
from tkinter import ttk

from .slide_design import legacy_text, normalize_presentation

CAPTION_STRATEGIES = {
    "Όλο το project": "all",
    "Φωτογραφίες / βίντεο": "by_type",
    "Ανά σκηνή / ομάδα": "individual",
}
CAPTION_FIELDS = {
    "category": "Κατηγορία / τύπος", "location": "Τοποθεσία", "price": "Τιμή",
    "details": "Λεπτομέρειες", "cta": "Call to action", "business_name": "Επωνυμία",
    "phone": "Τηλέφωνο", "website": "Ιστότοπος",
}


class CaptionInspectorMixin:
    def _set_caption_strategy(self, strategy):
        self._commit_pending_caption_apply()
        if strategy not in CAPTION_STRATEGIES.values() or strategy == self.project_caption_mode:
            return
        self.push_undo()
        if strategy == "individual":
            for kind, _path, edit in self.media_files:
                value = normalize_presentation(edit.get("presentation"))
                if value["mode"] == "global":
                    value.update(mode="custom", description=self.get_text_for(kind))
                    value.update(title="", subtitle="")
                    edit["presentation"] = value
        self.project_caption_mode = strategy
        self._inline_refresh()
        self._render_inspector()

    def _render_captions_inspector(self, body):
        self.inspector_title_var.set("Captions")
        strategy = self.project_caption_mode
        label = next(label for label, value in CAPTION_STRATEGIES.items() if value == strategy)
        choice, combo = self._inline_field(body, "Εφαρμογή σε", label, lambda: None,
                                            CAPTION_STRATEGIES)
        combo.bind("<<ComboboxSelected>>",
                   lambda _e: self._set_caption_strategy(CAPTION_STRATEGIES[choice.get()]))
        individual = strategy == "individual"
        _index, item = self._selected_item()
        media = self.media_files
        targets = [media[index] for index in self._selected()] if individual else []
        if individual and not targets and item is not None:
            targets = [item]
        focused = {"widget": None}
        fields, widgets = {}, {}
        dirty = set()

        def changed(key):
            dirty.add(key)
            self._inline_changed(2000)

        if individual and not targets:
            self._empty_inspector(body, "Πρόσθεσε media για να γράψεις κείμενο ανά σκηνή.")
        elif individual:
            def caption(target):
                kind, _path, edit = target
                value = normalize_presentation(edit.get("presentation"))
                # Existing hidden captions stay editable after switching from shared mode.
                if value["mode"] in ("custom", "combine"):
                    return "\n".join(value[key] for key in ("title", "subtitle", "description")
                                     if value[key])
                return legacy_text(value, self.get_text_for(kind))

            texts = [caption(target) for target in targets]
            if len(targets) > 1:
                note = f"Ομάδα: {len(targets)} σκηνές. Το νέο κείμενο εφαρμόζεται σε όλες."
                if len(set(texts)) > 1:
                    note += " Έχουν διαφορετικές λεζάντες· εμφανίζεται η πρώτη."
            else:
                note = "Επίλεξε σκηνή ή Ctrl/Shift + κλικ για ομάδα."
            self._inline_label(body, note, pady=(7, 2))
            widget = self._inline_text(body, "Κείμενο", texts[0],
                                       lambda: changed("description"), 7)
            fields["description"] = widget
            widgets["description"] = widget
            value = normalize_presentation(targets[0][2].get("presentation"))
            advanced = ttk.LabelFrame(body, text="Προαιρετικές πληροφορίες", padding=5)
            toggle = tk.BooleanVar(value=False)
            ttk.Checkbutton(body, text="Περισσότερα πεδία", variable=toggle,
                            command=lambda: advanced.pack(fill="x") if toggle.get()
                            else advanced.pack_forget()).pack(anchor="w", pady=6)
            for key, label in CAPTION_FIELDS.items():
                var, entry = self._inline_field(advanced, label, value[key],
                                                lambda k=key: changed(k))
                fields[key], widgets[key] = var, entry
        else:
            shared = (("project_text_all", "Κοινό κείμενο"),) if strategy == "all" else (
                ("project_text_photos", "Κείμενο φωτογραφιών"),
                ("project_text_videos", "Κείμενο βίντεο"))
            for key, label in shared:
                widget = self._inline_text(body, label, getattr(self, key, ""),
                                           lambda k=key: changed(k), 7 if strategy == "all" else 5)
                fields[key], widgets[key] = widget, widget

        for widget in widgets.values():
            widget.bind("<FocusIn>", lambda _e, w=widget: focused.update(widget=w), add="+")
        focused["widget"] = next(iter(widgets.values()), None)
        instructions = self._inline_text(body, "Επιπλέον οδηγίες για AI",
                                         self.project_ai_instructions,
                                         lambda: changed("instructions"), 3)

        def values():
            return {key: (widget.get("1.0", "end-1c") if isinstance(widget, tk.Text)
                          else widget.get()) for key, widget in fields.items() if key in dirty}

        def apply():
            if self.media_files is not media or not body.winfo_exists() or not dirty:
                return False
            data = values()
            self.push_undo()
            self.project_ai_instructions = instructions.get("1.0", "end-1c")
            if individual and data:
                if "description" in data:
                    data.update(title="", subtitle="")
                for target in targets:
                    if any(target is entry for entry in media):
                        current = normalize_presentation(target[2].get("presentation"))
                        current.update(data, mode="custom")
                        target[2]["presentation"] = current
            else:
                for key, text in data.items():
                    setattr(self, key, text)
            dirty.clear()
            self._inline_refresh()
            return True

        self._caption_apply_callback = apply
        if focused["widget"] is None:
            return

        def improve():
            widget = focused["widget"]
            key = next(key for key, candidate in widgets.items() if candidate is widget)
            text = widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get()

            def receive(value):
                if not body.winfo_exists() or self.media_files is not media:
                    return
                if isinstance(widget, tk.Text):
                    widget.delete("1.0", "end")
                    widget.insert("1.0", value)
                else:
                    widget.delete(0, "end")
                    widget.insert(0, value)
                changed(key)
                self._commit_pending_caption_apply()

            self.improve_text_with_ai(text, instructions.get("1.0", "end-1c"), receive)

        ttk.Button(body, text="Βελτίωση με AI", command=improve).pack(fill="x", pady=3)
