"""Validated conversational edits against stable scene/library/audio IDs."""

import copy
import hashlib
import json
import math
import re
import uuid
from pathlib import Path

from .slide_design import normalize_presentation
from .slide_templates import STYLE_FIELDS, template_base
from .timeline_model import empty_audio, normalize_audio
from .ui_widgets import aspect_label, resolution_for_aspect


def project_fingerprint(app):
    state = [app.media_files, getattr(app, "project_audio", {}), app.project_caption_mode,
             app.project_text_all, app.project_text_photos, app.project_text_videos,
             app.project_template_name, app.project_template_override,
             {key: app.settings.get(key) for key in ("resolution", "slide_duration",
                                                     "transition_effect", "transition_duration")}]
    return hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode()).hexdigest()


def project_context(app):
    app._ensure_library_ids()
    scenes = []
    timing, total = app.timeline_layout()
    for index, (kind, path, edit) in enumerate(app.media_files):
        presentation = normalize_presentation(edit.get("presentation"))
        edit["presentation"] = presentation
        resolved = app._resolve_presentation_style(presentation)
        scenes.append({"scene_id": presentation["scene_id"], "position": index + 1,
                       "filename": Path(path).name, "type": kind, "group_id": edit.get("group_id"),
                       "caption": app._presentation_text(app._presentation_for(edit), kind),
                       "start": timing[index]["start"], "duration": timing[index]["duration"],
                       "template": resolved.get("template_name"),
                       "style": {key: resolved.get(key) for key in STYLE_FIELDS},
                       "background_mode": presentation.get("background_mode")})
    tracks = getattr(app, "_timeline_display_tracks", None) or getattr(app, "project_audio", {}).get("tracks", [])
    return {"brief": getattr(app, "project_ai_brief", ""), "duration": total,
            "aspect": aspect_label(app.settings.get("resolution")),
            "project_template": app._effective_project_template_name(),
            "transition_effect": app.settings.get("transition_effect"),
            "template_names": list(app.template_registry()), "scenes": scenes,
            "selected_scene_ids": [scenes[i]["scene_id"] for i in app._selected()],
            "library": [{"source_id": edit["library_id"], "filename": Path(path).name,
                         "type": kind, "description": edit.get("ai_description", "")}
                        for kind, path, edit in app.library_media],
            "audio_tracks": [{"track_id": track["id"], "name": track["name"], "mute": track["mute"],
                              "solo": track["solo"], "volume_db": track["volume_db"],
                              "clips": [{"filename": Path(clip["path"]).name, **{key: clip.get(key) for key in (
                                  "id", "start", "offset", "duration", "volume_db")}}
                                        for clip in track["clips"]]} for track in tracks]}


def chat_messages(context, history, instruction):
    system = (
        "Είσαι βοηθός μοντάζ στο Slideshow Video Creator. Συνέχισε τις οδηγίες του χρήστη "
        "πάνω στο ΤΡΕΧΟΝ project. Απάντησε μόνο JSON: {\"message\":\"απάντηση στα ελληνικά\","
        "\"operations\":[...]}. Για ερώτηση/διευκρίνιση βάλε operations:[]. Μην αλλάζεις "
        "μέρη που δεν ζητήθηκαν. Μόνο έγκυρα IDs από το context, ποτέ paths ή κώδικα. "
        "Επιτρεπόμενα operations:\n"
        "update_scenes: {type,scene_ids:[...],caption?,duration?,template_name?,background_mode?,style?:{...}}; "
        "οι αλλαγές σε μέλος ομάδας εφαρμόζονται σε όλη την ομάδα.\n"
        "reorder: {type,scene_ids:[όλα τα scene IDs στη νέα σειρά]}.\n"
        "remove_scenes: {type,scene_ids:[...]}.\n"
        "add_media: {type,source_ids:[library IDs],caption?,duration?,after_scene_id?}.\n"
        "project: {type,aspect?,template_name?,transition_effect?,slide_duration?}.\n"
        "update_audio: {type,clip_id,start?,offset?,duration?,volume_db?,fade_in?,fade_out?}.\n"
        "mute_track: {type,track_id,mute:true|false}.\n"
        "style keys: font_size,font_family,text_color,accent_color,panel_color,text_position,"
        "text_align,panel_opacity,panel_width_pct,panel_padding_pct,panel_min_height_pct,text_layout. "
        "background_mode: null|blur|white|black|fit_and_move. "
        "Captions: **bold**, ##έμφαση##, %+1%μεγαλύτερο%%. Διάρκειες σε δευτερόλεπτα."
    )
    messages = [{"role": "system", "content": system},
                {"role": "system", "content": "Τρέχον project:\n" + json.dumps(context, ensure_ascii=False)}]
    messages += [{"role": item["role"], "content": str(item["content"])[:12000]}
                 for item in history[-20:] if item.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": instruction})
    return messages


def checked_number(value, low, high, label):
    if isinstance(value, bool):
        raise ValueError(f"Μη έγκυρη τιμή {label}.")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"Μη έγκυρη τιμή {label}.")
    return number


def apply_chat_edits(app, reply):
    """Build changes on copies first; a rejected operation changes nothing."""
    if not isinstance(reply, dict) or not isinstance(reply.get("operations"), list):
        raise ValueError("Το AI δεν επέστρεψε έγκυρες αλλαγές.")
    operations = reply.get("operations", [])
    if len(operations) > 100:
        raise ValueError("Πάρα πολλές αλλαγές σε ένα μήνυμα.")
    media = copy.deepcopy(app.media_files)
    audio = normalize_audio(getattr(app, "project_audio", empty_audio()))
    if audio["mode"] == "auto" and getattr(app, "_timeline_display_tracks", None):
        audio["tracks"] = copy.deepcopy(app._timeline_display_tracks)
    registry = app.template_registry()
    settings = {}
    template = None
    caption_change = any(op.get("type") in ("update_scenes", "add_media") and "caption" in op
                         for op in operations if isinstance(op, dict))
    if caption_change:
        for kind, _path, edit in media:
            p = normalize_presentation(edit.get("presentation"))
            if app.project_caption_mode != "individual" or p["mode"] == "global":
                p.update(mode="custom", title="", subtitle="", description=app.get_text_for(kind))
                edit["presentation"] = p

    def find(ids, expand=False):
        if not isinstance(ids, list) or not ids:
            raise ValueError("Λείπουν scene IDs.")
        by_id = {item[2]["presentation"]["scene_id"]: item for item in media}
        if any(scene_id not in by_id for scene_id in ids):
            raise ValueError("Το AI αναφέρθηκε σε σκηνή που δεν υπάρχει.")
        targets = [by_id[scene_id] for scene_id in ids]
        groups = {item[2].get("group_id") for item in targets if item[2].get("group_id")}
        if expand and groups:
            target_ids = set(ids)
            targets = [item for item in media if item[2]["presentation"]["scene_id"] in target_ids
                       or item[2].get("group_id") in groups]
        return targets

    for op in operations:
        if not isinstance(op, dict):
            raise ValueError("Μη έγκυρη εντολή AI.")
        action = op.get("type")
        if action == "update_scenes":
            targets = find(op.get("scene_ids"), True)
            changes = {}
            if "caption" in op:
                if not isinstance(op["caption"], str) or len(op["caption"]) > 8000:
                    raise ValueError("Μη έγκυρο caption.")
                changes.update(mode="custom", description=op["caption"], title="", subtitle="")
            if "duration" in op:
                changes["duration"] = checked_number(op["duration"], 1, 30, "διάρκειας")
            if "background_mode" in op:
                if op["background_mode"] not in (None, "blur", "white", "black", "fit_and_move"):
                    raise ValueError("Μη έγκυρο φόντο.")
                changes["background_mode"] = op["background_mode"]
            chosen_template = op.get("template_name")
            if chosen_template is not None and chosen_template not in registry:
                raise ValueError("Το template δεν υπάρχει.")
            style = op.get("style", {})
            if not isinstance(style, dict) or any(key not in STYLE_FIELDS for key in style):
                raise ValueError("Μη επιτρεπτή αλλαγή στυλ.")
            for key, value in style.items():
                if key.endswith("_color") and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(value)):
                    raise ValueError("Μη έγκυρο χρώμα.")
                if key == "font_size":
                    checked_number(value, 8, 400, "γραμματοσειράς")
                if key in ("panel_opacity", "panel_width_pct", "panel_padding_pct", "panel_min_height_pct"):
                    high = {"panel_padding_pct": 15, "panel_min_height_pct": 80}.get(key, 100)
                    checked_number(value, 0, high, key)
                if key == "font_family" and (not isinstance(value, str) or len(value) > 160):
                    raise ValueError("Μη έγκυρη γραμματοσειρά.")
                if key == "text_layout" and value not in ("overlay", "below"):
                    raise ValueError("Μη έγκυρη τοποθέτηση κειμένου.")
                if key == "text_align" and value not in ("left", "center", "right"):
                    raise ValueError("Μη έγκυρη στοίχιση.")
                if key == "text_position" and value not in ("top", "center", "bottom"):
                    raise ValueError("Μη έγκυρη θέση κειμένου.")
            for item in targets:
                p = normalize_presentation(item[2].get("presentation"))
                p.update(changes)
                if chosen_template:
                    p.update(template=template_base(chosen_template, registry),
                             template_name=chosen_template, style_overrides=[])
                p.update(style)
                p["style_overrides"] = sorted(set(p.get("style_overrides", [])) | set(style))
                item[2]["presentation"] = normalize_presentation(p)
        elif action == "reorder":
            ordered = find(op.get("scene_ids"))
            if len(ordered) != len(media) or len(set(op["scene_ids"])) != len(media):
                raise ValueError("Η αναδιάταξη πρέπει να περιλαμβάνει κάθε σκηνή μία φορά.")
            media = ordered
        elif action == "remove_scenes":
            find(op.get("scene_ids"))
            media = [item for item in media if item[2]["presentation"]["scene_id"] not in op["scene_ids"]]
        elif action == "add_media":
            sources = {edit.get("library_id"): (kind, path) for kind, path, edit in app.library_media}
            ids = op.get("source_ids")
            if not isinstance(ids, list) or not ids or any(source not in sources for source in ids):
                raise ValueError("Το AI ζήτησε media εκτός βιβλιοθήκης.")
            new_items = []
            group = uuid.uuid4().hex if len(ids) > 1 else None
            for source in ids:
                kind, path = sources[source]
                item = app._new_item(kind, path)
                item[2]["source_library_id"] = source
                if group:
                    item[2]["group_id"] = group
                if "caption" in op:
                    item[2]["presentation"].update(mode="custom", description=str(op["caption"])[:8000])
                    caption_change = True
                if "duration" in op:
                    item[2]["presentation"]["duration"] = checked_number(op["duration"], 1, 30, "διάρκειας")
                new_items.append(item)
            after = op.get("after_scene_id")
            position = len(media)
            if after:
                anchor = find([after])[0]
                position = media.index(anchor) + 1
            media[position:position] = new_items
        elif action == "project":
            if "aspect" in op:
                if op["aspect"] not in ("9:16", "4:5", "1:1", "16:9"):
                    raise ValueError("Μη έγκυρη μορφή project.")
                settings["resolution"] = resolution_for_aspect(op["aspect"])
            if "template_name" in op:
                if op["template_name"] not in registry:
                    raise ValueError("Το template δεν υπάρχει.")
                template = op["template_name"]
            if "slide_duration" in op:
                settings["slide_duration"] = checked_number(op["slide_duration"], 1, 30, "διάρκειας")
            if "transition_effect" in op:
                if op["transition_effect"] not in ("none", "fade", "fadeblack", "fadewhite", "wipeleft",
                                                   "wiperight", "wipeup", "wipedown", "smoothleft", "smoothright", "random"):
                    raise ValueError("Μη έγκυρο εφέ.")
                settings["transition_effect"] = op["transition_effect"]
        elif action in ("update_audio", "mute_track"):
            audio["mode"] = "manual"
            if action == "mute_track":
                tracks = [track for track in audio["tracks"] if track["id"] == op.get("track_id")]
                if not tracks or not isinstance(op.get("mute"), bool):
                    raise ValueError("Μη έγκυρο audio track.")
                tracks[0]["mute"] = op["mute"]
            else:
                clips = [clip for track in audio["tracks"] for clip in track["clips"] if clip["id"] == op.get("clip_id")]
                if not clips:
                    raise ValueError("Το audio clip δεν υπάρχει.")
                for key in ("start", "offset", "duration", "volume_db", "fade_in", "fade_out"):
                    if key in op:
                        clips[0][key] = checked_number(op[key], -60 if key == "volume_db" else .05 if key == "duration" else 0,
                                                       20 if key == "volume_db" else 86400, key)
                information = app._analyze_project_audio(clips[0]["path"])
                if clips[0]["offset"] + clips[0]["duration"] > information["duration"] + .05:
                    raise ValueError("Το trim ήχου ξεπερνά τη διάρκεια του αρχείου.")
        else:
            raise ValueError(f"Μη υποστηριζόμενη εντολή AI: {action}")
    if operations:
        app._stop_preview_play()
        app.push_undo()
        app.media_files = media
        app.project_audio = audio
        app.settings.update(settings)
        if template:
            app.project_template_name = template
            app.project_template = template_base(template, registry)
            app.project_template_override = True
        if caption_change:
            app.project_caption_mode = "individual"
        app.selected_indices = {0} if media else set()
        app.is_modified = True
        app.update_media_display()
        app._refresh_inspector_after_media(force=True)
    return str(reply.get("message") or ("Οι αλλαγές εφαρμόστηκαν." if operations
                                       else "Δεν ζητήθηκαν αλλαγές."))[:16000]
