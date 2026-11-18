"""Startup welcome screen and a compact three-step new-project wizard."""

import json
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .deps import Image, ImageTk
from .slide_design import TEMPLATES


RESOLUTIONS = ("1080x1080", "1920x1080", "1080x1920", "1080x1350", "720x1280")
BACKGROUND_LABELS = {
    "Θολό φόντο": "blur",
    "Λευκό φόντο": "white",
    "Μαύρο φόντο": "black",
    "Fit and Move": "fit_and_move",
}
TRANSITION_LABELS = {
    "None": "none", "Fade": "fade", "Fade to Black": "fadeblack",
    "Fade to White": "fadewhite", "Wipe Left": "wipeleft",
    "Wipe Right": "wiperight", "Smooth Left": "smoothleft",
    "Smooth Right": "smoothright", "Random": "random",
}


class WelcomeMixin:
    """Show startup choices and guide new projects without replacing the app UI."""

    def open_recent_projects(self):
        """Reopen the startup project browser after the user saves the active work."""
        if self.is_modified:
            messagebox.showinfo(
                "Save project first",
                "Αποθήκευσε πρώτα το τρέχον project (Ctrl+S) και μετά άνοιξε τα πρόσφατα projects.")
            return
        return self.show_welcome_screen()

    def show_welcome_screen(self):
        if getattr(self, "_welcome_dialog", None) is not None:
            try:
                if self._welcome_dialog.winfo_exists():
                    self._welcome_dialog.lift()
                    return self._welcome_dialog
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self.root)
        self._welcome_dialog = dialog
        dialog.title("Καλώς ήρθες — Slideshow Video Creator Pro")
        dialog.geometry("1180x800")
        dialog.minsize(920, 640)
        dialog.resizable(True, True)
        if not getattr(self, "_root_hidden_until_welcome", False):
            dialog.transient(self.root)
        else:
            try:
                dialog.attributes("-topmost", True)
            except tk.TclError:
                pass
        dialog.grab_set()

        modern = self.settings.get("ui_theme", "modern") == "modern"
        window_bg = "#202127" if modern else "SystemButtonFace"
        card_bg = "#292b31" if modern else "#f2f2f2"
        text_fg = "#f2f2f2" if modern else "#202020"
        muted_fg = "#b8bbc2" if modern else "#555555"
        accent = "#d6b86a" if modern else "#3b6ea8"
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        body.rowconfigure(1, weight=1)
        body.columnconfigure(0, weight=1)

        header = ttk.Frame(body)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Slideshow Video Creator Pro",
                  font=("Calibri", 21, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Τα 30 πιο πρόσφατα projects",
                  font=("Calibri", 11), foreground=muted_fg).grid(
            row=1, column=0, sticky="w", pady=(2, 0))
        search_var = tk.StringVar()
        ttk.Label(header, text="Αναζήτηση όλων των projects:", foreground=muted_fg).grid(
            row=0, column=1, sticky="e", padx=(12, 0))
        search = ttk.Entry(header, textvariable=search_var, width=32)
        search.grid(row=1, column=1, sticky="e", padx=(12, 0))

        records = []
        for project_path in sorted(self.projects_dir.glob("*.json"),
                                   key=lambda path: path.stat().st_mtime, reverse=True):
            try:
                with open(project_path, "r", encoding="utf-8-sig") as stream:
                    data = json.load(stream)
            except Exception:
                data = {}
            media = data.get("media_files", data.get("media", [])) if isinstance(data, dict) else []
            candidates = []
            for item in media if isinstance(media, list) else []:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                candidate = str(item[1])
                if Path(candidate).is_file():
                    candidates.append((str(item[0]).lower(), candidate))
            preferred = next((item for item in candidates if item[0] == "video"),
                             candidates[0] if candidates else ("", ""))
            records.append({
                "path": project_path,
                "name": str(data.get("name") or project_path.stem),
                "media_path": preferred[1],
                "media_type": preferred[0],
            })
        recent_records = records[:30]

        content = ttk.Frame(body)
        content.grid(row=1, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        cards_canvas = tk.Canvas(content, bg=window_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=cards_canvas.yview)
        cards_canvas.configure(yscrollcommand=scrollbar.set)
        cards_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        cards_frame = ttk.Frame(cards_canvas)
        cards_window = cards_canvas.create_window((0, 0), window=cards_frame, anchor="nw")
        cards_frame.bind("<Configure>", lambda _e: cards_canvas.configure(
            scrollregion=cards_canvas.bbox("all")))
        cards_canvas.bind("<Configure>", lambda e: cards_canvas.itemconfigure(
            cards_window, width=e.width))
        status = ttk.Label(body, text="", foreground=muted_fg)
        status.grid(row=2, column=0, sticky="w", pady=(5, 0))
        ttk.Label(body, text=f"Φάκελος projects: {self.projects_dir}",
                  foreground=muted_fg, font=("Calibri", 8)).grid(
            row=3, column=0, sticky="w", pady=(2, 0))

        selected = {"path": recent_records[0]["path"] if recent_records else None}
        card_widgets = {}
        thumbnail_cache = {}
        thumbnail_refs = {}
        thumbnail_labels = {}
        thumbnail_pending = set()
        thumbnail_failed = set()
        welcome_state = {"closed": False}

        def choose(record):
            selected["path"] = record["path"]
            for path, frame in card_widgets.items():
                frame.configure(highlightbackground=(accent if path == selected["path"]
                                                     else ("#41434a" if modern else "#b8b8b8")),
                                highlightthickness=3 if path == selected["path"] else 1)
            status.config(text=f"Επιλεγμένο: {record['name']}")

        def open_selected(_event=None):
            project_path = selected.get("path")
            if project_path is None:
                open_project_browser()
                return
            self.load_project(project_path=project_path, on_loaded=close)

        def load_project_thumbnail(record):
            if record["media_type"] == "video":
                image = self._video_first_frame(record["media_path"])
            else:
                image = Image.open(record["media_path"])
                image.load()
            image = image.convert("RGB")
            target_w, target_h = 320, 180
            scale = max(target_w / image.width, target_h / image.height)
            image = image.resize((round(image.width * scale), round(image.height * scale)),
                                 Image.Resampling.LANCZOS)
            left = max(0, (image.width - target_w) // 2)
            top = max(0, (image.height - target_h) // 2)
            return image.crop((left, top, left + target_w, top + target_h))

        def set_thumbnail(project_path, image):
            thumbnail_pending.discard(project_path)
            if welcome_state["closed"]:
                return
            if image is None:
                thumbnail_failed.add(project_path)
                return
            photo = ImageTk.PhotoImage(image)
            thumbnail_cache[project_path] = photo
            thumbnail_refs[project_path] = photo
            label = thumbnail_labels.get(project_path)
            if label is not None:
                try:
                    if label.winfo_exists():
                        label.configure(image=photo, text="", width=0, height=0)
                        label.image_ref = photo
                except tk.TclError:
                    pass

        def request_thumbnails(project_list):
            todo = []
            for record in project_list:
                project_path = record["path"]
                if (record["media_path"] and project_path not in thumbnail_cache and
                        project_path not in thumbnail_pending and
                        project_path not in thumbnail_failed):
                    thumbnail_pending.add(project_path)
                    todo.append(record)
            if not todo:
                return

            def worker():
                for record in todo:
                    if welcome_state["closed"]:
                        return
                    try:
                        image = load_project_thumbnail(record)
                    except Exception:
                        image = None
                    self._post_ui(set_thumbnail, record["path"], image)

            threading.Thread(target=worker, daemon=True).start()

        def make_card(record, index, columns):
            row, column = divmod(index, columns)
            frame = tk.Frame(cards_frame, bg=card_bg, highlightthickness=1,
                             highlightbackground=(accent if record["path"] == selected["path"]
                                                  else ("#41434a" if modern else "#b8b8b8")))
            frame.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
            cards_frame.columnconfigure(column, weight=1, uniform="recent-projects")
            image = thumbnail_cache.get(record["path"])
            if image is not None:
                thumb = tk.Label(frame, image=image, bg=card_bg)
                thumb.image_ref = image
            else:
                thumb = tk.Label(frame, text="▣", bg=card_bg, fg=muted_fg,
                                 width=40, height=9, font=("Segoe UI", 25))
            thumb.pack(fill="both", padx=6, pady=(6, 2))
            title = tk.Label(frame, text=record["name"], bg=card_bg, fg=text_fg,
                             anchor="w", justify="left", wraplength=310,
                             font=("Segoe UI", 10, "bold"))
            title.pack(fill="x", padx=8, pady=(3, 8))
            card_widgets[record["path"]] = frame
            thumbnail_labels[record["path"]] = thumb
            for widget in (frame, thumb, title):
                widget.bind("<Button-1>", lambda _e, item=record: choose(item))
                widget.bind("<Double-Button-1>", open_selected)
            if image:
                thumbnail_refs[record["path"]] = image

        def refresh_cards(*_):
            for widget in cards_frame.winfo_children():
                widget.destroy()
            card_widgets.clear()
            thumbnail_labels.clear()
            query = search_var.get().strip().casefold()
            visible = ([record for record in records
                        if query in record["name"].casefold() or
                        query in record["path"].stem.casefold()]
                       if query else recent_records)
            width = max(1, cards_canvas.winfo_width())
            columns = max(1, min(4, width // 340))
            for index, record in enumerate(visible):
                make_card(record, index, columns)
            if selected.get("path") not in {record["path"] for record in visible}:
                selected["path"] = visible[0]["path"] if visible else None
            request_thumbnails(visible[:30])
            if not records:
                status.config(text="Δεν υπάρχουν αποθηκευμένα projects ακόμη.")
            elif not visible:
                status.config(text="Δεν βρέθηκαν projects με αυτό το όνομα.")
            else:
                selected_record = next((record for record in visible
                                        if record["path"] == selected.get("path")), None)
                status.config(text=(f"Επιλεγμένο: {selected_record['name']}" if selected_record
                                   else f"Βρέθηκαν {len(visible)} project(s). Διάλεξε ένα για άνοιγμα."))

        search_state = {"job": None}

        def schedule_search(*_):
            if search_state["job"]:
                try:
                    dialog.after_cancel(search_state["job"])
                except tk.TclError:
                    pass
            search_state["job"] = dialog.after(180, refresh_cards)

        search_var.trace_add("write", schedule_search)
        cards_canvas.bind("<Configure>", refresh_cards, add="+")
        refresh_cards()

        def close():
            welcome_state["closed"] = True
            try:
                if dialog.grab_current() == dialog:
                    dialog.grab_release()
            except tk.TclError:
                pass
            if getattr(self, "_welcome_dialog", None) is dialog:
                self._welcome_dialog = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass
            if getattr(self, "_root_hidden_until_welcome", False):
                self._root_hidden_until_welcome = False
                try:
                    self.root.deiconify()
                    self.root.lift()
                except tk.TclError:
                    pass

        def restore_welcome_grab(_event=None):
            try:
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.lift()
            except tk.TclError:
                pass

        def open_project_browser():
            load_dialog = self.load_project(on_loaded=close)
            if load_dialog is not None:
                load_dialog.bind("<Destroy>", restore_welcome_grab, add="+")

        def open_wizard():
            wizard = self.open_new_project_wizard(on_created=close)
            if wizard is not None:
                wizard.bind("<Destroy>", restore_welcome_grab, add="+")

        footer = ttk.Frame(body)
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(footer, text="Open Project", command=open_selected).pack(side="right", padx=4)
        ttk.Button(footer, text="New Project Wizard",
                   command=open_wizard).pack(side="right", padx=4)
        ttk.Button(footer, text="New Project",
                   command=lambda: (self.new_project(), close())).pack(side="right", padx=4)

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        self.apply_ui_theme()
        dialog.update_idletasks()
        x = max(0, (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2)
        y = max(0, (dialog.winfo_screenheight() - dialog.winfo_height()) // 3)
        dialog.geometry(f"+{x}+{y}")
        return dialog

    def open_new_project_wizard(self, on_created=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Οδηγός νέου project")
        dialog.geometry("720x590")
        dialog.minsize(620, 520)
        dialog.resizable(True, True)
        owner = getattr(self, "_welcome_dialog", None) or self.root
        dialog.transient(owner)
        dialog.grab_set()

        name_var = tk.StringVar(value=self.name_var.get().strip())
        folder_var = tk.StringVar(value=(self.out_var.get().strip() or
                                         self.settings.get("output_folder", str(self.app_dir))))
        resolution_var = tk.StringVar(value=self.settings.get("resolution", "1080x1080"))
        current_template = TEMPLATES.get(self.project_template, TEMPLATES["legacy"])
        template_var = tk.StringVar(value=current_template)
        background_var = tk.StringVar(value=next(
            (label for label, value in BACKGROUND_LABELS.items()
             if value == self.settings.get("background_mode")), "Θολό φόντο"))
        duration_var = tk.IntVar(value=int(self.settings.get("slide_duration", 3)))
        cropping_var = tk.BooleanVar(value=bool(self.settings.get("cropping", False)))
        transition_var = tk.StringVar(value=next(
            (label for label, value in TRANSITION_LABELS.items()
             if value == self.settings.get("transition_effect")), "Fade"))
        transition_duration_var = tk.DoubleVar(
            value=float(self.settings.get("transition_duration", 0.7)))

        outer = ttk.Frame(dialog, padding=18)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 10))
        step_title = ttk.Label(header, text="Βήμα 1 από 3 — Στοιχεία project",
                               font=("Calibri", 14, "bold"))
        step_title.pack(anchor="w")
        ttk.Label(header, text="Ρύθμισε τα βασικά. Μπορείς να τα αλλάξεις αργότερα.",
                  foreground="#666").pack(anchor="w", pady=(3, 0))

        pages = [ttk.Frame(outer), ttk.Frame(outer), ttk.Frame(outer)]

        # --------------------------- step 1: project details
        p1 = pages[0]
        ttk.Label(p1, text="Όνομα project").pack(anchor="w", pady=(12, 3))
        name_entry = ttk.Entry(p1, textvariable=name_var, font=("Calibri", 12))
        name_entry.pack(fill="x")
        ttk.Label(p1, text="Φάκελος εξόδου").pack(anchor="w", pady=(16, 3))
        folder_row = ttk.Frame(p1)
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=folder_var).pack(side="left", fill="x", expand=True)

        def browse_folder():
            path = filedialog.askdirectory(parent=dialog, initialdir=folder_var.get() or None)
            if path:
                folder_var.set(path)

        ttk.Button(folder_row, text="Αναζήτηση…", command=browse_folder).pack(side="left", padx=(6, 0))
        ttk.Label(p1, text="Το project παραμένει επεξεργάσιμο· το export γίνεται από το κύριο παράθυρο.",
                  foreground="#666", wraplength=610).pack(anchor="w", pady=(12, 0))

        # --------------------------- step 2: format and design
        p2 = pages[1]
        ttk.Label(p2, text="Μορφή / ανάλυση βίντεο").pack(anchor="w", pady=(12, 3))
        ttk.Combobox(p2, textvariable=resolution_var, values=RESOLUTIONS,
                     state="readonly").pack(fill="x")
        ttk.Label(p2, text="Προεπιλεγμένο template project").pack(anchor="w", pady=(14, 3))
        ttk.Combobox(p2, textvariable=template_var, values=list(TEMPLATES.values()),
                     state="readonly").pack(fill="x")
        ttk.Label(p2, text="Τα slides με «Use Project Default» κληρονομούν αυτό το template· "
                         "κάθε slide μπορεί να έχει δικό του override.",
                  foreground="#666", wraplength=610).pack(anchor="w", pady=(4, 8))
        ttk.Label(p2, text="Λειτουργία φόντου (για το κλασικό template)").pack(
            anchor="w", pady=(4, 3))
        ttk.Combobox(p2, textvariable=background_var, values=list(BACKGROUND_LABELS),
                     state="readonly").pack(fill="x")
        ttk.Checkbutton(p2, text="Γέμισμα κάδρου με crop στις άκρες της εικόνας",
                        variable=cropping_var).pack(anchor="w", pady=(10, 0))

        # --------------------------- step 3: pacing and transitions
        p3 = pages[2]
        ttk.Label(p3, text="Προεπιλεγμένη διάρκεια φωτογραφίας (δευτερόλεπτα)").pack(
            anchor="w", pady=(12, 3))
        ttk.Spinbox(p3, from_=1, to=30, textvariable=duration_var, width=8).pack(anchor="w")
        ttk.Label(p3, text="Προεπιλεγμένη μετάβαση μεταξύ slides").pack(anchor="w", pady=(15, 3))
        ttk.Combobox(p3, textvariable=transition_var, values=list(TRANSITION_LABELS),
                     state="readonly").pack(fill="x")
        tr_row = ttk.Frame(p3)
        tr_row.pack(fill="x", pady=(12, 0))
        ttk.Label(tr_row, text="Διάρκεια μετάβασης (δευτερόλεπτα)").pack(side="left")
        ttk.Spinbox(tr_row, from_=0.2, to=2.0, increment=0.1,
                    textvariable=transition_duration_var, width=8).pack(side="left", padx=10)
        ttk.Label(p3, text="Μπορείς αργότερα να ορίσεις ξεχωριστή διάρκεια και μετάβαση ανά slide.",
                  foreground="#666").pack(anchor="w", pady=(16, 0))

        warning = ttk.Label(outer, text="", foreground="#b3261e", wraplength=620)
        warning.pack(fill="x", pady=(4, 0))
        footer = ttk.Frame(outer)
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        back_btn = ttk.Button(footer, text="← Πίσω")
        next_btn = ttk.Button(footer, text="Επόμενο →")
        create_btn = ttk.Button(footer, text="Δημιουργία project")
        cancel_btn = ttk.Button(footer, text="Ακύρωση", command=dialog.destroy)
        cancel_btn.pack(side="right", padx=(6, 0))
        create_btn.pack(side="right")
        next_btn.pack(side="right", padx=6)
        back_btn.pack(side="left")
        state = {"step": 0}

        def show_step(index):
            state["step"] = max(0, min(2, index))
            for page in pages:
                page.pack_forget()
            pages[state["step"]].pack(fill="both", expand=True)
            labels = ("Βήμα 1 από 3 — Στοιχεία project", "Βήμα 2 από 3 — Μορφή και εμφάνιση",
                      "Βήμα 3 από 3 — Ρυθμός και μεταβάσεις")
            step_title.config(text=labels[state["step"]])
            back_btn.config(state="normal" if state["step"] > 0 else "disabled")
            next_btn.pack_forget()
            create_btn.pack_forget()
            if state["step"] < 2:
                next_btn.pack(side="right", padx=6)
            else:
                create_btn.pack(side="right")
            warning.config(text="")

        def finish():
            name = name_var.get().strip()
            folder = folder_var.get().strip()
            if not name:
                warning.config(text="Γράψε ένα όνομα για το project.")
                name_entry.focus_set()
                return
            if not folder or not Path(folder).is_dir():
                warning.config(text="Διάλεξε έναν υπαρκτό φάκελο εξόδου.")
                return
            transition = TRANSITION_LABELS.get(transition_var.get(), "fade")
            try:
                duration = max(0.2, min(2.0, float(transition_duration_var.get())))
                slide_duration = max(1, min(30, int(duration_var.get())))
            except (tk.TclError, ValueError, TypeError):
                warning.config(text="Έλεγξε τις τιμές διάρκειας και δοκίμασε ξανά.")
                return

            self.new_project()
            self.name_var.set(name)
            self.out_var.set(folder)
            self.project_template = next(
                (key for key, label in TEMPLATES.items() if label == template_var.get()), "legacy")
            self._remember_caption_template(self.project_template)
            self.settings.update({
                "output_folder": folder,
                "resolution": resolution_var.get(),
                "background_mode": BACKGROUND_LABELS.get(background_var.get(), "blur"),
                "cropping": bool(cropping_var.get()),
                "slide_duration": slide_duration,
                "transition_effect": transition,
                "transition_duration": duration,
                "random_transitions": self.settings.get("random_transitions", []),
            })
            self.project_settings = self._capture_project_settings()
            self._active_project_settings = bool(self.project_settings)
            self.save_settings()
            self.is_modified = True
            self.update_media_display()
            self._schedule_preview()
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            if on_created:
                on_created()

        back_btn.config(command=lambda: show_step(state["step"] - 1))
        next_btn.config(command=lambda: show_step(state["step"] + 1))
        create_btn.config(command=finish)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda _e: (dialog.destroy(), "break")[1])
        show_step(0)
        name_entry.focus_set()
        return dialog
