"""The export drawer: output folder, quality, estimate and progress."""

import threading
import tkinter as tk
from tkinter import ttk, filedialog

from .export_quality import EXPORT_QUALITY_OPTIONS
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import aspect_label, flat_button, format_duration, primary_button


class ExportPanelMixin:
    """The export drawer: output folder, quality, estimate and progress."""

    def _build_export_panel(self):
        self.out_var = tk.StringVar(value=self.settings.get("output_folder", ""))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_var.trace_add("write", self._on_export_progress)
        self.export_eta_var = tk.StringVar(value="Remaining: —")
        self.export_estimate_var = tk.StringVar(value="Πρόσθεσε media για εκτίμηση")
        self.export_summary_var = tk.StringVar(value="")

        window = tk.Toplevel(self.root)
        window.withdraw()
        window.title("Εξαγωγή βίντεο")
        window.configure(bg=P["background"])
        window.geometry("580x640")
        window.minsize(520, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", window.withdraw)
        self.export_window = window

        body = tk.Frame(window, bg=P["background"], padx=22, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="ΕΞΑΓΩΓΗ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(body, text="Δημιουργία βίντεο", bg=P["background"], fg=P["text"],
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", pady=(1, 0))
        self.export_project_label = tk.Label(body, text="", bg=P["background"],
                                             fg=P["muted"], font=("Segoe UI", 9),
                                             wraplength=500, justify="left")
        self.export_project_label.pack(anchor="w", pady=(3, 14))

        summary = tk.Frame(body, bg=P["raised"], highlightthickness=1,
                           highlightbackground=P["border"], padx=14, pady=12)
        summary.pack(fill="x")
        tk.Label(summary, text="ΣΥΝΟΨΗ", bg=P["raised"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(summary, textvariable=self.export_summary_var, bg=P["raised"],
                 fg=P["text"], font=("Segoe UI", 10, "bold"),
                 justify="left", wraplength=500).pack(anchor="w", pady=(3, 0))
        tk.Label(summary, textvariable=self.export_estimate_var, bg=P["raised"],
                 fg=P["muted"], font=("Segoe UI", 9),
                 justify="left", wraplength=500).pack(anchor="w", pady=(2, 0))

        tk.Label(body, text="ΦΑΚΕΛΟΣ ΕΞΟΔΟΥ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(16, 4))
        folder_row = tk.Frame(body, bg=P["background"])
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.out_var, style="Field.TEntry").pack(
            side="left", fill="x", expand=True)
        flat_button(folder_row, "Αλλαγή", self._browse_export_folder,
                    background=P["raised"], foreground=P["text"],
                    active_background=P["selected"], font=("Segoe UI", 8),
                    padx=10, pady=6).pack(side="left", padx=(6, 0))

        quality_row = tk.Frame(body, bg=P["background"])
        quality_row.pack(fill="x", pady=(12, 0))
        tk.Label(quality_row, text="ΠΟΙΟΤΗΤΑ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        quality_mode = self.settings.get("export_quality", "high")
        quality_label = next((label for label, mode in EXPORT_QUALITY_OPTIONS.items()
                              if mode == quality_mode), "Υψηλή")
        self.export_quality_var = tk.StringVar(value=quality_label)
        quality_combo = ttk.Combobox(quality_row, textvariable=self.export_quality_var,
                                     values=list(EXPORT_QUALITY_OPTIONS), state="readonly")
        quality_combo.pack(fill="x", pady=(4, 0))
        quality_combo.bind("<<ComboboxSelected>>", self._save_export_quality, add="+")

        self.render_live_preview_var = tk.BooleanVar(
            value=bool(self.settings.get("render_live_preview", False)))
        self.render_live_preview_check = flat_button(
            body, "", self._toggle_live_preview, background=P["background"],
            foreground=P["muted"], active_background=P["selected"],
            font=("Segoe UI", 9), padx=0, pady=3, anchor="w")
        self.render_live_preview_check.pack(anchor="w", pady=(10, 0), fill="x")
        self._update_live_preview_toggle()

        self._section_line(body)
        tk.Label(body, text="ΠΡΟΟΔΟΣ", bg=P["background"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 4))
        progress_row = tk.Frame(body, bg=P["background"])
        progress_row.pack(fill="x")
        ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100).pack(
            side="left", fill="x", expand=True)
        tk.Label(progress_row, textvariable=self.export_eta_var, bg=P["background"],
                 fg=P["muted"], font=("Segoe UI", 8)).pack(side="right", padx=(8, 0))

        footer = tk.Frame(body, bg=P["background"])
        footer.pack(side="bottom", fill="x", pady=(16, 0))
        self._export_start_btn = primary_button(footer, "Έναρξη εξαγωγής",
                                                self._start_export_from_panel)
        self._export_start_btn.pack(side="right")
        self.cancel_btn = flat_button(footer, "Ακύρωση", self.cancel_export,
                                      background=P["raised"], foreground=P["muted"],
                                      active_background=P["selected"])
        self.cancel_btn.configure(state="disabled")
        self.cancel_btn.pack(side="right", padx=(6, 0))
        flat_button(footer, "Κλείσιμο", window.withdraw, background=P["background"],
                    foreground=P["muted"], active_background=P["selected"],
                    pady=7).pack(side="left")
        self._refresh_export_estimate()

    @staticmethod
    def _section_line(parent):
        tk.Frame(parent, bg=P["border"], height=1).pack(fill="x", pady=(14, 0))

    def _browse_export_folder(self):
        folder = filedialog.askdirectory(parent=self.export_window,
                                         initialdir=self.out_var.get() or None)
        if folder:
            self.out_var.set(folder)
            self.settings["output_folder"] = folder
            self.save_settings()

    def _save_export_quality(self, _event=None):
        value = EXPORT_QUALITY_OPTIONS.get(self.export_quality_var.get(), "high")
        if self.settings.get("export_quality") != value:
            self.settings["export_quality"] = value
            self.save_settings()
        self._refresh_export_estimate()

    def _toggle_live_preview(self):
        self.render_live_preview_var.set(not self.render_live_preview_var.get())
        self._save_live_preview_setting()
        self._update_live_preview_toggle()

    def _update_live_preview_toggle(self):
        active = bool(self.render_live_preview_var.get())
        text = ("●  Ζωντανή προεπισκόπηση κατά το render (1 καρέ/δευτ.)" if active
                else "○  Ζωντανή προεπισκόπηση κατά το render (1 καρέ/δευτ.)")
        try:
            self.render_live_preview_check.configure(
                text=text, foreground=(P["accent"] if active else P["muted"]))
        except tk.TclError:
            pass

    def _save_live_preview_setting(self):
        self.settings["render_live_preview"] = bool(self.render_live_preview_var.get())
        self.save_settings()

    def show_export_panel(self):
        commit_captions = getattr(self, "_commit_pending_caption_apply", None)
        if commit_captions:
            commit_captions()
        self._update_export_summary()
        self._refresh_export_estimate()
        try:
            if not getattr(self, "_export_positioned", False):
                self.export_window.update_idletasks()
                width = self.export_window.winfo_width()
                height = self.export_window.winfo_height()
                x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
                y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 3)
                self.export_window.geometry(f"+{x}+{y}")
                self._export_positioned = True
            self.export_window.deiconify()
            self.export_window.lift()
            self.export_window.focus_force()
        except tk.TclError:
            pass
        return self.export_window

    def _update_export_summary(self):
        resolution = self.settings.get("resolution", "1080x1080")
        name = self.name_var.get().strip() or "(χωρίς όνομα)"
        count = len(getattr(self, "media_files", []))
        self.export_project_label.configure(text=f"Project: {name}")
        self.export_summary_var.set(
            f"{aspect_label(resolution)} · {resolution} · {count} "
            f"{'σκηνή' if count == 1 else 'σκηνές'}")

    def _refresh_export_estimate(self):
        job = getattr(self, "_export_estimate_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._export_estimate_job = self.root.after(300, self._calculate_export_estimate)

    def _calculate_export_estimate(self):
        self._export_estimate_job = None
        if not getattr(self, "media_files", None):
            self.export_estimate_var.set("Πρόσθεσε media για εκτίμηση")
            return
        self._export_estimate_token = getattr(self, "_export_estimate_token", 0) + 1
        token = self._export_estimate_token
        self.export_estimate_var.set("Υπολογισμός εκτίμησης…")

        def worker():
            try:
                duration, size_mb = self.estimate_export_metrics()
                self._post_ui(self._show_export_estimate, token, duration, size_mb, None)
            except Exception as exc:
                self._post_ui(self._show_export_estimate, token, None, None, exc)

        threading.Thread(target=worker, daemon=True).start()

    def _show_export_estimate(self, token, duration, size_mb, error):
        if token != getattr(self, "_export_estimate_token", 0):
            return
        if error is not None:
            self.export_estimate_var.set("Η εκτίμηση δεν είναι διαθέσιμη")
        else:
            self.export_estimate_var.set(
                f"Εκτιμώμενη διάρκεια: {format_duration(duration)} · "
                f"μέγεθος: περίπου {size_mb:.1f} MB")

    def _start_export_from_panel(self):
        if getattr(self, "_export_running", False):
            return
        self._export_running = True
        try:
            self._export_start_btn.configure(state="disabled")
        except tk.TclError:
            pass
        self.export_video()

        def check_started():
            if not getattr(self, "_export_active", False):
                self._export_finished()

        self.root.after(800, check_started)

    def _export_finished(self, completed=False, cancelled=False):
        self._export_running = False
        button = getattr(self, "_export_start_btn", None)
        if button is not None:
            try:
                button.configure(state="normal")
            except tk.TclError:
                pass
        if completed and not cancelled:
            window = getattr(self, "export_window", None)
            if window is not None:
                try:
                    window.withdraw()
                except tk.TclError:
                    pass
