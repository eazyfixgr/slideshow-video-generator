"""Startup welcome screen and a compact three-step new-project wizard."""

from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

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
        dialog.geometry("620x500")
        dialog.minsize(560, 440)
        dialog.resizable(True, True)
        dialog.transient(self.root)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Slideshow Video Creator Pro",
                  font=("Calibri", 22, "bold")).pack(anchor="w", pady=(8, 2))
        ttk.Label(body, text="Τι θέλεις να κάνεις;",
                  font=("Calibri", 12), foreground="#555").pack(anchor="w", pady=(0, 18))

        def close():
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

        def restore_welcome_grab(_event=None):
            try:
                if dialog.winfo_exists():
                    dialog.grab_set()
                    dialog.lift()
            except tk.TclError:
                pass

        def open_existing():
            project_dialog = self.load_project(on_loaded=close)
            if project_dialog is not None:
                project_dialog.bind("<Destroy>", restore_welcome_grab, add="+")

        def open_wizard():
            wizard = self.open_new_project_wizard(on_created=close)
            if wizard is not None:
                wizard.bind("<Destroy>", restore_welcome_grab, add="+")

        actions = ttk.Frame(body)
        actions.pack(fill="x", expand=True)
        ttk.Button(actions, text="Αναζήτηση / Άνοιγμα υπάρχοντος project…",
                   command=open_existing).pack(fill="x", pady=5, ipady=5)
        ttk.Button(actions, text="Νέο project με οδηγό…",
                   command=open_wizard).pack(fill="x", pady=5, ipady=5)
        ttk.Button(actions, text="Νέο project (κλασικό)",
                   command=lambda: (self.new_project(), close())).pack(fill="x", pady=5, ipady=5)
        ttk.Separator(body).pack(fill="x", pady=(12, 8))
        ttk.Button(body, text="Συνέχεια χωρίς project", command=close).pack(
            anchor="e", pady=(0, 4))

        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
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
        dialog.transient(self.root)
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
