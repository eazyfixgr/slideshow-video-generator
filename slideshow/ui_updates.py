"""Settings -> Updates: release comparison, download, install and restart."""

import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .updates import (UpdateCancelled, latest_release, launch_installer,
                      prepare_update, update_package)
from .version import installed_version, version_tuple


class UpdatesMixin:
    def show_updates(self):
        existing = getattr(self, "_updates_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        dialog = tk.Toplevel(self.root)
        self._updates_dialog = dialog
        dialog.title("Ενημερώσεις εφαρμογής")
        dialog.geometry("660x500")
        dialog.minsize(560, 430)
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        current = installed_version()
        kind = "windows" if getattr(sys, "frozen", False) else "source"
        ttk.Label(body, text="Ενημερώσεις", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"Εγκατεστημένη έκδοση: {current}",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 3))
        ttk.Label(body, text="Εγκατάσταση: " + ("Windows .exe" if kind == "windows" else "Python")).pack(anchor="w")
        available = tk.StringVar(value="Διαθέσιμη έκδοση: —")
        ttk.Label(body, textvariable=available).pack(anchor="w", pady=(6, 2))
        status = tk.StringVar(value="Έλεγχος GitHub Releases…")
        ttk.Label(body, textvariable=status, wraplength=590, justify="left").pack(
            anchor="w", fill="x", pady=(6, 8))
        progress = ttk.Progressbar(body, maximum=100)
        progress.pack(fill="x")
        ttk.Label(body, text="Σημειώσεις έκδοσης").pack(anchor="w", pady=(12, 3))
        notes = scrolledtext.ScrolledText(body, height=8, wrap="word", state="disabled",
                                         font=("Segoe UI", 9))
        notes.pack(fill="both", expand=True)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        state = {"package": None, "busy": False, "cancel": threading.Event(), "prepared": None}

        def exists():
            return bool(dialog.winfo_exists())

        def checking_done(release=None, package=None, error=None):
            if not exists():
                return
            state["busy"] = False
            check_btn.configure(state="normal")
            if release:
                available.set(f"Διαθέσιμη έκδοση: {release['version']}")
                notes.configure(state="normal")
                notes.delete("1.0", "end")
                notes.insert("1.0", release["notes"] or "Δεν υπάρχουν σημειώσεις έκδοσης.")
                notes.configure(state="disabled")
            if error:
                status.set(str(error))
                return
            comparison = version_tuple(release["version"]) > version_tuple(current)
            if comparison and package:
                state["package"] = package
                status.set("Υπάρχει νέα έκδοση. Πάτησε «Ενημέρωση» για λήψη και επανεκκίνηση.")
                update_btn.configure(state="normal")
            elif comparison:
                status.set("Υπάρχει νέα έκδοση, αλλά δεν παρέχει συμβατό πακέτο αυτόματης ενημέρωσης.")
            elif version_tuple(release["version"]) == version_tuple(current):
                status.set("Η εφαρμογή είναι ενημερωμένη.")
            else:
                status.set("Έχεις νεότερη έκδοση από το τελευταίο δημοσιευμένο release.")

        def check():
            if state["busy"]:
                return
            state["busy"] = True
            state["package"] = None
            if state["prepared"]:
                shutil.rmtree(state["prepared"]["work"], ignore_errors=True)
                state["prepared"] = None
            check_btn.configure(state="disabled")
            update_btn.configure(state="disabled")
            status.set("Έλεγχος GitHub Releases…")

            def worker():
                release = None
                try:
                    release = latest_release()
                    package = None
                    if version_tuple(release["version"]) > version_tuple(current):
                        package = update_package(release, kind)
                    self._post_ui(checking_done, release, package)
                except Exception as error:
                    self._post_ui(checking_done, release, None, error)
            threading.Thread(target=worker, daemon=True).start()

        def report(done, total):
            def display():
                if exists():
                    progress.configure(value=100 * done / max(1, total))
                    status.set(f"Λήψη: {done / 1048576:.1f} / {total / 1048576:.1f} MB")
            self._post_ui(display)

        def downloaded(prepared=None, error=None):
            if not exists():
                if prepared:
                    shutil.rmtree(prepared["work"], ignore_errors=True)
                return
            state["busy"] = False
            state["prepared"] = prepared
            cancel_btn.configure(state="disabled")
            check_btn.configure(state="normal")
            if error:
                status.set(str(error))
                update_btn.configure(state="normal" if state["package"] else "disabled")
                return
            self._commit_pending_caption_apply()
            if getattr(self, "is_modified", False):
                answer = messagebox.askyesnocancel(
                    "Ενημέρωση", "Να αποθηκευτεί το project πριν την επανεκκίνηση;", parent=dialog)
                if answer is None or (answer and not self.save_project()):
                    status.set("Η λήψη ολοκληρώθηκε. Πάτησε «Ενημέρωση» όταν είσαι έτοιμος.")
                    update_btn.configure(state="normal")
                    return
            try:
                self._remember_workspace_layout()
                self._save_window_state()
                self.save_settings()
                self.save_profile_registry()
                self.save_music_tracker()
                launch_installer(prepared, self.app_dir)
            except Exception as install_error:
                status.set(f"Δεν ξεκίνησε η εγκατάσταση: {install_error}")
                update_btn.configure(state="normal")
                return
            self._stop_preview_play()
            self.root.destroy()

        def update():
            if state["busy"] or not state["package"]:
                return
            if getattr(self, "_export_running", False):
                status.set("Περίμενε να ολοκληρωθεί η εξαγωγή πριν την ενημέρωση.")
                return
            if (getattr(self, "_voiceover_recording", False) or
                    (getattr(self, "_voiceover_state", None) or {}).get("recorder") is not None):
                status.set("Σταμάτησε την εγγραφή voice-over πριν την ενημέρωση.")
                return
            if state["prepared"]:
                downloaded(state["prepared"])
                return
            state["cancel"].clear()
            state["busy"] = True
            check_btn.configure(state="disabled")
            update_btn.configure(state="disabled")
            cancel_btn.configure(state="normal")
            status.set("Προετοιμασία λήψης…")

            def worker():
                try:
                    prepared = prepare_update(state["package"], report, state["cancel"])
                    self._post_ui(downloaded, prepared)
                except UpdateCancelled as error:
                    self._post_ui(downloaded, None, error)
                except Exception as error:
                    self._post_ui(downloaded, None, error)
            threading.Thread(target=worker, daemon=True).start()

        def close():
            state["cancel"].set()
            if state["prepared"]:
                shutil.rmtree(state["prepared"]["work"], ignore_errors=True)
            dialog.destroy()

        check_btn = ttk.Button(buttons, text="Έλεγχος ξανά", command=check)
        check_btn.pack(side="left")
        update_btn = ttk.Button(buttons, text="Ενημέρωση και επανεκκίνηση", command=update, state="disabled")
        update_btn.pack(side="left", padx=8)
        cancel_btn = ttk.Button(buttons, text="Ακύρωση λήψης", command=state["cancel"].set, state="disabled")
        cancel_btn.pack(side="left")
        ttk.Button(buttons, text="Κλείσιμο", command=close).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)
        check()
        return dialog
