"""Export quality profiles and Facebook-oriented file-size targeting."""


EXPORT_QUALITY_OPTIONS = {
    "Υψηλή": "high",
    "Ισορροπημένη": "balanced",
    "Μικρότερο αρχείο": "compact",
    "Facebook (<100 MB, αυτόματο)": "facebook",
}


class ExportQualityMixin:
    """Select CRF profiles or estimate a capped bitrate from project duration."""

    @staticmethod
    def facebook_video_bitrate(target_mb, duration, audio_bitrate=128_000):
        """Compute a conservative video bitrate for a target total file size."""
        target_bytes = max(10.0, min(99.0, float(target_mb))) * 1_000_000
        duration = max(1.0, float(duration))
        video_budget = target_bytes * 8 * 0.88 / duration
        return max(64_000, min(20_000_000, int(video_budget - audio_bitrate)))

    def estimate_export_duration(self):
        """Estimate total slide duration without subtracting transition overlaps."""
        default_image_duration = float(self.settings.get("slide_duration", 3) or 3)
        total = 0.0
        for media_type, path, edit in self.media_files:
            presentation = self._presentation_for(edit)
            if media_type == "image":
                duration = presentation["duration"] or default_image_duration
            else:
                source_duration = self._video_duration(path)
                if source_duration > 0:
                    duration = sum(length for _start, length in
                                   self.video_keep_segments(edit, source_duration))
                else:
                    duration = default_image_duration
                if presentation["duration"] is not None:
                    duration = min(duration, presentation["duration"])
            total += max(0.1, float(duration))
        return max(1.0, total)

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
