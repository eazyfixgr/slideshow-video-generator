"""The app's dark design system and a native Windows fallback theme."""

import tkinter as tk
from tkinter import ttk


THEMES = {"Modern Dark": "modern", "Classic Windows": "classic"}

MODERN_PALETTE = {
    "background": "#101319",
    "panel": "#171b22",
    "raised": "#1d232c",
    "field": "#12161d",
    "text": "#f1f3f7",
    "muted": "#9da9b9",
    "accent": "#e8bd79",
    "accent_text": "#1b160d",
    "accent_faint": "#2b2619",
    "good": "#84c5a5",
    "danger": "#e89a8f",
    "selected": "#252c36",
    "border": "#2a313d",
    "line": "#2a313d",
    "stage": "#0b0e13",
}
_MODERN = MODERN_PALETTE

_NEUTRAL_BACKGROUNDS = {
    "white", "#fff", "#ffffff", "#eee", "#eeeeee", "#f0f0f0", "#f4f4f4",
    "#d9d9d9", "#f2f2f2", "systembuttonface", "systemwindow", "systemwindowframe",
}
_MODERN_BACKGROUNDS = {value.lower() for key, value in _MODERN.items()
                       if key in {"background", "panel", "raised", "field", "selected",
                                  "border", "line", "accent_faint"}}
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
            self.root.option_add("*selectBackground", palette["selected"])
            self.root.option_add("*selectForeground", palette["text"])
            self.root.option_add("*Menu.background", palette["panel"])
            self.root.option_add("*Menu.foreground", palette["text"])
            self.root.option_add("*Menu.activeBackground", palette["selected"])
            self.root.option_add("*Menu.activeForeground", palette["text"])
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
        if not getattr(self.root, "_slideshow_combobox_wheel_locked", False):
            self.root.bind_class("TCombobox", "<MouseWheel>",
                                 self._combobox_scroll)
            self.root._slideshow_combobox_wheel_locked = True
        self._theme_widget_tree(self.root, palette)

    def _combobox_scroll(self, event):
        """Scroll the panel under the pointer instead of changing the value."""
        try:
            delta = int(event.delta)
        except (TypeError, ValueError):
            delta = 0
        units = -1 if delta > 0 else 1 if delta < 0 else 0
        widget = event.widget
        while widget is not None:
            scroll = getattr(widget, "scroll", None)
            if callable(scroll):
                try:
                    if units:
                        scroll(units)
                except Exception:
                    pass
                return "break"
            widget = getattr(widget, "master", None)
        return "break"

    @staticmethod
    def _configure_modern_styles(style):
        p = _MODERN
        style.configure(".", background=p["background"], foreground=p["text"],
                        font=("Segoe UI", 10))
        style.configure("TFrame", background=p["background"])
        style.configure("Panel.TFrame", background=p["panel"])
        style.configure("Card.TFrame", background=p["raised"])
        style.configure("Stage.TFrame", background=p["stage"])
        style.configure("TLabel", background=p["background"], foreground=p["text"])
        style.configure("Panel.TLabel", background=p["panel"], foreground=p["text"])
        style.configure("Card.TLabel", background=p["raised"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["background"], foreground=p["muted"])
        style.configure("PanelMuted.TLabel", background=p["panel"], foreground=p["muted"])
        style.configure("Eyebrow.TLabel", background=p["panel"], foreground=p["muted"],
                        font=("Segoe UI", 8, "bold"))
        style.configure("Title.TLabel", background=p["background"], foreground=p["text"],
                        font=("Segoe UI", 15, "bold"))
        style.configure("PanelTitle.TLabel", background=p["panel"], foreground=p["text"],
                        font=("Segoe UI", 12, "bold"))
        style.configure("Section.TLabel", background=p["panel"], foreground=p["text"],
                        font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TLabel", background=p["background"], foreground=p["accent"],
                        font=("Segoe UI", 9, "bold"))
        style.configure("PanelAccent.TLabel", background=p["panel"], foreground=p["accent"],
                        font=("Segoe UI", 9, "bold"))
        style.configure("Good.TLabel", background=p["panel"], foreground=p["good"])
        style.configure("Danger.TLabel", background=p["panel"], foreground=p["danger"])
        style.configure("TLabelframe", background=p["background"], foreground=p["text"],
                        bordercolor=p["border"])
        style.configure("TLabelframe.Label", background=p["background"], foreground=p["text"])
        style.configure("TButton", background=p["raised"], foreground=p["text"],
                        bordercolor=p["border"], padding=(11, 6), focuscolor=p["accent"],
                        lightcolor=p["border"], darkcolor=p["border"],
                        font=("Segoe UI", 9))
        style.map("TButton", background=[("pressed", p["accent"]),
                                         ("active", p["selected"]),
                                         ("disabled", p["field"])],
                  foreground=[("pressed", p["accent_text"]),
                              ("disabled", p["muted"])],
                  lightcolor=[("active", p["border"]), ("pressed", p["accent"])],
                  darkcolor=[("active", p["border"]), ("pressed", p["accent"])],
                  bordercolor=[("focus", p["accent"]), ("active", p["border"])])
        style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_text"],
                        bordercolor=p["accent"], padding=(14, 7),
                        font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton",
                  background=[("pressed", "#f3d39b"), ("active", "#f0ca8c"),
                              ("disabled", p["field"])],
                  foreground=[("pressed", p["accent_text"]),
                              ("disabled", p["muted"])])
        style.configure("Quiet.TButton", background=p["panel"], foreground=p["muted"],
                        bordercolor=p["panel"], padding=(9, 5), font=("Segoe UI", 9))
        style.map("Quiet.TButton", background=[("active", p["selected"])],
                  foreground=[("active", p["text"]), ("disabled", p["border"])])
        style.configure("TEntry", fieldbackground=p["field"], foreground=p["text"],
                        insertcolor=p["text"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"],
                        focuscolor=p["accent"], padding=6)
        style.configure("Field.TEntry", fieldbackground=p["field"], foreground=p["text"],
                        insertcolor=p["text"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"],
                        focuscolor=p["accent"], padding=7)
        style.map("TEntry",
                  bordercolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  lightcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  darkcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  fieldbackground=[("disabled", p["panel"])],
                  foreground=[("disabled", p["muted"])])
        style.configure("TSpinbox", background=p["raised"], fieldbackground=p["field"],
                        foreground=p["text"], arrowcolor=p["text"],
                        insertcolor=p["text"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"],
                        focuscolor=p["accent"])
        style.map("TSpinbox", fieldbackground=[("readonly", p["field"]),
                                                ("disabled", p["panel"])],
                  foreground=[("readonly", p["text"]), ("disabled", p["muted"])],
                  lightcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  darkcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  arrowcolor=[("disabled", p["muted"]), ("pressed", p["accent"]),
                              ("active", p["text"])])
        style.configure("TCombobox", fieldbackground=p["field"], foreground=p["text"],
                        arrowcolor=p["text"], bordercolor=p["border"],
                        lightcolor=p["border"], darkcolor=p["border"],
                        focuscolor=p["accent"], padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", p["field"])],
                  foreground=[("readonly", p["text"])],
                  lightcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  darkcolor=[("focus", p["accent"]), ("!focus", p["border"])],
                  arrowcolor=[("active", p["accent"])])
        style.configure("TCheckbutton", background=p["background"], foreground=p["text"],
                        indicatorbackground=p["field"],
                        indicatorforeground=p["accent"],
                        upperbordercolor=p["border"], lowerbordercolor=p["border"])
        style.map("TCheckbutton", background=[("active", p["selected"])],
                  foreground=[("disabled", p["muted"]), ("active", p["text"])],
                  indicatorbackground=[("disabled", p["panel"]),
                                       ("selected", p["accent"]),
                                       ("active", p["field"])],
                  indicatorforeground=[("selected", p["accent_text"]),
                                       ("disabled", p["muted"])])
        style.configure("Panel.TCheckbutton", background=p["panel"], foreground=p["text"],
                        indicatorbackground=p["field"],
                        indicatorforeground=p["accent"],
                        upperbordercolor=p["border"], lowerbordercolor=p["border"])
        style.map("Panel.TCheckbutton", background=[("active", p["selected"])],
                  foreground=[("disabled", p["muted"]), ("active", p["text"])],
                  indicatorbackground=[("disabled", p["panel"]),
                                       ("selected", p["accent"]),
                                       ("active", p["field"])],
                  indicatorforeground=[("selected", p["accent_text"])])
        style.configure("TRadiobutton", background=p["background"], foreground=p["text"],
                        indicatorbackground=p["field"],
                        indicatorforeground=p["accent"],
                        upperbordercolor=p["border"], lowerbordercolor=p["border"])
        style.configure("Panel.TRadiobutton", background=p["panel"], foreground=p["text"],
                        indicatorbackground=p["field"],
                        indicatorforeground=p["accent"],
                        upperbordercolor=p["border"], lowerbordercolor=p["border"])
        style.map("Panel.TRadiobutton", background=[("active", p["selected"])],
                  indicatorbackground=[("selected", p["accent"]),
                                       ("active", p["field"])],
                  indicatorforeground=[("selected", p["accent_text"])])
        style.configure("TNotebook", background=p["background"], borderwidth=0)
        style.configure("TNotebook.Tab", background=p["panel"], foreground=p["muted"],
                        padding=(12, 7))
        style.map("TNotebook.Tab", background=[("selected", p["accent"]),
                                                ("active", p["selected"])],
                  foreground=[("selected", p["accent_text"])])
        style.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                        foreground=p["text"], rowheight=26, bordercolor=p["border"])
        style.map("Treeview", background=[("selected", p["selected"])])
        for scrollbar_style in ("TScrollbar", "Vertical.TScrollbar",
                                "Horizontal.TScrollbar"):
            style.configure(scrollbar_style, background=p["raised"],
                            troughcolor=p["background"], bordercolor=p["background"],
                            arrowcolor=p["muted"], lightcolor=p["raised"],
                            darkcolor=p["raised"], gripcount=0, arrowsize=12)
        style.configure("Horizontal.TProgressbar", background=p["accent"],
                        troughcolor=p["field"], bordercolor=p["border"])
        style.configure("Horizontal.TScale", background=p["accent"],
                        troughcolor=p["field"], bordercolor=p["border"],
                        lightcolor=p["accent"], darkcolor=p["accent"],
                        sliderrelief="flat", gripcount=0)
        style.map("Horizontal.TScale",
                  background=[("active", p["accent"]), ("pressed", p["accent"])],
                  troughcolor=[("active", p["field"])])
        style.configure("TSeparator", background=p["border"])
        style.configure("TPanedwindow", background=p["border"])
        style.configure("Sash", background=p["border"], sashthickness=6)

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
