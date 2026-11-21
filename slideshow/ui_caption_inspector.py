"""Three caption strategies with automatic scene and group editing."""

import re
import tkinter as tk
from tkinter import ttk

from .rich_text import markup_ranges, parse_markup, size_factor
from .slide_design import legacy_text, normalize_presentation
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import flat_button

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
    def _caption_text_from_item(self, item):
        kind, _path, edit = item
        value = normalize_presentation(edit.get("presentation"))
        if value["mode"] in ("custom", "combine"):
            parts = [value[key] for key in ("title", "subtitle", "description")
                     if value[key]]
            if parts:
                return "\n".join(parts)
        return legacy_text(value, self.get_text_for(kind))

    def _caption_source_text(self, old_mode, media_type=None):
        _index, selected = self._selected_item()
        candidates = []
        if selected is not None and media_type in (None, selected[0]):
            candidates.append(selected)
        candidates.extend(item for item in self.media_files
                          if media_type is None or item[0] == media_type)
        for item in candidates:
            text = self._caption_text_from_item(item).strip()
            if text:
                return text
        if old_mode == "all":
            return (self.project_text_all or "").strip()
        if media_type == "video":
            return (self.project_text_videos or "").strip()
        if media_type == "image":
            return (self.project_text_photos or "").strip()
        return ((self.project_text_all or self.project_text_photos or
                 self.project_text_videos) or "").strip()

    def _set_caption_strategy(self, strategy):
        self._commit_pending_caption_apply()
        if strategy not in CAPTION_STRATEGIES.values() or strategy == self.project_caption_mode:
            return
        old = self.project_caption_mode
        old_all = self.project_text_all
        old_photos = self.project_text_photos
        old_videos = self.project_text_videos
        generic = self._caption_source_text(old)
        selected_text = self._caption_source_text(old, None)
        self.push_undo()

        if strategy == "individual":
            for kind, _path, edit in self.media_files:
                value = normalize_presentation(edit.get("presentation"))
                source = (old_all if old == "all" else
                          old_videos if kind == "video" else old_photos)
                source = (source or generic or "").strip()
                if value["mode"] == "global":
                    value.update(mode="custom", description=source,
                                 title="", subtitle="")
                    edit["presentation"] = value
                elif not (value["title"] or value["subtitle"] or
                          value["description"]).strip():
                    value["description"] = source
                    edit["presentation"] = value
        elif strategy == "all":
            if not (self.project_text_all or "").strip():
                if old == "individual":
                    self.project_text_all = selected_text
                elif old == "by_type":
                    _index, selected = self._selected_item()
                    if not self.selected_indices:
                        selected = None
                    chosen = (old_videos if selected is not None and selected[0] == "video"
                              else old_photos if selected is not None and selected[0] == "image"
                              else old_videos or old_photos)
                    self.project_text_all = (chosen or generic).strip()
        elif strategy == "by_type" and old == "all":
            if not (self.project_text_photos or "").strip():
                self.project_text_photos = old_all
            if not (self.project_text_videos or "").strip():
                self.project_text_videos = old_all
        elif strategy == "by_type" and old == "individual":
            if not (self.project_text_photos or "").strip():
                self.project_text_photos = self._caption_source_text(old, "image")
            if not (self.project_text_videos or "").strip():
                self.project_text_videos = self._caption_source_text(old, "video")

        self.project_caption_mode = strategy
        self._inline_refresh()
        self._render_inspector()

    def _caption_accent_color(self):
        _index, item = self._selected_item()
        if item is not None:
            resolved = self._resolve_presentation_style(item[2].get("presentation"))
            return resolved.get("accent_color") or P["accent"]
        registry = self.template_registry()
        name = self._effective_project_template_name(registry)
        return registry.get(name, {}).get("style", {}).get("accent_color", P["accent"])

    def _setup_rich_text(self, widget, accent):
        widget._rich_accent_color = accent
        widget._rich_show_markup = bool(getattr(widget, "_rich_show_markup", False))
        widget.tag_configure("rich_markup", foreground="#687384",
                             font=("Segoe UI", 8))
        widget.tag_configure("rich_hidden", elide=True)
        widget.tag_configure("rich_accent", foreground=accent)
        tags = {}
        for steps in range(-10, 21):
            size = max(6, round(10 * size_factor(steps)))
            for bold in (False, True):
                tag = f"rich_font_{steps}_{int(bold)}"
                widget.tag_configure(
                    tag, font=("Segoe UI", size, "bold" if bold else "normal"))
                tags[(steps, bold)] = tag
        widget._rich_font_tags = tags
        widget._rich_all_tags = ["rich_markup", "rich_hidden", "rich_accent",
                                 *tags.values()]

    def _refresh_rich_tags(self, widget):
        if not isinstance(widget, tk.Text) or not hasattr(widget, "_rich_font_tags"):
            return
        try:
            text = widget.get("1.0", "end-1c")
            for tag in widget._rich_all_tags:
                widget.tag_remove(tag, "1.0", "end")
            for span in parse_markup(text):
                if not span.text:
                    continue
                start = f"1.0+{span.start}c"
                end = f"1.0+{span.end}c"
                tag = widget._rich_font_tags.get(
                    (span.size_steps, span.bold),
                    widget._rich_font_tags.get((0, span.bold)))
                if tag:
                    widget.tag_add(tag, start, end)
                if span.accent:
                    widget.tag_add("rich_accent", start, end)
            for start, end in markup_ranges(text):
                widget.tag_add("rich_markup", f"1.0+{start}c",
                               f"1.0+{end}c")
                if not getattr(widget, "_rich_show_markup", False):
                    widget.tag_add("rich_hidden", f"1.0+{start}c",
                                   f"1.0+{end}c")
        except tk.TclError:
            pass

    def _build_caption_format_toolbar(self, parent, focused, accent):
        row = tk.Frame(parent, bg=P["panel"])
        row.pack(fill="x", pady=(8, 2))
        tk.Label(row, text="ΜΟΡΦΟΠΟΙΗΣΗ", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 6))

        def apply(kind, delta=0):
            widget = focused.get("widget")
            if isinstance(widget, tk.Text):
                self._format_rich_selection(widget, kind, delta)

        def toggle_markup():
            widget = focused.get("widget")
            if not isinstance(widget, tk.Text):
                return
            widget._rich_show_markup = not getattr(widget, "_rich_show_markup", False)
            self._refresh_rich_tags(widget)
            markup_button.configure(
                foreground=accent if widget._rich_show_markup else P["muted"])

        flat_button(row, "B", lambda: apply("bold"), background=P["raised"],
                    foreground=P["text"], active_background=P["selected"],
                    font=("Segoe UI", 9, "bold"), padx=8, pady=2,
                    takefocus=0).pack(side="left", padx=(0, 3))
        flat_button(row, "A", lambda: apply("accent"),
                    background=P["raised"], foreground=accent,
                    active_background=P["selected"], font=("Segoe UI", 9, "bold"),
                    padx=8, pady=2, takefocus=0).pack(side="left", padx=(0, 3))
        flat_button(row, "A−", lambda: apply("size", -1),
                    background=P["raised"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8),
                    padx=6, pady=2, takefocus=0).pack(side="left", padx=(0, 3))
        flat_button(row, "A+", lambda: apply("size", 1),
                    background=P["raised"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8),
                    padx=6, pady=2, takefocus=0).pack(side="left", padx=(0, 3))
        markup_button = flat_button(
            row, "Markup", toggle_markup, background=P["raised"],
            foreground=P["muted"], active_background=P["selected"],
            font=("Segoe UI", 8), padx=6, pady=2, takefocus=0)
        markup_button.pack(side="left")
        tk.Label(parent, text="Επίλεξε κείμενο · **bold**   "
                              "##χρώμα έμφασης##   %+1%μεγαλύτερο%%   "
                              "%-1%μικρότερο%%",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8),
                 anchor="w", justify="left", wraplength=300).pack(
            fill="x", pady=(2, 4))

    def _format_rich_selection(self, widget, kind, delta=1):
        try:
            start = widget.index(tk.SEL_FIRST)
            end = widget.index(tk.SEL_LAST)
            selected = widget.get(start, end)
        except tk.TclError:
            start = end = widget.index(tk.INSERT)
            selected = ""

        if kind in ("bold", "accent"):
            marker = "**" if kind == "bold" else "##"
            outer_start = outer_end = None
            inner = selected
            if (selected.startswith(marker) and selected.endswith(marker) and
                    len(selected) > len(marker) * 2):
                inner = selected[len(marker):-len(marker)]
                outer_start, outer_end = start, end
            elif selected:
                names = set(widget.tag_names(start))
                styled = (any(name.startswith("rich_font_") and name.endswith("_1")
                              for name in names) if kind == "bold"
                          else "rich_accent" in names)
                if styled:
                    full = widget.get("1.0", "end-1c")
                    start_off = len(widget.get("1.0", start))
                    open_pos = full.rfind(marker, 0, start_off)
                    close_pos = full.find(marker, start_off + len(selected))
                    if open_pos >= 0 and close_pos >= 0:
                        outer_start = widget.index(f"1.0+{open_pos}c")
                        outer_end = widget.index(
                            f"1.0+{close_pos + len(marker)}c")
                        inner = full[open_pos + len(marker):close_pos]
            if outer_start is not None:
                widget.delete(outer_start, outer_end)
                widget.insert(outer_start, inner)
                new_start = outer_start
                new_end = widget.index(f"{outer_start}+{len(inner)}c")
            elif selected:
                widget.insert(end, marker)
                widget.insert(start, marker)
                new_start = widget.index(f"{start}+{len(marker)}c")
                new_end = widget.index(f"{new_start}+{len(selected)}c")
            else:
                widget.insert(start, marker + marker)
                widget.mark_set(tk.INSERT, f"{start}+{len(marker)}c")
                new_start = new_end = widget.index(tk.INSERT)
            self._finish_rich_edit(widget, new_start, new_end)
            return

        if kind != "size":
            return
        before = widget.get(widget.index(f"{start}-10c"), start)
        size_before = re.search(r"(%[+-]\d+%)$", before)
        size_selected = re.match(r"^(%[+-]\d+%)([\s\S]*?)(%%)$", selected)
        outer_start = outer_end = open_marker = inner = None
        if size_selected:
            open_marker, inner = size_selected.group(1), size_selected.group(2)
            outer_start, outer_end = start, end
        elif size_before and widget.get(end, widget.index(f"{end}+2c")) == "%%":
            open_marker = size_before.group(1)
            inner = selected
            outer_start = widget.index(f"{start}-{len(open_marker)}c")
            outer_end = widget.index(f"{end}+2c")
        if outer_start is not None:
            try:
                current = int(open_marker[1:-1])
            except ValueError:
                current = 0
            steps = max(-10, min(20, current + int(delta)))
            replacement = inner if steps == 0 else f"%{steps:+d}%{inner}%%"
            widget.delete(outer_start, outer_end)
            widget.insert(outer_start, replacement)
            if steps == 0:
                new_start = outer_start
                new_end = widget.index(f"{outer_start}+{len(inner)}c")
            else:
                new_start = widget.index(f"{outer_start}+{len(f'%{steps:+d}%')}c")
                new_end = widget.index(f"{new_start}+{len(inner)}c")
        else:
            open_marker = f"%{int(delta):+d}%"
            if selected:
                widget.insert(end, "%%")
                widget.insert(start, open_marker)
                new_start = widget.index(f"{start}+{len(open_marker)}c")
                new_end = widget.index(f"{new_start}+{len(selected)}c")
            else:
                widget.insert(start, open_marker + "%%")
                widget.mark_set(tk.INSERT, f"{start}+{len(open_marker)}c")
                new_start = new_end = widget.index(tk.INSERT)
        self._finish_rich_edit(widget, new_start, new_end)

    def _finish_rich_edit(self, widget, start, end):
        try:
            widget.tag_remove(tk.SEL, "1.0", "end")
            if start and end and widget.compare(start, "!=", end):
                widget.tag_add(tk.SEL, start, end)
            widget.mark_set(tk.INSERT, end or start)
            widget.focus_set()
        except tk.TclError:
            pass
        callback = getattr(widget, "_inline_on_change", None)
        if callback:
            callback()
        else:
            self._refresh_rich_tags(widget)

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

        accent_color = self._caption_accent_color()
        self._build_caption_format_toolbar(body, focused, accent_color)

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
                                       lambda: changed("description"), 7,
                                       rich=True, accent_color=accent_color)
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
                                           lambda k=key: changed(k), 7 if strategy == "all" else 5,
                                           rich=True, accent_color=accent_color)
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
                if isinstance(widget, tk.Text):
                    self._refresh_rich_tags(widget)
                changed(key)
                self._commit_pending_caption_apply()

            self.improve_text_with_ai(text, instructions.get("1.0", "end-1c"), receive)

        ttk.Button(body, text="Βελτίωση με AI", command=improve).pack(fill="x", pady=3)
