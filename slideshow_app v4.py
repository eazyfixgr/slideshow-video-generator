"""Slideshow Video Creator Pro — entry point.

Εκτέλεση:  python "slideshow_app v4.py"

Η εφαρμογή ζει πλέον στο πακέτο ``slideshow/`` (ένα αρχείο ανά αρμοδιότητα).
Αυτό το αρχείο υπάρχει μόνο για να ξεκινάει την εφαρμογή, ώστε η εντολή που
χρησιμοποιούσες μέχρι τώρα να δουλεύει ακριβώς όπως πριν.

Η παλιά μονολιθική έκδοση φυλάσσεται στο
``old/slideshow_app v4 (single file, πριν το σπάσιμο).py``.
"""
import sys
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

# Επιτρέπει το `import slideshow` ανεξάρτητα από τον φάκελο εκτέλεσης.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:
    TkinterDnD = None


def main():
    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    root.withdraw()

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#202127")
    try:
        splash.attributes("-topmost", True)
    except tk.TclError:
        pass
    width, height = 500, 250
    x = max(0, (splash.winfo_screenwidth() - width) // 2)
    y = max(0, (splash.winfo_screenheight() - height) // 2)
    splash.geometry(f"{width}x{height}+{x}+{y}")

    card = tk.Frame(splash, bg="#202127", padx=34, pady=30)
    card.pack(fill="both", expand=True)
    tk.Label(card, text="SLIDESHOW", bg="#202127", fg="#d6b86a",
             font=("Segoe UI", 11, "bold")).pack(anchor="w")
    tk.Label(card, text="Video Creator Pro", bg="#202127", fg="#f2f2f2",
             font=("Segoe UI", 24, "bold")).pack(anchor="w", pady=(3, 4))
    status = tk.Label(card, text="Φόρτωση εφαρμογής…", bg="#202127", fg="#b8bbc2",
                      font=("Segoe UI", 10))
    status.pack(anchor="w", pady=(0, 20))
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Splash.Horizontal.TProgressbar", troughcolor="#34363d",
                    background="#d6b86a", bordercolor="#202127", lightcolor="#d6b86a",
                    darkcolor="#d6b86a")
    progress = ttk.Progressbar(card, mode="indeterminate", length=420,
                               style="Splash.Horizontal.TProgressbar")
    progress.pack(fill="x")
    progress.start(12)
    splash.update_idletasks()
    splash.update()
    splash_started = time.monotonic()

    loaded = queue.Queue()

    def import_application():
        try:
            from slideshow import deps as _deps
            from slideshow.app import SlideshowApp
            loaded.put((SlideshowApp, None))
        except BaseException as exc:
            loaded.put((None, exc))

    threading.Thread(target=import_application, daemon=True).start()

    def check_loaded():
        try:
            app_class, error = loaded.get_nowait()
        except queue.Empty:
            root.after(30, check_loaded)
            return
        if error is not None:
            progress.stop()
            splash.destroy()
            root.deiconify()
            messagebox.showerror("Startup error", f"Δεν μπόρεσα να φορτώσω την εφαρμογή:\n{error}")
            root.destroy()
            return

        try:
            status.config(text="Προετοιμασία χώρου εργασίας…")
            app = app_class(root, show_welcome=False)
        except Exception as exc:
            progress.stop()
            splash.destroy()
            root.deiconify()
            messagebox.showerror("Startup error", f"Δεν μπόρεσα να ξεκινήσω την εφαρμογή:\n{exc}")
            root.destroy()
            return

        remaining = max(0, int((2.0 - (time.monotonic() - splash_started)) * 1000) + 1)

        def finish_startup():
            progress.stop()
            splash.destroy()
            app._root_hidden_until_welcome = True
            app.show_welcome_screen()

        root.after(remaining, finish_startup)

    root.after(25, check_loaded)
    root.mainloop()


if __name__ == "__main__":
    main()
