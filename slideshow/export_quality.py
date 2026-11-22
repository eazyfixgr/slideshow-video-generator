"""Export quality profiles and Facebook-oriented file-size targeting."""


EXPORT_QUALITY_OPTIONS = {
    "Υψηλή": "high",
    "Ισορροπημένη": "balanced",
    "Μικρότερο αρχείο": "compact",
    "Facebook (<100 MB, αυτόματο)": "facebook",
}

_ESTIMATED_BITRATES = {
    "high": (5_500_000, 600_000),
    "balanced": (3_500_000, 400_000),
    "compact": (1_800_000, 250_000),
}


class ExportQualityMixin:
    """Select CRF profiles or estimate a capped bitrate from project duration."""

    @staticmethod
    def facebook_video_bitrate(target_mb, duration, audio_bitrate=128_000):
        """Compute a conservative video bitrate for a target total file size."""
        target_bytes = max(10.0, min(99.0, float(target_mb))) * 1_000_000
        duration = max(1.0, float(duration))
        total_bitrate = target_bytes * 8 / duration
        return max(16_000, min(20_000_000, int(total_bitrate - audio_bitrate)))

    def _estimate_export_clips(self):
        default_image_duration = float(self.settings.get("slide_duration", 3) or 3)
        clips = []
        for media_type, path, edit in self.media_files:
            presentation = self._presentation_for(edit)
            if media_type == "image":
                duration = presentation["duration"] or default_image_duration
            else:
                duration_cache = getattr(self, "_video_dur_cache", None)
                cache_key = str(path)
                source_duration = (duration_cache.get(cache_key)
                                   if duration_cache is not None else None)
                if not source_duration:
                    queue = getattr(self, "_queue_timeline_video_duration", None)
                    if queue:
                        queue(path)
                    duration = presentation["duration"] or default_image_duration
                else:
                    duration = sum(length for _start, length in
                                   self.video_keep_segments(edit, source_duration))
                    if presentation["duration"] is not None:
                        duration = min(duration, presentation["duration"])
            clips.append({
                "type": "video" if media_type == "video" else "image",
                "duration": max(0.1, float(duration)),
                "transition": presentation.get("transition", "global"),
                "transition_duration": presentation.get("transition_duration"),
            })
        return clips

    def _estimate_export_duration_parts(self, clips=None):
        clips = self._estimate_export_clips() if clips is None else clips
        parts = {"image": 0.0, "video": 0.0}
        for clip in clips:
            parts[clip["type"]] += clip["duration"]
        return parts

    def _estimate_final_duration(self, clips):
        if not clips:
            return 1.0
        global_effect = self.settings.get("transition_effect", "fade")
        global_duration = float(self.settings.get("transition_duration", 0.7) or 0.7)
        valid_effects = {"fade", "fadeblack", "fadewhite", "wipeleft", "wiperight",
                         "wipeup", "wipedown", "smoothleft", "smoothright"}
        merged = clips[0]["duration"]
        for clip in clips[1:]:
            effect = clip["transition"]
            if effect in ("", None, "global"):
                effect = global_effect
            if effect == "random":
                effect = "fade"
            if effect not in valid_effects and effect != "none":
                effect = "fade"
            duration = clip["transition_duration"]
            if duration is None:
                duration = global_duration
            duration = max(0.2, min(2.0, float(duration)))
            overlap = min(duration, merged, clip["duration"]) if effect != "none" else 0.0
            merged += clip["duration"] - overlap
        return max(1.0, merged)

    def estimate_export_duration(self):
        """Estimate final duration, including configured transition overlaps."""
        return self._estimate_final_duration(self._estimate_export_clips())

    def estimate_export_metrics(self):
        """Return rough (seconds, decimal MB) estimates for the selected quality."""
        clips = self._estimate_export_clips()
        parts = self._estimate_export_duration_parts(clips)
        raw_duration = sum(parts.values())
        if raw_duration <= 0:
            return 0.0, 0.0
        duration = self._estimate_final_duration(clips)

        quality = self.settings.get("export_quality", "high")
        if quality == "facebook":
            video_bitrate = self.facebook_video_bitrate(
                self.settings.get("facebook_target_mb", 95), duration)
            size_mb = (video_bitrate + 128_000) * duration / 8_000_000
            return duration, size_mb

        try:
            width, height = map(int, self.settings.get("resolution", "1920x1080").split("x"))
            resolution_scale = max(0.25, width * height / (1920 * 1080))
        except (TypeError, ValueError):
            resolution_scale = 1.0
        video_bitrate, image_bitrate = _ESTIMATED_BITRATES.get(
            quality, _ESTIMATED_BITRATES["high"])
        content_bitrate = (parts["video"] * video_bitrate +
                           parts["image"] * image_bitrate) / raw_duration
        total_bitrate = content_bitrate * resolution_scale + 128_000
        size_mb = total_bitrate * duration / 8_000_000 * 1.04
        return duration, size_mb

    @staticmethod
    def format_estimated_duration(seconds):
        total = max(0, int(round(float(seconds or 0))))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        return (f"{hours}:{minutes:02d}:{seconds:02d}" if hours else
                f"{minutes:02d}:{seconds:02d}")

    def video_encode_options(self, preset="fast"):
        """Return ffmpeg encoder arguments for the selected quality profile."""
        quality = self.settings.get("export_quality", "high")
        if quality == "facebook":
            bitrate = getattr(self, "_export_video_bitrate", None)
            if bitrate is None:
                duration = self.estimate_export_duration()
                bitrate = self.facebook_video_bitrate(
                    self.settings.get("facebook_target_mb", 95), duration)
            return ["-preset", preset, "-b:v", str(bitrate),
                    "-maxrate", str(bitrate), "-bufsize", str(bitrate * 2)]
        crf = {"high": 18, "balanced": 23, "compact": 28}.get(quality, 18)
        return ["-preset", preset, "-crf", str(crf)]
