"""Unified AI Settings: object erase, text improvement and AI Director."""

import threading

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from .erase import DEFAULT_MODEL, MODEL_DIR_NAME, MODELS, download_model
from .ui_ai_text import (DEFAULT_BASE_URL, DEEPSEEK_MODELS, DIRECTOR_PROVIDERS,
                         LOCAL_BASE_URL, LOCAL_MODELS)


class AISettingsMixin:
    def show_ai_settings(self):
        existing = getattr(self, "_ai_settings_dialog", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.deiconify()
                    existing.lift()
                    return existing
            except tk.TclError:
                pass
        dlg = tk.Toplevel(self.root)
        self._ai_settings_dialog = dlg
        dlg.title("AI Settings")
        dlg.geometry("780x820")
        dlg.minsize(650, 620)
        dlg.transient(self.root)
        dlg.grab_set()
        notebook = ttk.Notebook(dlg)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        tabs = {
            "erase": ttk.Frame(notebook),
            "text": ttk.Frame(notebook),
            "director": ttk.Frame(notebook),
        }
        notebook.add(tabs["erase"], text="  AI σβήσιμο αντικειμένων  ")
        notebook.add(tabs["text"], text="  AI βελτίωση κειμένου  ")
        notebook.add(tabs["director"], text="  AI Director  ")
        self._build_ai_erase_tab(tabs["erase"], dlg)
        self._build_ai_text_tab(tabs["text"])
        self._build_ai_director_tab(tabs["director"])
        footer = ttk.Frame(dlg)
        footer.pack(fill="x", padx=14, pady=(0, 10))
        ttk.Button(footer, text="Κλείσιμο", command=dlg.destroy).pack(side="right")
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        return dlg

    def _build_ai_text_tab(self, parent):
        body = ttk.Frame(parent, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Βελτίωση κειμένου με AI",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(body, foreground="#666", wraplength=660, justify="left",
                  text="Χρησιμοποιείται από τα κουμπιά «Βελτίωση με AI» και το Talk to AI. "
                       "Το κείμενο στέλνεται μόνο στον πάροχο που επιλέγεις.").pack(
            anchor="w", pady=(2, 8))
        enabled_var = tk.BooleanVar(value=bool(self.settings.get("ai_enabled")))
        ttk.Checkbutton(body, text="Ενεργό", variable=enabled_var).pack(anchor="w")
        provider_var = tk.StringVar(value=self.ai_provider())
        provider_frame = ttk.LabelFrame(body, text=" Πάροχος ", padding=8)
        provider_frame.pack(fill="x", pady=(8, 4))
        ttk.Radiobutton(provider_frame, text="DeepSeek API (διαδίκτυο)",
                        variable=provider_var, value="deepseek",
                        command=lambda: toggle_provider()).pack(anchor="w")
        ttk.Radiobutton(provider_frame, text="Τοπικό Ollama / llama.cpp",
                        variable=provider_var, value="local",
                        command=lambda: toggle_provider()).pack(anchor="w")
        fields = ttk.Frame(body)
        fields.pack(fill="x")
        remote = ttk.Frame(fields)
        key_var = tk.StringVar(value=self.settings.get("ai_api_key", ""))
        key_row = ttk.Frame(remote)
        key_row.pack(fill="x", pady=3)
        ttk.Label(key_row, text="API key", width=14).pack(side="left")
        key_entry = ttk.Entry(key_row, textvariable=key_var, show="•")
        key_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(key_row, text="••", width=3,
                   command=lambda: key_entry.config(
                       show="" if key_entry.cget("show") else "•")).pack(
            side="left", padx=(4, 0))
        model_var = tk.StringVar(value=self.settings.get("ai_model", DEEPSEEK_MODELS[0]))
        model_row = ttk.Frame(remote)
        model_row.pack(fill="x", pady=3)
        ttk.Label(model_row, text="Μοντέλο", width=14).pack(side="left")
        ttk.Combobox(model_row, textvariable=model_var, values=DEEPSEEK_MODELS,
                     width=30).pack(side="left")
        base_var = tk.StringVar(value=self.settings.get("ai_base_url", DEFAULT_BASE_URL))
        base_row = ttk.Frame(remote)
        base_row.pack(fill="x", pady=3)
        ttk.Label(base_row, text="Base URL", width=14).pack(side="left")
        ttk.Entry(base_row, textvariable=base_var).pack(side="left", fill="x", expand=True)
        local = ttk.Frame(fields)
        local_url_var = tk.StringVar(value=self.settings.get("ai_local_url", LOCAL_BASE_URL))
        local_url_row = ttk.Frame(local)
        local_url_row.pack(fill="x", pady=3)
        ttk.Label(local_url_row, text="Server URL", width=14).pack(side="left")
        ttk.Entry(local_url_row, textvariable=local_url_var).pack(
            side="left", fill="x", expand=True)
        local_model_var = tk.StringVar(
            value=self.settings.get("ai_local_model", LOCAL_MODELS[0]))
        local_model_row = ttk.Frame(local)
        local_model_row.pack(fill="x", pady=3)
        ttk.Label(local_model_row, text="Μοντέλο", width=14).pack(side="left")
        ttk.Combobox(local_model_row, textvariable=local_model_var,
                     values=LOCAL_MODELS, width=30).pack(side="left")

        def toggle_provider():
            if provider_var.get() == "local":
                remote.pack_forget()
                local.pack(fill="x")
            else:
                local.pack_forget()
                remote.pack(fill="x")
        toggle_provider()

        ttk.Label(body, text="Παγκόσμιες οδηγίες για τη βελτίωση κειμένου",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 3))
        glob = scrolledtext.ScrolledText(body, height=7, wrap=tk.WORD, undo=True)
        glob.pack(fill="x", pady=(2, 4))
        glob.insert("1.0", self.settings.get("ai_global_instructions", ""))
        glob.edit_reset()
        ttk.Label(body, foreground="#777", wraplength=660, justify="left",
                  text="Μπορείς να χρησιμοποιήσεις **bold**, ##χρώμα έμφασης## "
                       "και %+1%μεγαλύτερο%% / %-1%μικρότερο%% κείμενο.").pack(
            anchor="w", pady=(0, 6))
        status = ttk.Label(body, text="", foreground="#333", wraplength=660)
        status.pack(anchor="w")

        def save():
            self.settings.update({
                "ai_enabled": bool(enabled_var.get()),
                "ai_provider": provider_var.get(),
                "ai_api_key": key_var.get().strip(),
                "ai_model": model_var.get().strip() or DEEPSEEK_MODELS[0],
                "ai_base_url": base_var.get().strip() or DEFAULT_BASE_URL,
                "ai_local_url": local_url_var.get().strip() or LOCAL_BASE_URL,
                "ai_local_model": local_model_var.get().strip() or LOCAL_MODELS[0],
                "ai_global_instructions": glob.get("1.0", tk.END).strip(),
            })
            self.save_settings()
            status.config(text="Οι ρυθμίσεις βελτίωσης κειμένου αποθηκεύτηκαν.",
                          foreground="#1e7a34")

        def test():
            status.config(text="Έλεγχος σύνδεσης...", foreground="#333")
            if provider_var.get() == "local":
                key, base, allow_empty = "", local_url_var.get(), True
            else:
                key, base, allow_empty = key_var.get(), base_var.get(), False
            self.ai_test_connection(
                key, base,
                lambda text, color="#333": status.config(text=text, foreground=color),
                allow_empty_key=allow_empty)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Δοκιμή σύνδεσης", command=test).pack(side="left")
        ttk.Button(buttons, text="Αποθήκευση", command=save).pack(side="right")

    def _build_ai_erase_tab(self, parent, dialog):
        body = ttk.Frame(parent, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="AI σβήσιμο αντικειμένων",
                  font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(body, foreground="#666", wraplength=660, justify="left",
                  text="Τοπικό μοντέλο inpainting (LaMa). Η επεξεργασία γίνεται "
                       "στον υπολογιστή σου· δεν στέλνονται φωτογραφίες στο internet.").pack(
            anchor="w", pady=(2, 10))
        engine = self._erase_engine()
        model_var = tk.StringVar(value=self.settings.get("erase_model", DEFAULT_MODEL))
        ttk.Label(body, text="Μοντέλο", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        for key, config in MODELS.items():
            ttk.Radiobutton(
                body, text=f"{config['label']} ({config['mb']} MB)",
                variable=model_var, value=key,
                command=lambda: (self.settings.__setitem__("erase_model", model_var.get()),
                                 self.save_settings(), refresh())).pack(
                anchor="w", padx=18)
        info = ttk.Label(body, text="", wraplength=660, justify="left")
        info.pack(anchor="w", pady=(6, 2))
        progress = ttk.Progressbar(body, maximum=100)
        progress.pack(fill="x", pady=(8, 3))
        note = ttk.Label(body, text="", wraplength=660, justify="left")
        note.pack(anchor="w")
        cache = ttk.Label(body, text="", foreground="#333")
        cache.pack(anchor="w", pady=(8, 0))

        def refresh_cache():
            count, total = self.erase_cache_info()
            cache.config(text=f"Cache: {count} αρχεία, {total / 1048576:.1f} MB")
        refresh_cache()
        cancel = {"value": False}
        state = {"busy": False}
        download_btn = ttk.Button(body)
        cancel_btn = ttk.Button(body, text="Ακύρωση", state="disabled",
                                command=lambda: (cancel.__setitem__("value", True),
                                                 note.config(text="Ακύρωση...")))
        clear_btn = ttk.Button(body, text="Καθαρισμός cache",
                               command=lambda: (self.clear_erase_cache(),
                                                self.__setattr__("_erase_cache", {}),
                                                refresh_cache(),
                                                note.config(text="Το cache καθαρίστηκε.")))

        def refresh():
            key = model_var.get()
            if engine.model_ready(key):
                size = engine.model_path(key).stat().st_size / 1048576
                info.config(text=f"Το μοντέλο είναι έτοιμο ({size:.0f} MB).",
                            foreground="#1e7a34")
                download_btn.config(text="Επανεγκατάσταση", state="normal")
            else:
                info.config(text="Το μοντέλο δεν έχει κατέβει ακόμη. Απαιτείται "
                                 "σύνδεση internet μόνο για τη λήψη του.",
                            foreground="#c0392b")
                download_btn.config(text=f"Λήψη μοντέλου ({MODELS[key]['mb']} MB)",
                                    state="normal")

        def set_busy(busy):
            state["busy"] = busy
            download_btn.config(state="disabled" if busy else "normal")
            cancel_btn.config(state="normal" if busy else "disabled")

        def finished(error):
            set_busy(False)
            cancel["value"] = False
            progress.config(value=0)
            if error:
                note.config(text=error, foreground="#c0392b")
            else:
                note.config(text="Το μοντέλο εγκαταστάθηκε.", foreground="#1e7a34")
                engine.prewarm()
            refresh()
            refresh_cache()

        def worker():
            def on_progress(done, total):
                pct = (done / total * 100) if total else 0
                text = (f"{done / 1048576:.0f} / {total / 1048576:.0f} MB"
                        if total else f"{done / 1048576:.0f} MB")
                self._post_ui(lambda: (progress.config(value=pct),
                                       note.config(text=text)))
            try:
                download_model(self.app_dir / MODEL_DIR_NAME, model_var.get(),
                               on_progress, lambda: cancel["value"])
                self._post_ui(finished, None)
            except Exception as error:
                self._post_ui(finished, str(error))

        def start():
            if state["busy"]:
                return
            key = model_var.get()
            if engine.model_ready(key) and not messagebox.askyesno(
                    "AI σβήσιμο", "Το μοντέλο υπάρχει. Να γίνει επανεγκατάσταση;",
                    parent=dialog):
                return
            cancel["value"] = False
            set_busy(True)
            note.config(text="Λήψη μοντέλου...", foreground="#333")
            threading.Thread(target=worker, daemon=True).start()

        download_btn.configure(command=start)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        download_btn.pack(in_=buttons, side="left")
        clear_btn.pack(in_=buttons, side="left", padx=6)
        cancel_btn.pack(in_=buttons, side="left", padx=6)
        refresh()

    def _build_ai_director_tab(self, parent):
        body = ttk.Frame(parent, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="AI Director", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(body, foreground="#666", wraplength=660, justify="left",
                  text="Ο Director φτιάχνει το πλάνο του βίντεο από το θέμα και "
                       "τη βιβλιοθήκη media. Υποστηρίζει οποιοδήποτε OpenAI-compatible "
                       "API (DeepSeek, OpenAI, OpenRouter, Ollama ή custom endpoint).").pack(
            anchor="w", pady=(2, 10))
        provider_label = {
            "deepseek": "DeepSeek", "openai": "OpenAI",
            "openrouter": "OpenRouter", "local": "Ollama (τοπικό)",
            "custom": "Custom / άλλο API",
        }.get(str(self.settings.get("ai_director_provider", "deepseek")).lower(),
              "DeepSeek")
        provider_var = tk.StringVar(value=provider_label)
        provider_row = ttk.Frame(body)
        provider_row.pack(fill="x", pady=3)
        ttk.Label(provider_row, text="Πάροχος", width=18).pack(side="left")
        provider_combo = ttk.Combobox(provider_row, textvariable=provider_var,
                                      values=list(DIRECTOR_PROVIDERS),
                                      state="readonly", width=28)
        provider_combo.pack(side="left", fill="x", expand=True)
        key_var = tk.StringVar(value=self.settings.get("ai_director_api_key", ""))
        key_row = ttk.Frame(body)
        key_row.pack(fill="x", pady=3)
        ttk.Label(key_row, text="API key", width=18).pack(side="left")
        key_entry = ttk.Entry(key_row, textvariable=key_var, show="•")
        key_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(key_row, text="••", width=3,
                   command=lambda: key_entry.config(
                       show="" if key_entry.cget("show") else "•")).pack(
            side="left", padx=(4, 0))
        ttk.Label(body, foreground="#777",
                  text="Κενό API key: χρησιμοποιείται το key της βελτίωσης κειμένου.",
                  wraplength=660).pack(anchor="w", padx=0, pady=(0, 3))
        base_var = tk.StringVar(value=self.settings.get("ai_director_base_url",
                                                        DEFAULT_BASE_URL))
        base_row = ttk.Frame(body)
        base_row.pack(fill="x", pady=3)
        ttk.Label(base_row, text="Base URL", width=18).pack(side="left")
        ttk.Entry(base_row, textvariable=base_var).pack(side="left", fill="x", expand=True)
        model_var = tk.StringVar(value=self.settings.get("ai_director_model",
                                                         "deepseek-chat"))
        model_row = ttk.Frame(body)
        model_row.pack(fill="x", pady=3)
        ttk.Label(model_row, text="Μοντέλο", width=18).pack(side="left")
        ttk.Entry(model_row, textvariable=model_var).pack(side="left", fill="x", expand=True)
        vision_var = tk.BooleanVar(value=bool(self.settings.get("ai_director_vision")))
        vision_row = ttk.Frame(body)
        vision_row.pack(fill="x", pady=(8, 3))
        ttk.Checkbutton(vision_row, text="Ανάλυση εικόνων (vision)",
                        variable=vision_var).pack(side="left")
        vision_model_var = tk.StringVar(
            value=self.settings.get("ai_director_vision_model", ""))
        vision_model_row = ttk.Frame(body)
        vision_model_row.pack(fill="x", pady=3)
        ttk.Label(vision_model_row, text="Vision model", width=18).pack(side="left")
        ttk.Entry(vision_model_row, textvariable=vision_model_var).pack(
            side="left", fill="x", expand=True)
        max_images_var = tk.StringVar(value=str(
            self.settings.get("ai_director_max_images", 8)))
        max_row = ttk.Frame(body)
        max_row.pack(fill="x", pady=3)
        ttk.Label(max_row, text="Μέγιστες εικόνες", width=18).pack(side="left")
        ttk.Spinbox(max_row, from_=0, to=20, textvariable=max_images_var,
                    width=8).pack(side="left")
        style_var = tk.StringVar(value=self.settings.get("ai_director_style", ""))
        style_row = ttk.Frame(body)
        style_row.pack(fill="x", pady=3)
        ttk.Label(style_row, text="Μόνιμο ύφος", width=18).pack(side="left")
        ttk.Entry(style_row, textvariable=style_var).pack(
            side="left", fill="x", expand=True)
        ttk.Label(body, foreground="#777", wraplength=660, justify="left",
                  text="Αν το vision δεν υποστηρίζεται από το μοντέλο, ο Director "
                       "συνεχίζει αυτόματα με metadata/filenames. Για DeepSeek δοκίμασε "
                       "πρώτα χωρίς vision· για εικόνες προτίμησε OpenAI/OpenRouter ή "
                       "τοπικό vision μοντέλο.").pack(anchor="w", pady=(6, 4))
        status = ttk.Label(body, text="", foreground="#333", wraplength=660)
        status.pack(anchor="w", pady=(4, 0))

        def apply_provider(_event=None):
            base, model, vision_model = DIRECTOR_PROVIDERS.get(
                provider_var.get(), ("", "", ""))
            if base:
                base_var.set(base)
            if model:
                model_var.set(model)
            if vision_model and not vision_model_var.get().strip():
                vision_model_var.set(vision_model)

        provider_combo.bind("<<ComboboxSelected>>", apply_provider, add="+")

        def save():
            try:
                max_images = max(0, min(20, int(float(max_images_var.get()))))
            except (TypeError, ValueError):
                max_images = 8
            provider_key = provider_var.get().split()[0].lower()
            if provider_var.get() == "OpenRouter":
                provider_key = "openrouter"
            elif provider_var.get() == "OpenAI":
                provider_key = "openai"
            elif provider_var.get().startswith("Ollama"):
                provider_key = "local"
            elif provider_var.get().startswith("Custom"):
                provider_key = "custom"
            self.settings.update({
                "ai_director_provider": provider_key,
                "ai_director_api_key": key_var.get().strip(),
                "ai_director_base_url": base_var.get().strip() or DEFAULT_BASE_URL,
                "ai_director_model": model_var.get().strip() or "deepseek-chat",
                "ai_director_vision": bool(vision_var.get()),
                "ai_director_vision_model": vision_model_var.get().strip(),
                "ai_director_max_images": max_images,
                "ai_director_style": style_var.get().strip(),
            })
            self.save_settings()
            status.config(text="Οι ρυθμίσεις του AI Director αποθηκεύτηκαν.",
                          foreground="#1e7a34")

        def test():
            status.config(text="Έλεγχος σύνδεσης...", foreground="#333")
            key = key_var.get().strip() or (self.settings.get("ai_api_key") or "").strip()
            base = (base_var.get().strip() or
                    self.settings.get("ai_director_base_url") or DEFAULT_BASE_URL)

            def worker():
                try:
                    data = self._ai_call("/models", timeout=30, key=key, base_url=base)
                    models = [item.get("id") for item in data.get("data", [])
                              if isinstance(item, dict) and item.get("id")]
                    message = ("Η σύνδεση λειτουργεί." +
                               (f" Μοντέλα: {', '.join(models[:5])}" if models else ""))
                    self._post_ui(status.config, text=message, foreground="#1e7a34")
                except Exception as error:
                    self._post_ui(status.config, text=str(error), foreground="#c0392b")
            threading.Thread(target=worker, daemon=True).start()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Δοκιμή σύνδεσης", command=test).pack(side="left")
        ttk.Button(buttons, text="Αποθήκευση", command=save).pack(side="right")
