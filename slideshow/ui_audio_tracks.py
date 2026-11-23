"""Timeline audio import, track/clip properties and asynchronous waveform loading."""

import copy
import json
import math
import threading
import uuid
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from .timeline_model import (audio_clip, audio_segments, cut_audio_edge, empty_audio,
                             new_track, remove_audio_range, set_audio_segments)


class AudioTracksMixin:
    def _queue_timeline_audio(self, duration):
        key = json.dumps([getattr(self, "project_audio", {}), round(duration, 4),
                          {k: self.settings.get(k) for k in ("music_folder", "volume_db", "crossfade_duration", "trim_silence")}],
                         sort_keys=True)
        if key == getattr(self, "_timeline_audio_key", None):
            return
        self._timeline_audio_key = key
        token = self._session_id

        def finished(tracks, information, error=None):
            if token != self._session_id or key != self._timeline_audio_key:
                return
            self._timeline_display_tracks = tracks
            self._timeline_waveforms = information
            if error:
                self.status.configure(text=f"Ήχος: {error}")
            elif (self.project_audio.get("mode") == "auto" and tracks and
                  self.project_audio.get("tracks") != tracks):
                self.project_audio["tracks"] = copy.deepcopy(tracks)
                self._persist_project_audio()
            self.render_storyboard()

        def worker():
            tracks, information = [], {}
            try:
                tracks = self.project_audio_plan(duration)
                for track in tracks:
                    for clip in track["clips"]:
                        if clip["path"] not in information:
                            information[clip["path"]] = self._analyze_project_audio(clip["path"])
                self._post_ui(finished, tracks, information)
            except Exception as error:
                self._post_ui(finished, tracks, information, str(error))
        threading.Thread(target=worker, daemon=True).start()

    def add_audio_files(self, track_id=None, start=None):
        paths = filedialog.askopenfilenames(title="Προσθήκη ήχου στο timeline", filetypes=[
            ("Audio", "*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.mp4 *.wma"), ("All", "*.*")])
        if not paths:
            return
        token = self._session_id
        position = float(getattr(self, "_playhead_seconds", 0) if start is None else start)
        self.status.configure(text="Ανάγνωση αρχείων ήχου…")

        def receive(values=None, error=None):
            if token != self._session_id:
                return
            if error:
                messagebox.showerror("Ήχος", str(error))
                return
            self.push_undo()
            audio = self._manual_audio()
            target_id = track_id or getattr(self, "_selected_audio_track", None)
            track = next((item for item in audio["tracks"] if item["id"] == target_id), None)
            if track is None:
                track = new_track(f"Ήχος {len(audio['tracks']) + 1}")
                audio["tracks"].append(track)
            at = position
            for path, info in values:
                track["clips"].append(audio_clip(path, info["duration"], at))
                at += info["duration"]
            self._selected_audio_track = track["id"]
            self._audio_changed()
            self.status.configure(text="Ο ήχος προστέθηκε. Σύρε το clip για θέση/track, τα άκρα για trim.")

        def worker():
            try:
                values = [(str(path), self._analyze_project_audio(path)) for path in paths]
                self._post_ui(receive, values)
            except Exception as error:
                self._post_ui(receive, None, str(error))
        threading.Thread(target=worker, daemon=True).start()

    def add_audio_track(self):
        self.push_undo()
        audio = self._manual_audio()
        track = new_track(f"Ήχος {len(audio['tracks']) + 1}")
        audio["tracks"].append(track)
        self._selected_audio_track = track["id"]
        self._audio_changed()

    def regenerate_music_plan(self):
        self.push_undo()
        self.project_audio = empty_audio()
        self._automatic_audio_cache = None
        self._timeline_audio_key = None
        self._timeline_display_tracks = []
        self._audio_changed()

    def _audio_by_id(self, clip_id):
        for track in self._manual_audio()["tracks"]:
            for clip in track["clips"]:
                if clip["id"] == clip_id:
                    return track, clip
        return None, None

    def delete_audio_clip(self, clip_id=None):
        clip_id = clip_id or getattr(self, "_selected_audio_clip", None)
        if not clip_id:
            return
        self.push_undo()
        track, clip = self._audio_by_id(clip_id)
        if clip is not None:
            track["clips"].remove(clip)
        self._selected_audio_clip = None
        self._audio_changed()

    def duplicate_audio_clip(self, clip_id):
        self.push_undo()
        track, clip = self._audio_by_id(clip_id)
        if clip is None:
            return
        copied = copy.deepcopy(clip)
        copied.update(id=uuid.uuid4().hex, start=clip["start"] + clip["duration"])
        track["clips"].append(copied)
        self._audio_changed()

    def show_audio_clip_properties(self, clip_id):
        # Opening this dialog must not turn automatic music into manual mode.
        tracks = (self.project_audio["tracks"] if self.project_audio["mode"] == "manual"
                  else getattr(self, "_timeline_display_tracks", []))
        source = next(((track, clip) for track in tracks for clip in track["clips"]
                       if clip["id"] == clip_id), None)
        if source is None:
            return
        source_track, source_clip = source
        info = self._analyze_project_audio(source_clip["path"])
        source_duration = max(.05, float(info["duration"]))
        working = copy.deepcopy(audio_segments(source_clip, source_duration))
        if not working:
            working = [[0.0, source_duration]]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Επεξεργασία ήχου — {Path(source_clip['path']).name}")
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=Path(source_clip["path"]).name,
                  font=("Segoe UI", 11, "bold"), wraplength=620).pack(anchor="w")

        labels = {f"{index + 1} — {track['name']}": track["id"]
                  for index, track in enumerate(tracks)}
        chosen = tk.StringVar(value=next(
            label for label, value in labels.items() if value == source_track["id"]))
        track_row = ttk.Frame(body)
        track_row.pack(fill="x", pady=(10, 3))
        ttk.Label(track_row, text="Audio track", width=18).pack(side="left")
        ttk.Combobox(track_row, textvariable=chosen, values=list(labels),
                     state="readonly").pack(side="left", fill="x", expand=True)

        volume_var = tk.DoubleVar(value=max(-60.0, min(20.0, float(source_clip["volume_db"]))))
        volume_text = tk.StringVar(value=f"{source_clip['volume_db']:g}")
        volume_row = ttk.Frame(body)
        volume_row.pack(fill="x", pady=3)
        ttk.Label(volume_row, text="Ένταση", width=18).pack(side="left")
        scale = ttk.Scale(volume_row, from_=-60, to=20, orient="horizontal",
                          variable=volume_var, length=330)
        scale.pack(side="left", fill="x", expand=True)
        volume_entry = ttk.Entry(volume_row, textvariable=volume_text, width=7)
        volume_entry.pack(side="left", padx=(8, 3))
        ttk.Label(volume_row, text="dB").pack(side="left")

        status = tk.StringVar()
        kept_label = tk.StringVar()

        def read_volume_text():
            try:
                value = max(-60.0, min(20.0,
                                       float(volume_text.get().replace(",", "."))))
            except ValueError:
                status.set("Η ένταση πρέπει να είναι από -60 έως +20 dB.")
                return None
            volume_var.set(value)
            volume_text.set(f"{value:g}")
            return value

        def apply_volume_text():
            read_volume_text()

        def on_scale(value):
            volume_text.set(f"{float(value):.0f}")

        scale.configure(command=on_scale)
        volume_entry.bind("<Return>", lambda _e: apply_volume_text())
        volume_entry.bind("<FocusOut>", lambda _e: apply_volume_text())

        fade_in_var = tk.StringVar(value=f"{source_clip['fade_in']:g}")
        fade_out_var = tk.StringVar(value=f"{source_clip['fade_out']:g}")
        fade_row = ttk.Frame(body)
        fade_row.pack(fill="x", pady=3)
        ttk.Label(fade_row, text="Fade in", width=12).pack(side="left")
        ttk.Entry(fade_row, textvariable=fade_in_var, width=8).pack(side="left")
        ttk.Label(fade_row, text="δευτ.").pack(side="left", padx=(3, 18))
        ttk.Label(fade_row, text="Fade out", width=10).pack(side="left")
        ttk.Entry(fade_row, textvariable=fade_out_var, width=8).pack(side="left")
        ttk.Label(fade_row, text="δευτ.").pack(side="left", padx=3)

        cut_start_var = tk.StringVar(value="0")
        cut_end_var = tk.StringVar(value="0")
        cut_row = ttk.Frame(body)
        cut_row.pack(fill="x", pady=3)
        ttk.Label(cut_row, text="Κόψιμο από αρχή", width=18).pack(side="left")
        ttk.Entry(cut_row, textvariable=cut_start_var, width=8).pack(side="left")
        ttk.Label(cut_row, text="δευτ.").pack(side="left", padx=(3, 18))
        ttk.Label(cut_row, text="Κόψιμο από τέλος", width=16).pack(side="left")
        ttk.Entry(cut_row, textvariable=cut_end_var, width=8).pack(side="left")
        ttk.Label(cut_row, text="δευτ.").pack(side="left", padx=3)

        ttk.Label(body, text="Waveform — σύρε πάνω της για να επιλέξεις κομμάτι και πάτησε «Διαγραφή επιλογής».",
                  wraplength=620).pack(anchor="w", pady=(12, 3))
        waveform = tk.Canvas(body, height=132, background="#10151f",
                             highlightthickness=0)
        waveform.pack(fill="x")
        selection = {"start": None, "end": None}
        peaks = info.get("peaks") or [0.0]

        def total_working():
            return sum(duration for _start, duration in working)

        def clamp_fades():
            total = total_working()
            for variable in (fade_in_var, fade_out_var):
                try:
                    value = max(0.0, float(variable.get().replace(",", ".")))
                except ValueError:
                    continue
                if value > total:
                    variable.set(f"{total:.2f}")

        def draw_waveform():
            width = max(20, waveform.winfo_width())
            height = 132
            waveform.delete("all")
            waveform.create_rectangle(0, 0, width, height, fill="#10151f", outline="")
            mid, amplitude = height / 2, height * .40

            def peak_at(seconds):
                index = int(max(0.0, min(1.0, seconds / source_duration)) *
                            (len(peaks) - 1))
                return peaks[index]

            for px in range(0, width, 2):
                seconds = px / max(1, width - 1) * source_duration
                half = min(amplitude, peak_at(seconds) * amplitude)
                waveform.create_line(px, mid - half, px, mid + half, fill="#3b4354")

            for start, duration in working:
                x1 = start / source_duration * (width - 1)
                x2 = (start + duration) / source_duration * (width - 1)
                for px in range(max(0, int(x1)), min(width, int(x2) + 1), 2):
                    seconds = px / max(1, width - 1) * source_duration
                    half = min(amplitude, peak_at(seconds) * amplitude)
                    waveform.create_line(px, mid - half, px, mid + half, fill="#4ade80")
                waveform.create_line(x1, 5, x1, height - 5, fill="#f59e0b", dash=(2, 3))
            if selection["start"] is not None and selection["end"] is not None:
                a, b = sorted((selection["start"], selection["end"]))
                x1, x2 = a / source_duration * (width - 1), b / source_duration * (width - 1)
                waveform.create_rectangle(x1, 4, x2, height - 4,
                                          outline="#fbbf24", width=2, dash=(4, 2))
            waveform.create_text(4, 11, anchor="w", text="0.0s", fill="#94a3b8",
                                 font=("Segoe UI", 8))
            waveform.create_text(width - 4, 11, anchor="e",
                                 text=f"{source_duration:.1f}s", fill="#94a3b8",
                                 font=("Segoe UI", 8))
            kept_label.set(f"Διατηρημένο: {total_working():.2f} / {source_duration:.2f} δευτ.")

        def source_at(event):
            return max(0.0, min(source_duration,
                                 event.x / max(1, waveform.winfo_width() - 1) * source_duration))

        def select_press(event):
            selection["start"] = selection["end"] = source_at(event)
            draw_waveform()

        def select_drag(event):
            if selection["start"] is None:
                return
            selection["end"] = source_at(event)
            draw_waveform()

        def select_release(event):
            if selection["start"] is None:
                return
            selection["end"] = source_at(event)
            if abs(selection["end"] - selection["start"]) < .05:
                selection["start"] = selection["end"] = None
            draw_waveform()

        def delete_selection():
            if selection["start"] is None or selection["end"] is None:
                status.set("Σύρε πρώτα πάνω στο waveform για να επιλέξεις κομμάτι.")
                return
            start, end = sorted((selection["start"], selection["end"]))
            updated = remove_audio_range(working, start, end, source_duration)
            if not updated:
                status.set("Δεν μπορεί να αφαιρεθεί όλο το τραγούδι.")
                return
            working[:] = updated
            selection["start"] = selection["end"] = None
            clamp_fades()
            draw_waveform()
            status.set(f"Αφαιρέθηκαν {end - start:.2f} δευτ. Πάτησε Εφαρμογή για αποθήκευση.")

        def restore_all():
            working[:] = [[0.0, source_duration]]
            selection["start"] = selection["end"] = None
            cut_start_var.set("0")
            cut_end_var.set("0")
            draw_waveform()
            status.set("Επαναφέρθηκε ολόκληρο το τραγούδι. Πάτησε Εφαρμογή για αποθήκευση.")

        waveform.bind("<Button-1>", select_press)
        waveform.bind("<B1-Motion>", select_drag)
        waveform.bind("<ButtonRelease-1>", select_release)
        waveform.bind("<Configure>", lambda _e: draw_waveform())
        waveform_buttons = ttk.Frame(body)
        waveform_buttons.pack(fill="x", pady=(4, 3))
        ttk.Button(waveform_buttons, text="Διαγραφή επιλογής",
                   command=delete_selection).pack(side="left")
        ttk.Button(waveform_buttons, text="Επαναφορά όλου του τραγουδιού",
                   command=restore_all).pack(side="left", padx=6)
        ttk.Label(body, textvariable=kept_label).pack(anchor="w")
        ttk.Label(body, text="Τα fade υπολογίζονται πάνω στη διάρκεια μετά τα κοψίματα.",
                  foreground="#64748b").pack(anchor="w", pady=(2, 0))
        ttk.Label(body, textvariable=status, wraplength=620).pack(anchor="w", pady=5)

        def apply():
            try:
                volume_db = read_volume_text()
                if volume_db is None:
                    return
                fade_in = max(0.0, float(fade_in_var.get().replace(",", ".")))
                fade_out = max(0.0, float(fade_out_var.get().replace(",", ".")))
                cut_start = max(0.0, float(cut_start_var.get().replace(",", ".")))
                cut_end = max(0.0, float(cut_end_var.get().replace(",", ".")))
                if not all(math.isfinite(value) for value in
                           (volume_db, fade_in, fade_out, cut_start, cut_end)):
                    raise ValueError()
                ranges = copy.deepcopy(working)
                if cut_start > 0:
                    ranges = cut_audio_edge(ranges, "start", cut_start, source_duration)
                if cut_end > 0:
                    ranges = cut_audio_edge(ranges, "end", cut_end, source_duration)
                total = sum(duration for _start, duration in ranges)
                if total < .05:
                    status.set("Το αποτέλεσμα είναι πολύ μικρό. Μείωσε τα κοψίματα.")
                    return
                fade_in = min(fade_in, total)
                fade_out = min(fade_out, total)
                target_id = labels.get(chosen.get())
                if target_id is None:
                    status.set("Διάλεξε ένα audio track.")
                    return
            except ValueError:
                status.set("Έλεγξε τις τιμές dB, fade και κοψίματος.")
                return
            self.push_undo()
            track, clip = self._audio_by_id(clip_id)
            if clip is None:
                dialog.destroy()
                return
            target = next(item for item in self.project_audio["tracks"]
                          if item["id"] == target_id)
            if target is not track:
                track["clips"].remove(clip)
                target["clips"].append(clip)
            clip["volume_db"] = volume_db
            clip["fade_in"] = fade_in
            clip["fade_out"] = fade_out
            set_audio_segments(clip, ranges, source_duration)
            dialog.destroy()
            self._audio_changed()

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Εφαρμογή", command=apply).pack(side="right")
        ttk.Button(buttons, text="Άκυρο", command=dialog.destroy).pack(side="right", padx=6)
        dialog.after(60, draw_waveform)

    def show_audio_track_properties(self, track_id):
        tracks = self.project_audio["tracks"] if self.project_audio["mode"] == "manual" else getattr(self, "_timeline_display_tracks", [])
        source = next((track for track in tracks if track["id"] == track_id), None)
        if source is None:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Audio track")
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        name, gain = tk.StringVar(value=source["name"]), tk.StringVar(value=str(source["volume_db"]))
        mute, solo = tk.BooleanVar(value=source["mute"]), tk.BooleanVar(value=source["solo"])
        for label, value in (("Όνομα track", name), ("Ένταση track (dB)", gain)):
            ttk.Label(body, text=label).pack(anchor="w")
            ttk.Entry(body, textvariable=value).pack(fill="x", pady=(0, 6))
        ttk.Checkbutton(body, text="Mute", variable=mute).pack(anchor="w")
        ttk.Checkbutton(body, text="Solo", variable=solo).pack(anchor="w")

        def apply(delete=False):
            try:
                value = float(gain.get())
                if not math.isfinite(value) or not -60 <= value <= 20:
                    return
            except ValueError:
                return
            self.push_undo()
            audio = self._manual_audio()
            track = next((track for track in audio["tracks"] if track["id"] == track_id), None)
            if track:
                if delete:
                    audio["tracks"].remove(track)
                else:
                    track.update(name=name.get().strip() or "Ήχος", volume_db=value, mute=mute.get(), solo=solo.get())
            dialog.destroy()
            self._audio_changed()
        ttk.Button(body, text="Εφαρμογή", command=apply).pack(fill="x", pady=(8, 3))
        ttk.Button(body, text="Διαγραφή track", command=lambda: apply(True)).pack(fill="x")

    def audio_clip_menu(self, event, clip_id):
        self._selected_audio_clip = clip_id
        self._active_media_panel = "audio"
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Επεξεργασία", command=lambda: self.show_audio_clip_properties(clip_id))
        menu.add_command(label="Αντιγραφή clip", command=lambda: self.duplicate_audio_clip(clip_id))
        menu.add_command(label="Διαγραφή clip", command=lambda: self.delete_audio_clip(clip_id))
        menu.add_separator()
        menu.add_command(label="Undo", command=self.undo)
        menu.tk_popup(event.x_root, event.y_root)
