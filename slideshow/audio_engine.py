"""Audio analysis, deterministic automatic music and shared multitrack mixer."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from .timeline_model import active_audio_clips, audio_clip, audio_segments, new_track

FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def analyze_audio(path, trim=False):
    duration_run = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30, creationflags=FLAGS)
    duration = float(duration_run.stdout.strip())
    if duration <= 0:
        raise ValueError("Το αρχείο ήχου δεν έχει διάρκεια.")
    decoded = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1",
         "-ar", "2000", "-t", "3600", "-f", "f32le", "-"],
        capture_output=True, timeout=90, creationflags=FLAGS)
    if decoded.returncode:
        raise ValueError(decoded.stderr.decode(errors="replace")[-300:])
    samples = np.abs(np.frombuffer(decoded.stdout, dtype="<f4"))
    peaks = [float(part.max()) if part.size else 0 for part in np.array_split(samples, 1200)]
    start, end = 0.0, duration
    if trim and samples.size and duration <= 3600:
        audible = np.flatnonzero(samples > 10 ** (-45 / 20))
        if audible.size:
            start = max(0, float(audible[0]) / 2000 - .05)
            end = min(duration, float(audible[-1]) / 2000 + .05)
    return {"duration": duration, "offset": start, "usable": max(.05, end - start),
            "peaks": peaks}


def automatic_music(settings, tracker, duration, analyze):
    folder = Path(settings.get("music_folder") or ".")
    names = list(tracker.get("available_music", []))
    used = set(tracker.get("used_music", []))
    order = [name for name in names if name not in used]
    if not order:
        order = names[:]
    track = new_track("Αυτόματη μουσική", id="auto-music", volume_db=float(settings.get("volume_db", 0)))
    position, previous_duration, sequence = 0.0, 0.0, 0
    while names and (position < duration or not track["clips"]) and sequence < 300:
        if not order:
            order = names[:]
        name = order.pop(0)
        sequence += 1
        path = folder / name
        if not path.is_file():
            if sequence >= len(names) and not track["clips"]:
                break
            continue
        info = analyze(path, bool(settings.get("trim_silence")))
        length = info["usable"]
        cross = min(float(settings.get("crossfade_duration", 0) or 0),
                    max(0, min(previous_duration, length) / 2)) if track["clips"] else 0
        start = max(0.0, position - cross)
        clip = audio_clip(str(path), length, start, offset=info["offset"],
                          id=f"auto-{sequence}", fade_in=cross)
        if track["clips"]:
            track["clips"][-1]["fade_out"] = cross
        track["clips"].append(clip)
        position = start + length
        previous_duration = length
    return [track] if track["clips"] else []


def extend_music(tracks, settings, tracker, duration, analyze):
    """Append songs after an existing project plan; never replace old clips."""
    tracks = copy.deepcopy(tracks)
    track = next((item for item in tracks if item.get("name") == "Αυτόματη μουσική"),
                 tracks[0] if tracks else None)
    if track is None or not track.get("clips"):
        return automatic_music(settings, tracker, duration, analyze)
    clips = track["clips"]
    position = max(clip["start"] + clip["duration"] for clip in clips)
    if position >= duration - .05:
        return tracks
    folder = Path(settings.get("music_folder") or ".")
    names = list(tracker.get("available_music", []))
    chosen = {str(Path(clip["path"]).resolve()) for clip in clips}
    order = [name for name in names
             if str((folder / name).resolve()) not in chosen] or names[:]
    guard = 0
    while order and position < duration and guard < 300:
        guard += 1
        path = folder / order.pop(0)
        if not path.is_file():
            continue
        info = analyze(path, bool(settings.get("trim_silence")))
        length = info["usable"]
        previous = clips[-1]
        cross = min(float(settings.get("crossfade_duration", 0) or 0),
                    max(0, min(previous["duration"], length) / 2))
        start = max(0.0, position - cross)
        previous["fade_out"] = cross
        clips.append(audio_clip(str(path), length, start, offset=info["offset"],
                                fade_in=cross))
        chosen.add(str(path.resolve()))
        position = start + length
        if not order and position < duration:
            last = str(Path(clips[-1]["path"]).resolve())
            order = [name for name in names
                     if str((folder / name).resolve()) != last] or names[:]
    return tracks


def mix_command(tracks, duration, output, video_clips=None):
    """All time offsets, trims, fades, track gains/mute/solo share one graph."""
    solo = any(track.get("solo") and not track.get("mute") for track in tracks)
    clips = list(active_audio_clips(tracks)) + ([] if solo else list(video_clips or []))
    inputs, graph, labels = [], [], []
    for clip in clips:
        if clip["start"] >= duration or clip["duration"] <= 0:
            continue
        if not Path(clip["path"]).is_file():
            raise FileNotFoundError(f"Λείπει αρχείο ήχου: {clip['path']}")
        index = len(labels)
        length = min(clip["duration"], duration - clip["start"])
        ranges, remaining = [], length
        for source_start, source_length in audio_segments(clip):
            take = min(source_length, remaining)
            if take > .001:
                ranges.append((source_start, take))
                remaining -= take
            if remaining <= .001:
                break
        if not ranges:
            continue
        inputs += ["-i", str(clip["path"])]
        segment_labels = []
        for segment_index, (source_start, source_length) in enumerate(ranges):
            label = f"[c{index}_{segment_index}]"
            graph.append(
                f"[{index}:a]atrim=start={source_start:.6f}:duration={source_length:.6f},"
                "asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo"
                f"{label}")
            segment_labels.append(label)
        if len(segment_labels) == 1:
            chain = segment_labels[0]
        else:
            chain = "".join(segment_labels) + f"concat=n={len(segment_labels)}:v=0:a=1[joined{index}]"
            graph.append(chain)
            chain = f"[joined{index}]"
        played = sum(segment_length for _start, segment_length in ranges)
        chain += f"volume={float(clip.get('volume_db', 0)):.3f}dB"
        fade_in = min(float(clip.get("fade_in", 0)), played)
        fade_out = min(float(clip.get("fade_out", 0)), played)
        if fade_in:
            chain += f",afade=t=in:st=0:d={fade_in:.6f}"
        if fade_out:
            chain += f",afade=t=out:st={played-fade_out:.6f}:d={fade_out:.6f}"
        delay = max(0, round(clip["start"] * 48000))
        chain += f",adelay={delay}S:all=1[a{index}]"
        labels.append(f"[a{index}]")
        graph.append(chain)
    if not labels:
        return ["ffmpeg", "-y", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
                "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.6f}", str(output)]
    graph.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,"
                 f"alimiter=limit=0.98:level=false:latency=1,apad,atrim=duration={duration:.6f}[mix]")
    return ["ffmpeg", "-y", "-nostdin", "-v", "error", *inputs, "-filter_complex",
            ";".join(graph), "-map", "[mix]", "-t", f"{duration:.6f}", str(output)]


def audio_fingerprint(tracks, duration, video_clips=None):
    payload = json.dumps([tracks, duration, video_clips], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
