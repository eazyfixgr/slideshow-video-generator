"""One content manager for project video text and photo captions."""

import copy
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .deps import Image, ImageTk
from .slide_design import normalize_presentation


PHOTO_MODES = {
    "Ίδιο κείμενο σε όλες τις φωτογραφίες": "shared",
    "Ξεχωριστό κείμενο ανά φωτογραφία": "individual",
    "Ίδιο κείμενο σε επιλεγμένη ομάδα": "group",
}


class CaptionsMixin:
    """Edit video text and photo captions together, with an explicit photo mode."""

    def open_video_text(self):
        return self.open_text_captions_manager("video")

    def open_photo_captions(self):
        return self.open_text_captions_manager("photo")

    def open_text_window(self):
        """Keep the old command working, but route it to the unified manager."""
        return self.open_text_captions_manager("video")

    def _schedule_caption_preview(self, parent, canvas, item_index, m_type, global_text,
                                  status=None, edit_override=None):
        """Render one current caption preview off-thread; Tk image creation stays on Tk."""
        if item_index is None or not (0 <= item_index < len(self.media_files)):
            return
        job = getattr(canvas, "_caption_preview_job", None)
        if job:
            try:
                parent.after_cancel(job)
            except tk.TclError:
                pass
        canvas._caption_preview_token = getattr(canvas, "_caption_preview_token", 0) + 1
        token = canvas._caption_preview_token
        m_type, path, current_edit = self.media_files[item_index]
        edit = copy.deepcopy(edit_override if edit_override is not None else current_edit)
        width, height = map(int, self.settings["resolution"].split("x"))
        if status is not None:
            status.config(text="Ενημέρωση preview…")

        def render():
            canvas._caption_preview_job = None

            def worker():
                try:
                    if m_type == "image":
                        source = Image.open(path)
                    else:
                        start = float(edit.get("trim_start") or 0.0)
                        source = self._video_frame_at(path, start) if start > .005 else \
                                 self._video_first_frame(path)
                    source = self._apply_image_edit(source, edit, path, m_type=m_type)
                    frame = self._render_with_text(source, m_type, global_text, width, height,
                                                   edit=edit)
                    frame = self._apply_watermark_overlay(frame)
                    self._post_ui(show, frame, token)
                except Exception as exc:
                    error = str(exc)
                    if status is not None:
                        self._post_ui(status.config, text=f"Preview: {error}")

            threading.Thread(target=worker, daemon=True).start()

        def show(frame, result_token):
            if result_token != getattr(canvas, "_caption_preview_token", -1):
                return
            try:
                if not canvas.winfo_exists():
                    return
                cw, ch = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
                scale = min(cw / frame.width, ch / frame.height)
                size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
                ref = ImageTk.PhotoImage(frame.resize(size, Image.Resampling.LANCZOS))
                canvas.delete("all")
                canvas.create_image(cw // 2, ch // 2, image=ref)
                canvas.image_ref = ref
                if status is not None:
                    status.config(text="Preview updated")
            except tk.TclError:
                pass

        canvas._caption_preview_job = parent.after(300, render)

    def open_text_captions_manager(self, initial_tab="video"):
        existing = getattr(self, "_text_captions_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    notebook = getattr(existing, "_captions_notebook", None)
                    if notebook is not None:
                        notebook.select(1 if initial_tab == "photo" else 0)
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self.root)
        self._text_captions_dialog = dialog
        dialog.title("Text & Captions")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        dialog.geometry(f"{min(1280, max(900, int(sw * .88)))}x"
                        f"{min(820, max(620, int(sh * .88)))}")
        dialog.minsize(820, 580)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ttk.Frame(dialog, padding=10)
        outer.pack(fill="both", expand=True)
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)
        dialog._captions_notebook = notebook

        video_tab = ttk.Frame(notebook, padding=10)
        photo_tab = ttk.Frame(notebook, padding=10)
        notebook.add(video_tab, text="  Video Text  ")
        notebook.add(photo_tab, text="  Photo Captions  ")
        notebook.select(1 if initial_tab == "photo" else 0)

        # --------------------------- shared helpers
        def bind_text(widget, on_change=None):
            self._bind_text_shortcuts(widget)
            menu = tk.Menu(widget, tearoff=0)

            def text_action(action):
                self._do_text_shortcut(widget, action)
                if on_change and action in ("paste", "cut", "undo"):
                    on_change()

            for label, action in (("Copy", "copy"), ("Paste", "paste"),
                                  ("Cut", "cut"), ("Undo", "undo")):
                menu.add_command(label=label,
                                 command=lambda a=action: text_action(a))

            def popup(event):
                menu.tk_popup(event.x_root, event.y_root)
                return "break"
            widget.bind("<Button-3>", popup, add="+")
            if on_change:
                widget.bind("<KeyRelease>", lambda _e: on_change(), add="+")

        def replace_text(widget, value):
            widget.delete("1.0", tk.END)
            widget.insert("1.0", value or "")
            widget.edit_reset()

        def update_preview():
            self.is_modified = True
            self._schedule_preview(500)

        def quick_paste(widget, on_change):
            try:
                widget.insert(tk.INSERT, self.root.clipboard_get())
                on_change()
            except tk.TclError:
                pass

        # --------------------------- Video Text tab
        video_tab.columnconfigure(0, weight=1)
        video_tab.columnconfigure(1, weight=2)
        video_tab.rowconfigure(1, weight=1)
        video_header = ttk.Frame(video_tab)
        video_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        video_header.columnconfigure(0, weight=1)
        ttk.Label(video_header, text="Κοινό κείμενο για τα video slides",
                  font=("Calibri", 12, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(video_header, text="Quick Paste",
                   command=lambda: quick_paste(video_text, update_video_text)).grid(
            row=0, column=1, sticky="e")
        video_text = scrolledtext.ScrolledText(video_tab, height=12, wrap=tk.WORD,
                                               undo=True, font=("Calibri", 12))
        video_text.grid(row=1, column=0, sticky="nsew")
        video_text.insert("1.0", self.project_text_videos)
        video_text.edit_reset()
        bind_text(video_text, lambda: update_video_text())

        video_preview_box = ttk.LabelFrame(video_tab, text="Preview", padding=5)
        video_preview_box.grid(row=0, column=1, rowspan=4, sticky="nsew", padx=(10, 0))
        video_preview_box.columnconfigure(0, weight=1)
        video_preview_box.rowconfigure(0, weight=1)
        video_preview_box.rowconfigure(1, weight=1)
        video_canvas = tk.Canvas(video_preview_box, bg="black", width=300, height=230,
                                 highlightthickness=1, highlightbackground="#666")
        video_canvas.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        photo_canvas = tk.Canvas(video_preview_box, bg="black", width=300, height=230,
                                 highlightthickness=1, highlightbackground="#666")
        photo_canvas.grid(row=1, column=0, sticky="nsew")

        ai_row = ttk.LabelFrame(video_tab, text="AI instructions (optional)", padding=6)
        ai_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ai_row.columnconfigure(0, weight=1)
        instructions = scrolledtext.ScrolledText(ai_row, height=3, wrap=tk.WORD,
                                                 undo=True, font=("Calibri", 10))
        instructions.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        instructions.insert("1.0", self.project_ai_instructions)
        instructions.edit_reset()
        bind_text(instructions, lambda: update_video_text())

        def update_video_text(_event=None):
            video_value = video_text.get("1.0", "end-1c").strip()
            instructions_value = instructions.get("1.0", "end-1c").strip()
            if (video_value != self.project_text_videos or
                    instructions_value != self.project_ai_instructions):
                self.project_text_videos = video_value
                self.project_ai_instructions = instructions_value
                update_preview()
                schedule_global_previews()

        global_preview_job = {"id": None}

        def schedule_global_previews():
            if global_preview_job["id"]:
                try:
                    dialog.after_cancel(global_preview_job["id"])
                except tk.TclError:
                    pass
            global_preview_job["id"] = dialog.after(
                450, lambda: self._render_text_dialog_previews(
                    video_canvas, photo_canvas, self.project_text_videos,
                    self.project_text_photos, *map(int, self.settings["resolution"].split("x"))))

        schedule_global_previews()
        ai_status = ttk.Label(ai_row, text="", foreground="#2d6cdf", wraplength=200)
        ai_status.grid(row=0, column=1, sticky="w")
        ai_video_button = ttk.Button(ai_row, text="Βελτίωση κειμένου με AI")
        ai_video_button.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        def set_ai_busy(busy):
            ai_video_button.config(state="disabled" if busy else "normal")
            ai_status.config(text="Το AI γράφει..." if busy else "")

        def improve_video():
            self.improve_text_with_ai(
                video_text.get("1.0", "end-1c"),
                instructions.get("1.0", "end-1c"),
                apply_result=lambda value: (replace_text(video_text, value), update_video_text()),
                set_busy=set_ai_busy)

        ai_video_button.config(command=improve_video)
        ttk.Label(video_tab, text="Για διαφορετικό κείμενο σε μεμονωμένο video, χρησιμοποίησε "
                                  "Edit → Presentation / Slide Design.",
                  foreground="#666").grid(row=3, column=0, sticky="w", pady=(6, 0))

        # --------------------------- Photo Captions tab
        photos = [(index, path, edit) for index, (kind, path, edit) in enumerate(self.media_files)
                  if kind == "image"]
        photo_mode = ("individual" if any(
            normalize_presentation(edit.get("presentation"))["mode"] in ("custom", "combine")
            for _index, _path, edit in photos) else "shared")
        mode_var = tk.StringVar(value=next(
            label for label, mode in PHOTO_MODES.items() if mode == photo_mode))
        photo_state = {"mode": photo_mode, "current": None, "loading": False, "dirty": False}

        photo_tab.columnconfigure(0, weight=1)
        photo_tab.rowconfigure(1, weight=1)
        mode_row = ttk.Frame(photo_tab)
        mode_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        mode_row.columnconfigure(1, weight=1)
        ttk.Label(mode_row, text="Τρόπος λεζάντας", font=("Calibri", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        mode_combo = ttk.Combobox(mode_row, textvariable=mode_var,
                                  values=list(PHOTO_MODES), state="readonly")
        mode_combo.grid(row=0, column=1, sticky="ew")

        photo_body = ttk.Frame(photo_tab)
        photo_body.grid(row=1, column=0, sticky="nsew")
        photo_body.columnconfigure(0, weight=1)
        photo_body.columnconfigure(1, weight=2)
        photo_body.rowconfigure(0, weight=1)
        list_box = ttk.LabelFrame(photo_body, text="Φωτογραφίες — Ctrl/Shift για ομάδα", padding=5)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_frame = ttk.Frame(list_box)
        list_frame.pack(fill="both", expand=True)
        photo_list = tk.Listbox(list_frame, exportselection=False, selectmode=tk.BROWSE,
                                font=("Calibri", 10))
        photo_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=photo_list.yview)
        photo_list.configure(yscrollcommand=photo_scroll.set)
        photo_list.pack(side="left", fill="both", expand=True)
        photo_scroll.pack(side="right", fill="y")
        for number, (_index, path, _edit) in enumerate(photos, 1):
            photo_list.insert(tk.END, f"{number:02d}. {Path(path).name}")

        right = ttk.Frame(photo_body)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        shared_frame = ttk.Frame(right)
        shared_frame.grid(row=0, column=0, sticky="nsew")
        shared_frame.columnconfigure(0, weight=1)
        shared_frame.rowconfigure(1, weight=1)
        shared_header = ttk.Frame(shared_frame)
        shared_header.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        shared_header.columnconfigure(0, weight=1)
        ttk.Label(shared_header, text="Ένα κοινό κείμενο για όλες τις φωτογραφίες",
                  font=("Calibri", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(shared_header, text="Quick Paste",
                   command=lambda: quick_paste(shared_text, update_shared_photo_text)).grid(
            row=0, column=1, sticky="e")
        shared_text = scrolledtext.ScrolledText(shared_frame, height=10, wrap=tk.WORD,
                                                undo=True, font=("Calibri", 12))
        shared_text.grid(row=1, column=0, sticky="nsew")
        shared_text.insert("1.0", self.project_text_photos)
        shared_text.edit_reset()
        bind_text(shared_text, lambda: update_shared_photo_text())
        shared_controls = ttk.Frame(shared_frame)
        shared_controls.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        shared_controls.columnconfigure(0, weight=1)
        shared_ai_button = ttk.Button(shared_controls, text="Βελτίωση με AI")
        shared_ai_button.grid(row=0, column=0, sticky="e")
        ttk.Button(shared_controls, text="Εφαρμογή κοινού κειμένου σε ΟΛΕΣ τις φωτογραφίες",
                   command=lambda: apply_shared_to_all()).grid(
            row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(shared_frame,
                  text="Αν αφήσεις το κείμενο κενό, χρησιμοποιείται το κοινό κείμενο των video.",
                  foreground="#666", wraplength=600).grid(row=3, column=0, sticky="w", pady=(5, 0))

        caption_frame = ttk.Frame(right)
        caption_frame.grid(row=0, column=0, sticky="nsew")
        caption_frame.columnconfigure(1, weight=1)
        caption_frame.rowconfigure(2, weight=1)
        photo_mode_title = ttk.Label(caption_frame, text="Λεζάντα φωτογραφίας",
                                     font=("Calibri", 11, "bold"))
        photo_mode_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
        ttk.Label(caption_frame, text="Τίτλος", width=15).grid(row=1, column=0, sticky="w", pady=4)
        caption_title = tk.StringVar()
        ttk.Entry(caption_frame, textvariable=caption_title).grid(
            row=1, column=1, sticky="ew", pady=4)
        ttk.Label(caption_frame, text="Υπότιτλος", width=15).grid(row=2, column=0, sticky="nw", pady=4)
        caption_subtitle = tk.StringVar()
        ttk.Entry(caption_frame, textvariable=caption_subtitle).grid(
            row=2, column=1, sticky="ew", pady=4)
        description_label = ttk.Frame(caption_frame)
        description_label.grid(row=3, column=0, sticky="nw", pady=4)
        ttk.Label(description_label, text="Περιγραφή").pack(anchor="w")
        caption_description = scrolledtext.ScrolledText(
            caption_frame, height=9, wrap=tk.WORD, undo=True, font=("Calibri", 12))
        caption_description.grid(row=3, column=1, sticky="nsew", pady=4)
        bind_text(caption_description, lambda: caption_changed())
        ttk.Button(description_label, text="Quick Paste",
                   command=lambda: quick_paste(caption_description, caption_changed)).pack(
            anchor="w", pady=(5, 0))
        caption_buttons = ttk.Frame(caption_frame)
        caption_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        caption_buttons.columnconfigure(1, weight=1)
        caption_apply = ttk.Button(caption_buttons, text="Εφαρμογή στη φωτογραφία")
        caption_apply.grid(row=0, column=0, sticky="w")
        design_button = ttk.Button(caption_buttons, text="Template / σχεδίαση…")
        design_button.grid(row=0, column=1, sticky="e")
        caption_hint = ttk.Label(caption_frame, text="", foreground="#666", wraplength=620)
        caption_hint.grid(row=5, column=0, columnspan=2, sticky="w", pady=(7, 0))

        photo_preview_box = ttk.LabelFrame(right, text="Preview φωτογραφίας", padding=4)
        photo_preview_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        photo_preview_box.columnconfigure(0, weight=1)
        photo_preview_box.rowconfigure(0, weight=1)
        photo_canvas = tk.Canvas(photo_preview_box, bg="black", width=360, height=260,
                                 highlightthickness=0)
        photo_canvas.grid(row=0, column=0, sticky="nsew")
        photo_status = ttk.Label(right, text="", foreground="#2d6cdf", wraplength=620)
        photo_status.grid(row=2, column=0, sticky="w", pady=(4, 0))

        def values_from_caption():
            return {
                "title": caption_title.get().strip(),
                "subtitle": caption_subtitle.get().strip(),
                "description": caption_description.get("1.0", "end-1c").strip(),
            }

        def schedule_photo_preview():
            if not photos:
                return
            if photo_state["mode"] == "individual":
                index = photo_state.get("current") or photos[0][0]
                edit_override = None
            elif photo_state["mode"] == "group":
                selected_positions = list(photo_list.curselection())
                index = (photos[selected_positions[0]][0] if selected_positions else photos[0][0])
                edit_override = copy.deepcopy(self.media_files[index][2])
                presentation = normalize_presentation(edit_override.get("presentation"))
                presentation["mode"] = "custom"
                presentation.update(values_from_caption())
                edit_override["presentation"] = presentation
            else:
                index = photos[0][0]
                edit_override = None
            self._schedule_caption_preview(
                dialog, photo_canvas, index, "image", self.get_text_for("image"),
                status=photo_status, edit_override=edit_override)

        def write_item_caption(index, values):
            if not 0 <= index < len(self.media_files):
                return
            edit = self.media_files[index][2]
            presentation = normalize_presentation(edit.get("presentation"))
            presentation["mode"] = "custom"
            presentation.update(values)
            edit["presentation"] = normalize_presentation(
                presentation, scene_id=presentation["scene_id"])
            self.is_modified = True

        def save_current_individual():
            index = photo_state.get("current")
            if photo_state["mode"] == "individual" and index is not None and \
                    not photo_state["loading"] and photo_state["dirty"]:
                write_item_caption(index, values_from_caption())
                photo_state["dirty"] = False
                self._schedule_preview(450)

        def caption_changed(*_):
            if photo_state["loading"]:
                return
            if photo_state["mode"] == "individual":
                photo_state["dirty"] = True
                save_current_individual()
                schedule_global_previews()
            schedule_photo_preview()

        caption_title.trace_add("write", caption_changed)
        caption_subtitle.trace_add("write", caption_changed)

        def load_individual(index):
            if not 0 <= index < len(self.media_files):
                return
            photo_state["loading"] = True
            edit = self.media_files[index][2]
            presentation = normalize_presentation(edit.get("presentation"))
            caption_title.set(presentation["title"])
            caption_subtitle.set(presentation["subtitle"])
            replace_text(caption_description, presentation["description"])
            photo_state["current"] = index
            photo_state["loading"] = False
            photo_state["dirty"] = False
            photo_mode_title.config(text=f"Λεζάντα: {Path(self.media_files[index][1]).name}")
            caption_apply.config(text="Αποθήκευση λεζάντας φωτογραφίας")
            caption_hint.config(text="Κάθε φωτογραφία κρατά το δικό της κείμενο και template.")
            schedule_photo_preview()

        def current_photo_selection():
            selected_positions = list(photo_list.curselection())
            if photo_state["mode"] == "individual":
                if not photos:
                    return
                try:
                    position = photo_list.index(tk.ACTIVE)
                except tk.TclError:
                    position = selected_positions[-1] if selected_positions else 0
                if not 0 <= position < len(photos):
                    position = selected_positions[-1] if selected_positions else 0
                index = photos[position][0]
                if index != photo_state.get("current"):
                    save_current_individual()
                    load_individual(index)
            elif photo_state["mode"] == "group":
                caption_hint.config(text=f"Επιλεγμένες φωτογραφίες: {len(selected_positions)}. "
                                         "Η εφαρμογή λεζάντας διατηρεί κάθε template.")
                schedule_photo_preview()

        def photo_mode_changed(*_):
            new_mode = PHOTO_MODES.get(mode_var.get(), "shared")
            old_mode = photo_state["mode"]
            if old_mode == "individual":
                save_current_individual()
            photo_state["mode"] = new_mode
            if new_mode == "shared":
                photo_list.configure(selectmode=tk.BROWSE)
                caption_frame.grid_remove()
                shared_frame.grid()
            else:
                shared_frame.grid_remove()
                caption_frame.grid()
                photo_list.configure(selectmode=(tk.EXTENDED if new_mode == "group" else tk.BROWSE))
                if new_mode == "individual":
                    caption_frame.grid()
                    if photos:
                        photo_list.selection_clear(0, tk.END)
                        photo_list.selection_set(0)
                        photo_list.activate(0)
                        load_individual(photos[0][0])
                    else:
                        photo_mode_title.config(text="Δεν υπάρχουν φωτογραφίες")
                        caption_apply.config(state="disabled")
                else:
                    photo_state["current"] = None
                    photo_list.selection_clear(0, tk.END)
                    caption_title.set("")
                    caption_subtitle.set("")
                    replace_text(caption_description, "")
                    photo_mode_title.config(text="Κοινή λεζάντα για επιλεγμένη ομάδα")
                    caption_apply.config(text="Εφαρμογή στα επιλεγμένα", state="normal")
                    caption_hint.config(text="Επίλεξε φωτογραφίες αριστερά με Ctrl/Shift, γράψε μία λεζάντα "
                                             "και πάτα «Εφαρμογή στα επιλεγμένα».")
            schedule_photo_preview()

        def update_shared_photo_text(_event=None):
            value = shared_text.get("1.0", "end-1c").strip()
            if value != self.project_text_photos:
                self.project_text_photos = value
                self.is_modified = True
                self._schedule_preview(500)
                schedule_global_previews()
                schedule_photo_preview()

        shared_ai_button.config(command=lambda: self.improve_text_with_ai(
            shared_text.get("1.0", "end-1c"),
            instructions.get("1.0", "end-1c"),
            apply_result=lambda value: (replace_text(shared_text, value),
                                        update_shared_photo_text()),
            set_busy=lambda busy: (shared_ai_button.config(
                state="disabled" if busy else "normal"),
                photo_status.config(text="Το AI γράφει..." if busy else ""))))

        def apply_shared_to_all():
            value = shared_text.get("1.0", "end-1c").strip()
            self.project_text_photos = value
            changed = False
            for index, _path, _edit in photos:
                presentation = normalize_presentation(
                    self.media_files[index][2].get("presentation"))
                if presentation["mode"] != "global":
                    presentation["mode"] = "global"
                    self.media_files[index][2]["presentation"] = presentation
                    changed = True
            if changed or value:
                self.is_modified = True
                self.update_media_display()
                self._schedule_preview()
            schedule_global_previews()
            schedule_photo_preview()
            photo_status.config(text=f"Κοινό κείμενο εφαρμόστηκε σε {len(photos)} φωτογραφίες")

        def apply_photo_caption():
            values = values_from_caption()
            if photo_state["mode"] == "individual":
                index = photo_state.get("current")
                if index is None:
                    messagebox.showinfo("Photo Captions", "Επίλεξε πρώτα μια φωτογραφία.",
                                        parent=dialog)
                    return
                write_item_caption(index, values)
                photo_state["dirty"] = False
                photo_status.config(text="Η λεζάντα της φωτογραφίας αποθηκεύτηκε")
            elif photo_state["mode"] == "group":
                positions = list(photo_list.curselection())
                if not positions:
                    messagebox.showinfo("Photo Captions", "Επίλεξε μία ή περισσότερες φωτογραφίες.",
                                        parent=dialog)
                    return
                for position in positions:
                    write_item_caption(photos[position][0], values)
                photo_status.config(text=f"Η λεζάντα εφαρμόστηκε σε {len(positions)} φωτογραφίες")
            self.update_media_display()
            self._schedule_preview()
            schedule_global_previews()
            schedule_photo_preview()

        caption_apply.config(command=apply_photo_caption)
        photo_list.bind("<<ListboxSelect>>", current_photo_selection)
        mode_combo.bind("<<ComboboxSelected>>", photo_mode_changed, add="+")
        if photos:
            photo_list.selection_set(0)
            photo_list.activate(0)
        if photo_mode == "individual":
            photo_state["mode"] = "shared"
            photo_mode_changed()
        else:
            photo_mode_changed()

        def open_photo_design():
            if photo_state["mode"] == "individual" and photo_state.get("current") is not None:
                self.open_presentation_editor(photo_state["current"])
            elif photos:
                positions = (list(photo_list.curselection()) if photo_state["mode"] == "group"
                             else list(range(len(photos))))
                self.selected_indices = {photos[position][0] for position in positions
                                         if 0 <= position < len(photos)}
                self.open_storyboard_editor()
            else:
                messagebox.showinfo("Slide Design", "Δεν υπάρχουν φωτογραφίες για επεξεργασία.",
                                    parent=dialog)
        design_button.config(command=open_photo_design)

        bottom = ttk.Frame(outer)
        bottom.pack(fill="x", pady=(8, 0))
        ttk.Label(bottom, text="Οι αλλαγές αποθηκεύονται στο project· Ctrl+S γράφει το project στο δίσκο.",
                  foreground="#666").pack(side="left")

        def close():
            save_current_individual()
            update_shared_photo_text()
            update_video_text()
            self.update_media_display()
            self._schedule_preview()
            self._text_captions_dialog = None
            dialog.destroy()

        ttk.Button(bottom, text="Κλείσιμο", command=close).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        return dialog
