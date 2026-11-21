"""Create and edit the local profiles shown on the welcome screen."""

import tkinter as tk
from tkinter import ttk

from .deps import ImageTk
from .profiles import PROFILE_COLORS, initials, update_profile
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import avatar_image, flat_button, primary_button


class ProfileDialogsMixin:
    """Create and edit the local profiles shown on the welcome screen."""

    def open_new_profile_dialog(self, on_created=None):
        return self._profile_dialog(None, on_created)

    def open_edit_profile_dialog(self, profile=None, on_saved=None):
        profile = profile or self.active_profile_data
        return self._profile_dialog(profile, on_saved)

    def show_first_profile_setup(self):
        existing = getattr(self, "_profile_setup_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

        def done(_profile):
            self._profile_setup_dialog = None
            self._needs_profile_setup = False
            self.show_welcome_screen()

        def cancel():
            self._profile_setup_dialog = None
            self.root.after(10, self.on_closing)

        dialog = self._profile_dialog(None, done, first_run=True, on_cancel=cancel)
        self._profile_setup_dialog = dialog
        return dialog

    def _profile_dialog(self, profile, callback, first_run=False, on_cancel=None):
        editing = profile is not None and not first_run
        owner = getattr(self, "_welcome_dialog", None) or self.root
        dialog = tk.Toplevel(owner)
        dialog.title("Καλώς ήρθες" if first_run else
                     ("Επεξεργασία προφίλ" if editing else "Νέο προφίλ"))
        dialog.configure(bg=P["background"])
        dialog.geometry("520x430")
        dialog.resizable(False, False)
        if not first_run:
            dialog.transient(owner)
        dialog.grab_set()

        body = tk.Frame(dialog, bg=P["background"], padx=24, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=("ΚΑΛΩΣ ΗΡΘΕΣ" if first_run else "ΠΡΟΦΙΛ"),
                 bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        heading = ("Δημιούργησε το προφίλ σου" if first_run else
                   ("Επεξεργασία προφίλ" if editing else "Νέο προφίλ"))
        tk.Label(body, text=heading, bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(2, 2))
        description = ("Πώς να σε προσφωνούμε; Το όνομα και το χρώμα θα εμφανίζονται "
                       "στο welcome screen." if first_run else
                       "Κάθε προφίλ έχει δικά του projects, ρυθμίσεις και μουσική.")
        tk.Label(body, text=description, bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 9), wraplength=455, justify="left").pack(
            anchor="w", pady=(0, 16))

        preview = tk.Label(body, bg=P["background"])
        preview.pack(anchor="w", pady=(0, 10))

        state = {
            "color": (profile or {}).get("color", PROFILE_COLORS[0]),
            "image": None,
        }
        name_var = tk.StringVar(value=(profile or {}).get("name", ""))
        role_var = tk.StringVar(value=(profile or {}).get("role", ""))

        def refresh_preview(*_):
            image = avatar_image(initials(name_var.get()), state["color"], 54, P["background"])
            photo = ImageTk.PhotoImage(image, master=dialog)
            state["image"] = photo
            preview.configure(image=photo)

        fields = tk.Frame(body, bg=P["background"])
        fields.pack(fill="x")
        fields.columnconfigure(1, weight=1)
        tk.Label(fields, text="Όνομα", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 12))
        name_entry = ttk.Entry(fields, textvariable=name_var, style="Field.TEntry",
                               font=("Segoe UI", 11))
        name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 10))
        tk.Label(fields, text="Δραστηριότητα", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(fields, textvariable=role_var, style="Field.TEntry",
                  font=("Segoe UI", 10)).grid(row=1, column=1, sticky="ew")

        tk.Label(body, text="Χρώμα προφίλ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(14, 5))
        colors = tk.Frame(body, bg=P["background"])
        colors.pack(anchor="w")
        swatches = {}

        def choose_color(color):
            state["color"] = color
            for value, swatch in swatches.items():
                swatch.configure(highlightbackground=(P["text"] if value == color
                                                       else P["border"]),
                                 highlightthickness=2 if value == color else 1)
            refresh_preview()

        for color in PROFILE_COLORS:
            swatch = tk.Label(colors, bg=color, width=3, height=1, bd=0,
                              highlightthickness=1, highlightbackground=P["border"],
                              cursor="hand2")
            swatch.pack(side="left", padx=3)
            swatch.bind("<Button-1>", lambda _e, value=color: choose_color(value))
            swatches[color] = swatch

        warning = tk.Label(body, text="", bg=P["background"], fg=P["danger"],
                           font=("Segoe UI", 9))
        warning.pack(anchor="w", pady=(10, 0))

        footer = tk.Frame(body, bg=P["background"])
        footer.pack(side="bottom", fill="x", pady=(12, 0))
        submitted = {"value": False}
        cancel = flat_button(footer, "Έξοδος" if first_run else "Ακύρωση",
                             lambda: close(),
                             background=P["panel"], foreground=P["muted"],
                             active_background=P["selected"])
        cancel.pack(side="right", padx=(8, 0))
        save_text = ("Δημιουργία προφίλ" if first_run else
                     ("Αποθήκευση" if editing else "Δημιουργία"))
        save = primary_button(footer, save_text, lambda: submit())
        save.pack(side="right")

        def submit():
            name = name_var.get().strip()
            if not name:
                warning.config(text="Γράψε ένα όνομα για το προφίλ.")
                name_entry.focus_set()
                return
            role = role_var.get().strip()
            if first_run:
                result = self.complete_profile_onboarding(name, role, state["color"])
            elif editing:
                update_profile(self.profiles_data, profile["id"], name=name, role=role,
                               color=state["color"])
                self.save_profile_registry()
                if profile["id"] == self.active_profile_id:
                    self.active_profile_data = profile
                    self._refresh_header()
                result = profile
            else:
                result = self.create_new_profile(name, role, state["color"])
            submitted["value"] = True
            close()
            if callback:
                callback(result)

        def close():
            try:
                if dialog.grab_current() == dialog:
                    dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()
            if not submitted["value"] and on_cancel:
                on_cancel()

        name_var.trace_add("write", refresh_preview)
        choose_color(state["color"])
        dialog.protocol("WM_DELETE_WINDOW", close)
        if not first_run:
            dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        dialog.bind("<Return>", lambda _e: (submit(), "break")[1])
        name_entry.focus_set()
        name_entry.selection_range(0, tk.END)
        dialog.update_idletasks()
        if first_run:
            dialog.attributes("-topmost", True)
            x = max(0, (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2)
            y = max(0, (dialog.winfo_screenheight() - dialog.winfo_height()) // 2)
        else:
            x = owner.winfo_rootx() + max(0, (owner.winfo_width() - dialog.winfo_width()) // 2)
            y = owner.winfo_rooty() + max(0, (owner.winfo_height() - dialog.winfo_height()) // 3)
        dialog.geometry(f"+{x}+{y}")
        return dialog
