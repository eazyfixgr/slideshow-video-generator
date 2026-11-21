"""The horizontal scene strip below the workspace."""

import os
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from .deps import Image, ImageTk
from .slide_design import normalize_presentation
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import SlimScrollbar, fit_cover, flat_button, format_duration


class StoryboardMixin:
    """The horizontal scene strip below the workspace."""

    def _build_storyboard(self, parent):
        frame = tk.Frame(parent, bg=P["panel"], height=170,
                         highlightbackground=P["border"], highlightthickness=1)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        frame.grid_propagate(False)
        frame.columnconfigure(0, weight=1)

        header = tk.Frame(frame, bg=P["panel"])
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 2))
        tk.Label(header, text="STORYBOARD", bg=P["panel"], fg=P["muted"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self.storyboard_count_var = tk.StringVar(value="0 σκηνές")
        tk.Label(header, textvariable=self.storyboard_count_var, bg=P["panel"],
                 fg=P["text"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(8, 0))
        tk.Label(header, text="Σύρε για αναδιάταξη · διπλό κλικ για επεξεργασία · "
                              "Ctrl/Shift για ομάδα και δεξί κλικ για ομαδοποίηση",
                 bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8)).pack(
            side="left", padx=(14, 0))
        canvas = tk.Canvas(frame, bg=P["panel"], highlightthickness=0, height=120)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 2))
        scrollbar = SlimScrollbar(frame, command=canvas.xview, orient="horizontal",
                                  background=P["panel"], color=P["border"],
                                  active=P["muted"])
        scrollbar.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        canvas.configure(xscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=P["panel"])
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, height=e.height))
        canvas.bind("<MouseWheel>", self._storyboard_scroll_wheel)
        inner.bind("<MouseWheel>", self._storyboard_scroll_wheel)

        self.storyboard_frame = frame
        self.storyboard_canvas = canvas
        self.storyboard_inner = inner
        self.storyboard_window = window
        self._sb_widgets = []
        self._sb_drag = None
        self._sb_anchor = None
        self._sb_token = 0
        self._sb_photo_refs = {}
        if not hasattr(self, "_sb_thumb_cache"):
            self._sb_thumb_cache = {}
        return frame

    @staticmethod
    def _storyboard_scroll_wheel(event):
        try:
            delta = int(event.delta)
        except (TypeError, ValueError):
            return None
        event.widget.xview_scroll(-1 if delta > 0 else 1, "units")
        return "break"

    def _scene_seconds(self, item):
        try:
            presentation = normalize_presentation(item[2].get("presentation"))
            override = presentation.get("duration")
            if override:
                return max(0.2, float(override))
        except (TypeError, ValueError):
            pass
        if item[0] == "video":
            cached = self._video_dur_cache.get(str(item[1]))
            if cached and cached > 0:
                return float(cached)
        try:
            return max(0.2, float(self.settings.get("slide_duration", 3)))
        except (TypeError, ValueError):
            return 3.0

    def _storyboard_thumb_key(self, item):
        path = str(item[1])
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
        return (path, mtime, str(item[2].get("presentation")), str(item[2].get("crop")),
                str(item[2].get("brightness")), str(item[2].get("color")),
                str(item[2].get("rotate", 0)), str(item[2].get("exif_orientation", 0)))

    def _make_storyboard_thumb(self, item):
        key = self._storyboard_thumb_key(item)
        cached = self._sb_thumb_cache.get(key)
        if cached is not None:
            return cached
        kind, path, edit = item
        if kind == "video":
            image = self._video_first_frame(path)
        else:
            image = self.open_thumbnail_image(path, 400, apply_exif=False)
        thumb_edit = {key: value for key, value in edit.items() if key != "erase"}
        image = self._apply_image_edit(image.copy(), thumb_edit, path, m_type=kind)
        image = fit_cover(image, 124, 58)
        self._sb_thumb_cache[key] = image
        return image

    def render_storyboard(self):
        if not hasattr(self, "storyboard_inner"):
            return
        token = getattr(self, "_sb_token", 0) + 1
        self._sb_token = token
        for child in self.storyboard_inner.winfo_children():
            child.destroy()
        self._sb_widgets = []
        self._sb_photo_refs = {}
        count = len(getattr(self, "media_files", []))
        self.storyboard_count_var.set(f"{count} {'σκηνή' if count == 1 else 'σκηνές'}")
        if not count:
            tk.Label(self.storyboard_inner, text="Οι σκηνές σου θα εμφανιστούν εδώ.",
                     bg=P["panel"], fg=P["muted"], font=("Segoe UI", 9)).pack(
                side="left", padx=16, pady=30)
            return

        start = 0.0
        pending = []
        index = 0
        while index < count:
            item = self.media_files[index]
            group_id = item[2].get("group_id")
            if group_id:
                end = index + 1
                while (end < count and
                       self.media_files[end][2].get("group_id") == group_id):
                    end += 1
                group = tk.Frame(self.storyboard_inner, bg=P["accent_faint"],
                                 highlightbackground=P["accent"],
                                 highlightthickness=2, padx=2, pady=2)
                group.pack(side="left", padx=5, pady=4)
                group.bind("<MouseWheel>", self._storyboard_scroll_wheel)
                for grouped in range(index, end):
                    item = self.media_files[grouped]
                    seconds = self._scene_seconds(item)
                    card = self._make_storyboard_card(
                        grouped, item, start, seconds, parent=group, pack=False)
                    card.pack(side="left", padx=2, pady=1)
                    start += seconds
                    self._sb_widgets.append(card)
                    key = self._storyboard_thumb_key(item)
                    cached = self._sb_thumb_cache.get(key)
                    if cached is not None:
                        self._apply_storyboard_thumb(card, grouped, cached)
                    else:
                        pending.append((grouped, item, card))
                index = end
                continue
            seconds = self._scene_seconds(item)
            card = self._make_storyboard_card(index, item, start, seconds)
            start += seconds
            self._sb_widgets.append(card)
            key = self._storyboard_thumb_key(item)
            cached = self._sb_thumb_cache.get(key)
            if cached is not None:
                self._apply_storyboard_thumb(card, index, cached)
            else:
                pending.append((index, item, card))
            index += 1
        if pending:
            self._queue_storyboard_thumbs(pending, token)

    def _make_storyboard_card(self, index, item, start, seconds, parent=None,
                              pack=True):
        selected = index in getattr(self, "selected_indices", set())
        card = tk.Frame(parent or self.storyboard_inner, bg=P["raised"],
                        width=132, height=100, highlightthickness=2,
                        highlightbackground=(P["accent"] if selected else P["border"]),
                        cursor="hand2")
        if pack:
            card.pack(side="left", padx=4, pady=7)
        card.pack_propagate(False)
        holder = tk.Frame(card, bg=P["stage"], width=124, height=58)
        holder.pack(padx=3, pady=(3, 1))
        holder.pack_propagate(False)
        thumb = tk.Label(holder, bg=P["stage"],
                         text=("▶" if item[0] == "video" else "▦"),
                         fg=P["muted"], font=("Segoe UI", 15))
        thumb.pack(fill="both", expand=True)
        row = tk.Frame(card, bg=P["raised"])
        row.pack(fill="x", padx=5)
        tk.Label(row, text=f"{index + 1:02d}", bg=P["raised"], fg=P["accent"],
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        tk.Label(row, text=f"{'βίντεο' if item[0] == 'video' else 'φωτό'} · "
                           f"{format_duration(seconds)}", bg=P["raised"], fg=P["muted"],
                 font=("Segoe UI", 7)).pack(side="right")
        time_row = tk.Frame(card, bg=P["raised"])
        time_row.pack(fill="x", padx=5)
        tk.Label(time_row, text=f"@{format_duration(start)}", bg=P["raised"],
                 fg=P["muted"], font=("Segoe UI", 7)).pack(side="left")
        tk.Label(time_row, text=Path(item[1]).name, bg=P["raised"], fg=P["muted"],
                 font=("Segoe UI", 7), anchor="e").pack(side="right")

        for widget in (card, holder, thumb, row, time_row, *row.winfo_children(),
                       *time_row.winfo_children()):
            widget.bind("<Button-1>", lambda e, i=index: self._storyboard_press(e, i))
            widget.bind("<B1-Motion>", lambda e, i=index: self._storyboard_motion(e, i))
            widget.bind("<ButtonRelease-1>", lambda e, i=index: self._storyboard_release(e, i))
            widget.bind("<Double-Button-1>", lambda e, i=index: self.open_edit_dialog(i))
            widget.bind("<Button-3>", lambda e, i=index: self.media_menu(e, i))
            widget.bind("<MouseWheel>", self._storyboard_scroll_wheel)
        card._thumb_label = thumb
        return card

    def _apply_storyboard_thumb(self, card, index, image):
        try:
            if not card.winfo_exists() or card not in self._sb_widgets:
                return
            label = getattr(card, "_thumb_label", None)
            if label is None or not label.winfo_exists():
                return
            photo = ImageTk.PhotoImage(image, master=self.root)
            self._sb_photo_refs[index] = photo
            label.configure(image=photo, text="", width=0, height=0)
        except tk.TclError:
            pass

    def _queue_storyboard_thumbs(self, pending, token):
        def worker():
            for index, item, card in pending:
                if token != getattr(self, "_sb_token", 0):
                    break
                try:
                    image = self._make_storyboard_thumb(item)
                except Exception:
                    continue
                self._post_ui(self._apply_storyboard_thumb, card, index, image)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_selection(self):
        for index, card in enumerate(getattr(self, "_sb_widgets", [])):
            selected = index in getattr(self, "selected_indices", set())
            try:
                card.configure(highlightbackground=(P["accent"] if selected
                                                    else P["border"]),
                               highlightthickness=2 if selected else 1)
            except tk.TclError:
                pass

    def _storyboard_press(self, event, index):
        self._active_media_panel = "project"
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            if index in self.selected_indices:
                self.selected_indices.discard(index)
            else:
                self.selected_indices.add(index)
            self._sb_anchor = index
        elif shift and self._sb_anchor is not None:
            a, b = sorted((self._sb_anchor, index))
            self.selected_indices = set(range(a, b + 1))
        else:
            self.selected_indices = {index}
            self._sb_anchor = index
        self._sel_anchor = min(self.selected_indices) if self.selected_indices else None
        self._refresh_selection()
        self._sb_drag = {"idx": index, "x": event.x_root, "moved": False,
                         "multi": ctrl or shift}

    def _storyboard_motion(self, event, index):
        drag = getattr(self, "_sb_drag", None)
        if not drag:
            return
        if not drag["moved"] and abs(event.x_root - drag["x"]) < 8:
            return
        drag["moved"] = True
        target = self._storyboard_index_at(event.x_root, event.y_root)
        for i, card in enumerate(self._sb_widgets):
            try:
                card.configure(highlightbackground=(P["accent"] if i == target else
                                                    (P["accent"] if i in self.selected_indices
                                                     else P["border"])))
            except tk.TclError:
                pass

    def _storyboard_release(self, event, index):
        drag = getattr(self, "_sb_drag", None)
        self._sb_drag = None
        if not drag:
            return
        if not drag["moved"]:
            if drag.get("multi"):
                self._refresh_stage()
                self._render_inspector()
                self._schedule_preview(120)
            else:
                self.select_scene(index, preview=True)
            return
        target = self._storyboard_index_at(event.x_root, event.y_root)
        if target is None or target == index:
            self.render_storyboard()
            return
        self._move_selection_to(target)

    def _storyboard_index_at(self, x_root, y_root):
        best, distance = None, float("inf")
        for index, card in enumerate(self._sb_widgets):
            try:
                x, y = card.winfo_rootx(), card.winfo_rooty()
                width, height = card.winfo_width(), card.winfo_height()
            except tk.TclError:
                continue
            if x <= x_root <= x + width and y <= y_root <= y + height:
                return index
            cx, cy = x + width / 2, y + height / 2
            current = (x_root - cx) ** 2 + (y_root - cy) ** 2
            if current < distance:
                distance, best = current, index
        return best
