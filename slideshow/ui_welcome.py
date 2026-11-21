"""Profile-aware welcome screen and the project setup dialogs."""

import json
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .deps import Image, ImageTk
from .profiles import initials
from .slide_design import TEMPLATES
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import (ScrollFrame, avatar_image, fit_cover, flat_button, format_duration,
                         hero_image, human_date, placeholder_cover, primary_button,
                         resolution_for_aspect, rounded_image, aspect_label)

RESOLUTIONS = ("1080x1080", "1920x1080", "1080x1920", "1080x1350", "720x1280")
ASPECT_CHOICES = (("9:16", "Κάθετο", "1080x1920"), ("4:5", "Portrait", "1080x1350"),
                  ("1:1", "Τετράγωνο", "1080x1080"), ("16:9", "Οριζόντιο", "1920x1080"))
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
    """Profile-aware welcome screen and the project setup dialogs."""

    def open_recent_projects(self):
        return self.return_to_welcome()

    # ------------------------------------------------------------ helpers
    def _welcome_project_records(self, limit=30):
        records = []
        try:
            files = sorted(self.projects_dir.glob("*.json"),
                           key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError:
            return []
        for project_path in files[:limit]:
            try:
                with open(project_path, "r", encoding="utf-8-sig") as stream:
                    data = json.load(stream)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            media = data.get("media_files", data.get("media", []))
            media = media if isinstance(media, list) else []
            cover_path, cover_kind = "", ""
            for item in media:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    candidate = str(item[1])
                    if Path(candidate).is_file():
                        cover_path, cover_kind = candidate, str(item[0]).lower()
                        break
            project_settings = data.get("project_settings")
            project_settings = project_settings if isinstance(project_settings, dict) else {}
            resolution = project_settings.get("resolution") or self.settings.get(
                "resolution", "1080x1080")
            try:
                default_slide = max(0.2, float(project_settings.get(
                    "slide_duration", self.settings.get("slide_duration", 3))))
            except (TypeError, ValueError):
                default_slide = 3.0
            total_seconds = 0.0
            for item in media:
                if not isinstance(item, (list, tuple)) or len(item) < 3:
                    continue
                try:
                    edit = item[2] if isinstance(item[2], dict) else {}
                    presentation = edit.get("presentation", {})
                    override = (presentation.get("duration")
                                if isinstance(presentation, dict) else None)
                    total_seconds += float(override) if override else default_slide
                except (TypeError, ValueError, IndexError):
                    total_seconds += default_slide
            try:
                modified = project_path.stat().st_mtime
            except OSError:
                modified = 0
            records.append({
                "path": project_path,
                "name": str(data.get("name") or project_path.stem or "Χωρίς όνομα"),
                "media_path": cover_path,
                "media_type": cover_kind,
                "count": len(media),
                "aspect": aspect_label(resolution),
                "duration": max(1, total_seconds),
                "modified": modified,
            })
        return records

    def _finish_welcome(self):
        state = getattr(self, "_welcome_state", None)
        if state:
            state["closed"] = True
        dialog = getattr(self, "_welcome_dialog", None)
        self._welcome_dialog = None
        self._welcome_state = None
        if dialog is not None:
            try:
                if dialog.grab_current() == dialog:
                    dialog.grab_release()
            except tk.TclError:
                pass
            try:
                dialog.destroy()
            except tk.TclError:
                pass

    def _enter_editor(self):
        self._root_hidden_until_welcome = False
        try:
            self.root.deiconify()
            self.root.state("zoomed")
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass
        self._refresh_header()
        self._refresh_stage()
        self._update_saved_status()
        if hasattr(self, "inspector_content"):
            self._render_inspector()

    def _open_project_from_welcome(self, path):
        path = Path(path)
        if not path.is_file():
            messagebox.showerror("Άνοιγμα project",
                                 "Το project δεν βρίσκεται πια στον φάκελο του προφίλ.")
            return False
        self._finish_welcome()
        self._root_hidden_until_welcome = False
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        if not self.load_project_file(path):
            try:
                self.root.withdraw()
            except tk.TclError:
                pass
            self.show_welcome_screen()
            return False
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass
        self._enter_editor()
        return True

    def _new_project_ready(self):
        self._finish_welcome()
        self._enter_editor()
        self.update_media_display()
        self._schedule_preview(150)
        self.render_storyboard()
        self._refresh_inspector_after_media()
        self._refresh_export_estimate()

    def _reopen_welcome(self):
        self._finish_welcome()
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        self.root.after(25, self.show_welcome_screen)

    # ---------------------------------------------------------- main screen
    def show_welcome_screen(self):
        existing = getattr(self, "_welcome_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self.root)
        dialog.title("Καλώς ήρθες — Slideshow Video Creator Pro")
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        width = min(1280, max(980, screen_w - 80))
        height = min(840, max(650, screen_h - 100))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(980, width), min(640, height))
        dialog.configure(bg=P["background"])
        self._welcome_dialog = dialog
        state = {
            "closed": False,
            "thumb_token": 0,
            "pil_cache": {},
            "photo_refs": {},
        }
        self._welcome_state = state
        try:
            dialog.attributes("-topmost", True)
            dialog.after(900, lambda: self._drop_topmost(dialog))
        except tk.TclError:
            pass

        body = tk.Frame(dialog, bg=P["background"], padx=26, pady=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        self._build_welcome_header(body)
        content = tk.Frame(body, bg=P["background"])
        content.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
        content.columnconfigure(0, minsize=252)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        profiles_panel = tk.Frame(content, bg=P["panel"], highlightthickness=1,
                                  highlightbackground=P["border"])
        profiles_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        right = tk.Frame(content, bg=P["background"])
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)

        records = self._welcome_project_records()
        last_path = self.get_last_project()
        if last_path is None and records:
            last_path = records[0]["path"]
        last_record = next((record for record in records
                            if record["path"] == Path(last_path)), None) if last_path else None
        if last_record is None and records:
            last_record = records[0]

        self._build_profile_panel(profiles_panel)
        self._build_hero(right, records, last_record)
        self._build_recent_projects(right, records)

        footer = tk.Frame(body, bg=P["background"])
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        tk.Label(footer, text=f"Χώρος εργασίας: {self.projects_dir}", bg=P["background"],
                 fg=P["border"], font=("Segoe UI", 8)).pack(side="left")
        tk.Label(footer, text="Τα δεδομένα μένουν στον υπολογιστή σου.",
                 bg=P["background"], fg=P["border"], font=("Segoe UI", 8)).pack(
            side="right")

        def close_app():
            self.on_closing()
            try:
                if dialog.winfo_exists() and self.root.winfo_exists():
                    dialog.lift()
            except tk.TclError:
                pass

        dialog.protocol("WM_DELETE_WINDOW", close_app)
        dialog.bind("<Escape>", lambda _e: (close_app(), "break")[1])
        dialog.update_idletasks()
        dialog.lift()
        dialog.focus_force()
        return dialog

    def _drop_topmost(self, dialog):
        try:
            if dialog.winfo_exists():
                dialog.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _build_welcome_header(self, parent):
        header = tk.Frame(parent, bg=P["background"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        mark = avatar_image("SV", P["accent"], 36, P["background"])
        photo = ImageTk.PhotoImage(mark)
        logo = tk.Label(header, image=photo, bg=P["background"])
        logo.image = photo
        logo.pack(side="left")
        brand = tk.Frame(header, bg=P["background"])
        brand.pack(side="left", padx=(10, 0))
        tk.Label(brand, text="SLIDESHOW", bg=P["background"], fg=P["accent"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(brand, text="Video Creator Pro", bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(header, text="Τοπικά projects · Ένα περιβάλλον για κάθε προφίλ",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 9)).pack(
            side="right", pady=(8, 0))

    def _build_profile_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        header = tk.Frame(parent, bg=P["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        tk.Label(header, text="ΠΡΟΦΙΛ", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        count = len(self.profiles_data.get("profiles", []))
        tk.Label(header, text=str(count), bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8)).pack(side="right")

        scroller = ScrollFrame(parent, background=P["panel"])
        scroller.grid(row=1, column=0, sticky="nsew", padx=(8, 4))
        body = scroller.body
        for profile in self.profiles_data.get("profiles", []):
            self._make_profile_row(body, profile)

        footer = tk.Frame(parent, bg=P["panel"])
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 12))
        primary_button(footer, "+  Νέο προφίλ", self._new_profile_from_welcome,
                       font=("Segoe UI", 9, "bold")).pack(fill="x", pady=(0, 4))
        flat_button(footer, "Επεξεργασία ενεργού προφίλ",
                    lambda: self.open_edit_profile_dialog(
                        self.active_profile_data, on_saved=lambda _p: self._reopen_welcome()),
                    background=P["panel"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8)).pack(fill="x")
        tk.Label(parent, text="Κάθε προφίλ έχει δικά του projects,\nρυθμίσεις και μουσική.",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 7),
                 justify="left").grid(row=3, column=0, sticky="w", padx=14, pady=(0, 12))

    def _make_profile_row(self, parent, profile):
        active = profile.get("id") == self.active_profile_id
        row_bg = P["accent_faint"] if active else P["panel"]
        row = tk.Frame(parent, bg=row_bg, cursor="hand2", padx=7, pady=6,
                       highlightthickness=1,
                       highlightbackground=(P["accent"] if active else row_bg))
        row.pack(fill="x", padx=2, pady=2)
        image = avatar_image(initials(profile.get("name")), profile.get("color", P["accent"]),
                             38, row_bg)
        photo = ImageTk.PhotoImage(image)
        avatar = tk.Label(row, image=photo, bg=row_bg, bd=0)
        avatar.image = photo
        avatar.pack(side="left")
        text = tk.Frame(row, bg=row_bg)
        text.pack(side="left", fill="x", expand=True, padx=(8, 0))
        tk.Label(text, text=profile.get("name", "Προφίλ"), bg=row_bg, fg=P["text"],
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        tk.Label(text, text=profile.get("role", "") or "Προφίλ", bg=row_bg,
                 fg=P["muted"], font=("Segoe UI", 7), anchor="w").pack(fill="x")
        if active:
            tk.Label(row, text="✓", bg=row_bg, fg=P["accent"],
                     font=("Segoe UI", 11, "bold")).pack(side="right")

        def choose(_event=None):
            if active:
                return
            self._finish_welcome()
            self.switch_profile(profile["id"])
            try:
                self.root.withdraw()
            except tk.TclError:
                pass
            self.root.after(20, self.show_welcome_screen)

        for widget in [row, avatar, text, *text.winfo_children()]:
            widget.bind("<Button-1>", choose)
            widget.bind("<Double-Button-1>", lambda _e, p=profile:
                        self.open_edit_profile_dialog(p, on_saved=lambda _p: self._reopen_welcome()))

    def _new_profile_from_welcome(self):
        return self.open_new_profile_dialog(
            on_created=lambda _profile: self._reopen_welcome())

    def _build_hero(self, parent, records, last_record):
        hero = tk.Frame(parent, bg=P["panel"], height=256, highlightthickness=1,
                        highlightbackground=P["border"])
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_propagate(False)
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=0)

        content = tk.Frame(hero, bg=P["panel"], padx=24, pady=18)
        content.grid(row=0, column=0, sticky="nsew")
        tk.Label(content, text="SLIDESHOW · VIDEO CREATOR PRO", bg=P["panel"],
                 fg=P["accent"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        name = self.active_profile_data.get("name", "").split()
        greeting = name[0] if name else "καλώς ήρθες"
        greeting_size = 22 if len(greeting) <= 18 else 20 if len(greeting) <= 26 else 18
        tk.Label(content, text=f"Καλώς ήρθες, {greeting}", bg=P["panel"], fg=P["text"],
                 font=("Segoe UI", greeting_size, "bold"), wraplength=470,
                 justify="left", anchor="w").pack(anchor="w", pady=(4, 2))
        role = self.active_profile_data.get("role", "")
        description = (f"{role} · " if role else "") + \
                      "Φτιάξε εντυπωσιακά βίντεο από τις φωτογραφίες σου."
        tk.Label(content, text=description, bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 9), wraplength=470, justify="left",
                 anchor="w").pack(anchor="w")
        last_text = (f"Τελευταίο project: {last_record['name']}" if last_record else
                     "Ξεκίνα το πρώτο σου project σε αυτό το προφίλ.")
        tk.Label(content, text=last_text, bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8), wraplength=470, justify="left",
                 anchor="w").pack(anchor="w", pady=(10, 0))

        buttons = tk.Frame(content, bg=P["panel"])
        buttons.pack(anchor="w", pady=(14, 0))
        if last_record:
            continue_text = "Συνέχεια στο project"
            continue_command = lambda: self._open_project_from_welcome(last_record["path"])
        else:
            continue_text = "Δημιουργία πρώτου project"
            continue_command = self._quick_new_project_from_welcome
        primary_button(buttons, continue_text, continue_command,
                       font=("Segoe UI", 9, "bold"), padx=16, pady=8).pack(side="left")
        flat_button(buttons, "Νέο project", self._quick_new_project_from_welcome,
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"], font=("Segoe UI", 9),
                    padx=16, pady=8).pack(side="left", padx=(8, 0))
        if records:
            flat_button(buttons, "Όλα τα projects", self._open_project_browser,
                        background=P["panel"], foreground=P["muted"],
                        active_background=P["selected"], font=("Segoe UI", 8),
                        padx=6, pady=8).pack(side="left", padx=(8, 0))

        photo_holder = tk.Frame(hero, bg=P["panel"], width=340, height=256)
        photo_holder.grid(row=0, column=1, sticky="nsew")
        photo_holder.pack_propagate(False)
        photo_label = tk.Label(photo_holder, bg=P["panel"])
        photo_label.pack(fill="both", expand=True)
        self._welcome_hero_label = photo_label
        self._queue_hero_image(photo_label, last_record)

    def _queue_hero_image(self, label, record):
        state = getattr(self, "_welcome_state", None)
        if state is None:
            return
        path = record["media_path"] if record else ""

        def apply(image):
            if state.get("closed"):
                return
            try:
                if not label.winfo_exists():
                    return
                photo = ImageTk.PhotoImage(image)
                state["photo_refs"]["hero"] = photo
                label.configure(image=photo, width=0, height=0)
                label.image = photo
            except tk.TclError:
                pass

        def worker():
            image = None
            if path and Path(path).is_file():
                try:
                    if record["media_type"] == "video":
                        image = self._video_first_frame(path)
                    else:
                        image = self.open_thumbnail_image(path, 1200)
                        image.load()
                except Exception:
                    image = None
            try:
                composed = hero_image(image, 340, 256, P["panel"], fade=0.6)
            except Exception:
                composed = placeholder_cover(340, 256, initials(
                    self.active_profile_data.get("name")), P["accent"])
            self._post_ui(apply, composed)

        threading.Thread(target=worker, daemon=True).start()

    def _build_recent_projects(self, parent, records):
        header = tk.Frame(parent, bg=P["background"])
        header.grid(row=1, column=0, sticky="ew", pady=(18, 6))
        tk.Label(header, text="Πρόσφατα project", bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 13, "bold")).pack(side="left")
        self._welcome_recent_count = tk.StringVar(value=f"{len(records)}")
        tk.Label(header, textvariable=self._welcome_recent_count, bg=P["background"],
                 fg=P["muted"], font=("Segoe UI", 9)).pack(side="left", padx=(7, 0))

        search_var = tk.StringVar()
        search = ttk.Entry(header, textvariable=search_var, width=28,
                           style="Field.TEntry")
        search.pack(side="right")
        tk.Label(header, text="Αναζήτηση", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))
        search.focus_set()

        scroller = ScrollFrame(parent, background=P["background"])
        scroller.grid(row=2, column=0, sticky="nsew")
        grid = scroller.body
        state = self._welcome_state
        state["grid"] = grid
        state["records"] = records
        state["search_var"] = search_var
        state["layout_job"] = None
        state["reflow_job"] = None
        state["card_widgets"] = {}

        def schedule_reflow(*_args):
            job = state.get("layout_job")
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            state["layout_job"] = self.root.after(160, reflow)

        def reflow():
            state["layout_job"] = None
            if state.get("closed"):
                return
            query = search_var.get().strip().casefold()
            visible = [record for record in records
                       if not query or query in record["name"].casefold() or
                       query in record["path"].stem.casefold()]
            self._welcome_recent_count.set(str(len(visible)))
            for child in grid.winfo_children():
                child.destroy()
            state["card_widgets"] = {}
            state["thumb_token"] = state.get("thumb_token", 0) + 1
            width = scroller.canvas.winfo_width()
            columns = 3 if width >= 980 else 2 if width >= 620 else 1
            for column in range(3):
                grid.columnconfigure(column, weight=1 if column < columns else 0,
                                     uniform="recent" if column < columns else "")
            if not records:
                self._welcome_empty_state(
                    grid, "Δεν υπάρχει ακόμη project σε αυτό το προφίλ.",
                    "Δημιούργησε το πρώτο σου project", self._quick_new_project_from_welcome)
                return
            if not visible:
                self._welcome_empty_state(
                    grid, "Δεν βρέθηκαν projects με αυτό το όνομα.",
                    "Καθάρισε την αναζήτηση", lambda: search_var.set(""))
                return
            card_width = max(210, (max(width, 600) - 12 * (columns + 1)) // columns)
            cover_height = 148
            todo = []
            for position, record in enumerate(visible):
                row, column = divmod(position, columns)
                card = self._make_recent_card(
                    grid, record, row, column, card_width, cover_height)
                state["card_widgets"][record["path"]] = card
                todo.append((record, card))
            self._queue_card_thumbs(todo[:15], max(120, card_width - 12), cover_height)

        def queue_resize(_event=None):
            job = state.get("reflow_job")
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            state["reflow_job"] = self.root.after(180, reflow)

        search_var.trace_add("write", schedule_reflow)
        scroller.canvas.bind("<Configure>", queue_resize, add="+")
        reflow()

    def _welcome_empty_state(self, parent, text, action_label, command):
        box = tk.Frame(parent, bg=P["raised"], highlightthickness=1,
                       highlightbackground=P["border"], padx=24, pady=28)
        box.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=6, pady=6)
        tk.Label(box, text="▣", bg=P["raised"], fg=P["accent"],
                 font=("Segoe UI", 26)).pack()
        tk.Label(box, text=text, bg=P["raised"], fg=P["text"],
                 font=("Segoe UI", 11, "bold"), wraplength=420).pack(pady=(6, 2))
        tk.Label(box, text="Μπορείς να αλλάξεις προφίλ ή να ξεκινήσεις νέο project.",
                 bg=P["raised"], fg=P["muted"], font=("Segoe UI", 8)).pack()
        primary_button(box, action_label, command).pack(pady=(14, 0))

    def _make_recent_card(self, parent, record, row, column, width, cover_height):
        card = tk.Frame(parent, bg=P["raised"], highlightthickness=1,
                        highlightbackground=P["border"], cursor="hand2")
        card.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
        holder = tk.Frame(card, bg=P["stage"], height=cover_height)
        holder.pack(fill="x", padx=6, pady=(6, 4))
        holder.pack_propagate(False)
        cover = tk.Label(holder, bg=P["stage"], text="▣", fg=P["muted"],
                         font=("Segoe UI", 22))
        cover.pack(fill="both", expand=True)
        card._cover_label = cover
        card._cover_holder = holder
        name = tk.Label(card, text=record["name"], bg=P["raised"], fg=P["text"],
                        font=("Segoe UI", 10, "bold"), anchor="w",
                        wraplength=max(160, width - 24), justify="left")
        name.pack(fill="x", padx=9)
        meta = tk.Frame(card, bg=P["raised"])
        meta.pack(fill="x", padx=9, pady=(2, 5))
        tk.Label(meta, text=f"{record['aspect']} · {record['count']} σκηνές",
                 bg=P["raised"], fg=P["muted"], font=("Segoe UI", 8)).pack(side="left")
        tk.Label(meta, text=f"≈ {format_duration(record['duration'])}",
                 bg=P["raised"], fg=P["muted"], font=("Segoe UI", 8)).pack(
            side="right")
        date_label = tk.Label(card, text=human_date(record["modified"]), bg=P["raised"],
                              fg=P["muted"], font=("Segoe UI", 7))
        date_label.pack(anchor="w", padx=9, pady=(0, 8))
        for widget in (card, holder, cover, name, date_label, meta, *meta.winfo_children()):
            widget.bind("<Button-1>", lambda _e, path=record["path"]:
                        self._open_project_from_welcome(path))
            widget.bind("<Enter>", lambda _e, c=card: c.configure(
                highlightbackground=P["accent_faint"]))
            widget.bind("<Leave>", lambda _e, c=card: c.configure(
                highlightbackground=P["border"]))
        menu = tk.Menu(card, tearoff=0)
        menu.add_command(label="Άνοιγμα",
                         command=lambda path=record["path"]:
                         self._open_project_from_welcome(path))
        menu.add_command(label="Άνοιγμα φακέλου",
                         command=lambda path=record["path"]:
                         self._open_project_folder(path))
        for widget in (card, cover, name):
            widget.bind("<Button-3>", lambda e, m=menu: m.tk_popup(e.x_root, e.y_root))
        return card

    def _open_project_folder(self, path):
        import os
        try:
            os.startfile(str(Path(path).parent))
        except OSError:
            pass

    def _queue_card_thumbs(self, todo, width, height):
        state = getattr(self, "_welcome_state", None)
        if state is None or state.get("closed"):
            return
        token = state["thumb_token"]

        def apply(card, image, path):
            if state.get("closed") or token != state.get("thumb_token", 0):
                return
            try:
                if not card.winfo_exists():
                    return
                cover = getattr(card, "_cover_label", None)
                if cover is None:
                    return
                photo = ImageTk.PhotoImage(image)
                cover.configure(image=photo, text="", width=0, height=0)
                cover.image = photo
                state["photo_refs"][str(path)] = photo
            except tk.TclError:
                pass

        pending = []
        for record, card in todo:
            key = (str(record["path"]), width, height)
            cached = state["pil_cache"].get(key)
            if cached is not None:
                apply(card, cached, record["path"])
            else:
                pending.append((record, card, key))

        if not pending:
            return

        def worker():
            for record, card, key in pending:
                if state.get("closed") or token != state.get("thumb_token", 0):
                    break
                image = None
                if record["media_path"] and Path(record["media_path"]).is_file():
                    try:
                        if record["media_type"] == "video":
                            image = self._video_first_frame(record["media_path"])
                        else:
                            image = self.open_thumbnail_image(record["media_path"], 800)
                            image.load()
                    except Exception:
                        image = None
                try:
                    if image is not None:
                        composed = rounded_image(image, (width, height), 9, P["raised"])
                    else:
                        composed = placeholder_cover(
                            width, height, record["name"][:2].upper(), P["accent"])
                except Exception:
                    composed = placeholder_cover(width, height, "SV", P["accent"])
                state["pil_cache"][key] = composed
                self._post_ui(apply, card, composed, record["path"])

        threading.Thread(target=worker, daemon=True).start()

    def _open_project_browser(self):
        def loaded():
            self._finish_welcome()
            self._enter_editor()

        return self.load_project(on_loaded=loaded)

    # ----------------------------------------------------- quick new project
    def _quick_new_project_from_welcome(self):
        return self.open_quick_new_project_dialog(on_created=self._new_project_ready)

    def open_quick_new_project_dialog(self, on_created=None):
        owner = getattr(self, "_welcome_dialog", None) or self.root
        dialog = tk.Toplevel(owner)
        dialog.title("Νέο project")
        dialog.configure(bg=P["background"])
        dialog.geometry("600x560")
        dialog.resizable(False, False)
        dialog.transient(owner)
        dialog.grab_set()

        body = tk.Frame(dialog, bg=P["background"], padx=24, pady=20)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="ΝΕΟ PROJECT", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(body, text="Ξεκίνα από μια ιδέα", bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", pady=(2, 2))
        tk.Label(body, text=f"Προφίλ: {self.active_profile_data.get('name', '')}",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 9)).pack(anchor="w")

        name_var = tk.StringVar()
        folder_var = tk.StringVar(value=(self.settings.get("output_folder") or
                                         str(self._default_output_folder())))
        aspect_var = tk.StringVar(value=aspect_label(self.settings.get("resolution")))

        tk.Label(body, text="Όνομα project", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(16, 4))
        name_entry = ttk.Entry(body, textvariable=name_var, style="Field.TEntry",
                               font=("Segoe UI", 11))
        name_entry.pack(fill="x")

        tk.Label(body, text="Κάδρο", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 4))
        aspects = tk.Frame(body, bg=P["background"])
        aspects.pack(fill="x")
        aspect_buttons = {}

        def choose_aspect(value):
            aspect_var.set(value)
            for key, button in aspect_buttons.items():
                button.configure(highlightbackground=(P["accent"] if key == value
                                                       else P["border"]),
                                 highlightthickness=2 if key == value else 1)

        for index, (value, label, _resolution) in enumerate(ASPECT_CHOICES):
            card = tk.Frame(aspects, bg=P["raised"], padx=12, pady=8,
                            highlightthickness=1, highlightbackground=P["border"],
                            cursor="hand2")
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=3, pady=3)
            aspects.columnconfigure(index % 2, weight=1)
            tk.Label(card, text=value, bg=P["raised"], fg=P["text"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w")
            tk.Label(card, text=label, bg=P["raised"], fg=P["muted"],
                     font=("Segoe UI", 8)).pack(anchor="w")
            for widget in (card, *card.winfo_children()):
                widget.bind("<Button-1>", lambda _e, v=value: choose_aspect(v))
            aspect_buttons[value] = card
        choose_aspect(aspect_var.get())

        tk.Label(body, text="Φάκελος εξόδου", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(14, 4))
        folder_row = tk.Frame(body, bg=P["background"])
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=folder_var, style="Field.TEntry").pack(
            side="left", fill="x", expand=True)

        def browse():
            folder = filedialog.askdirectory(parent=dialog,
                                             initialdir=folder_var.get() or None)
            if folder:
                folder_var.set(folder)

        flat_button(folder_row, "Αλλαγή", browse, background=P["raised"],
                    foreground=P["text"], active_background=P["selected"],
                    font=("Segoe UI", 8)).pack(side="left", padx=(6, 0))

        warning = tk.Label(body, text="", bg=P["background"], fg=P["danger"],
                           font=("Segoe UI", 9))
        warning.pack(anchor="w", pady=(8, 0))

        footer = tk.Frame(body, bg=P["background"])
        footer.pack(side="bottom", fill="x", pady=(10, 0))

        def close():
            try:
                if dialog.grab_current() == dialog:
                    dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        def advanced():
            close()
            self.open_new_project_wizard(on_created=on_created)

        def create():
            name = name_var.get().strip()
            folder = folder_var.get().strip()
            if not name:
                warning.config(text="Γράψε ένα όνομα για το project.")
                name_entry.focus_set()
                return
            if not folder or not Path(folder).is_dir():
                warning.config(text="Διάλεξε έναν υπαρκτό φάκελο εξόδου.")
                return
            self.new_project()
            self.name_var.set(name)
            self.out_var.set(folder)
            self.settings["output_folder"] = folder
            self.settings["resolution"] = resolution_for_aspect(aspect_var.get())
            self.save_settings()
            self.is_modified = True
            close()
            if on_created:
                on_created()

        flat_button(footer, "Περισσότερες ρυθμίσεις…", advanced,
                    background=P["background"], foreground=P["muted"],
                    active_background=P["selected"], font=("Segoe UI", 8)).pack(
            side="left")
        primary_button(footer, "Δημιουργία project", create,
                       font=("Segoe UI", 9, "bold")).pack(side="right")
        flat_button(footer, "Ακύρωση", close, background=P["raised"],
                    foreground=P["muted"], active_background=P["selected"],
                    font=("Segoe UI", 9)).pack(side="right", padx=(6, 0))

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        name_entry.focus_set()
        dialog.update_idletasks()
        try:
            x = owner.winfo_rootx() + max(0, (owner.winfo_width() - dialog.winfo_width()) // 2)
            y = owner.winfo_rooty() + max(0, (owner.winfo_height() - dialog.winfo_height()) // 3)
            dialog.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass
        return dialog

    # ------------------------------------------------------- advanced wizard
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
        template_names = list(self.template_registry())
        current_template = self._effective_project_template_name()
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

        p2 = pages[1]
        ttk.Label(p2, text="Μορφή / ανάλυση βίντεο").pack(anchor="w", pady=(12, 3))
        ttk.Combobox(p2, textvariable=resolution_var, values=RESOLUTIONS,
                     state="readonly").pack(fill="x")
        ttk.Label(p2, text="Προεπιλεγμένο template project").pack(anchor="w", pady=(14, 3))
        ttk.Combobox(p2, textvariable=template_var, values=template_names,
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
            chosen_template = template_var.get()
            if not self.set_project_template(chosen_template, mark_modified=False):
                self.project_template = next(
                    (key for key, label in TEMPLATES.items()
                     if label == chosen_template), "legacy")
                self.project_template_name = chosen_template
                self.project_template_override = True
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

