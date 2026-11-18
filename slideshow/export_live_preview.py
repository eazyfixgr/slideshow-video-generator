"""Optional low-rate preview updates while individual export clips render."""

import threading
import time


class ExportLivePreviewMixin:
    """Render the current clip into its matching preview canvas when enabled."""

    def _run_media_clip_with_live_preview(
            self, command, description, media_type, path, edit, frame=None, segments=None):
        return self._with_live_render_preview(
            lambda: self._run_ffmpeg_or_raise(command, description),
            media_type, path, edit, frame, segments)

    def _with_live_render_preview(
            self, render, media_type, path, edit, frame=None, segments=None):
        if not getattr(self, "_live_render_previews_enabled", False):
            return render()
        preview = self._start_live_render_preview(media_type, path, edit, frame, segments)
        try:
            return render()
        finally:
            self._stop_live_render_preview(preview)

    def _start_live_render_preview(self, media_type, path, edit, frame=None, segments=None):
        stop = threading.Event()
        width, height = map(int, self.settings["resolution"].split("x"))
        canvas = (self.preview_video_canvas if media_type == "video"
                  else self.preview_photo_canvas)
        self._live_render_preview_token = getattr(self, "_live_render_preview_token", 0) + 1
        token = self._live_render_preview_token
        prepared_frame = self._apply_watermark_overlay(frame) if frame is not None else None
        kept_segments = list(segments or [])

        def video_time(elapsed):
            remaining = float(elapsed)
            for start, duration in kept_segments:
                if remaining < duration:
                    return start + min(remaining, max(0.0, duration - 1 / 30))
                remaining -= duration
            if kept_segments:
                start, duration = kept_segments[-1]
                return start + max(0.0, duration - 1 / 30)
            return max(0.0, float(elapsed))

        def update_preview():
            elapsed = 0
            while not stop.is_set():
                tick_started = time.monotonic()
                try:
                    if media_type == "image" and prepared_frame is not None:
                        self._post_ui(self._show_live_render_preview, token, canvas,
                                      prepared_frame.copy())
                    elif media_type == "video":
                        self._render_preview(
                            path, "video", width, height, canvas, edit,
                            t_start=video_time(elapsed), display_token=token)
                    else:
                        self._render_preview(
                            path, "image", width, height, canvas, edit,
                            display_token=token)
                except Exception:
                    pass
                elapsed += 1
                wait = max(0.0, 1.0 - (time.monotonic() - tick_started))
                if stop.wait(wait):
                    break

        thread = threading.Thread(target=update_preview, daemon=True)
        thread.start()
        return stop, thread, token

    def _stop_live_render_preview(self, preview):
        if preview is None:
            return
        stop, thread, token = preview
        if getattr(self, "_live_render_preview_token", None) == token:
            self._live_render_preview_token += 1
        stop.set()
        if thread.is_alive():
            thread.join(timeout=2)

    def _show_live_render_preview(self, token, canvas, frame):
        if token == getattr(self, "_live_render_preview_token", None):
            self._show_preview(canvas, frame)
