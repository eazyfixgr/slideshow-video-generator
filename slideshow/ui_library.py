"""The media library: adding/removing/reordering items and their badges.

Supports single and multi selection (Ctrl/Shift + click), drag & drop reorder,
video duration + file name tooltips, and Undo/Redo for structural changes.
"""

import copy
import os
import re
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .deps import Image, ImageTk
from .slide_design import has_presentation_settings
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import fit_cover


class LibraryMixin:
    """The media library: adding/removing/reordering items and their badges."""

    # ----------------------------------------------------------- undo/redo
    def _editor_snapshot(self):
        return copy.deepcopy({"media": self.media_files,
                              "caption_mode": self.project_caption_mode,
                              "all": self.project_text_all,
                              "photos": self.project_text_photos,
                              "videos": self.project_text_videos,
                              "instructions": self.project_ai_instructions})

    def _restore_editor_snapshot(self, snapshot):
        self.media_files = snapshot["media"]
        self.project_caption_mode = snapshot["caption_mode"]
        self.project_text_all = snapshot["all"]
        self.project_text_photos = snapshot["photos"]
        self.project_text_videos = snapshot["videos"]
        self.project_ai_instructions = snapshot["instructions"]

    def push_undo(self):
        """Snapshot media and caption strategy before an edit."""
        self._undo_stack.append(self._editor_snapshot())
        if len(self._undo_stack) > 30:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self):
        self._commit_pending_caption_apply()
        if not self._undo_stack:
            return
        self._redo_stack.append(self._editor_snapshot())
        self._restore_editor_snapshot(self._undo_stack.pop())
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()

    def redo(self):
        self._commit_pending_caption_apply()
        if not self._redo_stack:
            return
        self._undo_stack.append(self._editor_snapshot())
        self._restore_editor_snapshot(self._redo_stack.pop())
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()

    # ------------------------------------------------------------ adding
    def import_media(self):
        """File → Import Media...: pick any mix of photos and videos at once."""
        fs = filedialog.askopenfilenames(
            title="Import Media",
            filetypes=[("Media (φωτογραφίες & βίντεο)",
                        "*.jpg *.jpeg *.png *.bmp *.mp4 *.avi *.mov *.mkv"),
                       ("Video", "*.mp4 *.avi *.mov *.mkv"),
                       ("Image", "*.jpg *.jpeg *.png *.bmp"),
                       ("All files", "*.*")])
        added = False
        for f in fs:
            ext = Path(f).suffix.lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv'):
                self.media_files.append(self._new_item("video", f))
                added = True
            elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self.media_files.append(self._new_item("image", f))
                added = True
        if added:
            self.is_modified = True
            self.update_media_display()

    def handle_drop(self, data):
        files = re.findall(r'\{([^}]*)\}', data) if '{' in data else data.split()
        added = False
        for f in files:
            f = f.strip('{} ')
            ext = Path(f).suffix.lower()
            if ext in ('.mp4', '.avi', '.mov', '.mkv'):
                self.media_files.append(self._new_item("video", f))
                added = True
            elif ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self.media_files.append(self._new_item("image", f))
                added = True
        if added:
            self.is_modified = True
            self.update_media_display()

    def add_videos(self):
        fs = filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.avi *.mov *.mkv")])
        if fs:
            for f in fs:
                self.media_files.append(self._new_item("video", f))
            self.is_modified = True
            self.update_media_display()

    def add_images(self):
        fs = filedialog.askopenfilenames(filetypes=[("Image", "*.jpg *.jpeg *.png *.bmp")])
        if fs:
            for f in fs:
                self.media_files.append(self._new_item("image", f))
            self.is_modified = True
            self.update_media_display()

    def clear_media(self):
        self._commit_pending_caption_apply()
        if self.media_files and not messagebox.askyesno(
                "Καθαρισμός", "Να αδειάσει όλη η βιβλιοθήκη;\n\n(Μπορείς να το αναιρέσεις με Undo)"):
            return
        self.push_undo()
        self.media_files = []
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()

    # ---------------------------------------------------------- selection
    def _selected(self):
        return sorted(i for i in self.selected_indices if 0 <= i < len(self.media_files))

    def _select_click(self, idx, event):
        self._commit_pending_caption_apply()
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        if ctrl:
            if idx in self.selected_indices:
                self.selected_indices.discard(idx)
            else:
                self.selected_indices.add(idx)
            self._sel_anchor = idx
        elif shift and self._sel_anchor is not None:
            a, b = sorted((self._sel_anchor, idx))
            self.selected_indices = set(range(a, b + 1))
        else:
            self.selected_indices = {idx}
            self._sel_anchor = idx
        self._refresh_selection()
        changed = getattr(self, "_selection_changed", None)
        if changed:
            changed()

    def _refresh_selection(self):
        mode = self.view_mode.get()
        indices = getattr(self, "_widget_indices", list(range(
            len(getattr(self, "_item_widgets", [])))))
        for position, w in enumerate(getattr(self, "_item_widgets", [])):
            index = indices[position] if position < len(indices) else position
            sel = index in self.selected_indices
            try:
                if mode == "list":
                    w.config(bg=(P["selected"] if sel else P["raised"]),
                             fg=P["text"])
                else:
                    w.config(highlightbackground=(P["accent"] if sel else P["border"]),
                             highlightthickness=2 if sel else 1)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ display
    def update_media_display(self):
        self.selected_indices = {i for i in self.selected_indices
                                 if 0 <= i < len(self.media_files)}
        for w in self.thumb_frame.winfo_children():
            w.destroy()
        self.thumbnails = []
        self._item_widgets = []
        filter_value = (self.library_filter_var.get()
                        if hasattr(self, "library_filter_var") else "all")
        visible = [(i, item) for i, item in enumerate(self.media_files)
                   if filter_value == "all" or item[0] == filter_value]
        self._widget_indices = [i for i, _item in visible]
        if self.view_mode.get() == "list":
            self._build_list(visible)
        else:
            self._build_icons(visible)
        self._refresh_selection()
        if not visible:
            empty = tk.Frame(self.thumb_frame, bg=P["panel"], padx=10, pady=14)
            empty.pack(fill="x", padx=6, pady=10)
            if not self.media_files:
                text = "Η βιβλιοθήκη είναι άδεια.\nΠρόσθεσε φωτογραφίες ή βίντεο."
            else:
                text = "Δεν υπάρχουν στοιχεία σε αυτό το φίλτρο."
            tk.Label(empty, text=text, bg=P["panel"], fg=P["muted"],
                     font=("Segoe UI", 9), justify="left", anchor="w",
                     wraplength=200).pack(anchor="w")
            if not self.media_files:
                tk.Button(empty, text="+  Προσθήκη media", command=self.import_media,
                          bg=P["accent"], fg=P["accent_text"], activebackground=P["accent"],
                          activeforeground=P["accent_text"], relief="flat", bd=0,
                          font=("Segoe UI", 8, "bold"), padx=10, pady=5,
                          cursor="hand2").pack(anchor="w", pady=(8, 0))
        count_var = getattr(self, "library_count_var", None)
        if count_var is not None:
            total = len(self.media_files)
            count_var.set(f"{len(visible)} / {total}" if filter_value != "all"
                          else f"{total} {'σκηνή' if total == 1 else 'σκηνές'}")
        self._schedule_preview()
        refresh_estimate = getattr(self, "_refresh_export_estimate", None)
        if refresh_estimate:
            refresh_estimate()
        storyboard = getattr(self, "render_storyboard", None)
        if storyboard:
            storyboard()
        stage = getattr(self, "_refresh_stage", None)
        if stage:
            stage()

    def _media_duration(self, m_type, path):
        if m_type != "video":
            return ""
        key = str(path)
        d = self._video_dur_cache.get(key)
        if d is None:
            try:
                d = self._video_duration(path)
            except Exception:
                d = 0.0
            self._video_dur_cache[key] = d
        return f"  ·  {self._tl_mmss(d)}" if d and d > 0 else ""

    def _build_list(self, visible):
        for i, (t, p, ed) in visible:
            icon = "▶" if t == "video" else "▦"
            mark = "  ✎" if self.has_edit(ed) else ""
            design = "  ✦" if has_presentation_settings(
                ed.get("presentation"), getattr(self, "project_template", "legacy")) else ""
            text = f"{i + 1:02d}  {icon}  {Path(p).name}{self._media_duration(t, p)}{mark}{design}"
            lbl = tk.Label(self.thumb_frame, text=text, anchor='w', bg=P["raised"],
                           fg=P["text"], padx=9, pady=5, font=("Segoe UI", 8))
            lbl.pack(fill='x', padx=4, pady=1)
            self._item_widgets.append(lbl)
            self._bind_item(lbl, i)
            self._add_tooltip(lbl, p)

    def _library_thumb_key(self, kind, path, edit):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0
        return (str(path), mtime, kind, repr(edit.get("crop")),
                str(edit.get("rotate", 0)), str(edit.get("brightness", 1)),
                str(edit.get("color", 1)), str(edit.get("exif_orientation", 0)),
                repr(edit.get("presentation")), repr(edit.get("erase")))

    def _library_duration_text(self, kind, path):
        if kind != "video":
            return ""
        duration = self._video_dur_cache.get(str(path))
        return self._tl_mmss(duration) if duration and duration > 0 else ""

    def _apply_library_thumb(self, token, outer, image, duration_text=""):
        if token != getattr(self, "_lib_thumb_token", 0):
            return
        try:
            if not outer.winfo_exists():
                return
            photo = ImageTk.PhotoImage(image)
            self.thumbnails.append(photo)
            outer._photo = photo
            label = getattr(outer, "_thumb_label", None)
            if label is not None:
                label.configure(image=photo, text="", width=0, height=0)
            duration_label = getattr(outer, "_duration_label", None)
            if duration_label is not None and duration_text:
                duration_label.configure(text=duration_text)
        except tk.TclError:
            pass

    def _library_thumb_worker(self, pending, token):
        for _index, kind, path, edit, outer, key, item_token in pending:
            if token != getattr(self, "_lib_thumb_token", 0):
                break
            try:
                if kind == "video":
                    image = self._video_first_frame(path)
                    duration = self._video_duration(path)
                    self._video_dur_cache[str(path)] = duration
                else:
                    image = self.open_thumbnail_image(path, 512, apply_exif=False)
                thumb_edit = {k: v for k, v in edit.items() if k != "erase"}
                image = self._apply_image_edit(image.copy(), thumb_edit, path, m_type=kind)
                image = fit_cover(image, 96, 68)
            except Exception:
                continue
            self._lib_thumb_cache[key] = image
            self._post_ui(self._apply_library_thumb, token, outer, image,
                          self._library_duration_text(kind, path))

    def _build_icons(self, visible):
        width = self.media_canvas.winfo_width()
        if width < 50:
            width = 230
        cols = max(1, min(3, (width - 8) // 104))
        if not hasattr(self, "_lib_thumb_cache"):
            self._lib_thumb_cache = {}
        self._lib_thumb_token = getattr(self, "_lib_thumb_token", 0) + 1
        token = self._lib_thumb_token
        pending = []
        for position, (i, (t, p, ed)) in enumerate(visible):
            outer = tk.Frame(self.thumb_frame, bg=P["raised"], bd=0,
                             highlightthickness=1, highlightbackground=P["border"])
            r, c = divmod(position, cols)
            outer.grid(row=r, column=c, padx=3, pady=3, sticky='n')
            self.thumb_frame.columnconfigure(c, weight=1)
            self._item_widgets.append(outer)

            holder = tk.Frame(outer, bg=P["stage"], width=96, height=68)
            holder.pack(padx=1, pady=1)
            holder.pack_propagate(False)
            thumb = tk.Label(holder, bg=P["stage"],
                             text=("▶" if t == "video" else "▦"),
                             fg=P["muted"], font=("Segoe UI", 14))
            thumb.pack(fill="both", expand=True)
            outer._thumb_label = thumb

            tk.Label(outer, text=str(i + 1), font=("Segoe UI", 8, "bold"),
                     fg=P["accent_text"], bg=P["accent"], padx=4).place(x=3, y=3)
            if t == "video":
                tk.Label(outer, text="▶", font=("Segoe UI", 8, "bold"),
                         fg=P["danger"], bg=P["stage"], padx=3).place(
                    relx=1.0, x=-3, y=3, anchor='ne')
                duration_label = tk.Label(outer, text="", font=("Segoe UI", 7),
                                          fg=P["text"], bg=P["stage"], padx=3)
                duration_label.place(relx=0.0, rely=1.0, x=3, y=-3, anchor='sw')
                outer._duration_label = duration_label
            if self.has_edit(ed):
                tk.Label(outer, text="✎", font=("Segoe UI", 8, "bold"),
                         fg=P["text"], bg=P["selected"], padx=3).place(
                    relx=1.0, x=-3, rely=1.0, y=-3, anchor='se')
            if has_presentation_settings(
                    ed.get("presentation"), getattr(self, "project_template", "legacy")):
                tk.Label(outer, text="✦", font=("Segoe UI", 8, "bold"),
                         fg=P["good"], bg=P["stage"], padx=3).place(
                    relx=1.0, x=-3, rely=1.0, y=-19, anchor='se')
            self._bind_tree(outer, i)
            self._add_tooltip(outer, p)

            key = self._library_thumb_key(t, p, ed)
            cached = self._lib_thumb_cache.get(key)
            if cached is not None:
                self._apply_library_thumb(token, outer, cached,
                                          self._library_duration_text(t, p))
            else:
                pending.append((i, t, p, ed, outer, key, token))
        if pending:
            threading.Thread(target=self._library_thumb_worker,
                             args=(pending, token), daemon=True).start()

    # -------------------------------------------------------- item events
    def _bind_tree(self, widget, idx):
        self._bind_item(widget, idx)
        for c in widget.winfo_children():
            self._bind_tree(c, idx)

    def _bind_item(self, w, idx):
        w.bind("<Button-1>", lambda e, i=idx: self._on_item_press(e, i))
        w.bind("<B1-Motion>", lambda e, i=idx: self._on_item_motion(e, i))
        w.bind("<ButtonRelease-1>", lambda e, i=idx: self._on_item_release(e, i))
        w.bind("<Double-Button-1>", lambda e, i=idx: self.open_edit_dialog(i))
        w.bind("<Button-3>", lambda e, i=idx: self.media_menu(e, i))

    def _on_item_press(self, event, idx):
        if idx not in self.selected_indices or (event.state & 0x0004):
            self._select_click(idx, event)
        self._drag = {"idx": idx, "x0": event.x_root, "y0": event.y_root, "moved": False}

    def _on_item_motion(self, event, idx):
        d = getattr(self, "_drag", None)
        if not d:
            return
        if not d["moved"] and (abs(event.x_root - d["x0"]) + abs(event.y_root - d["y0"])) < 6:
            return
        d["moved"] = True
        self._show_drop_marker(self._index_at_pointer(event.x_root, event.y_root))

    def _on_item_release(self, event, idx):
        d = getattr(self, "_drag", None)
        self._drag = None
        if not d or not d["moved"]:
            return
        self._move_selection_to(self._index_at_pointer(event.x_root, event.y_root))

    def _index_at_pointer(self, xr, yr):
        best, bd = None, float("inf")
        indices = getattr(self, "_widget_indices", [])
        for position, w in enumerate(getattr(self, "_item_widgets", [])):
            index = indices[position] if position < len(indices) else position
            try:
                x, y = w.winfo_rootx(), w.winfo_rooty()
                ww, hh = w.winfo_width(), w.winfo_height()
            except tk.TclError:
                continue
            if x <= xr <= x + ww and y <= yr <= y + hh:
                return index
            cx, cy = x + ww / 2, y + hh / 2
            dist = (xr - cx) ** 2 + (yr - cy) ** 2
            if dist < bd:
                bd, best = dist, index
        return best

    def _show_drop_marker(self, tgt):
        mode = self.view_mode.get()
        indices = getattr(self, "_widget_indices", [])
        for position, w in enumerate(getattr(self, "_item_widgets", [])):
            index = indices[position] if position < len(indices) else position
            try:
                if mode == "list":
                    w.config(bg=(P["accent_faint"] if index == tgt else
                                 (P["selected"] if index in self.selected_indices
                                  else P["raised"])))
                else:
                    w.config(highlightbackground=(P["accent"] if index == tgt else
                                                 (P["accent_faint"]
                                                  if index in self.selected_indices
                                                  else P["border"])))
            except tk.TclError:
                pass

    def _move_selection_to(self, target):
        self._commit_pending_caption_apply()
        sel = self._selected()
        if not sel or target is None or target in sel:
            self._refresh_selection()
            return
        before = sum(1 for i in sel if i < target)
        insert_at = target - before
        block = [self.media_files[i] for i in sel]
        rest = [m for i, m in enumerate(self.media_files) if i not in self.selected_indices]
        self.push_undo()
        for m in block:
            rest.insert(insert_at, m)
            insert_at += 1
        self.media_files = rest
        self.selected_indices = set(range(target - before, target - before + len(block)))
        self._sel_anchor = min(self.selected_indices) if self.selected_indices else None
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()

    # ----------------------------------------------------------- tooltips
    def _add_tooltip(self, widget, path):
        def show(_e=None):
            hide()
            try:
                self._tooltip = tk.Toplevel(self.root)
                self._tooltip.wm_overrideredirect(True)
                self._tooltip.attributes("-topmost", True)
                x = widget.winfo_rootx() + 12
                y = widget.winfo_rooty() + widget.winfo_height() + 4
                self._tooltip.wm_geometry(f"+{x}+{y}")
                tk.Label(self._tooltip, text=Path(path).name, bg=P["raised"],
                         fg=P["text"], relief='solid', borderwidth=1,
                         padx=6, pady=3, font=("Segoe UI", 8)).pack()
            except Exception:
                self._tooltip = None

        def hide(_e=None):
            t = getattr(self, "_tooltip", None)
            if t is not None:
                try:
                    t.destroy()
                except Exception:
                    pass
                self._tooltip = None

        widget.bind("<Enter>", show, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    # -------------------------------------------------------------- menu
    def media_menu(self, event, idx):
        if idx not in self.selected_indices:
            self.selected_indices = {idx}
            self._sel_anchor = idx
            self._refresh_selection()
        n = len(self.selected_indices)
        m = tk.Menu(self.root, tearoff=0)
        m_type = self.media_files[idx][0]
        edit_label = "Edit (crop & trim)..." if m_type == "video" else "Edit (crop & brightness)..."
        m.add_command(label=edit_label, command=lambda: self.open_edit_dialog(idx))
        m.add_command(label="Presentation / Slide Design...",
                      command=lambda: self.open_presentation_editor(idx))
        m.add_separator()
        m.add_command(label="Delete" if n == 1 else f"Delete ({n} επιλεγμένα)",
                      command=self.delete_selected)
        m.add_command(label="Change Position", command=lambda: self.change_pos(idx))
        m.add_separator()
        m.add_command(label="Move Left/Up", command=lambda: self.move_media(idx, -1))
        m.add_command(label="Move Right/Down", command=lambda: self.move_media(idx, 1))
        m.add_separator()
        m.add_command(label="Undo", command=self.undo)
        m.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ editing
    def delete_selected(self):
        self._commit_pending_caption_apply()
        sel = self._selected()
        if not sel:
            if self.media_files:
                messagebox.showinfo("Διαγραφή", "Διάλεξε πρώτα ένα στοιχείο.")
            return
        msg = ("Να διαγραφεί το επιλεγμένο στοιχείο;" if len(sel) == 1
               else f"Να διαγραφούν {len(sel)} στοιχεία;")
        if not messagebox.askyesno("Διαγραφή", msg + "\n\n(Αναιρείται με Undo)"):
            return
        self.push_undo()
        self.media_files = [m for i, m in enumerate(self.media_files)
                            if i not in self.selected_indices]
        self.selected_indices = set()
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()

    def delete_media(self, idx):
        self.selected_indices = {idx}
        self.delete_selected()

    def change_pos(self, idx):
        new_idx = simpledialog.askinteger("Position", f"Move item {idx+1} to position:",
                                          initialvalue=idx + 1, minvalue=1,
                                          maxvalue=len(self.media_files))
        if new_idx:
            self.push_undo()
            item = self.media_files.pop(idx)
            self.media_files.insert(new_idx - 1, item)
            self.selected_indices = {new_idx - 1}
            self.is_modified = True
            self.update_media_display()
            self._refresh_inspector_after_media()

    def move_media(self, idx, d):
        sel = sorted(self._selected() or [idx])
        if not sel:
            return
        if d < 0 and sel[0] == 0:
            return
        if d > 0 and sel[-1] == len(self.media_files) - 1:
            return
        self.push_undo()
        if d < 0:
            for i in sel:
                self.media_files[i - 1], self.media_files[i] = \
                    self.media_files[i], self.media_files[i - 1]
            self.selected_indices = {i - 1 for i in sel}
        else:
            for i in reversed(sel):
                self.media_files[i + 1], self.media_files[i] = \
                    self.media_files[i], self.media_files[i + 1]
            self.selected_indices = {i + 1 for i in sel}
        self.is_modified = True
        self.update_media_display()
        self._refresh_inspector_after_media()
