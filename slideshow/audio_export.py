"""Render the timeline's exact multitrack audio and mux it into the final video."""

import os
from pathlib import Path

from .audio_engine import mix_command
from .timeline_model import audio_clip


class AudioExportMixin:
    def finalize_audio_ffmpeg(self, vid_p, out_p, duration, temp_dir, voice_path=None):
        tracks = self.project_audio_plan(duration)
        source_audio = []
        if voice_path and Path(voice_path).is_file():
            source_audio = [audio_clip(str(voice_path), duration,
                                      volume_db=float(self.settings.get("video_audio_volume_db", 0)))]
        mix = temp_dir / "timeline_audio.m4a"
        self._run_ffmpeg_or_raise(mix_command(tracks, duration, mix, source_audio),
                                   "mixing timeline audio")
        output = Path(out_p)
        temporary = output.with_name(output.stem + "_tmp" + output.suffix)
        try:
            self._run_ffmpeg_or_raise(
                ["ffmpeg", "-y", "-i", str(vid_p), "-i", str(mix), "-map", "0:v:0",
                 "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-t", f"{duration:.6f}",
                 str(temporary)], "muxing timeline audio into video")
            if self._probe_duration(temporary, 0) < duration - .15:
                raise RuntimeError("Το τελικό βίντεο βγήκε μικρότερο από το timeline.")
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        self._export_voice_used = bool(source_audio) or any(
            clip.get("recording") for track in tracks for clip in track["clips"])
        self._export_music_missing = (getattr(self, "project_audio", {}).get("mode", "auto") == "auto"
                                      and not tracks)
        if getattr(self, "project_audio", {}).get("mode", "auto") == "auto":
            for track in tracks:
                for clip in track["clips"]:
                    self.mark_music_used(clip["path"])
            self.save_music_tracker()
        self._log_export(f"timeline audio: {len(tracks)} track(s), duration {duration:.3f}s")
