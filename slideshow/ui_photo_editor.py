"""The photo Edit dialog: two tabs - crop/brightness/colour, and erasing."""

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from .deps import Image, ImageTk, ImageEnhance
from .ui_erase import ErasePanel


class PhotoEditorMixin:
    """The photo Edit dialog: crop / brightness / colour, plus the erase tool."""

    def _open_photo_editor(self, idx):
        _, path, edit = self.media_files[idx]
        try:
            src = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Edit", f"Δεν μπόρεσα να ανοίξω τη φωτογραφία:\n{e}")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit φωτογραφίας — {Path(path).name}")
        self._setup_edit_dialog(dlg, on_fullscreen=lambda full: recompute_preview(full))

        nb = ttk.Notebook(dlg)
        nb.pack(fill='both', expand=True, padx=10, pady=(10, 0))
        tab_crop = ttk.Frame(nb)
        tab_erase = ttk.Frame(nb)
        nb.add(tab_crop, text="  ✂  Crop & Φως  ")
        nb.add(tab_erase, text="  🧽  Σβήσιμο  ")

        # ============================ tab 1: crop / brightness / colour
        # The crop and the erase strokes are stored against the *rotated* image,
        # so rotation happens first in the render pipeline (_apply_image_edit).
        state = {"crop": list(edit["crop"]) if edit.get("crop") else None,
                 "drag": None,
                 "rotate": int(edit.get("rotate", 0) or 0) % 360}
        panel_holder = {}

        def base_image():
            return self._rotate_image(src, state["rotate"])

        prev_src = base_image()
        prev_src.thumbnail((840, 690))   # 50% bigger than the old 560x460
        pw, ph = prev_src.size

        brightness_var = tk.DoubleVar(value=float(edit.get("brightness", 1.0) or 1.0))
        color_var = tk.DoubleVar(value=float(edit.get("color", 1.0) or 1.0))

        ttk.Label(tab_crop, text="Σύρε το ποντίκι πάνω στην εικόνα για crop. Η προεπισκόπηση "
                                 "δείχνει αμέσως φωτεινότητα και χρώμα. Με ↺/↻ περιστρέφεις "
                                 "τη φωτογραφία.",
                  foreground="#555").pack(padx=12, pady=(10, 0), anchor='w')

        canvas = tk.Canvas(tab_crop, width=pw, height=ph, bg='black', cursor='crosshair',
                           highlightthickness=1, highlightbackground='#888')
        canvas.pack(padx=12, pady=8)

        def render_image():
            canvas.delete('base')
            img = prev_src
            b, c = brightness_var.get(), color_var.get()
            if abs(b - 1.0) > 1e-3:
                img = ImageEnhance.Brightness(img).enhance(b)
            if abs(c - 1.0) > 1e-3:
                img = ImageEnhance.Color(img).enhance(c)
            tk_img = ImageTk.PhotoImage(img)
            canvas.create_image(0, 0, image=tk_img, anchor='nw', tags='base')
            canvas.img_ref = tk_img
            canvas.tag_raise('ovl')

        def render_overlay():
            canvas.delete('ovl')
            self._draw_crop_overlay(canvas, state["crop"], pw, ph, tag='ovl')
            update_size_lbl()

        def render_all():
            render_image()
            render_overlay()

        def preview_max(full):
            if full:
                sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
                return max(1, int(sw * 0.80)), max(1, int(sh * 0.72))
            return 840, 690

        def refit_preview():
            nonlocal prev_src, pw, ph
            p = base_image()
            p.thumbnail(preview_max(bool(self.settings.get("edit_fullscreen", False))))
            prev_src = p
            pw, ph = p.size
            canvas.config(width=pw, height=ph)

        def recompute_preview(full):
            """Re-fit the preview to the window size (normal 1.5x, or fullscreen)."""
            refit_preview()
            render_all()

        def on_press(e):
            state["drag"] = (min(max(e.x, 0), pw), min(max(e.y, 0), ph))
            state["crop"] = None
            render_overlay()

        def on_move(e):
            if not state["drag"]:
                return
            x0, y0 = state["drag"]
            x1, y1 = min(max(e.x, 0), pw), min(max(e.y, 0), ph)
            if x1 < x0:
                x0, x1 = x1, x0
            if y1 < y0:
                y0, y1 = y1, y0
            if (x1 - x0) >= 5 and (y1 - y0) >= 5:
                state["crop"] = [x0 / pw, y0 / ph, x1 / pw, y1 / ph]
            else:
                state["crop"] = None
            render_overlay()

        def on_release(e):
            state["drag"] = None
            render_overlay()

        size_lbl = ttk.Label(tab_crop, text="", foreground="#555")
        size_lbl.pack(padx=12, anchor='w')

        def update_size_lbl():
            bw, bh = base_image().size
            crop = state["crop"]
            if crop:
                w = int(round((crop[2] - crop[0]) * bw))
                h = int(round((crop[3] - crop[1]) * bh))
                size_lbl.config(text=f"Crop: {w} x {h} px  (από {bw} x {bh})")
            else:
                size_lbl.config(text=f"Χωρίς crop — {bw} x {bh} px")

        # ---- rotation (rotates crop + erase strokes with the image) ------
        def rebuild_erase_panel(strokes):
            for w in tab_erase.winfo_children():
                w.destroy()
            panel_holder["panel"] = ErasePanel(self, tab_erase,
                                               {"erase": strokes}, base_image(), path)

        def do_rotate(delta):
            state["rotate"] = (state["rotate"] + delta) % 360
            if state["crop"]:
                state["crop"] = self.rotate_crop(state["crop"], delta)
            panel = panel_holder.get("panel")
            strokes = [self.rotate_stroke(s, delta) for s in panel.get_strokes()] if panel else []
            if panel:
                panel.close()
            refit_preview()
            rebuild_erase_panel(strokes)
            render_all()

        rot_row = ttk.Frame(tab_crop)
        rot_row.pack(padx=12, pady=(0, 2), anchor='w')
        ttk.Label(rot_row, text="Περιστροφή:").pack(side='left')
        ttk.Button(rot_row, text="↺ 90° αριστερά",
                   command=lambda: do_rotate(-90)).pack(side='left', padx=4)
        ttk.Button(rot_row, text="↻ 90° δεξιά",
                   command=lambda: do_rotate(90)).pack(side='left', padx=4)

        sl = ttk.Frame(tab_crop)
        sl.pack(fill='x', padx=14, pady=(6, 2))
        ttk.Label(sl, text="Φωτεινότητα", width=16).grid(row=0, column=0, sticky='w')
        ttk.Scale(sl, from_=0.2, to=2.0, variable=brightness_var, length=330,
                  command=lambda *a: render_image()).grid(row=0, column=1)
        b_lbl = ttk.Label(sl, width=7)
        b_lbl.grid(row=0, column=2)
        ttk.Label(sl, text="Χρώμα (κορεσμός)", width=16).grid(row=1, column=0, sticky='w')
        ttk.Scale(sl, from_=0.0, to=2.0, variable=color_var, length=330,
                  command=lambda *a: render_image()).grid(row=1, column=1)
        c_lbl = ttk.Label(sl, width=7)
        c_lbl.grid(row=1, column=2)

        def update_vals(*_):
            b_lbl.config(text=f"{brightness_var.get():.2f}x")
            c_lbl.config(text=f"{color_var.get():.2f}x")

        brightness_var.trace_add('write', update_vals)
        color_var.trace_add('write', update_vals)
        update_vals()

        # Two separate "apply to all" switches: the crop ratio and the
        # brightness/colour are independent decisions.
        apply_crop_var = tk.BooleanVar(value=False)
        apply_colour_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tab_crop, text="Ίδιο crop σε όλες τις φωτογραφίες",
                        variable=apply_crop_var).pack(padx=14, pady=(8, 0), anchor='w')
        ttk.Checkbutton(tab_crop, text="Ίδια φωτεινότητα / χρώμα σε όλες τις φωτογραφίες",
                        variable=apply_colour_var).pack(padx=14, pady=(2, 0), anchor='w')

        row_crop = ttk.Frame(tab_crop)
        row_crop.pack(pady=(8, 10))

        def clear_crop():
            state["crop"] = None
            render_overlay()

        def reset_tab1():
            brightness_var.set(1.0)
            color_var.set(1.0)
            state["crop"] = None
            render_all()

        ttk.Button(row_crop, text="Καθαρισμός crop", command=clear_crop).pack(side='left', padx=4)
        ttk.Button(row_crop, text="Επαναφορά crop & φωτός",
                   command=reset_tab1).pack(side='left', padx=4)

        canvas.bind("<Button-1>", on_press)
        canvas.bind("<B1-Motion>", on_move)
        canvas.bind("<ButtonRelease-1>", on_release)
        render_all()

        # ============================ tab 2: erase
        rebuild_erase_panel(edit.get("erase") or [])

        def _on_destroy(e):
            if e.widget is dlg and panel_holder.get("panel"):
                panel_holder["panel"].close()
        dlg.bind("<Destroy>", _on_destroy)

        # ============================ shared buttons
        btns = ttk.Frame(dlg)
        btns.pack(fill='x', padx=12, pady=10)

        def apply_and_close():
            target = self.media_files[idx][2]
            target["crop"] = list(state["crop"]) if state["crop"] else None
            target["brightness"] = round(brightness_var.get(), 4)
            target["color"] = round(color_var.get(), 4)
            target["rotate"] = int(state["rotate"]) % 360
            strokes = panel_holder["panel"].get_strokes()
            target["erase"] = strokes or None
            if apply_crop_var.get():
                for item in self.media_files:
                    if item[0] == "image":
                        item[2]["crop"] = list(target["crop"]) if target["crop"] else None
            if apply_colour_var.get():
                for item in self.media_files:
                    if item[0] == "image":
                        item[2]["brightness"] = target["brightness"]
                        item[2]["color"] = target["color"]
            self.is_modified = True
            self.update_media_display()
            dlg.destroy()

        ttk.Button(btns, text="Άκυρο", command=dlg.destroy).pack(side='right', padx=4)
        ttk.Button(btns, text="Εφαρμογή", command=apply_and_close).pack(side='right')
