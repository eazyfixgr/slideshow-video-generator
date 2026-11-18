"""Turning one photo/video frame into the final canvas (fit, blur, text, pan)."""

import io
import json
import os
import random
import re
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog

from .deps import (Image, ImageTk, ImageFilter, ImageDraw, ImageFont, ImageEnhance,
                   VideoFileClip, AudioFileClip, concatenate_audioclips, np,
                   DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .slide_design import (compose_design_frame, legacy_text, normalize_presentation,
                           presentation_fields, TEMPLATES)


# Regular / bold font files for the families offered in Settings → Text.
_TEXT_FONT_FILES = {
    "Calibri": ("calibri.ttf", "calibrib.ttf"),
    "Arial": ("arial.ttf", "arialbd.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"),
    "Georgia": ("georgia.ttf", "georgiab.ttf"),
}


class RenderMixin:
    """Turning one photo/video frame into the final canvas (fit, blur, text, pan)."""

    def get_text_for(self, m_type):
        """Text overlay for a media type.

        In the project-wide mode every item shares ``project_text_all``. In
        separate media-type mode an empty text remains empty, while projects
        imported from older schemas are migrated to preserve their old fallback.
        """
        videos = self.project_text_videos or ""
        photos = self.project_text_photos or ""
        if m_type == "image":
            if getattr(self, "project_caption_mode", "by_type") == "all":
                return self.project_text_all or ""
            return photos
        if getattr(self, "project_caption_mode", "by_type") == "all":
            return self.project_text_all or ""
        return videos


    def _presentation_for(self, edit):
        stored = (edit or {}).get("presentation")
        scene_id = stored.get("scene_id") if isinstance(stored, dict) else None
        drafts = getattr(self, "_presentation_preview_drafts", {})
        source = drafts.get(scene_id, stored) if scene_id else stored
        return self._effective_presentation(source)


    def _set_presentation_preview_draft(self, value):
        presentation = normalize_presentation(value)
        drafts = getattr(self, "_presentation_preview_drafts", None)
        if drafts is None:
            drafts = self._presentation_preview_drafts = {}
        drafts[presentation["scene_id"]] = presentation
        self._active_presentation_scene_id = presentation["scene_id"]
        try:
            self._schedule_preview(250)
        except tk.TclError:
            pass


    def _clear_presentation_preview_draft(self, scene_id, clear_active=False):
        drafts = getattr(self, "_presentation_preview_drafts", None)
        changed = bool(drafts and drafts.pop(scene_id, None) is not None)
        if clear_active and getattr(self, "_active_presentation_scene_id", None) == scene_id:
            self._active_presentation_scene_id = None
            changed = True
        if changed:
            try:
                self._schedule_preview(100)
            except tk.TclError:
                pass


    def _effective_presentation(self, value):
        presentation = normalize_presentation(value)
        if presentation["template"] == "project":
            default = getattr(self, "project_template", "legacy")
            presentation["template"] = (default if isinstance(default, str) and default in TEMPLATES
                                         else "legacy")
        return presentation


    def _presentation_text(self, presentation, m_type, global_text=None):
        if global_text is None:
            global_text = self.get_text_for(m_type)
        return legacy_text(presentation, global_text)


    def _presentation_fields(self, presentation, m_type, global_text=None):
        if global_text is None:
            global_text = self.get_text_for(m_type)
        return presentation_fields(presentation, global_text)


    def _presentation_before_image(self, presentation, fallback=None):
        """Load the selected Before image for the comparison template, if any."""
        path = (presentation or {}).get("compare_path")
        if not path:
            return fallback
        try:
            item = next((it for it in self.media_files
                         if it[0] == "image" and os.path.normcase(str(it[1])) ==
                         os.path.normcase(str(path))), None)
            if item:
                img = Image.open(item[1])
                return self._apply_image_edit(img, item[2], item[1], m_type="image")
            img = Image.open(path)
            img.load()
            return img.convert("RGB")
        except Exception:
            return fallback


    def _render_design_frame(self, source, edit, m_type, width, height, global_text=None):
        """Render a still frame through the shared slide template engine."""
        presentation = self._presentation_for(edit)
        auto_position_video = (m_type == "video" and
                               self.settings.get("auto_position_videos", False))
        if auto_position_video:
            presentation["text_position"] = "bottom"
        fields = self._presentation_fields(presentation, m_type, global_text)
        before = self._presentation_before_image(presentation, fallback=source)
        frame, overflow = compose_design_frame(
            source, width, height, presentation, fields, before_image=before,
            auto_position_video=auto_position_video,
            video_fill_mode=self.settings.get("video_auto_position_fill", "panel"))
        return frame, overflow


    def render_text_on_image(self, img, text, w, h, align="left"):
        if not text:
            return img
        img = img.copy().convert("RGBA")
        draw = ImageDraw.Draw(img)
        fs = self.settings["font_size"]
        font, f_bold = self._get_text_fonts(fs)
        parts, lines = self._wrap_text_lines(text, w, fs)
        
        lh = fs + 5
        y = h - (len(lines) * lh) - 15
        if self.settings["text_style"] == "black_box" and lines:
            max_lw = max([l[1] for l in lines])
            box_x = self._legacy_text_x(w, max_lw, align)
            draw.rectangle([box_x - 15, y - 5, box_x + max_lw + 15, h - 5],
                           fill=(255, 255, 255, 255))
        for lp, lw in lines:
            x = self._legacy_text_x(w, lw, align)
            for is_b, txt in lp:
                f = f_bold if is_b else font
                draw.text((x, y), txt, font=f, fill="black")
                x += f.getlength(txt)
            y += lh
        return img


    def _auto_video_text_layout(self, text, width, height):
        """Reserve a bottom caption area so auto-positioned video stays unobscured."""
        if not (text or "").strip():
            return max(1, int(height)), 0
        font_size = int(self.settings.get("font_size", 32))
        _parts, lines = self._wrap_text_lines(text, width, font_size)
        text_height = len(lines) * (font_size + 5) + 40
        return max(100, int(height) - text_height), 20


    def _render_auto_position_video(self, source, presentation, text, width, height):
        """Fit the whole video above its caption and fill side gaps consistently."""
        available_h, top = self._auto_video_text_layout(text, width, height)
        if self.settings.get("video_auto_position_fill", "panel") == "blur":
            frame = self._create_blur_bg(source, width, height)
        else:
            frame = Image.new("RGB", (width, height),
                              presentation.get("panel_color", "#111B2B"))
        source = source.convert("RGB")
        scale = min(width / source.width, available_h / source.height)
        fitted = source.resize((max(1, round(source.width * scale)),
                               max(1, round(source.height * scale))),
                              Image.Resampling.LANCZOS)
        x = max(0, (width - fitted.width) // 2)
        frame.paste(fitted, (x, top))
        return self.render_text_on_image(
            frame, text, width, height, align=presentation["text_align"])


    @staticmethod
    def _legacy_text_x(width, line_width, align):
        if align == "right":
            return width - line_width - 15
        if align == "center":
            return (width - line_width) // 2
        return 15


    def _wrap_text_lines(self, text, w, fs=None):
        """Split text into drawable parts and wrapped lines — same layout as rendering.

        Returns (parts, lines) where parts is [(is_bold, chunk), ...] used for
        drawing and lines is [(chunk_list, line_width), ...] used both for
        drawing and for estimating how much vertical space the text occupies.
        """
        if fs is None:
            fs = self.settings["font_size"]
        font, f_bold = self._get_text_fonts(fs)

        parts = []
        last = 0
        for m in re.finditer(r'\*\*\s*([\s\S]*?)\s*\*\*', text):
            if m.start() > last:
                parts.append((False, text[last:m.start()]))
            parts.append((True, m.group(1)))
            last = m.end()
        if last < len(text):
            parts.append((False, text[last:]))

        lines = []
        cur_line = []
        cur_w = 0
        for is_b, txt in parts:
            f = f_bold if is_b else font
            paragraphs = txt.split('\n')
            for idx, p in enumerate(paragraphs):
                for word in p.split():
                    ww = f.getlength(word + " ")
                    if cur_w + ww > w - 60 and cur_line:
                        lines.append((cur_line, cur_w))
                        cur_line = []
                        cur_w = 0
                    cur_line.append((is_b, word + " "))
                    cur_w += ww
                # Flush only on actual newline (not at the end of the last paragraph)
                if idx < len(paragraphs) - 1:
                    if cur_line:
                        lines.append((cur_line, cur_w))
                        cur_line = []
                        cur_w = 0
        if cur_line:
            lines.append((cur_line, cur_w))
            cur_line = []
            cur_w = 0
        return parts, lines


    def _get_text_fonts(self, fs):
        """Regular + bold ImageFont for the chosen family (Settings → Text).

        Windows ships these fonts, so we look them up in the Fonts folder. A
        missing family falls back to Calibri, then to Pillow's built-in font,
        so rendering never breaks.
        """
        family = self.settings.get("font_family", "Calibri")
        reg, bold = _TEXT_FONT_FILES.get(family, _TEXT_FONT_FILES["Calibri"])
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        candidates = [
            (os.path.join(fonts_dir, reg), os.path.join(fonts_dir, bold)),
            _TEXT_FONT_FILES["Calibri"],   # fall back to Calibri by name
        ]
        for reg_path, bold_path in candidates:
            try:
                return ImageFont.truetype(reg_path, fs), ImageFont.truetype(bold_path, fs)
            except Exception:
                continue
        default = ImageFont.load_default()
        return default, default


    def _watermark_text_image(self, text, color, font_size, opacity=1.0):
        """An RGBA image of the watermark text, ready to overlay."""
        font, _ = self._get_text_fonts(max(8, int(font_size)))
        probe = Image.new("RGBA", (4, 4))
        draw = ImageDraw.Draw(probe)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
        except Exception:
            bbox = (0, 0, max(1, len(text) * font_size // 2), font_size)
        w = max(1, bbox[2] - bbox[0])
        h = max(1, bbox[3] - bbox[1])
        img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
        ImageDraw.Draw(img).text((2 - bbox[0], 2 - bbox[1]), text, font=font, fill=color)
        if opacity < 1.0:
            img.putalpha(img.getchannel("A").point(lambda v: int(v * opacity)))
        return img


    def _create_blur_bg(self, img, tw, th):
        img = img.convert("RGB")  # GaussianBlur does not support palette/RGBA modes
        iw, ih = img.size
        ratio = max(tw/iw, th/ih)
        bg = img.resize((int(iw*ratio), int(ih*ratio)), Image.Resampling.LANCZOS)
        x0 = (bg.width - tw) // 2
        y0 = (bg.height - th) // 2
        return bg.crop((x0, y0, x0 + tw, y0 + th)).filter(ImageFilter.GaussianBlur(30))


    def _make_text_overlay(self, text, width, height, align="left"):
        """Precompute the text overlay (white box + text on a transparent layer)
        once, so it can be pasted onto every frame cheaply instead of re-rendering
        the text 120 times per photo."""
        if not text:
            return None
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        return self.render_text_on_image(base, text, width, height, align=align)


    def _render_fit_and_move_frame(self, bg, fit_move_data, pos, width, height, overlay=None):
        """Render one pan frame at relative position pos (0 = start, 1 = end)."""
        fg = fit_move_data["fg"]
        is_landscape = fit_move_data["is_landscape"]
        available_h = fit_move_data["available_h"]
        if is_landscape:
            pan_range = max(0, fg.width - width)
            crop_x = int(round(pos * pan_range))
            crop_y = (fg.height - available_h) // 2
        else:
            pan_range = max(0, fg.height - available_h)
            crop_x = (fg.width - width) // 2
            crop_y = int(round(pos * pan_range))
        frame = bg.copy()
        window = fg.crop((crop_x, crop_y, crop_x + width, crop_y + available_h))
        frame.paste(window, (0, 0))
        if overlay is not None:
            frame.paste(overlay, (0, 0), overlay)
        return frame


    def _render_fit_and_move_clip(self, bg, fit_move_data, temp_dir, index, width, height,
                                  image_duration, clip_path, text_align="left",
                                  design_layers=None):
        """Render a slow pan clip for the 'Fit and Move' background mode.

        The foreground image was already zoomed in ``_fit_image_logic`` so it
        overflows the visible area. Here we pan across it — horizontally for
        landscape photos, vertically for portrait ones — over the slide
        duration, starting from a random side. The text overlay is drawn once
        and the frames are streamed straight into ffmpeg as raw RGB, which
        avoids writing 120 PNG files and makes this several times faster.
        """
        fg = fit_move_data["fg"]
        is_landscape = fit_move_data["is_landscape"]
        available_h = fit_move_data["available_h"]

        fps = 30
        total_frames = max(1, int(image_duration * fps))
        forward = random.choice([True, False])
        if design_layers is None:
            overlay = self._make_text_overlay(self.get_text_for("image"), width, height,
                                              align=text_align)
            design_pan_background = None
            base = fixed_overlay = rect = None
        else:
            base, fixed_overlay, rect = design_layers
            _x, _y, rect_width, rect_height = rect
            design_pan_background = Image.new("RGB", (rect_width, rect_height))
            overlay = None
        self._log_export(f"fit_and_move img {index}: is_landscape={is_landscape} "
                         f"available_h={available_h} fg={fg.size} frames={total_frames} "
                         f"direction={'L->R' if forward else 'R->L'}")

        cmd = ['ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
               '-s', f'{width}x{height}', '-r', str(fps), '-i', '-',
               '-c:v', 'libx264', *self.video_encode_options('veryfast'),
               '-r', str(fps), '-pix_fmt', 'yuv420p', '-an', str(clip_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for f_idx in range(total_frames):
                if getattr(self, "_export_cancel", False):
                    raise RuntimeError("cancelled")
                t = f_idx / (total_frames - 1) if total_frames > 1 else 0.0
                pos = t if forward else (1.0 - t)
                if design_layers is None:
                    frame = self._render_fit_and_move_frame(
                        bg, fit_move_data, pos, width, height, overlay)
                else:
                    x, y, rw, rh = rect
                    moving = self._render_fit_and_move_frame(
                        design_pan_background, fit_move_data, pos, rw, rh)
                    frame = base.copy()
                    frame.paste(moving, (x, y))
                    frame = Image.alpha_composite(
                        frame.convert("RGBA"), fixed_overlay).convert("RGB")
                # Always feed exact 3-bytes-per-pixel RGB: PNG-with-alpha sources
                # would otherwise produce RGBA bytes that ffmpeg misreads.
                proc.stdin.write(frame.convert("RGB").tobytes())
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
            raise
        finally:
            proc.stdin.close()
        _, err = proc.communicate()
        if proc.returncode != 0:
            err_tail = err.decode(errors='replace')[-500:] if err else ""
            self._log_export(f"ffmpeg FAILED encoding Fit and Move clip: {err_tail}")
            raise RuntimeError(f"ffmpeg failed while encoding Fit and Move clip:\n{err_tail}")
        return float(image_duration)


    def _fit_image_logic(self, img, tw, th, m_type, text=None):
        img = img.convert("RGB")  # keep every downstream op (blur, resize, paste, rawvideo) in RGB
        auto_pos = self.settings.get("auto_position_photos" if m_type == "image" else "auto_position_videos", False)
        iw, ih = img.size
        lh = self.settings["font_size"] + 5
        text_here = self.get_text_for(m_type) if text is None else text
        _, wrapped_lines = self._wrap_text_lines(text_here, tw) if text_here.strip() else ([], [])
        
        bg_m = self.settings["background_mode"]
        if bg_m in ("blur", "fit_and_move"):
            bg = self._create_blur_bg(img, tw, th)
        else:
            bg = Image.new("RGB", (tw, th), (255,255,255) if bg_m == "white" else (0,0,0))
        
        if bg_m == "fit_and_move":
            # Fit the image in the area above the text, zoom in a bit, and attach
            # pan data so the export can animate a slow pan across the rest of the
            # photo. Auto-position is effectively implied (image sits above text).
            text_h = (len(wrapped_lines) * lh + 40) if wrapped_lines else 0
            available_h = max(th - text_h, 100)
            is_landscape = (iw / ih) >= (tw / available_h)
            zoom = min(1.6, max(1.25, 1.25 * th / available_h))
            if is_landscape:
                r = (available_h * zoom) / ih
            else:
                r = (tw * zoom) / iw
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            bg.fit_move_data = {"fg": fg, "is_landscape": is_landscape, "available_h": available_h}
            crop_x = (fg.width - tw) // 2
            crop_y = (fg.height - available_h) // 2
            bg.paste(fg.crop((crop_x, crop_y, crop_x + tw, crop_y + available_h)), (0, 0))
            return bg
        elif auto_pos:
            av_h = th - (len(wrapped_lines) * lh + 40)
            r = min(tw/iw, max(100, av_h)/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            y = 20
        elif self.settings["cropping"]:
            r = max(tw/iw, th/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            x0 = (fg.width - tw) // 2
            y0 = (fg.height - th) // 2
            fg = fg.crop((x0, y0, x0 + tw, y0 + th))
            y = 0
        else:
            r = min(tw/iw, th/ih)
            fg = img.resize((int(iw*r), int(ih*r)), Image.Resampling.LANCZOS)
            y = (th - fg.height) // 2
        
        bg.paste(fg, ((tw-fg.width)//2, max(0, y)))
        return bg


    def _render_video_first_frame(self, img, tw, th):
        """Replicate the export video branch: blurred background + video frame
        scaled with force_original_aspect_ratio=decrease (or increase+crop when
        cropping is enabled), centered."""
        bg = self._create_blur_bg(img, tw, th)
        iw, ih = img.size
        if self.settings.get("cropping"):
            r = max(tw / iw, th / ih)
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            x0 = (fg.width - tw) // 2
            y0 = (fg.height - th) // 2
            fg = fg.crop((x0, y0, x0 + tw, y0 + th))
            bg.paste(fg, (0, 0))
        else:
            r = min(tw / iw, th / ih)
            fg = img.resize((int(iw * r), int(ih * r)), Image.Resampling.LANCZOS)
            bg.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
        return bg


    def _preview_canvas_size(self, w, h):
        """Display size for a preview, preserving the resolution's aspect ratio."""
        max_w, max_h = 240, 420
        ar = w / h
        if ar >= 1.0:
            cw, ch = max_w, max(1, int(max_w / ar))
        else:
            cw, ch = max(1, int(max_h * ar)), max_h
        return cw, ch

