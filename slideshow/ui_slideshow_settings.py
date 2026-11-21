"""The Slideshow Settings window: live templates, defaults and preview."""

import copy
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, simpledialog

from .deps import Image, ImageDraw, ImageTk
from .slide_design import (TEMPLATES, compose_design_frame, normalize_presentation)
from .slide_templates import (DEFAULT_KEY, REGISTRY_KEY, STYLE_FIELDS,
                              BUILTIN_STYLES, FONT_CHOICES, PANEL_STYLE_CHOICES,
                              TEXT_ALIGN_CHOICES, TEXT_LAYOUT_CHOICES,
                              TEXT_POSITION_CHOICES, normalize_style,
                              read_template_registry)
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import ScrollFrame, flat_button, primary_button

TRANSITIONS = {
    "Fade": "fade", "Καμία": "none", "Fade to black": "fadeblack",
    "Fade to white": "fadewhite", "Wipe left": "wipeleft",
    "Wipe right": "wiperight", "Smooth left": "smoothleft",
    "Smooth right": "smoothright",
}
BACKGROUNDS = {"Θολό": "blur", "Λευκό": "white", "Μαύρο": "black",
               "Fit and Move": "fit_and_move"}
SAMPLE_FIELDS = {
    "title": "Σύγχρονο διαμέρισμα",
    "subtitle": "Με θέα στην πόλη",
    "description": "Φωτεινό, ανακαινισμένο και έτοιμο να το απολαύσεις.",
    "category": "ΠΩΛΗΣΗ",
    "location": "Αθήνα, Κολωνάκι",
    "price": "€250.000",
    "details": "95 τ.μ. · 3ος όροφος",
    "cta": "Επικοινωνήστε μαζί μας",
    "business_name": "Το γραφείο σου",
    "phone": "210 000 0000",
    "website": "www.example.gr",
}


class SlideshowSettingsMixin:
    """Build and persist the per-profile template registry."""

    def show_slideshow_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Slideshow Settings")
        dialog.geometry("1240x820")
        dialog.minsize(980, 640)
        dialog.transient(self.root)
        dialog.grab_set()

        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._settings_dialog = dialog
        self._settings_sample_image = None
        self._settings_preview_jobs = {}

        templates_tab = tk.Frame(notebook, bg=P["background"])
        defaults_tab = tk.Frame(notebook, bg=P["background"])
        preview_tab = tk.Frame(notebook, bg=P["background"])
        notebook.add(templates_tab, text="  Templates  ")
        notebook.add(defaults_tab, text="  Defaults  ")
        notebook.add(preview_tab, text="  Preview  ")

        state = {
            "name": None,
            "draft": {},
            "base": "legacy",
            "dirty": False,
            "loading": False,
            "preview_canvas": None,
            "listbox": None,
            "editor": None,
            "status": None,
            "preview_job": None,
        }
        self._slideshow_settings_state = state
        self._build_templates_tab(templates_tab, state)
        self._build_settings_defaults_tab(defaults_tab)
        self._build_settings_preview_tab(preview_tab)

        def close():
            if state["dirty"]:
                answer = messagebox.askyesnocancel(
                    "Slideshow Settings",
                    "Έχεις αλλαγές στο template που δεν αποθηκεύτηκαν.\n\n"
                    "Ναι: αποθήκευση και κλείσιμο.\nΌχι: κλείσιμο χωρίς αποθήκευση.",
                    parent=dialog)
                if answer is None:
                    return
                if answer and not self._settings_save_template(state):
                    return
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        self._refresh_slideshow_settings_templates(state)

    # ---------------------------------------------------------- templates tab
    def _build_templates_tab(self, parent, state):
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        left = tk.Frame(parent, bg=P["panel"], width=290,
                        highlightthickness=1, highlightbackground=P["border"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_propagate(False)
        tk.Label(left, text="TEMPLATES", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
        list_frame = tk.Frame(left, bg=P["panel"])
        list_frame.pack(fill="both", expand=True, padx=8, pady=4)
        listbox = tk.Listbox(list_frame, exportselection=False, bg=P["field"],
                             fg=P["text"], selectbackground=P["selected"],
                             selectforeground=P["text"], relief="flat", bd=0,
                             highlightthickness=1, highlightbackground=P["border"],
                             activestyle="none", font=("Segoe UI", 9))
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        state["listbox"] = listbox
        listbox.bind("<<ListboxSelect>>", lambda _e: self._settings_select_template(state))

        buttons = tk.Frame(left, bg=P["panel"])
        buttons.pack(fill="x", padx=10, pady=(6, 10))
        primary_button(buttons, "+  Νέο από αυτό", 
                       lambda: self._settings_save_as(state)).pack(fill="x", pady=(0, 4))
        flat_button(buttons, "Ορισμός ως default",
                    lambda: self._settings_set_default(state),
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"], font=("Segoe UI", 8, "bold")).pack(
            fill="x", pady=2)
        flat_button(buttons, "Επαναφορά template",
                    lambda: self._settings_reset_template(state),
                    background=P["raised"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8)).pack(
            fill="x", pady=2)
        flat_button(buttons, "Διαγραφή custom",
                    lambda: self._settings_delete_template(state),
                    background=P["raised"], foreground=P["danger"],
                    active_background=P["selected"], font=("Segoe UI", 8)).pack(
            fill="x", pady=2)
        tk.Label(left, text="Built-in templates μπορούν να αλλάξουν και να\n"
                           "επαναφερθούν. Custom templates διαγράφονται.",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 7),
                 justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        right = tk.Frame(parent, bg=P["background"])
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        preview_box = tk.Frame(right, bg=P["panel"], highlightthickness=1,
                               highlightbackground=P["border"])
        preview_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        preview_box.columnconfigure(0, weight=1)
        tk.Label(preview_box, text="ΠΡΟΕΠΙΣΚΟΠΗΣΗ", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w",
                                                    padx=10, pady=(7, 0))
        canvas = tk.Canvas(preview_box, bg=P["stage"], height=320,
                           highlightthickness=0, bd=0)
        canvas.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 10))
        state["preview_canvas"] = canvas
        canvas.bind("<Configure>", lambda _e: self._settings_schedule_preview(state),
                    add="+")
        editor_scroller = ScrollFrame(right, background=P["background"])
        editor_scroller.grid(row=1, column=0, sticky="nsew")
        editor = tk.Frame(editor_scroller.body, bg=P["background"], padx=14, pady=8)
        editor.pack(fill="both", expand=True)
        state["editor"] = editor
        state["status"] = tk.StringVar(value="")
        tk.Label(editor, textvariable=state["status"], bg=P["background"],
                 fg=P["accent"], font=("Segoe UI", 8)).pack(anchor="w", pady=(0, 4))
        self._settings_editor_body = editor

    def _refresh_slideshow_settings_templates(self, state, select=None):
        registry = read_template_registry(self.settings)
        current = select or state["name"]
        default_name = self._default_template_name(registry)
        listbox = state["listbox"]
        listbox.delete(0, tk.END)
        names = list(registry)
        for name in names:
            marker = "● " if name == default_name else "   "
            listbox.insert(tk.END, f"{marker}{name}")
        if current not in names:
            current = default_name if default_name in names else (names[0] if names else None)
        state["name"] = current
        if current is not None:
            index = names.index(current)
            listbox.selection_set(index)
            listbox.see(index)
            self._settings_load_template(state, registry, current)

    def _settings_select_template(self, state):
        listbox = state["listbox"]
        if not listbox.curselection():
            return
        registry = read_template_registry(self.settings)
        names = list(registry)
        choice = listbox.curselection()[0]
        if choice >= len(names):
            return
        name = names[choice]
        if state["dirty"]:
            answer = messagebox.askyesnocancel(
                "Slideshow Settings",
                "Να αποθηκευτούν οι αλλαγές του προηγούμενου template;",
                parent=self._settings_dialog)
            if answer is None:
                self._refresh_slideshow_settings_templates(state)
                return
            if answer:
                self._settings_save_template(state)
        state["dirty"] = False
        self._settings_load_template(state, registry, name)

    def _settings_load_template(self, state, registry, name):
        entry = registry.get(name)
        if entry is None:
            return
        state["loading"] = True
        state["name"] = name
        state["base"] = entry["base"]
        state["draft"] = copy.deepcopy(entry["style"])
        for child in state["editor"].winfo_children():
            child.destroy()
        body = state["editor"]
        tk.Label(body, text=name, bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(body, text="Built-in template" if entry["builtin"] else "Custom template",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 8)).pack(
            anchor="w", pady=(0, 8))
        self._settings_build_template_fields(body, state)
        save_row = tk.Frame(body, bg=P["background"])
        save_row.pack(fill="x", pady=(12, 2))
        primary_button(save_row, "Αποθήκευση",
                       lambda: self._settings_save_template(state)).pack(side="left")
        flat_button(save_row, "Αποθήκευση ως νέο",
                    lambda: self._settings_save_as(state),
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"], font=("Segoe UI", 8)).pack(
            side="left", padx=(6, 0))
        status = state["status"]
        status.set("")
        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass
        state["loading"] = False
        state["dirty"] = False
        self._settings_schedule_preview(state)

    def _settings_build_template_fields(self, parent, state):
        draft = state["draft"]

        def mark_dirty():
            if not state["loading"]:
                state["dirty"] = True
                state["status"].set("Μη αποθηκευμένες αλλαγές")
                self._settings_schedule_preview(state)

        def section(text):
            tk.Label(parent, text=text, bg=P["background"], fg=P["muted"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(12, 4))

        def labelled(text):
            tk.Label(parent, text=text, bg=P["background"], fg=P["muted"],
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(6, 2))

        def combo_field(key, label, choices):
            labelled(label)
            labels = list(choices)
            values = [choices[k] for k in labels]
            current = draft.get(key, values[0])
            var = tk.StringVar(value=next((k for k in labels if choices[k] == current), labels[0]))
            widget = ttk.Combobox(parent, textvariable=var, values=labels,
                                  state="readonly")
            widget.pack(fill="x")
            def changed(_event=None):
                draft[key] = choices[var.get()]
                mark_dirty()
            widget.bind("<<ComboboxSelected>>", changed, add="+")
            return var

        def text_field(key, label, values=None):
            labelled(label)
            var = tk.StringVar(value=str(draft.get(key, "")))
            widget = ttk.Combobox(parent, textvariable=var, values=list(values),
                                  state="readonly") if values else ttk.Entry(
                parent, textvariable=var)
            widget.pack(fill="x")
            def changed(*_args):
                try:
                    draft[key] = int(var.get()) if key == "font_size" else var.get()
                    mark_dirty()
                    state["status"].set("")
                except ValueError:
                    state["status"].set("Γράψε έγκυρο αριθμό.")
            var.trace_add("write", changed)
            return var

        def slider_field(key, label, low, high, suffix="%", invert=False):
            labelled(label)
            row = tk.Frame(parent, bg=P["background"])
            row.pack(fill="x")
            value_var = tk.StringVar()
            scale = tk.Scale(row, from_=low, to=high, orient="horizontal",
                             bg=P["background"], fg=P["text"],
                             troughcolor=P["field"], highlightthickness=0,
                             activebackground=P["accent"], showvalue=False,
                             command=lambda value: changed(value))
            scale.pack(side="left", fill="x", expand=True)
            value_lbl = tk.Label(row, textvariable=value_var, bg=P["background"],
                                 fg=P["text"], width=7, font=("Segoe UI", 8))
            value_lbl.pack(side="right", padx=(6, 0))

            def set_label(value):
                value = float(value)
                value_var.set("Auto" if int(value) == 0 and key != "panel_opacity"
                              else f"{int(value)}{suffix}")

            def stored_value(display):
                return (high - int(display)) if invert else int(display)

            def changed(value):
                number = int(float(value))
                stored = stored_value(number)
                if stored == int(draft.get(key, 0) or 0):
                    set_label(value)
                    return
                draft[key] = stored
                set_label(value)
                mark_dirty()
            initial = int(draft.get(key, 0) or 0)
            scale.set((high - initial) if invert else initial)
            set_label(scale.get())
            return scale

        def color_field(key, label):
            labelled(label)
            row = tk.Frame(parent, bg=P["background"])
            row.pack(fill="x")
            swatch = tk.Button(row, bg=draft.get(key, "#FFFFFF"), width=4,
                               relief="flat", bd=0, highlightthickness=1,
                               highlightbackground=P["border"], cursor="hand2")
            swatch.pack(side="left")
            entry_var = tk.StringVar(value=draft.get(key, "#FFFFFF"))
            entry = ttk.Entry(row, textvariable=entry_var, width=12)
            entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
            def update_swatch(*_args):
                value = entry_var.get().strip()
                if len(value) == 7 and value.startswith("#"):
                    try:
                        swatch.configure(bg=value)
                        draft[key] = value
                        mark_dirty()
                    except tk.TclError:
                        pass
            def choose():
                color = colorchooser.askcolor(draft.get(key), parent=self._settings_dialog)[1]
                if color:
                    entry_var.set(color)
                    update_swatch()
            swatch.configure(command=choose)
            entry_var.trace_add("write", update_swatch)

        section("ΤΥΠΟΓΡΑΦΙΑ")
        text_field("font_family", "Γραμματοσειρά", FONT_CHOICES)
        text_field("font_size", "Μέγεθος γραμματοσειράς")
        combo_field("text_position", "Θέση κειμένου", TEXT_POSITION_CHOICES)
        combo_field("text_align", "Στοίχιση κειμένου", TEXT_ALIGN_CHOICES)

        section("ΧΡΩΜΑΤΑ & ΠΛΑΙΣΙΟ")
        color_field("text_color", "Χρώμα κειμένου")
        color_field("panel_color", "Χρώμα πλαισίου")
        color_field("accent_color", "Χρώμα έμφασης")
        tk.Label(editor, text="Στα captions: επίλεξε λέξεις και πάτα A, "
                               "ή γράψε ##κείμενο##.",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 8),
                 anchor="w", justify="left", wraplength=300).pack(
            anchor="w", pady=(0, 6))
        slider_field("panel_opacity", "Διαφάνεια πλαισίου (0 = συμπαγές)",
                     0, 100, invert=True)
        slider_field("panel_width_pct", "Πλάτος πλαισίου (0 = Auto)", 0, 100)
        slider_field("panel_padding_pct", "Εσωτερικό padding (0 = Auto)", 0, 15)
        slider_field("panel_min_height_pct", "Ελάχιστο ύψος (0 = Auto)", 0, 80)

        section("ΤΟΠΟΘΕΤΗΣΗ")
        combo_field("text_layout", "Τοποθέτηση κειμένου", TEXT_LAYOUT_CHOICES)

    def _settings_save_data(self, state, name, base, builtin, style, select=None,
                            status_text="Το template αποθηκεύτηκε."):
        stored = self.settings.setdefault(REGISTRY_KEY, {})
        stored[name] = {"base": base, "builtin": builtin,
                        "style": normalize_style(base, style)}
        self.save_settings()
        self._template_registry_cache = None
        state["dirty"] = False
        state["status"].set(status_text)
        self._refresh_after_template_change()
        self._refresh_slideshow_settings_templates(state, select=select or name)
        self._refresh_settings_preview_tab()

    def _settings_save_template(self, state):
        if not state["name"]:
            return False
        style = self._settings_validated_draft(state)
        if style is None:
            return False
        registry = read_template_registry(self.settings)
        entry = registry.get(state["name"], {})
        builtin = bool(entry.get("builtin")) and state["name"] in TEMPLATES.values()
        self._settings_save_data(state, state["name"], state["base"],
                                 builtin, style, select=state["name"])
        return True

    def _settings_validated_draft(self, state):
        try:
            size = int(float(state["draft"].get("font_size", 0)))
        except (TypeError, ValueError):
            state["status"].set("Γράψε έγκυρο μέγεθος γραμματοσειράς.")
            return None
        if size < 4 or size > 400:
            state["status"].set("Το μέγεθος γραμματοσειράς πρέπει να είναι 4–400.")
            return None
        return normalize_style(state["base"], state["draft"])

    def _settings_save_as(self, state):
        if not state["name"]:
            return
        style = self._settings_validated_draft(state)
        if style is None:
            return
        registry = read_template_registry(self.settings)
        name = simpledialog.askstring(
            "Νέο template", "Όνομα για το νέο template:",
            parent=self._settings_dialog)
        if not name:
            return
        name = name.strip()
        if not name or name in registry or name in TEMPLATES.values():
            messagebox.showwarning("Template", "Διάλεξε ένα μοναδικό όνομα.",
                                   parent=self._settings_dialog)
            return
        self._settings_save_data(state, name, state["base"], False, style,
                                 select=name,
                                 status_text="Δημιουργήθηκε νέο custom template.")

    def _settings_delete_template(self, state):
        registry = read_template_registry(self.settings)
        name = state["name"]
        entry = registry.get(name)
        if not name or not entry or entry["builtin"] and name in TEMPLATES.values():
            messagebox.showinfo("Template", "Τα built-in templates δεν διαγράφονται.",
                                parent=self._settings_dialog)
            return
        if not messagebox.askyesno(
                "Διαγραφή template",
                f"Να διαγραφεί το custom template «{name}»;",
                parent=self._settings_dialog):
            return
        stored = self.settings.setdefault(REGISTRY_KEY, {})
        stored.pop(name, None)
        if self.settings.get(DEFAULT_KEY) == name:
            fallback = next(iter(TEMPLATES.values()))
            self.settings[DEFAULT_KEY] = fallback
            self.settings["last_caption_template"] = TEMPLATES and next(
                (key for key, label in TEMPLATES.items() if label == fallback), "legacy")
            self.settings["last_caption_template_is_global"] = True
        self.save_settings()
        self._template_registry_cache = None
        state["dirty"] = False
        self._refresh_after_template_change()
        self._refresh_slideshow_settings_templates(state)
        self._refresh_settings_preview_tab()

    def _settings_reset_template(self, state):
        registry = read_template_registry(self.settings)
        name = state["name"]
        entry = registry.get(name)
        if not name or not entry:
            return
        if not messagebox.askyesno(
                "Επαναφορά template",
                "Να επαναφερθούν οι εργοστασιακές ρυθμίσεις αυτού του template;",
                parent=self._settings_dialog):
            return
        stored = self.settings.setdefault(REGISTRY_KEY, {})
        if entry["builtin"] and name in TEMPLATES.values():
            stored.pop(name, None)
        else:
            stored[name] = {"base": entry["base"], "builtin": False,
                            "style": normalize_style(entry["base"])}
        self.save_settings()
        self._template_registry_cache = None
        state["dirty"] = False
        self._refresh_after_template_change()
        self._refresh_slideshow_settings_templates(state, select=name)

    def _settings_set_default(self, state):
        if not state["name"]:
            return
        if state["dirty"] and not self._settings_save_template(state):
            return
        self.set_default_template(state["name"])
        if hasattr(self, "_settings_large_preview_var"):
            self._settings_large_preview_var.set(state["name"])
        self._refresh_slideshow_settings_templates(state)
        self._refresh_settings_preview_tab()
        state["status"].set("Ορίστηκε ως default template.")

    # --------------------------------------------------------- preview helpers
    def _settings_sample(self):
        if self._settings_sample_image is not None:
            return self._settings_sample_image
        index = self._selected_item_index()
        image = None
        if index is not None:
            kind, path, _edit = self.media_files[index]
            try:
                image = (self._video_first_frame(path) if kind == "video"
                         else self.open_thumbnail_image(path, 1200))
                image.load()
            except Exception:
                image = None
        if image is None:
            image = Image.new("RGB", (1200, 800), P["raised"])
            draw = ImageDraw.Draw(image)
            for y in range(800):
                ratio = y / 799
                draw.line((0, y, 1200, y),
                          fill=(int(30 + 40 * ratio), int(40 + 45 * ratio),
                                int(52 + 35 * ratio)))
            draw.ellipse((650, 120, 1100, 570), fill=P["accent_faint"])
        self._settings_sample_image = image.convert("RGB")
        return self._settings_sample_image

    def _settings_render_preview(self, style, base, width=480, height=320):
        source = self._settings_sample()
        resolution = str(self.settings.get("resolution", "1080x1080"))
        try:
            rw, rh = map(int, resolution.split("x"))
        except (TypeError, ValueError):
            rw, rh = 1080, 1080
        scale = min(width / rw, height / rh)
        w = max(180, int(rw * scale))
        h = max(180, int(rh * scale))
        presentation = normalize_presentation({
            "template": base, "mode": "custom", "font_size": style["font_size"],
            "font_family": style["font_family"], "text_position": style["text_position"],
            "text_align": style["text_align"], "text_color": style["text_color"],
            "panel_color": style["panel_color"], "accent_color": style["accent_color"],
            "panel_style": style["panel_style"], "panel_opacity": style["panel_opacity"],
            "panel_width_pct": style["panel_width_pct"],
            "panel_padding_pct": style["panel_padding_pct"],
            "panel_min_height_pct": style["panel_min_height_pct"],
            "text_layout": style["text_layout"],
            "title": SAMPLE_FIELDS["title"], "subtitle": SAMPLE_FIELDS["subtitle"],
            "description": SAMPLE_FIELDS["description"],
            "category": SAMPLE_FIELDS["category"], "location": SAMPLE_FIELDS["location"],
            "price": SAMPLE_FIELDS["price"], "details": SAMPLE_FIELDS["details"],
            "cta": SAMPLE_FIELDS["cta"], "business_name": SAMPLE_FIELDS["business_name"],
            "phone": SAMPLE_FIELDS["phone"], "website": SAMPLE_FIELDS["website"],
        })
        if base == "legacy":
            preview_font = max(8, int(style["font_size"] * min(w, h) / 540))
            presentation["font_size"] = preview_font
            text = (f"{SAMPLE_FIELDS['title']}\n{SAMPLE_FIELDS['subtitle']}")
            frame = self._fit_image_logic(source, w, h, "image", text=text,
                                          presentation=presentation)
            frame = self.render_text_on_image(
                frame, text, w, h, align=presentation["text_align"],
                presentation=presentation)
            return frame
        frame, _overflow = compose_design_frame(
            source, w, h, presentation, SAMPLE_FIELDS)
        return frame

    def _settings_draw_preview(self, canvas, style, base):
        if canvas is None:
            return
        try:
            frame = self._settings_render_preview(style, base,
                                                  canvas.winfo_width() or 480,
                                                  canvas.winfo_height() or 250)
        except Exception:
            return
        photo = ImageTk.PhotoImage(frame, master=self.root)
        canvas._settings_photo = photo
        canvas.delete("all")
        canvas.create_image(canvas.winfo_width() // 2, canvas.winfo_height() // 2,
                            image=photo)

    def _settings_schedule_preview(self, state):
        if state["loading"]:
            return
        job = state.get("preview_job")
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        state["preview_job"] = self.root.after(
            220, lambda: self._settings_draw_preview(
                state["preview_canvas"], state["draft"], state["base"]))

    # ----------------------------------------------------------- defaults tab
    def _build_settings_defaults_tab(self, parent):
        body = tk.Frame(parent, bg=P["background"], padx=24, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="ΠΡΟΕΠΙΛΟΓΕΣ SLIDESHOW", bg=P["background"],
                 fg=P["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(body, text="Ισχύουν για νέα projects και για τις ρυθμίσεις που "
                           "δεν έχουν project override.",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 9),
                 wraplength=620, justify="left").pack(anchor="w", pady=(2, 14))
        registry = read_template_registry(self.settings)
        names = list(registry)

        def row(label):
            frame = tk.Frame(body, bg=P["background"])
            frame.pack(fill="x", pady=5)
            tk.Label(frame, text=label, bg=P["background"], fg=P["text"],
                     width=28, anchor="w", font=("Segoe UI", 9)).pack(side="left")
            return frame

        default_var = tk.StringVar(value=self._default_template_name(registry))
        default_row = row("Default template")
        ttk.Combobox(default_row, textvariable=default_var, values=names,
                     state="readonly").pack(side="left", fill="x", expand=True)
        resolution_var = tk.StringVar(value=self.settings.get("resolution", "1080x1080"))
        res_row = row("Ανάλυση")
        ttk.Combobox(res_row, textvariable=resolution_var,
                     values=("1080x1080", "1920x1080", "1080x1920", "1080x1350", "720x1280"),
                     state="readonly").pack(side="left", fill="x", expand=True)
        duration_var = tk.StringVar(value=str(self.settings.get("slide_duration", 3)))
        duration_row = row("Διάρκεια slide (δευτ.)")
        ttk.Spinbox(duration_row, from_=1, to=60, textvariable=duration_var,
                    width=8).pack(side="left")
        transition_var = tk.StringVar(value=next(
            (label for label, value in TRANSITIONS.items()
             if value == self.settings.get("transition_effect")), "Fade"))
        transition_row = row("Transition")
        ttk.Combobox(transition_row, textvariable=transition_var,
                     values=list(TRANSITIONS), state="readonly").pack(
            side="left", fill="x", expand=True)
        tr_duration_var = tk.StringVar(value=str(self.settings.get("transition_duration", .7)))
        tr_duration_row = row("Διάρκεια transition (δευτ.)")
        ttk.Spinbox(tr_duration_row, from_=0.2, to=2.0, increment=0.1,
                    textvariable=tr_duration_var, width=8).pack(side="left")
        background_var = tk.StringVar(value=next(
            (label for label, value in BACKGROUNDS.items()
             if value == self.settings.get("background_mode")), "Θολό"))
        background_row = row("Background")
        ttk.Combobox(background_row, textvariable=background_var,
                     values=list(BACKGROUNDS), state="readonly").pack(
            side="left", fill="x", expand=True)
        crop_var = tk.BooleanVar(value=bool(self.settings.get("cropping", False)))
        tk.Checkbutton(body, text="Γέμισμα κάδρου με crop", variable=crop_var,
                       indicatoron=False, bg=P["raised"], fg=P["text"],
                       selectcolor=P["accent_faint"], activebackground=P["selected"],
                       activeforeground=P["text"], relief="flat", bd=0,
                       anchor="w", padx=10, pady=6,
                       font=("Segoe UI", 9)).pack(fill="x", pady=(8, 0))
        status = tk.StringVar(value="")
        tk.Label(body, textvariable=status, bg=P["background"], fg=P["accent"],
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(10, 0))

        def save_defaults():
            try:
                duration = max(1, min(60, int(float(duration_var.get()))))
                tr_duration = max(0.2, min(2.0, float(tr_duration_var.get())))
            except (TypeError, ValueError):
                status.set("Έλεγξε τις τιμές διάρκειας.")
                return
            self.settings.update({
                "resolution": resolution_var.get(),
                "slide_duration": duration,
                "transition_effect": TRANSITIONS.get(transition_var.get(), "fade"),
                "transition_duration": tr_duration,
                "background_mode": BACKGROUNDS.get(background_var.get(), "blur"),
                "cropping": bool(crop_var.get()),
            })
            self.set_default_template(default_var.get())
            if hasattr(self, "_settings_large_preview_var"):
                self._settings_large_preview_var.set(default_var.get())
            self.save_settings()
            state = getattr(self, "_slideshow_settings_state", None)
            if state is not None:
                self._refresh_slideshow_settings_templates(state)
            status.set("Οι προεπιλογές αποθηκεύτηκαν.")
            self._refresh_after_template_change()
            if hasattr(self, "_refresh_settings_preview_tab"):
                self._refresh_settings_preview_tab()

        primary_button(body, "Αποθήκευση προεπιλογών", save_defaults).pack(
            anchor="w", pady=(14, 0))

    # ------------------------------------------------------------ preview tab
    def _build_settings_preview_tab(self, parent):
        body = tk.Frame(parent, bg=P["background"], padx=16, pady=12)
        body.pack(fill="both", expand=True)
        top = tk.Frame(body, bg=P["background"])
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Προεπισκόπηση default template", bg=P["background"],
                 fg=P["text"], font=("Segoe UI", 12, "bold")).pack(side="left")
        registry = read_template_registry(self.settings)
        default_var = tk.StringVar(value=self._default_template_name(registry))
        combo = ttk.Combobox(top, textvariable=default_var, values=list(registry),
                             state="readonly", width=32)
        combo.pack(side="right")
        canvas = tk.Canvas(body, bg=P["stage"], highlightthickness=1,
                           highlightbackground=P["border"])
        canvas.pack(fill="both", expand=True)
        self._settings_large_preview_var = default_var
        self._settings_large_preview_canvas = canvas

        def refresh(_event=None):
            registry = read_template_registry(self.settings)
            name = default_var.get()
            entry = registry.get(name)
            if entry:
                self._settings_draw_preview(canvas, entry["style"], entry["base"])
        combo.bind("<<ComboboxSelected>>", refresh, add="+")
        canvas.bind("<Configure>", lambda _e: refresh(), add="+")
        self._refresh_settings_preview_tab = lambda: refresh()
        body.after(100, refresh)
