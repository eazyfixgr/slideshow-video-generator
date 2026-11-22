"""Timeline audio import, track/clip properties and asynchronous waveform loading."""

import copy
import json
import math
import threading
import uuid
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from .timeline_model import audio_clip, empty_audio, new_track


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
        # Opening a property dialog must not turn automatic music into manual mode.
        tracks = (self.project_audio["tracks"] if self.project_audio["mode"] == "manual"
                  else getattr(self, "_timeline_display_tracks", []))
        source = next(((track, clip) for track in tracks for clip in track["clips"]
                       if clip["id"] == clip_id), None)
        if source is None:
            return
        source_track, source_clip = source
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Ήχος — {Path(source_clip['path']).name}")
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=Path(source_clip["path"]).name,
                  font=("Segoe UI", 11, "bold"), wraplength=440).pack(anchor="w")
        variables = {}
        for key, label in (("start", "Έναρξη στο timeline (δευτ.)"), ("offset", "Αρχή μέσα στο αρχείο (δευτ.)"),
                           ("duration", "Διάρκεια clip (δευτ.)"), ("volume_db", "Ένταση clip (dB)"),
                           ("fade_in", "Fade in (δευτ.)"), ("fade_out", "Fade out (δευτ.)")):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=34).pack(side="left")
            variables[key] = tk.StringVar(value=f"{source_clip[key]:g}")
            ttk.Entry(row, textvariable=variables[key], width=12).pack(side="left")
        labels = {f"{index + 1} — {track['name']}": track["id"] for index, track in enumerate(tracks)}
        chosen = tk.StringVar(value=next(label for label, value in labels.items() if value == source_track["id"]))
        ttk.Label(body, text="Audio track").pack(anchor="w", pady=(5, 2))
        ttk.Combobox(body, textvariable=chosen, values=list(labels), state="readonly").pack(fill="x")
        status = tk.StringVar()
        ttk.Label(body, textvariable=status, wraplength=440).pack(anchor="w", pady=5)

        def apply():
            try:
                values = {key: float(value.get()) for key, value in variables.items()}
                if any(not math.isfinite(value) for value in values.values()):
                    raise ValueError()
                info = self._analyze_project_audio(source_clip["path"])
                if (values["start"] < 0 or values["offset"] < 0 or values["duration"] < .05 or
                        values["offset"] + values["duration"] > info["duration"] + .05 or
                        not -60 <= values["volume_db"] <= 20 or
                        min(values["fade_in"], values["fade_out"]) < 0):
                    raise ValueError()
            except (ValueError, OSError):
                status.set("Έλεγξε διάρκειες/trim και ένταση (-60 έως +20 dB).")
                return
            self.push_undo()
            track, clip = self._audio_by_id(clip_id)
            if clip is None:
                dialog.destroy()
                return
            target = next(item for item in self.project_audio["tracks"] if item["id"] == labels[chosen.get()])
            if target is not track:
                track["clips"].remove(clip)
                target["clips"].append(clip)
            clip.update(values)
            dialog.destroy()
            self._audio_changed()
        ttk.Button(body, text="Εφαρμογή", command=apply).pack(anchor="e", pady=(6, 0))

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
        menu.add_command(label="Ιδιότητες / trim / ένταση", command=lambda: self.show_audio_clip_properties(clip_id))
        menu.add_command(label="Αντιγραφή clip", command=lambda: self.duplicate_audio_clip(clip_id))
        menu.add_command(label="Διαγραφή clip", command=lambda: self.delete_audio_clip(clip_id))
        menu.add_separator()
        menu.add_command(label="Undo", command=self.undo)
        menu.tk_popup(event.x_root, event.y_root)
