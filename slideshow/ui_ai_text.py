"""Optional AI text improvement through an OpenAI-compatible API (DeepSeek).

The whole feature is inert until the user stores an API key in the settings,
so a machine without internet or without a key behaves exactly as before.
Only the stdlib is used for the network call - no extra dependency.
"""

import json
import threading
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODELS = ["deepseek-chat", "deepseek-reasoner"]

# A local, OpenAI-compatible server (Ollama by default; llama.cpp's server also
# speaks this API). Runs entirely on this PC, needs no API key, and keeps the
# text off the internet - good for Greek and English alike.
LOCAL_BASE_URL = "http://localhost:11434/v1"
LOCAL_MODELS = ["llama3.1", "qwen2.5", "gemma2", "mistral", "phi3"]

# The app renders **bold** out of the box, and every newline becomes its own
# line in the video, so the model is told to respect both.
SYSTEM_PROMPT = (
    "Είσαι επαγγελματίας copywriter. Παίρνεις ένα κείμενο και το ξαναγράφεις καλύτερα, "
    "χωρίς να αλλάξεις το νόημα, τα γεγονότα ή τα στοιχεία επικοινωνίας.\n"
    "Κανόνες:\n"
    "- Απάντησε ΜΟΝΟ με το βελτιωμένο κείμενο. Χωρίς σχόλια, χωρίς εισαγωγικά, χωρίς εξηγήσεις.\n"
    "- Κράτα την ίδια γλώσσα με το αρχικό κείμενο.\n"
    "- Κράτα τις αλλαγές γραμμής: κάθε γραμμή του αρχικού κειμένου εμφανίζεται σε ξεχωριστή "
    "γραμμή στο βίντεο.\n"
    "- Για έμφαση χρησιμοποίησε **έντονα** (διπλά αστεράκια). Μην χρησιμοποιείς άλλα σύμβολα "
    "markdown, ούτε emoji, hashtags ή συνδέσμους αν δεν σου ζητηθεί ρητά.\n"
    "- Μην προσθέτεις πληροφορίες που δεν υπάρχουν στο αρχικό κείμενο (τιμές, τηλέφωνα, "
    "διευθύνσεις, ονόματα)."
)

_HTTP_HINTS = {
    400: "Το αίτημα απορρίφθηκε από το AI",
    401: "Λάθος ή άκυρο API key — ξαναγράψε το στις ρυθμίσεις AI",
    402: "Το υπόλοιπο του λογαριασμού σου στο AI τελείωσε",
    403: "Το AI αρνήθηκε το αίτημα",
    404: "Το μοντέλο ή η διεύθυνση (base URL) δεν βρέθηκε — έλεγξε τις ρυθμίσεις AI",
    422: "Το AI δεν κατάλαβε το αίτημα",
    429: "Πολλά αιτήματα σε λίγο χρόνο — περίμενε λίγο και δοκίμασε ξανά",
    500: "Σφάλμα στον server του AI",
    502: "Ο server του AI δεν απάντησε σωστά",
    503: "Το AI είναι προσωρινά εκτός λειτουργίας",
}


class AITextMixin:
    """Settings, API client and helpers for the optional AI text improvement."""

    # ---------------------------------------------------------------- config
    def ai_provider(self):
        """Which backend the AI text feature talks to: 'deepseek' or 'local'."""
        return (self.settings.get("ai_provider") or "deepseek").strip().lower()

    def ai_configured(self):
        """True when the feature is on and its backend is usable.

        The cloud (DeepSeek) backend needs an API key; the local one just needs
        a URL (the server itself may not be running yet).
        """
        if not self.settings.get("ai_enabled"):
            return False
        if self.ai_provider() == "local":
            return bool((self.settings.get("ai_local_url") or "").strip()
                        or LOCAL_BASE_URL)
        return bool((self.settings.get("ai_api_key") or "").strip())

    def _ai_base_url(self, override=None):
        if override is not None:
            base = override
        elif self.ai_provider() == "local":
            base = self.settings.get("ai_local_url")
        else:
            base = self.settings.get("ai_base_url")
        fallback = LOCAL_BASE_URL if self.ai_provider() == "local" else DEFAULT_BASE_URL
        return ((base or "").strip() or fallback).rstrip("/")

    def _ai_model(self):
        if self.ai_provider() == "local":
            return (self.settings.get("ai_local_model") or "").strip() or LOCAL_MODELS[0]
        return (self.settings.get("ai_model") or "").strip() or DEEPSEEK_MODELS[0]

    def build_ai_system_prompt(self, project_instructions=""):
        """Global instructions always apply; project ones are added on top."""
        parts = [SYSTEM_PROMPT]
        g = (self.settings.get("ai_global_instructions") or "").strip()
        if g:
            parts.append("Μόνιμες οδηγίες του χρήστη (ισχύουν πάντα):\n" + g)
        p = (project_instructions or "").strip()
        if p:
            parts.append("Οδηγίες μόνο για αυτό το project:\n" + p)
        return "\n\n".join(parts)

    # ------------------------------------------------------------- API calls
    def _ai_call(self, path, payload=None, timeout=120, key=None, base_url=None):
        """One JSON call to the configured OpenAI-compatible endpoint.

        Always called from a worker thread; failures raise RuntimeError with a
        ready-to-show Greek message.
        """
        token = (key if key is not None else self.settings.get("ai_api_key") or "").strip()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(self._ai_base_url(base_url) + path, data=data,
                                     method="POST" if data is not None else "GET")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if token:      # the local server needs no key; don't send an empty header
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(self._ai_http_error(e))
        except urllib.error.URLError as e:
            raise RuntimeError(f"Δεν μπόρεσα να συνδεθώ με το AI ({e.reason}). "
                               "Έλεγξε τη σύνδεση στο internet.")
        except (TimeoutError, OSError) as e:
            raise RuntimeError(f"Το AI άργησε να απαντήσει ({e}). Δοκίμασε ξανά.")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Το AI έστειλε μη αναμενόμενη απάντηση ({e}).")

    @staticmethod
    def _ai_http_error(e):
        try:
            body = json.loads(e.read().decode("utf-8", errors="replace"))
            detail = (body.get("error") or {}).get("message") or ""
        except Exception:
            detail = ""
        hint = _HTTP_HINTS.get(e.code, f"Σφάλμα AI ({e.code})")
        return f"{hint}." + (f"\n\n{detail}" if detail else "")

    # ---------------------------------------------------------- improvement
    def improve_text_with_ai(self, text, project_instructions, apply_result, set_busy=None):
        """Rewrite ``text`` with the AI and hand the result to ``apply_result``.

        The network call runs on a daemon thread; ``apply_result(new_text)``
        and ``set_busy(False)`` always come back on the Tk main thread.
        """
        text = (text or "").strip()
        if not text:
            messagebox.showinfo("AI", "Γράψε πρώτα ένα κείμενο και μετά πάτα Βελτίωση με AI.")
            return
        if not self.ai_configured():
            if messagebox.askyesno(
                    "AI",
                    "Η βελτίωση κειμένου με AI δεν είναι ρυθμισμένη.\n\n"
                    "Θέλεις να ανοίξεις τις ρυθμίσεις AI τώρα;"):
                self.show_ai_settings()
            return
        if set_busy:
            set_busy(True)
        threading.Thread(target=self._ai_improve_worker,
                         args=(text, project_instructions, apply_result, set_busy),
                         daemon=True).start()

    def _ai_improve_worker(self, text, project_instructions, apply_result, set_busy):
        model = self._ai_model()
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.build_ai_system_prompt(project_instructions)},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }
        try:
            data = self._ai_call("/chat/completions", payload)
            choices = data.get("choices") or []
            out = (choices[0].get("message", {}).get("content") if choices else "") or ""
            out = out.strip()
            if not out:
                raise RuntimeError("Το AI δεν επέστρεψε κείμενο. Δοκίμασε ξανά.")
        except Exception as e:
            err = str(e)   # bound before the lambda: `e` is cleared at block end
            self._post_ui(self._ai_done, None, set_busy, apply_result, err)
            return
        self._post_ui(self._ai_done, out, set_busy, apply_result, None)

    def _ai_done(self, result, set_busy, apply_result, error):
        """Back on the Tk main thread: restore the UI, then show or apply."""
        if set_busy:
            set_busy(False)
        if error:
            messagebox.showerror("AI", error)
            return
        apply_result(result)

    # ------------------------------------------------------------ test/test
    def ai_test_connection(self, key, base_url, set_status, set_busy=None,
                           allow_empty_key=False):
        """Check the key against the endpoint's /models route on a worker thread."""
        if not (key or "").strip() and not allow_empty_key:
            set_status("Γράψε πρώτα το API key.", "#c0392b")
            return
        if set_busy:
            set_busy(True)
        threading.Thread(target=self._ai_test_worker,
                         args=(key, base_url, set_status, set_busy), daemon=True).start()

    def _ai_test_worker(self, key, base_url, set_status, set_busy):
        try:
            data = self._ai_call("/models", timeout=30, key=key, base_url=base_url)
            ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict)]
            ids = [i for i in ids if i]
            msg = "Το κλειδί δουλεύει." + (f"  Μοντέλα: {', '.join(ids[:6])}" if ids else "")
            color = "#1e7a34"
        except Exception as e:
            msg, color = str(e), "#c0392b"
        self._post_ui(self._ai_test_done, msg, color, set_status, set_busy)

    def _ai_test_done(self, msg, color, set_status, set_busy):
        if set_busy:
            set_busy(False)
        set_status(msg, color)

    # ---------------------------------------------------------- settings UI
    def show_ai_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("AI — Βελτίωση κειμένου (DeepSeek ή Τοπικό)")
        dlg.geometry("680x740")
        dlg.minsize(560, 460)
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()

        body, bottom = self._scrollable(dlg, 650)

        ttk.Label(body, text="Βελτίωση κειμένου με AI", font=("Calibri", 11, "bold")).pack(
            padx=20, pady=(14, 2), anchor='w')
        intro = ttk.Label(body, foreground="#555", wraplength=610, justify='left')
        intro.pack(padx=20, anchor='w', pady=(0, 8))

        enabled_var = tk.BooleanVar(value=bool(self.settings.get("ai_enabled")))
        ttk.Checkbutton(body, text="Ενεργό — εμφάνιση κουμπιών «Βελτίωση με AI»",
                        variable=enabled_var).pack(padx=20, anchor='w')

        # ---- provider ----------------------------------------------------
        provider_var = tk.StringVar(value=self.ai_provider())
        pf = ttk.LabelFrame(body, text=" Πάροχος AI ", padding=8)
        pf.pack(fill='x', padx=20, pady=(8, 4))
        ttk.Radiobutton(pf, text="DeepSeek API (διαδίκτυο)", variable=provider_var,
                        value="deepseek", command=lambda: set_provider()).pack(anchor='w')
        ttk.Radiobutton(pf, text="Τοπικό — Ollama / llama.cpp (χωρίς αποστολή πουθενά)",
                        variable=provider_var, value="local",
                        command=lambda: set_provider()).pack(anchor='w')

        fields = ttk.Frame(body)
        fields.pack(fill='x', padx=0)

        # DeepSeek fields
        ds_frame = ttk.Frame(fields)
        key_var = tk.StringVar(value=self.settings.get("ai_api_key", ""))
        kf = ttk.Frame(ds_frame)
        kf.pack(fill='x', padx=20, pady=(6, 2))
        ttk.Label(kf, text="API key:", width=14).pack(side='left')
        key_entry = ttk.Entry(kf, textvariable=key_var, show='•')
        key_entry.pack(side='left', fill='x', expand=True)

        def toggle_key():
            key_entry.config(show='' if key_entry.cget('show') else '•')
        ttk.Button(kf, text="👁", width=3, command=toggle_key).pack(side='left', padx=(4, 0))

        mf = ttk.Frame(ds_frame)
        mf.pack(fill='x', padx=20, pady=4)
        ttk.Label(mf, text="Μοντέλο:", width=14).pack(side='left')
        model_var = tk.StringVar(value=self.settings.get("ai_model", DEEPSEEK_MODELS[0]))
        ttk.Combobox(mf, textvariable=model_var, values=DEEPSEEK_MODELS,
                     width=26).pack(side='left')
        ttk.Label(mf, text="  deepseek-chat = γρήγορο, reasoner = καλύτερο κείμενο",
                  foreground="#777").pack(side='left')

        bf = ttk.Frame(ds_frame)
        bf.pack(fill='x', padx=20, pady=4)
        ttk.Label(bf, text="Base URL:", width=14).pack(side='left')
        base_var = tk.StringVar(value=self.settings.get("ai_base_url", DEFAULT_BASE_URL))
        ttk.Entry(bf, textvariable=base_var).pack(side='left', fill='x', expand=True)
        ttk.Label(ds_frame, foreground="#777", wraplength=610, justify='left',
                  text="Το κείμενο στέλνεται στους server του DeepSeek. Το κλειδί αποθηκεύεται "
                       "σε απλό κείμενο στο settings.json — μην το μοιραστείς."
                  ).pack(padx=20, anchor='w', pady=(0, 4))

        # Local fields
        loc_frame = ttk.Frame(fields)
        luf = ttk.Frame(loc_frame)
        luf.pack(fill='x', padx=20, pady=(6, 2))
        ttk.Label(luf, text="Server URL:", width=14).pack(side='left')
        local_url_var = tk.StringVar(value=self.settings.get("ai_local_url", LOCAL_BASE_URL))
        ttk.Entry(luf, textvariable=local_url_var).pack(side='left', fill='x', expand=True)

        lmf = ttk.Frame(loc_frame)
        lmf.pack(fill='x', padx=20, pady=4)
        ttk.Label(lmf, text="Μοντέλο:", width=14).pack(side='left')
        local_model_var = tk.StringVar(value=self.settings.get("ai_local_model", LOCAL_MODELS[0]))
        ttk.Combobox(lmf, textvariable=local_model_var, values=LOCAL_MODELS,
                     width=26).pack(side='left')
        ttk.Label(lmf, text="  π.χ. llama3.1, qwen2.5, gemma2", foreground="#777").pack(side='left')

        ttk.Label(loc_frame, foreground="#777", wraplength=610, justify='left',
                  text="Τρέξε στον υπολογιστή σου έναν OpenAI-compatible server:\n"
                       "  • Ollama:  ollama serve   και μετά   ollama pull llama3.1\n"
                       "  • llama.cpp:  llama-server --port 8080  →  URL http://localhost:8080/v1\n"
                       "Το κείμενο δεν φεύγει ποτέ από τον υπολογιστή σου. Η ποιότητα εξαρτάται "
                       "από το μοντέλο — για ελληνικά δοκίμασε qwen2.5."
                  ).pack(padx=20, anchor='w', pady=(0, 4))

        def set_provider():
            if provider_var.get() == "local":
                intro.config(text="Τοπικό AI: το κείμενο βελτιώνεται τοπικά, χωρίς αποστολή "
                                   "στο διαδίκτυο. Χρειάζεται ένας τοπικός server (βλ. παρακάτω).")
                ds_frame.pack_forget()
                loc_frame.pack(fill='x')
            else:
                intro.config(text="Το κείμενο που βελτιώνεις στέλνεται στους server του DeepSeek. "
                                   "Το κλειδί αποθηκεύεται σε απλό κείμενο στο settings.json — "
                                   "μην το μοιραστείς.")
                loc_frame.pack_forget()
                ds_frame.pack(fill='x')
        set_provider()

        ttk.Separator(body).pack(fill='x', padx=20, pady=(12, 6))
        ttk.Label(body, text="Παγκόσμιες οδηγίες (ισχύουν σε όλα τα projects)",
                  font=("Calibri", 10, "bold")).pack(padx=20, anchor='w')
        glob = scrolledtext.ScrolledText(body, height=8, wrap=tk.WORD, undo=True)
        glob.pack(fill='x', expand=True, padx=20, pady=(4, 2))
        glob.insert("1.0", self.settings.get("ai_global_instructions", ""))
        glob.edit_reset()

        ttk.Label(body, foreground="#777", wraplength=610, justify='left',
                  text='Παράδειγμα: «Γράψε ζεστά και σύντομα, σε πρώτο πληθυντικό. Ξεκίνα με ένα '
                       'δυνατό **έντονο** σημείο. Μέγιστο 4 γραμμές, χωρίς emoji.»'
                  ).pack(padx=20, anchor='w', pady=(0, 6))

        status_lbl = ttk.Label(body, text="", wraplength=610, justify='left')
        status_lbl.pack(padx=20, anchor='w')

        def set_status(text, color="#333"):
            status_lbl.config(text=text, foreground=color)

        btns = ttk.Frame(bottom)
        btns.pack(fill='x')

        def do_test():
            set_status("Έλεγχος...", "#333")
            if provider_var.get() == "local":
                key, base, empty = "", local_url_var.get(), True
            else:
                key, base, empty = key_var.get(), base_var.get(), False
            self.ai_test_connection(
                key, base, set_status,
                set_busy=lambda b: test_btn.config(state='disabled' if b else 'normal'),
                allow_empty_key=empty)
        test_btn = ttk.Button(btns, text="Δοκιμή σύνδεσης", command=do_test)
        test_btn.pack(side='left')

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
            dlg.destroy()

        ttk.Button(btns, text="Άκυρο", command=dlg.destroy).pack(side='right', padx=4)
        ttk.Button(btns, text="Αποθήκευση", command=save).pack(side='right')
