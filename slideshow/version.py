"""One version for Python installations, release archives and frozen builds."""

import json
import re
import sys
from pathlib import Path

REPOSITORY = "eazyfixgr/slideshow-video-generator"
APP_EXE = "SlideshowVideoCreator.exe"
LAUNCHER = "slideshow_app v4.py"


def version_tuple(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(value).strip())
    if not match:
        raise ValueError(f"Μη έγκυρη έκδοση: {value}")
    return tuple(int(part or 0) for part in match.groups())


def installed_version():
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    try:
        data = json.loads((base / "build_version.json").read_text(encoding="utf-8-sig"))
        version_tuple(data["version"])
        return str(data["version"])
    except (OSError, ValueError, KeyError, TypeError):
        return "0.0.0"
