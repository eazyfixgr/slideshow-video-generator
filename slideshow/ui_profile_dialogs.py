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

    def _profile_dialog(self, profile, callback):
        editing = profile is not None
        owner = getattr(self, "_welcome_dialog", None) or self.root
        dialog = tk.Toplevel(owner)
        dialog.title("Επεξεργασία προφίλ" if editing else "Νέο προφίλ")
        dialog.configure(bg=P["background"])
        dialog.geometry("520x430")
        dialog.resizable(False, False)
        dialog.transient(owner)
        dialog.grab_set()

        body = tk.Frame(dialog, bg=P["background"], padx=24, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="ΠΡΟΦΙΛ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(body, text=("Επεξεργασία προφίλ" if editing else "Νέο προφίλ"),
                 bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(2, 2))
        tk.Label(body, text="Κάθε προφίλ έχει δικά του projects, ρυθμίσεις και μουσική.",
                 bg=P["background"], fg=P["muted"], font=("Segoe UI", 9),
                 wraplength=455, justify="left").pack(anchor="w", pady=(0, 16))

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
        cancel = flat_button(footer, "Ακύρωση", dialog.destroy,
                             background=P["panel"], foreground=P["muted"],
                             active_background=P["selected"])
        cancel.pack(side="right", padx=(8, 0))
        save = primary_button(footer, "Αποθήκευση" if editing else "Δημιουργία",
                              lambda: submit())
        save.pack(side="right")

        def submit():
            name = name_var.get().strip()
            if not name:
                warning.config(text="Γράψε ένα όνομα για το προφίλ.")
                name_entry.focus_set()
                return
            role = role_var.get().strip()
            if editing:
                update_profile(self.profiles_data, profile["id"], name=name, role=role,
                               color=state["color"])
                self.save_profile_registry()
                if profile["id"] == self.active_profile_id:
                    self.active_profile_data = profile
                    self._refresh_header()
                result = profile
            else:
                result = self.create_new_profile(name, role, state["color"])
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

        name_var.trace_add("write", refresh_preview)
        choose_color(state["color"])
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _e: (close(), "break")[1])
        dialog.bind("<Return>", lambda _e: (submit(), "break")[1])
        name_entry.focus_set()
        name_entry.selection_range(0, tk.END)
        dialog.update_idletasks()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - dialog.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - dialog.winfo_height()) // 3)
        dialog.geometry(f"+{x}+{y}")
        return dialog
