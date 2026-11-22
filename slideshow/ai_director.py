"""AI Director: turn a brief + media inventory into a validated video plan."""

import base64
import io
import json
import re
import uuid
from pathlib import Path

from .slide_design import normalize_presentation
from .ui_widgets import aspect_label, resolution_for_aspect

BACKGROUND_MODES = {"blur", "white", "black", "fit_and_move"}
ASPECTS = {"9:16", "4:5", "1:1", "16:9"}


def ensure_inventory(app):
    if hasattr(app, "_ensure_library_ids"):
        app._ensure_library_ids()
    inventory = []
    for kind, path, edit in getattr(app, "library_media", []):
        source_id = str(edit.get("library_id") or "")
        if not source_id:
            continue
        filename = Path(path).name
        duration = None
        if kind == "video":
            cached = app._video_dur_cache.get(str(path))
            if cached is None:
                try:
                    cached = app._video_duration(path)
                except Exception:
                    cached = 0
                app._video_dur_cache[str(path)] = cached
            duration = round(float(cached or 0), 2) or None
        inventory.append({
            "id": source_id,
            "type": kind,
            "filename": filename,
            "duration": duration,
            "description": str(edit.get("ai_description") or ""),
            "path": str(path),
        })
    return inventory


def public_inventory(inventory):
    return [{key: item.get(key) for key in ("id", "type", "filename",
                                            "duration", "description")}
            for item in inventory]


def parse_plan(text):
    text = str(text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Ο AI Director δεν επέστρεψε έγκυρο JSON.")
    return json.loads(text[start:end + 1])


def validate_plan(plan, inventory, current_aspect="9:16", registry=None):
    if not isinstance(plan, dict):
        raise ValueError("Το πλάνο του AI Director δεν είναι έγκυρο.")
    by_id = {item["id"]: item for item in inventory}
    scenes = []
    for raw in plan.get("scenes") or []:
        if not isinstance(raw, dict):
            continue
        raw_ids = raw.get("source_ids")
        if not isinstance(raw_ids, list):
            raw_ids = [raw.get("source_id")]
        source_ids = []
        for source_id in raw_ids:
            source_id = str(source_id or "")
            if source_id in by_id and source_id not in source_ids:
                source_ids.append(source_id)
        if not source_ids:
            continue
        try:
            duration = max(1.0, min(30.0, float(raw.get("duration") or 3)))
        except (TypeError, ValueError):
            duration = 3.0
        background = raw.get("background_mode")
        if background not in BACKGROUND_MODES:
            background = None
        caption = str(raw.get("caption") or "").strip()[:600]
        scenes.append({
            "source_ids": source_ids,
            "duration": round(duration, 2),
            "caption": caption,
            "background_mode": background,
        })
    scenes = scenes[:30]
    if not scenes:
        raise ValueError("Το AI Director δεν διάλεξε κανένα έγκυρο media. "
                         "Πρόσθεσε περισσότερα media ή περιέγραψέ τα καλύτερα.")
    aspect = str(plan.get("aspect") or current_aspect)
    if aspect not in ASPECTS:
        aspect = current_aspect if current_aspect in ASPECTS else "9:16"
    template = plan.get("template")
    if not isinstance(template, str) or (registry is not None and template not in registry):
        template = None
    try:
        target = max(5.0, min(120.0, float(plan.get("target_duration") or 30)))
    except (TypeError, ValueError):
        target = 30.0
    return {
        "version": 1,
        "title": str(plan.get("title") or "AI Director video").strip()[:120],
        "aspect": aspect,
        "target_duration": round(target, 1),
        "template": template,
        "scenes": scenes,
    }


def build_messages(brief, inventory, options, vision=False):
    system = (
        "Είσαι AI video director. Σχεδιάζεις ένα σύντομο slideshow από τα media "
        "που σου δίνονται. Απαντάς ΜΟΝΟ με ένα έγκυρο JSON object, χωρίς markdown, "
        "χωρίς σχόλια. Χρησιμοποίησε μόνο τα source_id που υπάρχουν στο inventory. "
        "Μπορείς να χρησιμοποιήσεις το ίδιο media περισσότερες από μία φορές. "
        "Γράψε τα captions στη γλώσσα του θέματος, με προαιρετικό markup "
        "**bold**, ##accent##, %+1%μεγαλύτερο%%. "
        "Το JSON πρέπει να έχει αυτό το σχήμα:\n"
        '{"title":"...","aspect":"9:16|4:5|1:1|16:9",'
        '"target_duration":30,"template":null,"scenes":['
        '{"source_ids":["..."],"duration":3.0,"caption":"...",'
        '"background_mode":null}]}'
    )
    payload = {
        "brief": str(brief or "").strip(),
        "target_duration": options.get("target_duration"),
        "aspect": options.get("aspect"),
        "preferred_template": options.get("template"),
        "style": options.get("style") or "",
        "media": public_inventory(inventory),
    }
    user = (
        "Θέμα / οδηγίες χρήστη:\n" + (brief or "") +
        "\n\nΣτοιχεία βίντεο:\n" + json.dumps(payload, ensure_ascii=False, indent=2) +
        "\n\nΚανόνες:\n"
        "- Διάλεξε 4 έως 12 σκηνές ανάλογα με το διαθέσιμο υλικό.\n"
        "- Σεβάσου τη συνολική διάρκεια (target_duration) όσο γίνεται.\n"
        "- Κάθε σκηνή 1–30 δευτερόλεπτα.\n"
        "- Όταν 2+ media πρέπει να έχουν το ίδιο caption/design/διάρκεια, "
        "βάλ' τα σε ΜΙΑ σκηνή με πολλά source_ids. Μην επαναλαμβάνεις το ίδιο "
        "caption σε ξεχωριστές σκηνές.\n"
        "- Χρησιμοποίησε description όταν υπάρχει, αλλιώς filename/type.\n"
        "- Αν το template είναι null, άφησε το project template ως έχει.\n"
        "- Μην εφεύρεις media ή στοιχεία που δεν υπάρχουν.\n"
        "- Απάντησε μόνο με JSON."
    )
    messages = [{"role": "system", "content": system}]
    if vision:
        messages.append({"role": "user", "content": [{"type": "text", "text": user}]})
    else:
        messages.append({"role": "user", "content": user})
    return messages


def prepare_vision_images(app, inventory, max_images=8):
    """Small JPEG data URLs for vision-capable OpenAI-compatible models."""
    from .deps import Image

    selected = []
    for item in inventory:
        if len(selected) >= max(0, int(max_images or 0)):
            break
        try:
            if item["type"] == "video":
                image = app._video_first_frame(item["path"])
            else:
                image = app.open_thumbnail_image(item["path"], 640, apply_exif=True)
            image = image.convert("RGB")
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, "JPEG", quality=82)
            url = ("data:image/jpeg;base64," +
                   base64.b64encode(buffer.getvalue()).decode("ascii"))
        except Exception:
            continue
        selected.append((item, url))
    return selected


def vision_message_parts(selected, user_text):
    content = [{"type": "text", "text": user_text}]
    for item, url in selected:
        content.append({"type": "text",
                        "text": f"Εικόνα για media id={item['id']} "
                                f"({item['filename']}):"})
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def apply_plan(app, plan):
    """Replace the project scenes with the AI plan and switch to per-scene captions."""
    app._ensure_library_ids()
    inventory = ensure_inventory(app)
    by_id = {item["id"]: item for item in inventory}
    app.push_undo()
    if plan.get("title") and not app.name_var.get().strip():
        app.name_var.set(plan["title"])
    aspect = plan.get("aspect") or aspect_label(app.settings.get("resolution"))
    app.settings["resolution"] = resolution_for_aspect(aspect)
    app.project_settings = app._capture_project_settings()
    app._active_project_settings = True
    template = plan.get("template")
    if template:
        app.set_project_template(template, mark_modified=False)
    app.media_files = []
    app.project_caption_mode = "individual"
    app.project_text_all = ""
    app.project_text_videos = ""
    app.project_text_photos = ""
    for scene in plan.get("scenes") or []:
        source_ids = [source_id for source_id in (scene.get("source_ids") or [])
                      if source_id in by_id]
        group_id = uuid.uuid4().hex if len(source_ids) > 1 else ""
        for source_id in source_ids:
            item = by_id[source_id]
            kind, path = item["type"], item["path"]
            _kind, _path, edit = app._new_item(kind, path)
            edit["source_library_id"] = item["id"]
            if group_id:
                edit["group_id"] = group_id
            presentation = normalize_presentation(
                edit.get("presentation"), project_template=app.project_template)
            presentation.update(mode="custom", title="", subtitle="",
                                description=str(scene.get("caption") or ""),
                                duration=scene.get("duration"),
                                background_mode=scene.get("background_mode"),
                                transition="global", transition_duration=None)
            edit["presentation"] = presentation
            app.media_files.append((kind, path, edit))
    app.selected_indices = {0} if app.media_files else set()
    app._sel_anchor = 0 if app.media_files else None
    app.is_modified = True
    app.update_media_display()
    app._refresh_inspector_after_media(force=True)
    app._schedule_preview(150)
    return app.media_files
