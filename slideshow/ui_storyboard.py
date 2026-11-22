"""Time-scaled visual/audio timeline, replacing the equal-width storyboard strip."""

import copy
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .audio_workspace import AudioWorkspaceMixin
from .deps import ImageTk
from .slide_design import normalize_presentation
from .timeline_model import trim_audio
from .ui_audio_tracks import AudioTracksMixin
from .ui_timeline_playback import TimelinePlaybackMixin, timecode
from .ui_voiceover import VoiceoverMixin
from .ui_theme import MODERN_PALETTE as P
from .ui_widgets import SlimScrollbar, fit_cover, flat_button

ORIGIN, VISUAL_TOP, VISUAL_BOTTOM, AUDIO_TOP, LANE = 140, 42, 126, 146, 58


class StoryboardMixin(AudioWorkspaceMixin, AudioTracksMixin, TimelinePlaybackMixin, VoiceoverMixin):
    def _build_storyboard(self, parent):
        frame = tk.Frame(parent, bg=P["panel"], height=310,
                         highlightbackground=P["border"], highlightthickness=1)
        frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        frame.grid_propagate(False)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        header = tk.Frame(frame, bg=P["panel"])
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        tk.Label(header, text="TIMELINE", bg=P["panel"], fg=P["text"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self.timeline_clock_var = tk.StringVar(value="00:00.000 / 00:00.000")
        self.storyboard_count_var = self.timeline_clock_var
        tk.Label(header, textvariable=self.timeline_clock_var, bg=P["panel"], fg=P["accent"],
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 12))
        for label, command in (("+ Ήχος", self.add_audio_files), ("+ Audio track", self.add_audio_track),
                               ("Αυτόματη μουσική", self.regenerate_music_plan),
                               ("Voice-over", self.show_voiceover_recorder),
                               ("−", lambda: self._timeline_zoom_by(.8)), ("+", lambda: self._timeline_zoom_by(1.25)),
                               ("Fit", self._timeline_fit_all)):
            flat_button(header, label, command, background=P["raised"], foreground=P["text"],
                        active_background=P["selected"], font=("Segoe UI", 8), padx=7, pady=3).pack(
                side="left", padx=2)
        height = ttk.Scale(header, from_=220, to=520, length=80,
                           command=lambda value: frame.configure(height=int(float(value))))
        height.set(310)
        height.pack(side="right")
        tk.Label(header, text="Ύψος", bg=P["panel"], fg=P["muted"], font=("Segoe UI", 8)).pack(side="right")
        canvas = tk.Canvas(frame, bg=P["background"], highlightthickness=0, cursor="crosshair")
        canvas.grid(row=1, column=0, sticky="nsew", padx=(2, 0))
        horizontal = SlimScrollbar(frame, command=self._timeline_xview, orient="horizontal",
                                   background=P["panel"], color=P["border"], active=P["muted"])
        horizontal.grid(row=2, column=0, sticky="ew", padx=3)
        vertical = SlimScrollbar(frame, command=canvas.yview, orient="vertical",
                                 background=P["panel"], color=P["border"], active=P["muted"])
        vertical.grid(row=1, column=1, sticky="ns")
        canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.storyboard_frame = frame
        self.storyboard_canvas = canvas
        self.storyboard_inner = canvas  # retained for callers that check the old strip's existence
        self._timeline_ready = True
        self._timeline_zoom, self._timeline_fit = 24.0, True
        self._sb_anchor, self._timeline_drag = None, None
        self._sb_widgets, self._sb_photo_refs = [], {}
        self._sb_thumb_cache, self._sb_pending = {}, set()
        self._timeline_display_tracks, self._timeline_waveforms = [], {}
        self._timeline_audio_key = None
        canvas.bind("<Button-1>", self._timeline_press)
        canvas.bind("<B1-Motion>", self._timeline_motion)
        canvas.bind("<ButtonRelease-1>", self._timeline_release)
        canvas.bind("<Double-Button-1>", self._timeline_double)
        canvas.bind("<Button-3>", self._timeline_menu)
        canvas.bind("<MouseWheel>", self._timeline_wheel)
        canvas.bind("<space>", lambda _e: self.toggle_timeline_playback())
        canvas.bind("<Configure>", lambda _e: self.render_storyboard())
        return frame

    def _timeline_fit_all(self):
        self._timeline_fit = True
        self.render_storyboard()

    def _timeline_zoom_by(self, factor):
        self._timeline_fit = False
        self._timeline_zoom = max(2, min(220, self._timeline_zoom * factor))
        self.render_storyboard()

    def _timeline_xview(self, *args):
        if hasattr(self, "storyboard_canvas"):
            self.storyboard_canvas.xview(*args)
            self._draw_track_labels()

    def _timeline_wheel(self, event):
        direction = -1 if event.delta > 0 else 1
        if event.state & 0x0004:
            self._timeline_zoom_by(1.2 if direction < 0 else 1 / 1.2)
        elif event.state & 0x0001:
            self._timeline_xview("scroll", direction * 3, "units")
        else:
            self.storyboard_canvas.yview_scroll(direction * 2, "units")
        return "break"

    def _timeline_tracks(self):
        return (self.project_audio["tracks"] if self.project_audio["mode"] == "manual"
                else self._timeline_display_tracks)

    def render_storyboard(self):
        if not hasattr(self, "storyboard_canvas") or not hasattr(self, "project_audio"):
            return
        canvas = self.storyboard_canvas
        layout, total = self.timeline_layout()
        self._timeline_layout, self._timeline_total = layout, total
        if self._timeline_fit and total:
            self._timeline_zoom = max(2, min(220, (max(500, canvas.winfo_width()) - ORIGIN - 30) / total))
        scale = self._timeline_zoom
        tracks = self._timeline_tracks()
        horizon = max(total, max((clip["start"] + clip["duration"] for track in tracks
                                  for clip in track["clips"]), default=0), 10)
        self._timeline_width = ORIGIN + horizon * scale + 100
        self._timeline_height = AUDIO_TOP + max(2, len(tracks)) * LANE + 12
        canvas.delete("all")
        canvas.configure(scrollregion=(0, 0, self._timeline_width, self._timeline_height))
        step = next((value for value in (.2, .5, 1, 2, 5, 10, 15, 30, 60, 120, 300)
                     if value * scale >= 60), 600)
        for tick in range(int(horizon / step) + 2):
            t = tick * step
            x = ORIGIN + t * scale
            canvas.create_line(x, 25, x, self._timeline_height, fill=P["border"])
            canvas.create_text(x + 3, 12, text=timecode(t)[:-4], anchor="w", fill=P["muted"], font=("Segoe UI", 8))
        groups = {}
        for timing, item in zip(layout, self.media_files):
            group = item[2].get("group_id")
            if group:
                bounds = groups.setdefault(group, [timing["start"], timing["end"]])
                bounds[0], bounds[1] = min(bounds[0], timing["start"]), max(bounds[1], timing["end"])
        for start, end in groups.values():
            canvas.create_rectangle(ORIGIN + start * scale, 30, ORIGIN + end * scale, VISUAL_BOTTOM + 5,
                                    outline=P["accent"], width=2)
        for timing, item in zip(layout, self.media_files):
            index = timing["index"]
            x1, x2 = ORIGIN + timing["start"] * scale, ORIGIN + timing["end"] * scale
            tag = f"scene:{index}"
            selected = index in self.selected_indices
            canvas.create_rectangle(x1, VISUAL_TOP, x2, VISUAL_BOTTOM, fill=P["raised"],
                                    outline=P["accent"] if selected else P["muted"], width=2 if selected else 1, tags=tag)
            thumb_key = (str(item[1]), repr(item[2].get("crop")), item[2].get("rotate", 0),
                         item[2].get("brightness", 1), item[2].get("color", 1))
            cached = self._sb_thumb_cache.get(thumb_key)
            if cached is not None and x2 - x1 > 16:
                image = cached.copy()
                image = fit_cover(image, max(1, min(124, int(x2 - x1 - 4))), 44)
                photo = ImageTk.PhotoImage(image, master=self.root)
                self._sb_photo_refs[index] = photo
                canvas.create_image(x1 + 2, VISUAL_TOP + 2, anchor="nw", image=photo,
                                    tags=(f"thumb:{index}", tag))
            elif thumb_key not in self._sb_pending:
                self._queue_scene_thumb(index, item, thumb_key)
            if timing["overlap"]:
                canvas.create_rectangle(x1, VISUAL_TOP, x1 + timing["overlap"] * scale, VISUAL_BOTTOM,
                                        outline=P["accent"], dash=(3, 3), tags=tag)
            if x2 - x1 > 35:
                caption = f"{index + 1:02d} · {timing['duration']:.2f}s"
                canvas.create_text(x1 + 4, VISUAL_BOTTOM - 24, anchor="w", text=caption,
                                   fill=P["text"], font=("Segoe UI", 8, "bold"), width=max(20, x2 - x1 - 8), tags=tag)
                canvas.create_text(x1 + 4, VISUAL_BOTTOM - 8, anchor="w", text=Path(item[1]).name[:max(3, int((x2-x1)/6))],
                                   fill=P["muted"], font=("Segoe UI", 7), tags=tag)
        for lane, track in enumerate(tracks):
            y = AUDIO_TOP + lane * LANE
            canvas.create_rectangle(ORIGIN, y, self._timeline_width, y + LANE - 4, fill=P["field"], outline="")
            for clip in track["clips"]:
                x1, x2 = ORIGIN + clip["start"] * scale, ORIGIN + (clip["start"] + clip["duration"]) * scale
                tag = f"audio:{clip['id']}"
                color = P["accent_faint"] if clip.get("recording") else P["selected"]
                selected = clip["id"] == getattr(self, "_selected_audio_clip", None)
                canvas.create_rectangle(x1, y + 3, x2, y + LANE - 7, fill=color,
                                        outline=P["accent"] if selected else P["muted"], tags=tag)
                info = self._timeline_waveforms.get(clip["path"])
                if info:
                    peaks = info["peaks"]
                    count = max(1, min(350, int((x2 - x1) / 3)))
                    for bin_index in range(count):
                        source_at = clip["offset"] + clip["duration"] * bin_index / count
                        peak = peaks[min(len(peaks)-1, int(source_at / max(.01, info["duration"]) * len(peaks)))]
                        x = x1 + (x2-x1) * bin_index / count
                        half = min(16, peak * 28)
                        canvas.create_line(x, y + 29 - half, x, y + 29 + half, fill=P["good"], tags=tag)
                if x2 - x1 > 45:
                    canvas.create_text(x1 + 4, y + 12, text=Path(clip["path"]).name[:max(4, int((x2-x1)/6))],
                                       anchor="w", fill=P["text"], font=("Segoe UI", 8), tags=tag)
        end_x = ORIGIN + total * scale
        canvas.create_line(end_x, 25, end_x, self._timeline_height, fill=P["danger"], dash=(5, 4))
        self._draw_track_labels()
        self._draw_timeline_playhead()
        self._update_timeline_clock_label(total)
        self._queue_timeline_audio(total)

    def _queue_scene_thumb(self, index, item, key):
        self._sb_pending.add(key)
        token = self._session_id

        def receive(image):
            if token != self._session_id:
                return
            self._sb_pending.discard(key)
            self._sb_thumb_cache[key] = image
            canvas = self.storyboard_canvas
            try:
                rectangles = [entry for entry in canvas.find_withtag(f"scene:{index}")
                              if canvas.type(entry) == "rectangle"]
                if not rectangles:
                    return
                x1, y1, x2, _y2 = canvas.coords(rectangles[0])
                width = max(1, min(124, int(x2 - x1 - 4)))
                photo = ImageTk.PhotoImage(fit_cover(image, width, 44), master=self.root)
                self._sb_photo_refs[index] = photo
                canvas.delete(f"thumb:{index}")
                canvas.create_image(x1 + 2, y1 + 2, anchor="nw", image=photo,
                                    tags=(f"thumb:{index}", f"scene:{index}"))
            except tk.TclError:
                pass

        def worker():
            try:
                kind, path, edit = item
                image = self._video_first_frame(path) if kind == "video" else self.open_thumbnail_image(path, 350, False)
                image = self._apply_image_edit(image.copy(), {k: v for k, v in edit.items() if k != "erase"}, path, m_type=kind)
                self._post_ui(receive, fit_cover(image, 124, 44))
            except Exception:
                if token == self._session_id:
                    self._sb_pending.discard(key)
        threading.Thread(target=worker, daemon=True).start()

    def _draw_track_labels(self):
        canvas = self.storyboard_canvas
        canvas.delete("lane-label")
        left = canvas.canvasx(0)
        for y, label, tag in [(0, "Χρόνος", "ruler"), (VISUAL_TOP, "V1 · Εικόνα / βίντεο", "visual")]:
            canvas.create_rectangle(left, y, left + ORIGIN - 3, y + (25 if y == 0 else 84), fill=P["panel"], outline="", tags="lane-label")
            canvas.create_text(left + 8, y + 12, anchor="w", text=label, fill=P["muted"], font=("Segoe UI", 8), tags=("lane-label", tag))
        for index, track in enumerate(self._timeline_tracks()):
            y = AUDIO_TOP + index * LANE
            tag = f"track:{track['id']}"
            canvas.create_rectangle(left, y, left + ORIGIN - 3, y + LANE - 4, fill=P["panel"], outline="", tags=("lane-label", tag))
            flags = (" MUTE" if track["mute"] else "") + (" SOLO" if track["solo"] else "")
            canvas.create_text(left + 8, y + 14, anchor="w", text=f"A{index+1} · {track['name'][:17]}",
                               fill=P["accent"] if flags else P["text"], font=("Segoe UI", 8, "bold"), tags=("lane-label", tag))
            canvas.create_text(left + 8, y + 32, anchor="w", text=f"{track['volume_db']:+g} dB{flags}",
                               fill=P["muted"], font=("Segoe UI", 7), tags=("lane-label", tag))

    def _draw_timeline_playhead(self):
        if not hasattr(self, "storyboard_canvas"):
            return
        canvas = self.storyboard_canvas
        canvas.delete("playhead")
        x = ORIGIN + getattr(self, "_playhead_seconds", 0) * self._timeline_zoom
        canvas.create_line(x, 24, x, getattr(self, "_timeline_height", 300), fill=P["danger"], width=2, tags="playhead")
        canvas.create_polygon(x-5, 1, x+5, 1, x, 10, fill=P["danger"], tags="playhead")
        if getattr(self, "_preview_playing", False) and x > canvas.canvasx(canvas.winfo_width() - 30):
            canvas.xview_moveto(max(0, (x - canvas.winfo_width() + 100) / max(1, self._timeline_width)))
            self._draw_track_labels()

    def _refresh_selection(self):
        self.render_storyboard()

    def _timeline_hit(self, event):
        canvas = self.storyboard_canvas
        x, y = canvas.canvasx(event.x), canvas.canvasy(event.y)
        tags = []
        for item in reversed(canvas.find_overlapping(x, y, x, y)):
            tags += list(canvas.gettags(item))
        for prefix in ("track:", "audio:", "scene:"):
            tag = next((tag for tag in tags if tag.startswith(prefix)), None)
            if tag:
                return prefix[:-1], tag.split(":", 1)[1], x, y
        return None, None, x, y

    def _timeline_press(self, event):
        if getattr(self, "_voiceover_recording", False):
            return
        self._stop_preview_play()
        self._commit_pending_caption_apply()
        self.storyboard_canvas.focus_set()
        kind, key, x, y = self._timeline_hit(event)
        self._timeline_drag = None
        if y < 28:
            self.seek_timeline(max(0, (x-ORIGIN)/self._timeline_zoom))
            self._timeline_drag = {"kind": "seek"}
            return
        if kind == "track":
            self._selected_audio_track = key
            self._selected_audio_clip = None
            self._active_media_panel = "audio"
            return
        if kind == "scene":
            index = int(key)
            if event.state & 0x0004:
                self.selected_indices.symmetric_difference_update({index})
            elif event.state & 0x0001 and self._sb_anchor is not None:
                a, b = sorted((index, self._sb_anchor))
                self.selected_indices = set(range(a, b+1))
            elif index not in self.selected_indices:
                self.selected_indices = {index}
            self._sb_anchor = index
            self._active_media_panel = "project"
            timing = self._timeline_layout[index]
            edge = abs(x-(ORIGIN+timing["end"]*self._timeline_zoom)) < 6
            self._timeline_drag = {"kind": "scene", "index": index, "x": x, "duration": timing["duration"],
                                   "edge": edge, "moved": False, "multi": bool(event.state & 5)}
            self._refresh_selection()
        elif kind == "audio":
            tracks = self._timeline_tracks()
            track, clip = next((track, clip) for track in tracks for clip in track["clips"] if clip["id"] == key)
            left = ORIGIN + clip["start"] * self._timeline_zoom
            right = left + clip["duration"] * self._timeline_zoom
            edge = "left" if abs(x-left) < 6 else "right" if abs(x-right) < 6 else "move"
            self._selected_audio_clip, self._selected_audio_track = key, track["id"]
            self._active_media_panel = "audio"
            self._timeline_drag = {"kind": "audio", "id": key, "x": x, "edge": edge,
                                   "clip": copy.deepcopy(clip), "track": track["id"], "moved": False}
            self.render_storyboard()

    def _timeline_motion(self, event):
        drag = self._timeline_drag
        if not drag:
            return
        canvas = self.storyboard_canvas
        x = canvas.canvasx(event.x)
        if drag["kind"] == "seek":
            self.seek_timeline(max(0, (x-ORIGIN)/self._timeline_zoom))
            return
        if abs(x-drag["x"]) > 4:
            drag["moved"] = True
        if drag["moved"]:
            canvas.delete("drag-ghost")
            canvas.create_line(x, 26, x, self._timeline_height, fill=P["accent"], width=2, tags="drag-ghost")

    def _timeline_release(self, event):
        drag = self._timeline_drag
        self._timeline_drag = None
        self.storyboard_canvas.delete("drag-ghost")
        if not drag or drag["kind"] == "seek":
            return
        x, y = self.storyboard_canvas.canvasx(event.x), self.storyboard_canvas.canvasy(event.y)
        delta = (x-drag["x"]) / self._timeline_zoom
        if drag["kind"] == "scene":
            if not drag["moved"]:
                if drag["multi"]:
                    self._render_inspector()
                else:
                    self.select_scene(drag["index"])
                return
            if drag["edge"]:
                self.push_undo()
                item = self.media_files[drag["index"]]
                p = normalize_presentation(item[2].get("presentation"))
                p["duration"] = max(1, min(30, drag["duration"] + delta))
                item[2]["presentation"] = p
                self._audio_changed()
                self._render_inspector()
            else:
                target = min(self._timeline_layout, key=lambda item: abs(
                    ORIGIN + (item["start"] + item["duration"] / 2) * self._timeline_zoom - x))["index"]
                self.selected_indices = set(self._grouped_selection_indices())
                self._move_selection_to(target)
        elif drag["moved"]:
            self.push_undo()
            track, clip = self._audio_by_id(drag["id"])
            if clip is None:
                return
            if drag["edge"] == "move":
                clip["start"] = max(0.0, round((drag["clip"]["start"] + delta) * 10) / 10)
                index = max(0, min(len(self.project_audio["tracks"])-1, int((y-AUDIO_TOP)/LANE)))
                destination = self.project_audio["tracks"][index]
                if destination is not track:
                    track["clips"].remove(clip)
                    destination["clips"].append(clip)
            else:
                info = self._analyze_project_audio(clip["path"])
                clip.update(trim_audio(drag["clip"], drag["edge"], delta, info["duration"]))
            self._audio_changed()

    def _timeline_double(self, event):
        kind, key, _x, _y = self._timeline_hit(event)
        if kind == "scene":
            self.open_edit_dialog(int(key))
        elif kind == "audio":
            self.show_audio_clip_properties(key)
        elif kind == "track":
            self.show_audio_track_properties(key)

    def _timeline_menu(self, event):
        kind, key, _x, _y = self._timeline_hit(event)
        if kind == "scene":
            self.media_menu(event, int(key))
        elif kind == "audio":
            self.audio_clip_menu(event, key)
        elif kind == "track":
            self.show_audio_track_properties(key)
