"""A selectable modern dark or native Windows appearance for the Tk UI."""

import tkinter as tk
from tkinter import ttk


THEMES = {"Modern Dark": "modern", "Classic Windows": "classic"}

_MODERN = {
    "background": "#202127",
    "panel": "#292b31",
    "field": "#34363d",
    "text": "#f2f2f2",
    "muted": "#b8bbc2",
    "accent": "#d6b86a",
    "selected": "#444b59",
    "border": "#41434a",
}
_NEUTRAL_BACKGROUNDS = {
    "white", "#fff", "#ffffff", "#eee", "#eeeeee", "#f0f0f0", "#f4f4f4",
    "#d9d9d9", "systembuttonface", "systemwindow", "systemwindowframe",
}
_MODERN_BACKGROUNDS = {value.lower() for key, value in _MODERN.items()
                       if key in {"background", "panel", "field", "selected", "border"}}
_MODERN_FOREGROUNDS = {_MODERN["text"].lower(), _MODERN["muted"].lower()}


class ThemeMixin:
    """Configure ttk styles and recolor existing Tk widgets without touching media canvases."""

    def apply_ui_theme(self, theme=None):
        theme = theme or self.settings.get("ui_theme", "modern")
        theme = theme if theme in ("modern", "classic") else "modern"
        self.settings["ui_theme"] = theme
        style = ttk.Style(self.root)

        if theme == "modern":
            try:
                style.theme_use("clam")
            except tk.TclError:
                pass
            self._configure_modern_styles(style)
            palette = _MODERN
            self.root.option_add("*Background", palette["background"])
            self.root.option_add("*Foreground", palette["text"])
            self.root.option_add("*insertBackground", palette["text"])
        else:
            available = set(style.theme_names())
            native = next((name for name in ("vista", "xpnative", "winnative", "clam")
                           if name in available), "default")
            try:
                style.theme_use(native)
            except tk.TclError:
                pass
            palette = None
            self.root.option_add("*Background", "SystemButtonFace")
            self.root.option_add("*Foreground", "SystemWindowText")
            self.root.option_add("*insertBackground", "SystemWindowText")

        try:
            self.root.configure(bg=(palette["background"] if palette else "SystemButtonFace"))
        except tk.TclError:
            pass
        if not getattr(self, "_theme_map_bound", False):
            self.root.bind_all("<Map>", self._theme_mapped, add="+")
            self._theme_map_bound = True
        self._theme_widget_tree(self.root, palette)

    @staticmethod
    def _configure_modern_styles(style):
        p = _MODERN
        style.configure(".", background=p["background"], foreground=p["text"],
                        font=("Segoe UI", 10))
        style.configure("TFrame", background=p["background"])
        style.configure("TLabel", background=p["background"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["background"], foreground=p["muted"])
        style.configure("TLabelframe", background=p["background"], foreground=p["text"],
                        bordercolor=p["border"])
        style.configure("TLabelframe.Label", background=p["background"], foreground=p["text"])
        style.configure("TButton", background=p["panel"], foreground=p["text"],
                        bordercolor=p["border"], padding=(11, 6), focuscolor=p["accent"])
        style.map("TButton", background=[("pressed", p["accent"]), ("active", p["selected"])],
                  foreground=[("pressed", "#17181b")])
        style.configure("TEntry", fieldbackground=p["field"], foreground=p["text"],
                        insertcolor=p["text"], bordercolor=p["border"])
        style.configure("TCombobox", fieldbackground=p["field"], foreground=p["text"],
                        arrowcolor=p["text"], bordercolor=p["border"])
        style.map("TCombobox", fieldbackground=[("readonly", p["field"])],
                  foreground=[("readonly", p["text"])])
        style.configure("TCheckbutton", background=p["background"], foreground=p["text"])
        style.configure("TRadiobutton", background=p["background"], foreground=p["text"])
        style.configure("TNotebook", background=p["background"], borderwidth=0)
        style.configure("TNotebook.Tab", background=p["panel"], foreground=p["muted"],
                        padding=(12, 7))
        style.map("TNotebook.Tab", background=[("selected", p["accent"]),
                                                ("active", p["selected"])],
                  foreground=[("selected", "#17181b")])
        style.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                        foreground=p["text"], rowheight=26)
        style.map("Treeview", background=[("selected", p["selected"])])
        style.configure("TScrollbar", background=p["panel"], troughcolor=p["background"],
                        bordercolor=p["background"], arrowcolor=p["muted"])
        style.configure("Horizontal.TProgressbar", background=p["accent"],
                        troughcolor=p["panel"], bordercolor=p["border"])
        style.configure("TSeparator", background=p["border"])

    def _theme_mapped(self, event):
        widget = event.widget
        if isinstance(widget, str):
            try:
                widget = self.root.nametowidget(widget)
            except (KeyError, tk.TclError):
                return
        if not hasattr(widget, "cget"):
            return
        theme = self.settings.get("ui_theme", "modern")
        self._theme_widget(widget, _MODERN if theme == "modern" else None)

    def _theme_widget_tree(self, widget, palette):
        self._theme_widget(widget, palette)
        try:
            children = widget.winfo_children()
        except tk.TclError:
            return
        for child in children:
            self._theme_widget_tree(child, palette)

    @staticmethod
    def _theme_widget(widget, palette):
        if not hasattr(widget, "cget"):
            return
        options = ("background", "foreground", "insertbackground", "selectbackground",
                   "selectforeground", "highlightbackground")
        saved = getattr(widget, "_slideshow_original_theme", None)
        if saved is None:
            saved = {}
            for option in options:
                try:
                    saved[option] = widget.cget(option)
                except (tk.TclError, TypeError):
                    pass
            try:
                widget._slideshow_original_theme = saved
            except Exception:
                pass

        is_window = isinstance(widget, (tk.Tk, tk.Toplevel))
        if palette is None:
            if is_window and "background" in saved:
                try:
                    widget.configure(background=saved["background"])
                except tk.TclError:
                    pass
            for option, value in saved.items():
                original_value = str(value).lower()
                if option == "background" and original_value in _MODERN_BACKGROUNDS:
                    value = ("SystemWindow" if isinstance(widget, (tk.Entry, tk.Text, tk.Listbox))
                             else "SystemButtonFace")
                elif option in ("foreground", "insertbackground") and \
                        original_value in _MODERN_FOREGROUNDS:
                    value = "SystemWindowText"
                elif option == "selectbackground" and original_value == _MODERN["selected"].lower():
                    value = "SystemHighlight"
                elif option == "selectforeground" and original_value == _MODERN["text"].lower():
                    value = "SystemHighlightText"
                try:
                    if option == "background" and not is_window:
                        widget.configure(**{option: value})
                    elif option != "background":
                        widget.configure(**{option: value})
                except tk.TclError:
                    pass
            return

        if is_window:
            try:
                widget.configure(background=palette["background"])
            except tk.TclError:
                pass
            return

        try:
            background = str(saved.get("background", "")).lower()
        except Exception:
            background = ""
        if background in _NEUTRAL_BACKGROUNDS:
            target = palette["field"] if isinstance(widget, (tk.Entry, tk.Text, tk.Listbox)) else \
                     palette["panel"]
            try:
                widget.configure(background=target)
            except tk.TclError:
                pass
        if isinstance(widget, (tk.Entry, tk.Text, tk.Listbox)):
            for option, value in (("foreground", palette["text"]),
                                  ("insertbackground", palette["text"]),
                                  ("selectbackground", palette["selected"]),
                                  ("selectforeground", palette["text"])):
                try:
                    widget.configure(**{option: value})
                except tk.TclError:
                    pass
        elif isinstance(widget, tk.Label):
            foreground = str(saved.get("foreground", "")).lower()
            if foreground in {"black", "#000", "#000000", "#111", "#111111",
                              "#333", "#333333", "#555", "#555555", "#666", "#666666"}:
                try:
                    widget.configure(foreground=palette["text"])
                except tk.TclError:
                    pass
