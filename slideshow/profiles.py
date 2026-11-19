"""Profile registry and per-profile workspace paths.

The first profile keeps using the existing ``settings.json`` and ``projects/``
so no user data is moved or copied. New profiles get an isolated folder under
``profiles/<id>/`` with their own settings, projects, music and temp data.
"""

import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

REGISTRY_NAME = "profiles.json"
DEFAULT_PROFILE_NAME = "Ρίτα Σαμοθράκη"
DEFAULT_PROFILE_ROLE = "Μεσιτικό γραφείο"
DEFAULT_PROFILE_COLOR = "#e8bd79"
PROFILE_COLORS = ("#e8bd79", "#84c5a5", "#8fb8e8", "#d59ce0", "#e89a8f", "#b8c18a")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value))


def initials(name, fallback="Π"):
    words = [word for word in re.split(r"\s+", str(name or "").strip()) if word]
    letters = "".join(word[0] for word in words[:2]).upper()
    return letters or fallback


def _default_profile():
    return {
        "id": "main",
        "name": DEFAULT_PROFILE_NAME,
        "role": DEFAULT_PROFILE_ROLE,
        "color": DEFAULT_PROFILE_COLOR,
        "legacy": True,
        "created_at": _now(),
        "last_project": "",
    }


def registry_path(app_dir):
    return Path(app_dir) / REGISTRY_NAME


def _sanitize_profile(profile):
    if not isinstance(profile, dict):
        return None
    profile_id = profile.get("id")
    if not _valid_id(profile_id):
        return None
    name = str(profile.get("name") or "Προφίλ").strip() or "Προφίλ"
    role = str(profile.get("role") or "").strip()
    color = str(profile.get("color") or DEFAULT_PROFILE_COLOR)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = DEFAULT_PROFILE_COLOR
    last_project = profile.get("last_project")
    if not isinstance(last_project, str):
        last_project = ""
    return {
        "id": profile_id,
        "name": name,
        "role": role,
        "color": color,
        "legacy": bool(profile.get("legacy")),
        "created_at": str(profile.get("created_at") or _now()),
        "last_project": last_project,
    }


def load_registry(app_dir):
    path = registry_path(app_dir)
    data = None
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8-sig") as stream:
                data = json.load(stream)
        except (OSError, ValueError):
            data = None

    profiles = []
    if isinstance(data, dict) and isinstance(data.get("profiles"), list):
        for profile in data["profiles"]:
            cleaned = _sanitize_profile(profile)
            if cleaned is not None:
                profiles.append(cleaned)
    if not profiles:
        profiles = [_default_profile()]

    active = data.get("active_profile") if isinstance(data, dict) else None
    if not any(profile["id"] == active for profile in profiles):
        active = profiles[0]["id"]
    registry = {"version": 1, "active_profile": active, "profiles": profiles}
    save_registry(app_dir, registry)
    return registry


def save_registry(app_dir, registry):
    path = registry_path(app_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(registry, stream, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def active_profile(registry):
    active_id = registry.get("active_profile")
    for profile in registry.get("profiles", []):
        if profile.get("id") == active_id:
            return profile
    profiles = registry.get("profiles", [])
    return profiles[0] if profiles else _default_profile()


def get_profile(registry, profile_id):
    for profile in registry.get("profiles", []):
        if profile.get("id") == profile_id:
            return profile
    return None


def set_active(registry, profile_id):
    profile = get_profile(registry, profile_id)
    if profile is None:
        return False
    registry["active_profile"] = profile_id
    return True


def update_profile(registry, profile_id, **fields):
    profile = get_profile(registry, profile_id)
    if profile is None:
        return False
    for key in ("name", "role", "color", "last_project"):
        if key in fields:
            profile[key] = fields[key]
    return True


def profile_base_dir(app_dir, profile):
    if profile.get("legacy"):
        return Path(app_dir)
    return Path(app_dir) / "profiles" / profile["id"]


def profile_paths(app_dir, profile):
    base = profile_base_dir(app_dir, profile)
    if profile.get("legacy"):
        return {
            "settings": Path(app_dir) / "settings.json",
            "projects": Path(app_dir) / "projects",
            "music_tracker": Path(app_dir) / "music_tracker.json",
            "temp": Path(app_dir) / "temp",
            "music": Path(app_dir) / "music",
            "output": Path(app_dir),
            "base": base,
        }
    return {
        "settings": base / "settings.json",
        "projects": base / "projects",
        "music_tracker": base / "music_tracker.json",
        "temp": base / "temp",
        "music": base / "music",
        "output": base / "output",
        "base": base,
    }


def ensure_profile_paths(app_dir, profile):
    paths = profile_paths(app_dir, profile)
    for key in ("projects", "temp", "music", "output"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths


def create_profile(registry, app_dir, name, role="", color=None):
    name = str(name or "").strip()
    if not name:
        raise ValueError("Το όνομα του προφίλ δεν μπορεί να είναι κενό.")
    profile_id = f"p_{uuid.uuid4().hex[:8]}"
    profile = {
        "id": profile_id,
        "name": name,
        "role": str(role or "").strip(),
        "color": color if re.fullmatch(r"#[0-9a-fA-F]{6}", str(color or "")) else
                 PROFILE_COLORS[len(registry.get("profiles", [])) % len(PROFILE_COLORS)],
        "legacy": False,
        "created_at": _now(),
        "last_project": "",
    }
    registry.setdefault("profiles", []).append(profile)
    registry["active_profile"] = profile_id
    ensure_profile_paths(app_dir, profile)
    save_registry(app_dir, registry)
    return profile


def last_project_path(app_dir, profile, projects_dir=None):
    filename = profile.get("last_project") or ""
    if not filename:
        return None
    base = Path(projects_dir) if projects_dir else profile_paths(app_dir, profile)["projects"]
    candidate = base / Path(filename).name
    return candidate if candidate.is_file() else None


def set_last_project(app_dir, registry, profile_id, project_path):
    profile = get_profile(registry, profile_id)
    if profile is None:
        return
    profile["last_project"] = Path(project_path).name
    save_registry(app_dir, registry)
