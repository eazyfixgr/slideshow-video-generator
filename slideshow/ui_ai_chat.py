"""A persistent project conversation that can make validated, undoable edits."""

import copy
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from .ai_chat import apply_chat_edits, chat_messages, project_context, project_fingerprint
from .ai_director import parse_plan


class AIChatMixin:
    def _chat_api_config(self):
        # Prefer the text backend (DeepSeek by default), even if the Director
        # uses a different, image-capable provider. Reuse Director as a fallback.
        if self.ai_provider() == "local" or (self.settings.get("ai_api_key") or "").strip():
            key = "" if self.ai_provider() == "local" else self.settings.get("ai_api_key", "").strip()
            return self._ai_base_url(), key, self._ai_model()
        return self._director_config()

    def show_ai_chat(self):
        existing = getattr(self, "_chat_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        dialog = tk.Toplevel(self.root)
        self._chat_dialog = dialog
        dialog.title("Talk to AI — Project chat")
        dialog.geometry("600x700")
        dialog.minsize(470, 500)
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Talk to AI", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(body, text="Συζήτησε αλλαγές για το υπάρχον project. Κάθε αλλαγή αναιρείται με Undo.",
                  wraplength=540).pack(anchor="w", pady=(3, 8))
        transcript = scrolledtext.ScrolledText(body, wrap="word", state="disabled", font=("Segoe UI", 10))
        transcript.pack(fill="both", expand=True)
        status = tk.StringVar(value="Έτοιμο")
        ttk.Label(body, textvariable=status, wraplength=540).pack(anchor="w", pady=(6, 3))
        text = tk.Text(body, height=4, wrap="word", font=("Segoe UI", 10), undo=True)
        text.pack(fill="x")
        self._bind_text_shortcuts(text)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(8, 0))
        state = {"busy": False}

        def refresh():
            if not dialog.winfo_exists():
                return
            transcript.configure(state="normal")
            transcript.delete("1.0", "end")
            for item in getattr(self, "ai_chat_history", []):
                name = "Εσύ" if item["role"] == "user" else "AI"
                transcript.insert("end", f"{name}:\n{item['content']}\n\n")
            transcript.configure(state="disabled")
            transcript.see("end")
        self._chat_refresh_callback = refresh

        def complete(reply, error, token, fingerprint):
            if not dialog.winfo_exists():
                return
            state["busy"] = False
            send_button.configure(state="normal")
            if token != self._session_id:
                status.set("Το project άλλαξε. Το μήνυμα δεν εφαρμόστηκε.")
                refresh()
                return
            if error:
                status.set(f"Σφάλμα AI: {error}")
                return
            try:
                if project_fingerprint(self) != fingerprint:
                    raise ValueError("Το project άλλαξε όσο απαντούσε το AI. Στείλε ξανά την οδηγία.")
                message = apply_chat_edits(self, reply)
                self.ai_chat_history.append({"role": "assistant", "content": message})
                self.ai_chat_history = self.ai_chat_history[-200:]
                self.is_modified = True
                status.set("Οι αλλαγές εφαρμόστηκαν." if reply.get("operations") else "Έτοιμο")
                refresh()
            except Exception as failure:
                status.set(str(failure))

        def send(_event=None):
            if state["busy"]:
                return "break"
            instruction = text.get("1.0", "end-1c").strip()
            if not instruction:
                return "break"
            self._commit_pending_caption_apply()
            self._stop_preview_play()
            base, key, model = self._chat_api_config()
            if not key and not base.startswith(("http://localhost", "http://127.")):
                status.set("Όρισε API key στο Settings → AI Settings → AI βελτίωση κειμένου.")
                return "break"
            context = project_context(self)
            fingerprint = project_fingerprint(self)
            token = self._session_id
            messages = chat_messages(context, copy.deepcopy(self.ai_chat_history), instruction)
            self.ai_chat_history.append({"role": "user", "content": instruction})
            self.ai_chat_history = self.ai_chat_history[-200:]
            self.is_modified = True
            text.delete("1.0", "end")
            refresh()
            state["busy"] = True
            send_button.configure(state="disabled")
            status.set("Το AI ετοιμάζει την απάντηση…")

            def worker():
                try:
                    response = self._ai_call("/chat/completions", {
                        "model": model, "messages": messages, "stream": False},
                        timeout=180, key=key, base_url=base)
                    choices = response.get("choices") or []
                    result = parse_plan(choices[0]["message"]["content"] if choices else "")
                    self._post_ui(complete, result, None, token, fingerprint)
                except Exception as failure:
                    self._post_ui(complete, None, str(failure), token, fingerprint)
            threading.Thread(target=worker, daemon=True).start()
            return "break"

        send_button = ttk.Button(buttons, text="Αποστολή", command=send)
        send_button.pack(side="left")
        ttk.Button(buttons, text="Undo αλλαγής", command=self.undo).pack(side="left", padx=6)
        ttk.Button(buttons, text="Κλείσιμο", command=dialog.destroy).pack(side="right")
        text.bind("<Return>", send)
        text.bind("<Shift-Return>", lambda _e: None)
        text.bind("<Control-Return>", send)
        refresh()
        text.focus_set()
        return dialog
