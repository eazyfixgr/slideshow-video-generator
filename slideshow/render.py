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

from .deps import (Image, ImageTk, ImageOps, ImageFilter, ImageDraw, ImageFont,
                   ImageEnhance, VideoFileClip, AudioFileClip, concatenate_audioclips,
                   np, DND_FILES, TkinterDnD, TKDND_AVAILABLE)
from .rich_text import line_height as rich_line_height
from .rich_text import line_width as rich_line_width
from .rich_text import wrap_spans
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
        project_template = getattr(self, "project_template", "legacy")
        presentation = normalize_presentation(value, project_template=project_template)
        if getattr(self, "project_caption_mode", None) in ("all", "by_type"):
            presentation["mode"] = "global"
        resolver = getattr(self, "_resolve_presentation_style", None)
        if resolver is not None:
            return resolver(presentation)
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
            img = ImageOps.exif_transpose(Image.open(path))
            img.load()
            return img.convert("RGB")
        except Exception:
            return fallback


    def _render_design_frame(self, source, edit, m_type, width, height, global_text=None):
        """Render a still frame through the shared slide template engine."""
        presentation = self._presentation_for(edit)
        layout = presentation.get("text_layout")
        below_media = ((layout == "below") if layout else
                       bool(self.settings.get("auto_position_videos" if m_type == "video"
                                              else "auto_position_photos", False)))
        fields = self._presentation_fields(presentation, m_type, global_text)
        before = self._presentation_before_image(presentation, fallback=source)
        frame, overflow = compose_design_frame(
            source, width, height, presentation, fields, before_image=before,
            auto_position_video=below_media,
            video_fill_mode=self.settings.get("video_auto_position_fill", "panel"),
            video_blur_contain=(m_type == "video" and
                                self._slide_background_mode(presentation) == "blur" and
                                not self.settings.get("cropping")))
        return frame, overflow


    def _legacy_style(self, presentation=None):
        presentation = presentation or {}
        family = (presentation.get("font_family") or
                  self.settings.get("font_family", "Calibri"))
        try:
            size = int(presentation.get("font_size") or
                       self.settings.get("font_size", 32))
        except (TypeError, ValueError):
            size = int(self.settings.get("font_size", 32) or 32)
        opacity = presentation.get("panel_opacity")
        if opacity is None:
            opacity = 100 if self.settings.get("text_style") == "black_box" else 0
        return {
            "font_family": family, "font_size": size,
            "text_color": presentation.get("text_color") or "#000000",
            "panel_color": presentation.get("panel_color") or "#FFFFFF",
            "accent_color": presentation.get("accent_color") or "#D6B86A",
            "panel_opacity": max(0, min(100, int(opacity))),
            "panel_width_pct": max(0, min(100, int(
                presentation.get("panel_width_pct") or 0))),
            "panel_padding_pct": float(presentation.get("panel_padding_pct") or 0),
            "panel_min_height_pct": int(presentation.get("panel_min_height_pct") or 0),
            "text_align": presentation.get("text_align") or "center",
        }

    def render_text_on_image(self, img, text, w, h, align="center", presentation=None):
        if not text:
            return img
        style = self._legacy_style(presentation)
        align = style["text_align"] if presentation is not None else align
        img = img.copy().convert("RGBA")
        draw = ImageDraw.Draw(img)
        fs = style["font_size"]
        family = style["font_family"]
        font, _f_bold = self._get_text_fonts(fs, family)
        width_pct = style["panel_width_pct"]
        area_w = max(1, int(w * width_pct / 100)) if 0 < width_pct < 100 else w
        area_x = (w - area_w) // 2
        _parts, lines = self._wrap_text_lines(text, area_w, fs, family)

        lh = fs + 5
        line_heights = [rich_line_height(line, lh) for line in lines]
        content_h = sum(line_heights)
        y = h - content_h - 15
        pad = max(15, int(min(w, h) * style["panel_padding_pct"] / 100))
        min_h = int(h * style["panel_min_height_pct"] / 100)
        if style["panel_opacity"] > 0 and lines:
            max_lw = max((int(rich_line_width(line, font)) for line in lines),
                         default=0)
            if 0 < width_pct < 100:
                box_x, box_w = area_x, area_w
            else:
                box_x = self._legacy_text_x(w, max_lw, align)
                box_w = max_lw + 2 * pad
            if 0 < width_pct < 100:
                left, right = box_x, box_x + box_w
            else:
                left, right = box_x - pad, box_x + max_lw + pad
            top = min(y - 5, h - max(content_h + 10, min_h) - 5)
            panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
            panel_draw = ImageDraw.Draw(panel)
            panel_color = style["panel_color"].lstrip("#")
            rgb = tuple(int(panel_color[i:i + 2], 16) for i in (0, 2, 4))
            alpha = int(style["panel_opacity"] * 2.55)
            panel_draw.rectangle(
                [left, top, right, h - 5 + max(0, min_h - content_h)],
                fill=(*rgb, alpha))
            img = Image.alpha_composite(img, panel)
            draw = ImageDraw.Draw(img)
        for line, line_h in zip(lines, line_heights):
            line_w = int(rich_line_width(line, font))
            x = area_x + self._legacy_text_x(area_w, line_w, align)
            for segment in line:
                if len(segment) == 2:
                    txt, seg_font = segment
                    is_accent = False
                else:
                    txt, seg_font, is_accent = segment
                color = style["accent_color"] if is_accent else style["text_color"]
                draw.text((x, y), txt, font=seg_font, fill=color)
                x += seg_font.getlength(txt)
            y += line_h
        return img


    def _auto_video_text_layout(self, text, width, height, presentation=None):
        """Reserve a bottom caption area so auto-positioned video stays unobscured."""
        if not (text or "").strip():
            return max(1, int(height)), 0
        style = self._legacy_style(presentation)
        font_size = style["font_size"]
        _parts, lines = self._wrap_text_lines(text, width, font_size,
                                              style["font_family"])
        text_height = sum(rich_line_height(line, font_size + 5)
                          for line in lines) + 40
        return max(100, int(height) - text_height), 20


    def _render_auto_position_video(self, source, presentation, text, width, height):
        """Fit the whole video above its caption and fill side gaps consistently."""
        available_h, top = self._auto_video_text_layout(text, width, height,
                                                        presentation)
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
            frame, text, width, height, align=presentation["text_align"],
            presentation=presentation)


    @staticmethod
    def _legacy_text_x(width, line_width, align):
        if align == "right":
            return width - line_width - 15
        if align == "center":
            return (width - line_width) // 2
        return 15


    def _wrap_text_lines(self, text, w, fs=None, family=None):
        """Split rich text into drawable wrapped lines - same layout as rendering.

        Returns (None, lines) where each line is [(text, font, is_accent), ...]
        so drawing and vertical-space estimates share the rich spans.
        """
        if fs is None:
            fs = self.settings.get("font_size", 32)
        if family is None:
            family = self.settings.get("font_family", "Calibri")
        base_font, _bold = self._get_text_fonts(fs, family)

        def font_factory(family_name, size, bold):
            regular, bold_font = self._get_text_fonts(size, family_name)
            return bold_font if bold else regular

        lines = wrap_spans(text, base_font, family, max(1, w - 60),
                           font_factory)
        return [], lines


    def _get_text_fonts(self, fs, family=None):
        """Regular + bold ImageFont for the chosen family."""
        family = family or self.settings.get("font_family", "Calibri")
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


    def _make_text_overlay(self, text, width, height, align="center", presentation=None):
        """Precompute the text overlay (panel + text on a transparent layer)
        once, so it can be pasted onto every frame cheaply instead of re-rendering
        the text 120 times per photo."""
        if not text:
            return None
        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        return self.render_text_on_image(base, text, width, height, align=align,
                                         presentation=presentation)


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
                                  image_duration, clip_path, text_align="center",
                                  design_layers=None, presentation=None):
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
                                              align=text_align,
                                              presentation=presentation)
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


    def _slide_background_mode(self, presentation=None):
        """Per-slide background override, else the project setting."""
        value = (presentation or {}).get("background_mode")
        if value in ("white", "black", "blur", "fit_and_move"):
            return value
        return self.settings.get("background_mode", "blur")

    def _fit_image_logic(self, img, tw, th, m_type, text=None, presentation=None):
        img = img.convert("RGB")  # keep every downstream op (blur, resize, paste, rawvideo) 
        style = self._legacy_style(presentation)
        layout = (presentation or {}).get("text_layout")
        auto_pos = ((layout == "below") if layout else
                    self.settings.get("auto_position_photos" if m_type == "image"
                                      else "auto_position_videos", False))
        iw, ih = img.size
        lh = style["font_size"] + 5
        text_here = self.get_text_for(m_type) if text is None else text
        _, wrapped_lines = (self._wrap_text_lines(text_here, tw, style["font_size"],
                                                  style["font_family"])
                            if text_here.strip() else ([], []))
        
        bg_m = self._slide_background_mode(presentation)
        if bg_m in ("blur", "fit_and_move"):
            bg = self._create_blur_bg(img, tw, th)
        else:
            bg = Image.new("RGB", (tw, th), (255,255,255) if bg_m == "white" else (0,0,0))
        
        if bg_m == "fit_and_move":
            # Fit the image in the area above the text, zoom in a bit, and attach
            # pan data so the export can animate a slow pan across the rest of the
            # photo. Auto-position is effectively implied (image sits above text).
            text_h = (sum(rich_line_height(line, lh) for line in wrapped_lines) + 40
                      if wrapped_lines else 0)
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
            av_h = th - (sum(rich_line_height(line, lh) for line in wrapped_lines) + 40)
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

