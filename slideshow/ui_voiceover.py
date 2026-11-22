"""Record voice-over against the running project preview and insert an audio clip."""

import threading
import time
import uuid
import tkinter as tk
from tkinter import ttk, messagebox

from .rich_text import strip_markup
from .timeline_model import audio_clip, new_track
from .voice_recording import MicrophoneRecorder, input_devices


class VoiceoverMixin:
    def show_voiceover_recorder(self):
        existing = getattr(self, "_voiceover_dialog", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            return existing
        if not self.media_files:
            messagebox.showinfo("Voice-over", "Πρόσθεσε σκηνές στο project πρώτα.")
            return
        dialog = tk.Toplevel(self.root)
        self._voiceover_dialog = dialog
        dialog.title("Voice-over — μικρόφωνο και preview")
        dialog.geometry("530x440")
        self.root.update_idletasks()
        dialog.geometry(f"+{max(0, self.root.winfo_rootx() + self.root.winfo_width() - 545)}"
                        f"+{max(0, self.root.winfo_rooty() + 80)}")
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Voice-over", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(body, text="Η εγγραφή αρχίζει στη θέση του δείκτη. Το preview παίζει χωρίς ήχο για να αποφύγεις μικροφωνισμό.",
                  wraplength=490).pack(anchor="w", pady=(2, 6))
        device = tk.StringVar()
        devices = ttk.Combobox(body, textvariable=device, values=[], state="readonly")
        devices.pack(fill="x")
        status = tk.StringVar(value="Αναζήτηση μικροφώνων…")
        ttk.Label(body, textvariable=status, wraplength=490).pack(anchor="w", pady=6)
        ttk.Label(body, text="Κείμενο εκφώνησης (προαιρετικό)").pack(anchor="w")
        script = tk.Text(body, height=8, wrap="word", font=("Segoe UI", 11), undo=True)
        script.pack(fill="both", expand=True)
        _index, item = self._selected_item()
        script.insert("1.0", strip_markup(self._caption_text_from_item(item)) if item else "")
        self._bind_text_shortcuts(script)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        state = {"recorder": None, "pending": False, "job": None, "saved": False,
                 "start": 0.0, "cancelled": False, "dialog": dialog, "status": status}
        self._voiceover_state = state
        self.root.bind("<Destroy>", lambda event: state["recorder"].stop()
                       if event.widget is self.root and state.get("recorder") is not None else None,
                       add="+")

        def available(values=None, error=None):
            if not dialog.winfo_exists():
                return
            if error or not values:
                status.set(error or "Δεν βρέθηκε μικρόφωνο. Έλεγξε Windows → Privacy → Microphone.")
            else:
                devices.configure(values=values)
                device.set(values[0])
                status.set("Έτοιμο. Τοποθέτησε τον δείκτη στο timeline και πάτησε Εγγραφή.")
                record.configure(state="normal")

        def find_devices():
            try:
                self._post_ui(available, input_devices(), None)
            except Exception as error:
                self._post_ui(available, None, str(error))
        threading.Thread(target=find_devices, daemon=True).start()

        def tick():
            if state["recorder"] is not None and not state["pending"] and dialog.winfo_exists():
                status.set(f"Εγγραφή {time.monotonic() - state['clock']:.1f}s · θέση {state['start']:.2f}s")
                state["job"] = self.root.after(100, tick)

        def started(error=None):
            state["pending"] = False
            if state["cancelled"] or not dialog.winfo_exists():
                self._stop_voiceover_capture(save=False)
                return
            if error:
                status.set(error)
                self._stop_voiceover_capture(save=False)
                record.configure(state="normal")
                return
            self._voiceover_recording = True
            state["clock"] = time.monotonic()
            stop.configure(state="normal")
            self._start_timeline_clock(state["start"], muted=True)
            tick()

        def begin():
            if state["recorder"] is not None:
                return
            self._stop_preview_play()
            recordings = self.projects_dir / "recordings"
            recordings.mkdir(exist_ok=True)
            path = recordings / f"voiceover_{uuid.uuid4().hex}.wav"
            state.update(start=float(getattr(self, "_playhead_seconds", 0)), saved=False,
                         pending=True, cancelled=False, recorder=MicrophoneRecorder(device.get(), path))
            record.configure(state="disabled")
            status.set("Εκκίνηση μικροφώνου…")

            def worker():
                try:
                    state["recorder"].start()
                    self._post_ui(started)
                except Exception as error:
                    self._post_ui(started, str(error))
            threading.Thread(target=worker, daemon=True).start()

        def finish():
            self._stop_voiceover_capture(save=True)
            record.configure(state="normal")
            stop.configure(state="disabled")

        def close():
            self._stop_voiceover_capture(save=True)
            dialog.destroy()
        record = ttk.Button(buttons, text="Εγγραφή", command=begin, state="disabled")
        record.pack(side="left")
        stop = ttk.Button(buttons, text="Stop / προσθήκη στο timeline", command=finish, state="disabled")
        stop.pack(side="left", padx=6)
        ttk.Button(buttons, text="Κλείσιμο", command=close).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", close)
        return dialog

    def _stop_voiceover_capture(self, save=True):
        state = getattr(self, "_voiceover_state", None)
        if not state or state.get("recorder") is None:
            return
        recorder = state["recorder"]
        state["cancelled"] = True
        length = recorder.stop()
        state["recorder"] = None
        self._voiceover_recording = False
        if state.get("job"):
            self.root.after_cancel(state["job"])
            state["job"] = None
        self._stop_preview_play()
        if save and length > .05 and not state["saved"]:
            self.push_undo()
            audio = self._manual_audio()
            track = next((item for item in audio["tracks"] if item["name"] == "Voice-over"), None)
            if track is None:
                track = new_track("Voice-over")
                audio["tracks"].append(track)
            track["clips"].append(audio_clip(str(recorder.path), length, state["start"], recording=True))
            state["saved"] = True
            self._audio_changed()
            if state["dialog"].winfo_exists():
                state["status"].set(f"Προστέθηκε voice-over {length:.1f}s στο timeline.")
        elif not save:
            recorder.path.unlink(missing_ok=True)
