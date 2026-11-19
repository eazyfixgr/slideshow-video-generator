"""Small Tk/PIL building blocks shared by the welcome screen and the editor."""

import math
import os
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from .deps import Image, ImageDraw, ImageFont, ImageTk
from .ui_theme import MODERN_PALETTE as P


def hex_to_rgb(value, fallback=(255, 255, 255)):
    try:
        value = str(value).lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return fallback


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(v))) for v in rgb[:3]))


def mix(color_a, color_b, amount):
    a, b = hex_to_rgb(color_a), hex_to_rgb(color_b)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * amount for i in range(3)))


def lighten(color, amount):
    return mix(color, "#ffffff", amount)


def darken(color, amount):
    return mix(color, "#000000", amount)


def tint(color, background, amount):
    return mix(background, color, amount)


def _font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"),
                 ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                           radius=radius, fill=255)
    return mask


def rounded_image(image, size, radius=12, background=P["raised"]):
    image = fit_cover(image, *size).convert("RGB")
    mask = rounded_mask(size, radius)
    plate = Image.new("RGB", size, background)
    plate.paste(image, (0, 0), mask)
    return plate


def fit_cover(image, width, height):
    width, height = max(1, int(width)), max(1, int(height))
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))),
                           Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def avatar_image(initials, color, size=44, background=P["panel"]):
    size = max(20, int(size))
    plate = Image.new("RGB", (size, size), background)
    circle = Image.new("L", (size, size), 0)
    ImageDraw.Draw(circle).rounded_rectangle((0, 0, size - 1, size - 1),
                                             radius=max(8, size // 3), fill=255)
    fill = Image.new("RGB", (size, size), tint(color, background, 0.22))
    plate.paste(fill, (0, 0), circle)
    draw = ImageDraw.Draw(plate)
    font = _font(max(10, int(size * 0.36)), bold=True)
    text = str(initials or "Π")[:2]
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=color)
    return plate


def hero_image(image, width, height, background=P["panel"], fade=0.55):
    width, height = max(1, int(width)), max(1, int(height))
    if image is None:
        plate = Image.new("RGB", (width, height), background)
        draw = ImageDraw.Draw(plate)
        for x in range(width):
            ratio = x / max(1, width - 1)
            draw.line((x, 0, x, height), fill=mix(background, P["accent_faint"],
                                                  ratio * 0.45))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((width * 0.55, -height * 0.4, width * 1.15, height * 1.1),
                   fill=(232, 189, 121, 38))
        plate = Image.alpha_composite(plate.convert("RGBA"), glow).convert("RGB")
        font = _font(max(24, height // 4), bold=True)
        draw = ImageDraw.Draw(plate)
        draw.text((width * 0.72, height * 0.5), "SV", font=font, fill=P["accent"],
                  anchor="mm")
        return plate

    cover = fit_cover(image, width, height).convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    fade_px = max(1, int(width * fade))
    bg_rgb = hex_to_rgb(background)
    for x in range(width):
        if x < fade_px:
            alpha = int(255 * (1 - x / fade_px))
        else:
            alpha = int(max(0, 0.18 - (x - fade_px) / max(1, width - fade_px) * 0.18) * 255)
        draw.line((x, 0, x, height), fill=(*bg_rgb, alpha))
    return Image.alpha_composite(cover, overlay).convert("RGB")


def placeholder_cover(width, height, label="", accent=P["accent"]):
    width, height = max(1, int(width)), max(1, int(height))
    plate = Image.new("RGB", (width, height), P["raised"])
    draw = ImageDraw.Draw(plate)
    for y in range(height):
        ratio = y / max(1, height - 1)
        draw.line((0, y, width, y), fill=mix(P["raised"], P["field"], ratio * 0.7))
    draw.rounded_rectangle((14, 14, width - 14, height - 14), radius=10,
                           outline=tint(accent, P["raised"], 0.35), width=1)
    font = _font(max(14, min(30, height // 4)), bold=True)
    draw.text((width / 2, height / 2), str(label or "SV")[:12], font=font,
              fill=tint(accent, P["raised"], 0.75), anchor="mm")
    return plate


def photo_for_label(image, master, cache, key, max_width=600):
    photo = ImageTk.PhotoImage(image, master=master)
    cache[key] = photo
    return photo


def format_duration(seconds):
    try:
        seconds = max(0, int(round(float(seconds))))
    except (TypeError, ValueError):
        return "—"
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


def clamp(value, low, high):
    return max(low, min(high, value))


def human_date(timestamp):
    try:
        moment = datetime.fromtimestamp(float(timestamp))
    except (TypeError, ValueError, OSError):
        return ""
    today = datetime.now().date()
    days = (today - moment.date()).days
    if days <= 0:
        return "Σήμερα"
    if days == 1:
        return "Χθες"
    if days < 7:
        return f"Πριν {days} ημέρες"
    if moment.year == today.year:
        return moment.strftime("%d %b")
    return moment.strftime("%d %b %Y")


def relative_time(timestamp):
    try:
        seconds = max(0, int(datetime.now().timestamp() - float(timestamp)))
    except (TypeError, ValueError, OSError):
        return ""
    if seconds < 60:
        return "μόλις τώρα"
    if seconds < 3600:
        return f"πριν {seconds // 60} λεπτά"
    if seconds < 86400:
        return f"πριν {seconds // 3600} ώρες"
    return human_date(timestamp)


ASPECTS = {
    "1080x1920": ("9:16", "Κάθετο"),
    "720x1280": ("9:16", "Κάθετο HD"),
    "1920x1080": ("16:9", "Οριζόντιο"),
    "1080x1350": ("4:5", "Portrait"),
    "1080x1080": ("1:1", "Τετράγωνο"),
}


def aspect_label(resolution):
    return ASPECTS.get(str(resolution), ("1:1", "Τετράγωνο"))[0]


def resolution_for_aspect(aspect):
    return {"9:16": "1080x1920", "4:5": "1080x1350", "1:1": "1080x1080",
            "16:9": "1920x1080"}.get(aspect, "1080x1080")


def scroll_wheel_units(event):
    try:
        delta = int(event.delta)
    except (TypeError, ValueError):
        delta = 0
    if delta == 0:
        return 0
    return -1 if delta > 0 else 1


def _scroll_dispatch(event):
    widget = event.widget
    if not isinstance(widget, str):
        try:
            x, y = event.x_root, event.y_root
            under = widget.winfo_containing(x, y)
        except (tk.TclError, AttributeError):
            under = None
        widget = under or widget
    while widget is not None and not isinstance(widget, ScrollFrame):
        try:
            widget = widget.master
        except AttributeError:
            widget = None
    if isinstance(widget, ScrollFrame):
        widget.scroll(scroll_wheel_units(event))
        return "break"
    return None


def _install_wheel(root):
    try:
        root = root._root()
    except AttributeError:
        pass
    if not getattr(root, "_slideshow_wheel_bound", False):
        root.bind_all("<MouseWheel>", _scroll_dispatch, add="+")
        root._slideshow_wheel_bound = True


class SlimScrollbar(tk.Canvas):
    """A thin, dark scrollbar drawn on a canvas (Windows native ones stay light)."""

    def __init__(self, parent, command, orient="vertical", background=P["background"],
                 color=P["border"], active=P["muted"], thickness=9):
        self.orient = orient
        if orient == "vertical":
            super().__init__(parent, bg=background, highlightthickness=0, bd=0,
                             width=thickness, cursor="hand2")
        else:
            super().__init__(parent, bg=background, highlightthickness=0, bd=0,
                             height=thickness, cursor="hand2")
        self._command = command
        self._color = color
        self._active_color = active
        self._first = 0.0
        self._last = 1.0
        self._drag = None
        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda _e: self._redraw(hover=True))
        self.bind("<Leave>", lambda _e: self._redraw(hover=False))

    def set(self, first, last):
        try:
            self._first, self._last = float(first), float(last)
        except (TypeError, ValueError):
            return
        self._redraw()

    def _length(self):
        return self.winfo_height() if self.orient == "vertical" else self.winfo_width()

    def _thumb_range(self):
        length = max(1, self._length())
        margin = 2
        track = max(1, length - 2 * margin)
        start = margin + track * max(0.0, min(1.0, self._first))
        end = margin + track * max(0.0, min(1.0, self._last))
        if end - start < 18:
            middle = (start + end) / 2
            start, end = middle - 9, middle + 9
        return margin, track, start, end

    def _redraw(self, hover=False):
        self.delete("thumb")
        if self._last - self._first >= 0.999:
            return
        margin, _track, start, end = self._thumb_range()
        color = self._active_color if (hover or self._drag) else self._color
        if self.orient == "vertical":
            x = max(1, self.winfo_width() // 2)
            self.create_line(x, start, x, end, width=4, capstyle="round",
                             fill=color, tags="thumb")
        else:
            y = max(1, self.winfo_height() // 2)
            self.create_line(start, y, end, y, width=4, capstyle="round",
                             fill=color, tags="thumb")

    def _on_press(self, event):
        length = max(1, self._length())
        margin, track, start, end = self._thumb_range()
        pos = event.y if self.orient == "vertical" else event.x
        if start <= pos <= end:
            self._drag = {"pos": pos, "first": self._first}
            self._redraw()
            return
        fraction = max(0.0, min(1.0, (pos - margin) / track))
        self._command("moveto", str(max(0.0, min(1.0, fraction - (
            self._last - self._first) / 2))))

    def _on_drag(self, event):
        if not self._drag:
            return
        _margin, track, _start, _end = self._thumb_range()
        pos = event.y if self.orient == "vertical" else event.x
        delta = (pos - self._drag["pos"]) / track
        self._command("moveto", str(max(0.0, min(1.0, self._drag["first"] + delta))))
        self._redraw()

    def _on_release(self, _event):
        self._drag = None
        self._redraw()


class ScrollFrame(ttk.Frame):
    """A vertically scrollable frame with a thin dark scrollbar."""

    def __init__(self, parent, background=P["background"], padding=0, **kwargs):
        super().__init__(parent, style="TFrame", **kwargs)
        self.background = background
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, bd=0)
        self.scrollbar = SlimScrollbar(self, command=self.canvas.yview,
                                       background=background)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body = tk.Frame(self.canvas, bg=background)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        _install_wheel(self.winfo_toplevel())

    def _on_body_configure(self, _event=None):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfigure(self._window, width=event.width)
        except tk.TclError:
            pass

    def scroll(self, units):
        try:
            self.canvas.yview_scroll(int(units), "units")
        except tk.TclError:
            pass

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def scroll_top(self):
        try:
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass


def flat_button(parent, text, command, background=P["raised"], foreground=P["text"],
                active_background=P["selected"], font=("Segoe UI", 9, "bold"),
                padx=12, pady=7, anchor="center", **kwargs):
    button = tk.Button(parent, text=text, command=command, bg=background, fg=foreground,
                       activebackground=active_background, activeforeground=foreground,
                       relief="flat", bd=0, highlightthickness=0, font=font,
                       padx=padx, pady=pady, cursor="hand2", anchor=anchor, **kwargs)
    return button


def primary_button(parent, text, command, **kwargs):
    return flat_button(parent, text, command, background=P["accent"],
                       foreground=P["accent_text"], active_background=lighten(P["accent"], 0.12),
                       **kwargs)


def chip(parent, text, background=P["accent_faint"], foreground=P["accent"],
         font=("Segoe UI", 8, "bold")):
    return tk.Label(parent, text=text, bg=background, fg=foreground, font=font,
                    padx=8, pady=2, bd=0, highlightthickness=0)


def bind_recursive(widget, sequence, callback):
    widget.bind(sequence, callback)
    for child in widget.winfo_children():
        bind_recursive(child, sequence, callback)


def set_cursor_recursive(widget, cursor="hand2"):
    try:
        widget.configure(cursor=cursor)
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        set_cursor_recursive(child, cursor)


def draw_safe_guides(canvas, image_box, color="#e8bd79"):
    x0, y0, x1, y1 = image_box
    width, height = x1 - x0, y1 - y0
    if width < 20 or height < 20:
        return
    left, right = x0 + width * 0.05, x1 - width * 0.05
    top, bottom = y0 + height * 0.08, y1 - height * 0.08
    canvas.create_rectangle(left, top, right, bottom, outline=color,
                            dash=(5, 4), width=1)
    canvas.create_line((left + right) / 2, y0, (left + right) / 2, y1,
                       fill=color, dash=(3, 5))
    canvas.create_line(x0, (top + bottom) / 2, x1, (top + bottom) / 2,
                       fill=color, dash=(3, 5))


def safe_stat(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def basename(path):
    try:
        return Path(path).name
    except TypeError:
        return ""
