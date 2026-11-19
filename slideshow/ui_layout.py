"""The main window layout (panels, library canvas, controls, preview canvases)."""

import io
import json
import os
import random
import re
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .export_quality import EXPORT_QUALITY_OPTIONS
from .slide_design import TEMPLATES, normalize_template


class LayoutMixin:
    """The main window layout (panels, library canvas, controls, preview canvases)."""

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill='x', padx=5, pady=(5, 0))
        ttk.Button(bar, text="↶ Undo", command=self.undo).pack(side='left', padx=2)
        ttk.Button(bar, text="↷ Redo", command=self.redo).pack(side='left', padx=2)
        ttk.Separator(bar, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Button(bar, text="Captions",
                   command=self.open_text_captions_manager).pack(side='left', padx=2)
        ttk.Label(bar, text="Template:").pack(side="left", padx=(8, 3))
        self._caption_template_var = tk.StringVar(
            value=TEMPLATES.get(self.project_template, TEMPLATES["legacy"]))
        template_combo = ttk.Combobox(
            bar, textvariable=self._caption_template_var, state="readonly",
            values=list(TEMPLATES.values()), width=27)
        template_combo.pack(side="left", padx=(0, 4))
        template_combo.bind("<<ComboboxSelected>>", self._on_caption_template_selected, add="+")


    def _sync_caption_template_dropdown(self):
        template_var = getattr(self, "_caption_template_var", None)
        if template_var is not None:
            template = normalize_template(getattr(self, "project_template", "legacy"))
            self.project_template = template
            template_var.set(TEMPLATES.get(template, TEMPLATES["legacy"]))


    def _remember_caption_template(self, template):
        template = normalize_template(template)
        self.settings["last_caption_template"] = template
        self.settings["last_caption_template_is_global"] = True
        self._sync_caption_template_dropdown()
        self.save_settings()
        return template


    def _on_caption_template_selected(self, _event=None):
        selected = self._caption_template_var.get()
        template = next((key for key, label in TEMPLATES.items()
                         if label == selected), "legacy")
        changed = template != self.project_template
        self.project_template = self._remember_caption_template(template)
        if not changed:
            return
        if self.media_files:
            self.update_media_display()
            self._schedule_preview()
        if getattr(self, "current_project", None) or self.name_var.get().strip():
            self.is_modified = True


    def _start_export_eta(self):
        job = getattr(self, "_export_eta_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        now = time.monotonic()
        self._export_eta_active = True
        self._export_eta_state = {
            "last_progress": float(self.progress_var.get()),
            "last_change": now,
            "seconds_per_percent": None,
        }
        self.export_eta_var.set("Estimating remaining time…")
        self._update_export_eta()


    def _on_export_progress(self, *_):
        if not getattr(self, "_export_eta_active", False):
            return
        try:
            progress = float(self.progress_var.get())
        except (tk.TclError, ValueError, TypeError):
            return
        state = self._export_eta_state
        previous = state["last_progress"]
        if progress <= previous:
            return
        now = time.monotonic()
        elapsed = now - state["last_change"]
        delta = progress - previous
        if elapsed > 0:
            sample = elapsed / delta
            old_rate = state["seconds_per_percent"]
            state["seconds_per_percent"] = (sample if old_rate is None else
                                             old_rate * 0.65 + sample * 0.35)
        state["last_progress"] = progress
        state["last_change"] = now


    def _update_export_eta(self):
        self._export_eta_job = None
        if not getattr(self, "_export_eta_active", False):
            return
        try:
            progress = max(0.0, min(100.0, float(self.progress_var.get())))
        except (tk.TclError, ValueError, TypeError):
            progress = 0.0
        state = self._export_eta_state
        seconds_per_percent = state["seconds_per_percent"]
        if progress >= 99.5:
            text = "Finishing export…"
        elif seconds_per_percent is None:
            text = "Estimating remaining time…"
        else:
            elapsed_since_update = time.monotonic() - state["last_change"]
            remaining = seconds_per_percent * (100.0 - progress) - elapsed_since_update
            text = (f"Remaining: {self.format_estimated_duration(remaining)}"
                    if remaining > 1 else "Re-estimating…")
        self.export_eta_var.set(text)
        self._export_eta_job = self.root.after(1000, self._update_export_eta)


    def _finish_export_eta(self, completed=False, cancelled=False):
        self._export_eta_active = False
        job = getattr(self, "_export_eta_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._export_eta_job = None
        if completed:
            self.export_eta_var.set("Export complete")
        elif cancelled:
            self.export_eta_var.set("Export cancelled")
        else:
            self.export_eta_var.set("Export stopped")


    def setup_gui(self):
        self._build_toolbar()

        # Two equal columns, always 50/50 and never draggable (no sash).
        container = ttk.Frame(self.root)
        container.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        container.columnconfigure(0, weight=1, uniform="half")
        container.columnconfigure(1, weight=1, uniform="half")
        container.rowconfigure(0, weight=1)

        # Left Panel: project name + library
        left = ttk.Frame(container)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 4))
        # Right Panel: Preview & ALL Controls
        right = ttk.Frame(container)
        right.grid(row=0, column=1, sticky='nsew', padx=(4, 0))

        name_frame = ttk.Frame(left)
        name_frame.pack(fill='x', padx=10, pady=(10, 2))
        ttk.Label(name_frame, text="Project Name:", font=("Calibri", 11, "bold")).pack(side='left')
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(name_frame, textvariable=self.name_var, font=("Calibri", 11))
        self.name_entry.pack(side='left', fill='x', expand=True, padx=(8, 0))

        media_header = ttk.Frame(left)
        media_header.pack(fill='x', padx=10, pady=(8,5))
        ttk.Label(media_header, text="Media Content Library", font=("Calibri", 12, "bold")).pack(side='left')
        ttk.Radiobutton(media_header, text="List", variable=self.view_mode, value="list", command=self.update_media_display).pack(side='right')
        ttk.Radiobutton(media_header, text="Icons", variable=self.view_mode, value="thumbnails", command=self.update_media_display).pack(side='right', padx=10)

        lib_container = ttk.Frame(left)
        lib_container.pack(fill='both', expand=True, padx=10, pady=5)
        self.media_canvas = tk.Canvas(lib_container, bg='#eee', highlightthickness=0)
        self.media_scrollbar = ttk.Scrollbar(lib_container, orient="vertical", command=self.media_canvas.yview)
        self.thumb_frame = ttk.Frame(self.media_canvas)
        self.canvas_window = self.media_canvas.create_window((0, 0), window=self.thumb_frame, anchor="nw")
        self.media_canvas.configure(yscrollcommand=self.media_scrollbar.set)
        
        self.media_canvas.pack(side='left', fill='both', expand=True)
        self.media_scrollbar.pack(side='right', fill='y')
        
        self.thumb_frame.bind("<Configure>", lambda e: self.media_canvas.configure(scrollregion=self.media_canvas.bbox("all")))
        self.media_canvas.bind("<Configure>", self._debounced_resize)
        self.media_canvas.bind_all("<MouseWheel>", lambda e: self.media_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # RIGHT PANEL
        # Bottom controls are packed first, so the preview gets all the rest.
        self.status = ttk.Label(right, text="Ready", relief='sunken')
        self.status.pack(side='bottom', fill='x')

        controls = ttk.Frame(right)
        controls.pack(side='bottom', fill='x', padx=10, pady=(0, 4))

        ttk.Label(controls, text="Output Folder:", font=("Calibri", 10, "bold")).pack(anchor='w')
        r2 = ttk.Frame(controls)
        r2.pack(fill='x', pady=5)
        self.out_var = tk.StringVar(value=self.settings.get("output_folder", ""))
        ttk.Entry(r2, textvariable=self.out_var).pack(side='left', fill='x', expand=True)
        def browse_out():
            f = filedialog.askdirectory()
            if f:
                self.out_var.set(f)
        ttk.Button(r2, text="Browse", command=browse_out).pack(side='left', padx=2)
        ttk.Button(r2, text="GENERATE VIDEO", command=self.export_video,
                   style='Accent.TButton').pack(side='left', padx=2)
        self.cancel_btn = ttk.Button(r2, text="Cancel Export", command=self.cancel_export, state='disabled')
        self.cancel_btn.pack(side='left', padx=2)

        quality_row = ttk.Frame(controls)
        quality_row.pack(fill='x', pady=(0, 4))
        ttk.Label(quality_row, text="Export quality:").pack(side="left", padx=(0, 6))
        quality_mode = self.settings.get("export_quality", "high")
        quality_label = next((label for label, mode in EXPORT_QUALITY_OPTIONS.items()
                              if mode == quality_mode), "Υψηλή")
        self.export_quality_var = tk.StringVar(value=quality_label)
        quality_combo = ttk.Combobox(
            quality_row, textvariable=self.export_quality_var, state="readonly",
            values=list(EXPORT_QUALITY_OPTIONS), width=27)
        quality_combo.pack(side="left")
        self.export_estimate_var = tk.StringVar(value="Add media for estimate")
        ttk.Label(quality_row, textvariable=self.export_estimate_var,
                  foreground="#666").pack(side="left", padx=8)

        estimate_state = {"job": None, "token": 0}

        def show_export_estimate(token, duration=None, size_mb=None, error=None):
            if token != estimate_state["token"]:
                return
            if error:
                self.export_estimate_var.set("Estimate unavailable")
            else:
                self.export_estimate_var.set(
                    f"Approx. {size_mb:.1f} MB · Duration: "
                    f"{self.format_estimated_duration(duration)}")

        def calculate_export_estimate():
            estimate_state["job"] = None
            if not self.media_files:
                self.export_estimate_var.set("Add media for estimate")
                return
            estimate_state["token"] += 1
            token = estimate_state["token"]
            self.export_estimate_var.set("Estimating export…")

            def worker():
                try:
                    duration, size_mb = self.estimate_export_metrics()
                    self._post_ui(show_export_estimate, token, duration, size_mb)
                except Exception as exc:
                    self._post_ui(show_export_estimate, token, error=exc)

            threading.Thread(target=worker, daemon=True).start()

        def schedule_export_estimate(*_):
            job = estimate_state.get("job")
            if job is not None:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
            estimate_state["job"] = self.root.after(250, calculate_export_estimate)

        self._refresh_export_estimate = schedule_export_estimate

        def save_export_quality(_event=None):
            value = EXPORT_QUALITY_OPTIONS.get(self.export_quality_var.get(), "high")
            if self.settings.get("export_quality") != value:
                self.settings["export_quality"] = value
                self.save_settings()
            schedule_export_estimate()

        quality_combo.bind("<<ComboboxSelected>>", save_export_quality, add="+")
        schedule_export_estimate()

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_var.trace_add("write", self._on_export_progress)
        progress_row = ttk.Frame(controls)
        progress_row.pack(fill="x", pady=(4, 0))
        ttk.Progressbar(progress_row, variable=self.progress_var, maximum=100).pack(
            side="left", fill="x", expand=True)
        self.export_eta_var = tk.StringVar(value="Remaining: —")
        ttk.Label(progress_row, textvariable=self.export_eta_var).pack(side="right", padx=(8, 0))

        self.render_live_preview_var = tk.BooleanVar(
            value=bool(self.settings.get("render_live_preview", False)))

        def save_live_preview_setting():
            self.settings["render_live_preview"] = bool(self.render_live_preview_var.get())
            self.save_settings()

        self.render_live_preview_check = ttk.Checkbutton(
            controls, text="Live preview during render (1 frame/sec)",
            variable=self.render_live_preview_var, command=save_live_preview_setting)
        self.render_live_preview_check.pack(anchor="w", pady=(2, 0))

        # Preview fills the rest of the panel, above the controls.
        ttk.Label(right, text="Preview (πρώτο καρέ / επιλεγμένο slide)",
                  font=("Calibri", 12, "bold")).pack(pady=(8, 0))
        prev_frame = ttk.Frame(right)
        prev_frame.pack(fill='both', expand=True, padx=6, pady=5)
        # Video first, photos after - the same order the export uses.
        self.preview_video_canvas = self._build_preview_canvas(prev_frame, "ΒΙΝΤΕΟ")
        self.preview_photo_canvas = self._build_preview_canvas(prev_frame, "ΦΩΤΟΓΡΑΦΙΑ")
        ttk.Label(right, text="Κλικ σε preview = μεγέθυνση σε πραγματικό μέγεθος",
                  foreground="#666", font=("Calibri", 8)).pack(pady=(0, 5))

        if TKDND_AVAILABLE:
            self.media_canvas.drop_target_register(DND_FILES)
            self.media_canvas.dnd_bind('<<Drop>>', lambda e: self.handle_drop(e.data))


    def _build_preview_canvas(self, parent, label):
        f = ttk.Frame(parent)
        f.pack(side='left', padx=4, fill='both', expand=True)
        ttk.Label(f, text=label, font=("Calibri", 9, "bold")).pack()
        c = tk.Canvas(f, bg='black', width=180, height=180,
                      highlightthickness=1, highlightbackground='#888')
        c.pack(fill='both', expand=True)
        c.bind("<Button-1>", lambda e: self._show_preview_zoom(c))
        c.bind("<Configure>", lambda e: self._on_preview_configure(c), add="+")
        return c


    def _debounced_resize(self, event):
        if self._resize_timer is not None:
            self.root.after_cancel(self._resize_timer)
        self._resize_timer = self.root.after(200, lambda: self._on_canvas_resize(event.width))


    def _on_canvas_resize(self, width):
        self.media_canvas.itemconfig(self.canvas_window, width=width)
        if self.view_mode.get() == "thumbnails":
            self.update_media_display()

