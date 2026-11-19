"""Locate missing project media and safely relink existing slide entries."""

import os
from pathlib import Path
import threading

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".bmp"},
    "video": {".mp4", ".avi", ".mov", ".mkv"},
}


class MediaRecoveryMixin:
    """Recover renamed/moved source folders without importing extra media."""

    @staticmethod
    def _replace_media_path(media_files, index, new_path):
        """Replace only a media path, preserving its edit object and list slot."""
        if not 0 <= index < len(media_files):
            return False
        kind, old_path, edit = media_files[index]
        resolved = str(Path(new_path).resolve())
        if os.path.normcase(str(old_path)) == os.path.normcase(resolved):
            return False
        media_files[index] = (kind, resolved, edit)
        return True

    def _resolve_existing_project_media(self, project_path):
        """Keep existing files and resolve relative paths against likely roots."""
        project_dir = Path(project_path).resolve().parent
        missing = []
        changed = False
        roots = (Path.cwd(), project_dir, Path(getattr(self, "app_dir", project_dir)))
        for index, item in enumerate(self.media_files):
            try:
                original = Path(str(item[1])).expanduser()
            except (TypeError, ValueError, OSError):
                missing.append(index)
                continue
            candidates = [original] if original.is_absolute() else [root / original for root in roots]
            existing = next((candidate for candidate in candidates if candidate.is_file()), None)
            if existing is None:
                missing.append(index)
                continue
            if not original.is_absolute() and self._replace_media_path(
                    self.media_files, index, existing):
                changed = True
        if changed:
            self.is_modified = True
        return missing

    @staticmethod
    def _best_media_candidate(original_path, candidates, roots):
        """Select a unique basename match, favoring matching relative subfolders."""
        candidates = sorted({str(Path(path).resolve()) for path in candidates},
                            key=str.casefold)
        if len(candidates) <= 1:
            return (candidates[0] if candidates else None), False

        original_parts = Path(original_path).parts[:-1]
        scores = []
        for candidate in candidates:
            candidate_path = Path(candidate)
            best_score = 0
            for root in roots:
                try:
                    relative_parts = candidate_path.relative_to(Path(root)).parts[:-1]
                except ValueError:
                    continue
                score = 0
                for old_part, new_part in zip(reversed(original_parts),
                                              reversed(relative_parts)):
                    if old_part.casefold() != new_part.casefold():
                        break
                    score += 1
                best_score = max(best_score, score)
            scores.append(best_score)
        highest = max(scores, default=0)
        winners = [path for path, score in zip(candidates, scores) if score == highest]
        if highest > 0 and len(winners) == 1:
            return winners[0], False
        return None, True

    def _show_missing_media_recovery(self, missing_indices):
        existing = getattr(self, "_media_recovery_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    return existing
            except tk.TclError:
                pass

        missing = tuple(index for index in missing_indices
                        if 0 <= index < len(self.media_files))
        original_paths = {index: str(self.media_files[index][1]) for index in missing}
        state = {"folders": [], "candidates": {}, "automatic": {}, "manual": {},
                 "scan_id": 0, "scanning": False, "closed": False}

        dialog = tk.Toplevel(self.root)
        self._media_recovery_dialog = dialog
        dialog.title("Επανασύνδεση media project")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        dialog.geometry(f"{min(1120, max(860, int(sw * .82)))}x"
                        f"{min(760, max(560, int(sh * .82)))}")
        dialog.minsize(min(800, sw - 80), min(520, sh - 80))
        dialog.transient(self.root)
        dialog.grab_set()

        outer = ttk.Frame(dialog, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(1, weight=1)
        ttk.Label(
            outer,
            text=(f"Δεν βρέθηκαν {len(missing)} αρχεία του project. Πρόσθεσε τους φακέλους όπου "
                  "μετακινήθηκαν τα media και πάτησε Σάρωση. Τα αρχεία που υπάρχουν ήδη "
                  "παραμένουν στη θέση τους· δεν εισάγονται άσχετα αρχεία."),
            wraplength=1000, justify="left").grid(row=0, column=0, columnspan=2,
                                                    sticky="ew", pady=(0, 10))

        missing_box = ttk.LabelFrame(outer, text="Missing media του project", padding=5)
        missing_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        missing_box.rowconfigure(0, weight=1)
        missing_box.columnconfigure(0, weight=1)
        media_tree = ttk.Treeview(missing_box, columns=("kind", "name", "status"),
                                  show="headings", selectmode="browse")
        media_tree.heading("kind", text="Τύπος")
        media_tree.heading("name", text="Αρχείο")
        media_tree.heading("status", text="Κατάσταση")
        media_tree.column("kind", width=95, stretch=False)
        media_tree.column("name", width=270, stretch=True)
        media_tree.column("status", width=150, stretch=False)
        media_tree.grid(row=0, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(missing_box, orient="vertical", command=media_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        media_tree.configure(yscrollcommand=tree_scroll.set)
        for index in missing:
            kind, path, _edit = self.media_files[index]
            kind_label = "Video" if kind == "video" else "Φωτογραφία"
            media_tree.insert("", "end", iid=str(index),
                              values=(kind_label, Path(str(path)).name, "Δεν βρέθηκε"))

        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        folder_box = ttk.LabelFrame(right, text="Φάκελοι προς σάρωση", padding=5)
        folder_box.grid(row=0, column=0, sticky="ew")
        folder_list = tk.Listbox(folder_box, height=4, exportselection=False)
        folder_list.pack(fill="x", expand=True)
        folder_buttons = ttk.Frame(folder_box)
        folder_buttons.pack(fill="x", pady=(5, 0))
        add_folder_button = ttk.Button(folder_buttons, text="Προσθήκη φακέλου…")
        add_folder_button.pack(side="left", padx=(0, 4))
        scan_button = ttk.Button(folder_buttons, text="Σάρωση επιλεγμένων φακέλων")
        scan_button.pack(side="left")

        candidates_box = ttk.LabelFrame(right, text="Υποψήφια αρχεία για το επιλεγμένο media",
                                        padding=5)
        candidates_box.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        candidate_list = tk.Listbox(candidates_box, height=8, exportselection=False)
        candidate_list.pack(fill="both", expand=True)
        link_button = ttk.Button(candidates_box, text="Σύνδεση με επιλεγμένο αρχείο",
                                 state="disabled")
        link_button.pack(anchor="e", pady=(5, 0))
        status = ttk.Label(right, text="Τα αντιστοιχισμένα αρχεία αντικαθιστούν μόνο το path missing media.",
                           foreground="#666", wraplength=400, justify="left")
        status.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        progress = ttk.Label(footer, text="", foreground="#2d6cdf")
        progress.pack(side="left", fill="x", expand=True)
        continue_button = ttk.Button(footer, text="Συνέχεια")
        continue_button.pack(side="right")

        def set_media_path(index, new_path):
            changed = self._replace_media_path(self.media_files, index, new_path)
            if changed:
                self.is_modified = True
            return changed

        def current_candidates(index):
            return state["candidates"].get(index, [])

        def refresh_missing_rows():
            for index in missing:
                if index in state["manual"]:
                    label = "Συνδέθηκε χειροκίνητα"
                elif index in state["automatic"]:
                    label = "Βρέθηκε αυτόματα"
                else:
                    count = len(current_candidates(index))
                    label = (f"Επιλογή από {count}" if count > 1 else
                             "Δεν βρέθηκε")
                kind, _path, _edit = self.media_files[index]
                media_tree.item(str(index), values=(
                    "Video" if kind == "video" else "Φωτογραφία",
                    Path(original_paths[index]).name, label))
            unresolved = sum(1 for index in missing
                             if index not in state["manual"] and index not in state["automatic"])
            continue_button.config(text=f"Συνέχεια ({unresolved} missing)" if unresolved else
                                   "Συνέχεια")

        def refresh_candidates(_event=None):
            candidate_list.delete(0, tk.END)
            link_button.state(["disabled"])
            selected = media_tree.selection()
            if not selected:
                return
            index = int(selected[0])
            paths = current_candidates(index)
            for candidate in paths:
                candidate_list.insert(tk.END, candidate)
            if paths:
                candidate_list.selection_set(0)
                link_button.state(["!disabled"])

        def add_folder():
            folder = filedialog.askdirectory(parent=dialog,
                                             title="Διάλεξε φάκελο με τα αρχεία του project")
            if not folder:
                return
            folder_path = str(Path(folder).resolve())
            if any(os.path.normcase(existing) == os.path.normcase(folder_path)
                   for existing in state["folders"]):
                return
            state["folders"].append(folder_path)
            folder_list.insert(tk.END, folder_path)

        def apply_scan_results(scan_id, candidates, automatic):
            if state["closed"] or scan_id != state["scan_id"]:
                return
            state["scanning"] = False
            state["candidates"] = candidates
            state["automatic"] = automatic
            for index in missing:
                path = state["manual"].get(index) or automatic.get(index) or original_paths[index]
                if set_media_path(index, path):
                    state["manual"].pop(index, None)
            scan_button.state(["!disabled"])
            add_folder_button.state(["!disabled"])
            refresh_missing_rows()
            refresh_candidates()
            resolved = sum(1 for index in missing
                           if index in state["manual"] or index in state["automatic"])
            status.config(text=f"Βρέθηκαν {resolved} από {len(missing)} αρχεία. "
                               "Για διπλά ονόματα, επίλεξε το σωστό path στη δεξιά λίστα.")

        def scan_folders():
            if not state["folders"]:
                messagebox.showinfo("Επανασύνδεση media", "Πρόσθεσε πρώτα έναν φάκελο.", parent=dialog)
                return
            state["scan_id"] += 1
            scan_id = state["scan_id"]
            state["scanning"] = True
            scan_button.state(["disabled"])
            add_folder_button.state(["disabled"])
            status.config(text="Σαρώνω τους επιλεγμένους φακέλους…")
            roots = tuple(state["folders"])
            specs = tuple((index, self.media_files[index][0], original_paths[index])
                          for index in missing if index not in state["manual"])

            def worker():
                by_name = {}
                wanted_types = {kind for _index, kind, _original in specs}
                accepted_extensions = set().union(
                    *(MEDIA_EXTENSIONS[kind] for kind in wanted_types)) if wanted_types else set()

                def ignore_walk_error(_error):
                    pass

                for root_path in roots:
                    for directory, _subdirs, filenames in os.walk(root_path, onerror=ignore_walk_error):
                        for filename in filenames:
                            extension = Path(filename).suffix.lower()
                            if extension not in accepted_extensions:
                                continue
                            candidate = str(Path(directory, filename).resolve())
                            for kind in wanted_types:
                                if extension in MEDIA_EXTENSIONS[kind]:
                                    by_name.setdefault((kind, filename.casefold()), []).append(candidate)

                candidates, automatic = {}, {}
                for index, kind, original in specs:
                    options = sorted(set(by_name.get((kind, Path(original).name.casefold()), [])),
                                     key=str.casefold)
                    candidates[index] = options
                    selected_path, ambiguous = self._best_media_candidate(original, options, roots)
                    if selected_path and not ambiguous:
                        automatic[index] = selected_path
                self._post_ui(apply_scan_results, scan_id, candidates, automatic)

            threading.Thread(target=worker, daemon=True).start()

        def link_selected_candidate():
            selected_media = media_tree.selection()
            selected_candidate = candidate_list.curselection()
            if not selected_media or not selected_candidate:
                return
            index = int(selected_media[0])
            paths = current_candidates(index)
            if not 0 <= selected_candidate[0] < len(paths):
                return
            path = paths[selected_candidate[0]]
            state["manual"][index] = path
            state["automatic"].pop(index, None)
            set_media_path(index, path)
            refresh_missing_rows()
            status.config(text=f"Συνδέθηκε: {Path(path).name}")

        def close():
            if state["closed"]:
                return
            state["closed"] = True
            if state["scanning"]:
                state["scan_id"] += 1
            self.update_media_display()
            self._schedule_preview()
            self._media_recovery_dialog = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        media_tree.bind("<<TreeviewSelect>>", refresh_candidates)
        candidate_list.bind("<<ListboxSelect>>", lambda _event: link_button.state(["!disabled"]))
        add_folder_button.config(command=add_folder)
        scan_button.config(command=scan_folders)
        link_button.config(command=link_selected_candidate)
        continue_button.config(command=close)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Escape>", lambda _event: (close(), "break")[1])

        refresh_missing_rows()
        if missing:
            media_tree.selection_set(str(missing[0]))
            media_tree.focus(str(missing[0]))
            refresh_candidates()
        return dialog
