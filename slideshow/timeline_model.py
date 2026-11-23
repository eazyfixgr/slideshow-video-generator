"""Time-based project/audio data shared by editing, preview and export."""

import copy
import math
import uuid


def number(value, default=0.0, low=0.0, high=86400.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value)) if math.isfinite(value) else default


def empty_audio():
    return {"version": 1, "mode": "auto", "tracks": []}


def new_track(name="Ήχος", **values):
    return {"id": uuid.uuid4().hex, "name": name, "volume_db": 0.0,
            "mute": False, "solo": False, "clips": [], **values}


def audio_clip(path, duration, start=0.0, **values):
    return {"id": uuid.uuid4().hex, "path": str(path), "start": max(0.0, start),
            "offset": 0.0, "duration": max(.05, duration), "volume_db": 0.0,
            "fade_in": 0.0, "fade_out": 0.0, **values}


def _clean_segments(values, source_duration=None):
    result = []
    for item in values if isinstance(values, list) else []:
        try:
            start, duration = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not math.isfinite(start) or not math.isfinite(duration):
            continue
        start = max(0.0, start)
        duration = max(0.0, duration)
        if source_duration is not None:
            duration = min(duration, max(0.0, float(source_duration) - start))
        if duration < .01:
            continue
        if result and abs(result[-1][0] + result[-1][1] - start) <= .001:
            result[-1][1] += duration
        else:
            result.append([start, duration])
    return result


def audio_segments(clip, source_duration=None):
    """Source ranges that remain in one timeline audio clip."""
    raw = clip.get("segments")
    segments = _clean_segments(raw, source_duration) if isinstance(raw, list) else []
    if segments:
        return segments
    offset = number(clip.get("offset"), 0)
    duration = number(clip.get("duration"), .05, .05)
    return _clean_segments([[offset, duration]], source_duration)


def set_audio_segments(clip, segments, source_duration=None):
    cleaned = _clean_segments(segments, source_duration)
    if not cleaned:
        return False
    clip["segments"] = cleaned
    clip["offset"] = cleaned[0][0]
    clip["duration"] = sum(duration for _start, duration in cleaned)
    return True


def remove_audio_range(segments, start, end, source_duration=None):
    """Remove a source-time range; the rest closes up without a silent hole."""
    source = _clean_segments(segments, source_duration)
    start, end = sorted((max(0.0, float(start)), max(0.0, float(end))))
    result = []
    for offset, duration in source:
        tail = offset + duration
        if end <= offset or start >= tail:
            result.append([offset, duration])
            continue
        if start > offset:
            result.append([offset, start - offset])
        if end < tail:
            result.append([end, tail - end])
    return _clean_segments(result, source_duration)


def cut_audio_edge(segments, edge, seconds, source_duration=None):
    """Remove ``seconds`` from the current kept beginning or end."""
    source = _clean_segments(segments, source_duration)
    seconds = max(0.0, float(seconds))
    if not source or seconds <= 0:
        return source
    if edge == "start":
        remaining = seconds
        while source and remaining > 0:
            offset, duration = source[0]
            if remaining >= duration - .001:
                remaining -= duration
                source.pop(0)
            else:
                source[0] = [offset + remaining, duration - remaining]
                remaining = 0
    else:
        remaining = seconds
        while source and remaining > 0:
            offset, duration = source[-1]
            if remaining >= duration - .001:
                remaining -= duration
                source.pop()
            else:
                source[-1] = [offset, duration - remaining]
                remaining = 0
    return _clean_segments(source, source_duration)


def normalize_audio(raw):
    if not isinstance(raw, dict):
        return empty_audio()
    result = {"version": 1, "mode": "manual" if raw.get("mode") == "manual" else "auto", "tracks": []}
    ids = set()
    for source in raw.get("tracks", []) if isinstance(raw.get("tracks"), list) else []:
        if not isinstance(source, dict):
            continue
        track = new_track(str(source.get("name") or "Ήχος")[:80])
        track["id"] = str(source.get("id") or track["id"])
        if track["id"] in ids:
            track["id"] = uuid.uuid4().hex
        ids.add(track["id"])
        track.update(volume_db=number(source.get("volume_db"), 0, -60, 20),
                     mute=bool(source.get("mute")), solo=bool(source.get("solo")))
        for item in source.get("clips", []) if isinstance(source.get("clips"), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                continue
            clip = audio_clip(item["path"], number(item.get("duration"), 1, .05))
            clip["id"] = str(item.get("id") or clip["id"])
            if clip["id"] in ids:
                clip["id"] = uuid.uuid4().hex
            ids.add(clip["id"])
            clip.update(start=number(item.get("start")), offset=number(item.get("offset")),
                        volume_db=number(item.get("volume_db"), 0, -60, 20),
                        fade_in=number(item.get("fade_in")), fade_out=number(item.get("fade_out")),
                        recording=bool(item.get("recording")))
            segments = _clean_segments(item.get("segments"))
            if segments:
                clip["segments"] = segments
                clip["offset"] = segments[0][0]
                clip["duration"] = sum(duration for _start, duration in segments)
            track["clips"].append(clip)
        result["tracks"].append(track)
    return result


def active_audio_clips(tracks):
    solo = any(track.get("solo") and not track.get("mute") for track in tracks)
    for track in tracks:
        if track.get("mute") or (solo and not track.get("solo")):
            continue
        for source in track.get("clips", []):
            clip = copy.deepcopy(source)
            clip["volume_db"] = number(track.get("volume_db"), 0, -60, 20) + number(
                source.get("volume_db"), 0, -60, 20)
            yield clip


def scene_timing(clips, settings):
    """Use the exact overlap formula used by FFmpeg xfade/concat."""
    timeline, end = [], 0.0
    for index, clip in enumerate(clips):
        duration = number(clip.get("duration"), 3, .1)
        effect = clip.get("transition", "global")
        if effect in ("", "global", None):
            effect = settings.get("transition_effect", "fade")
        raw = clip.get("transition_duration")
        transition = number(raw if raw is not None else settings.get("transition_duration", .7), .7, .2, 2)
        overlap = min(transition, end, duration) if index and effect != "none" else 0.0
        if overlap < .05:
            overlap = 0.0
        start = max(0.0, end - overlap)
        end = start + duration
        timeline.append({"index": index, "start": start, "end": end,
                         "duration": duration, "overlap": overlap, "effect": effect})
    return timeline, end


def source_time(segments, local_time):
    remaining = max(0.0, local_time)
    for start, duration in segments:
        if remaining < duration:
            return start + remaining
        remaining -= duration
    return sum(segments[-1]) - .02 if segments else 0.0


def trim_audio(clip, edge, delta, source_duration):
    result = copy.deepcopy(clip)
    if not isinstance(result.get("segments"), list) or not result["segments"]:
        if edge == "left":
            delta = max(-min(result["start"], result["offset"]),
                        min(delta, result["duration"] - .05))
            result["start"] += delta
            result["offset"] += delta
            result["duration"] -= delta
        else:
            result["duration"] = max(.05, min(result["duration"] + delta,
                                              source_duration - result["offset"]))
        return result

    segments = audio_segments(result, source_duration)
    total = sum(duration for _start, duration in segments)
    if edge == "left":
        delta = max(-min(result["start"], segments[0][0]), min(delta, total - .05))
        result["start"] = max(0.0, result["start"] + delta)
        if delta >= 0:
            segments = cut_audio_edge(segments, "start", delta, source_duration)
        else:
            extension = -delta
            segments[0][0] = max(0.0, segments[0][0] - extension)
            segments[0][1] += extension
    else:
        if delta >= 0:
            last = segments[-1]
            extend = max(0.0, min(delta, source_duration - last[0] - last[1]))
            last[1] += extend
        else:
            segments = cut_audio_edge(segments, "end", -delta, source_duration)
    if segments:
        set_audio_segments(result, segments, source_duration)
    return result
