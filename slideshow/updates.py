"""GitHub release checks, verified downloads and staged Windows updates."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .version import APP_EXE, LAUNCHER, REPOSITORY, version_tuple

MANIFEST_NAME = "update-manifest.json"
PACKAGE_INDEX = "update-package.json"
SOURCE_ROOT_FILES = {
    LAUNCHER, "build_version.json", "requirements.txt", "run.bat", "install.bat",
    "install.ps1", "LICENSE", "README.md",
}


class UpdateCancelled(Exception):
    pass


def _request(url):
    return urllib.request.Request(url, headers={
        "User-Agent": "SlideshowVideoCreator-Updater",
        "Accept": "application/vnd.github+json" if "api.github.com/" in url else "application/json",
    })


def _get_json(url):
    try:
        with urllib.request.urlopen(_request(url), timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError("Η απάντηση ενημέρωσης είναι πολύ μεγάλη.")
        return json.loads(data.decode("utf-8-sig"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise RuntimeError("Δεν υπάρχει διαθέσιμο release στο GitHub.") from error
        if error.code in (403, 429):
            raise RuntimeError("Το GitHub περιόρισε προσωρινά τους ελέγχους. Δοκίμασε αργότερα.") from error
        raise RuntimeError(f"Αποτυχία ελέγχου ενημέρωσης (HTTP {error.code}).") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Δεν ήταν δυνατή η σύνδεση στο GitHub: {error.reason}") from error


def _asset_url(value):
    url = str(value or "")
    parsed = urllib.parse.urlparse(url)
    prefix = f"/{REPOSITORY}/releases/download/"
    if parsed.scheme != "https" or parsed.netloc != "github.com" or not parsed.path.startswith(prefix):
        raise ValueError("Μη έγκυρη διεύθυνση αρχείου ενημέρωσης.")
    return url


def latest_release():
    data = _get_json(f"https://api.github.com/repos/{REPOSITORY}/releases/latest")
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise ValueError("Το GitHub δεν επέστρεψε σταθερό release.")
    version = str(data.get("tag_name", "")).removeprefix("v")
    version_tuple(version)
    assets = {asset["name"]: asset for asset in data.get("assets", [])
              if isinstance(asset, dict) and asset.get("name")}
    return {"version": version, "notes": str(data.get("body") or ""),
            "url": data.get("html_url"), "assets": assets}


def update_package(release, kind):
    asset = release["assets"].get(MANIFEST_NAME)
    if not asset:
        raise ValueError("Αυτό το release δεν διαθέτει πακέτο αυτόματης ενημέρωσης.")
    manifest = _get_json(_asset_url(asset.get("browser_download_url")))
    if manifest.get("schema") != 1 or version_tuple(manifest.get("version")) != version_tuple(release["version"]):
        raise ValueError("Το αρχείο ενημέρωσης δεν αντιστοιχεί στην έκδοση release.")
    package = manifest.get("packages", {}).get(kind, {})
    target_asset = release["assets"].get(package.get("asset"))
    digest = str(package.get("sha256") or "").lower()
    if not target_asset or not re_full_hash(digest):
        raise ValueError("Δεν βρέθηκε συμβατό πακέτο ενημέρωσης για αυτή την εγκατάσταση.")
    size = int(package.get("size") or 0)
    if size <= 0 or size != int(target_asset.get("size") or 0):
        raise ValueError("Το μέγεθος του πακέτου ενημέρωσης δεν είναι έγκυρο.")
    return {"url": _asset_url(target_asset.get("browser_download_url")),
            "size": size, "sha256": digest, "version": release["version"], "kind": kind}


def re_full_hash(value):
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def allowed_path(name, kind):
    if not isinstance(name, str) or "\\" in name or ":" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in (".", "..") for part in path.parts):
        return False
    if path.as_posix() != name:
        return False
    if kind == "source":
        return name in SOURCE_ROOT_FILES or (
            path.parts[0] == "slideshow" and path.suffix in (".py", ".ps1"))
    if kind == "windows":
        return (name in (APP_EXE, "build_version.json") or
                (path.parts[0] == "_internal" and len(path.parts) > 1) or
                name in ("ffmpeg/ffmpeg.exe", "ffmpeg/ffprobe.exe", "ffmpeg/ffplay.exe"))
    return False


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_package(package, destination, progress=None, cancel=None):
    digest, done = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(_request(package["url"]), timeout=60) as response, open(destination, "wb") as stream:
            while True:
                if cancel is not None and cancel.is_set():
                    raise UpdateCancelled("Η λήψη ακυρώθηκε.")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > package["size"]:
                    raise ValueError("Το πακέτο υπερβαίνει το αναμενόμενο μέγεθος.")
                stream.write(chunk)
                digest.update(chunk)
                if progress:
                    progress(done, package["size"])
        if done != package["size"] or digest.hexdigest() != package["sha256"]:
            raise ValueError("Ο έλεγχος SHA-256 απέτυχε. Η ενημέρωση δεν εγκαταστάθηκε.")
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def extract_package(archive, stage, kind, version, cancel=None):
    """Only listed application files can leave the ZIP; user data is never a target."""
    stage = Path(stage)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("Το πακέτο περιέχει διπλά αρχεία.")
        index = json.loads(bundle.read(PACKAGE_INDEX).decode("utf-8-sig"))
        if (index.get("schema") != 1 or index.get("kind") != kind or
                version_tuple(index.get("version")) != version_tuple(version)):
            raise ValueError("Το πακέτο δεν αντιστοιχεί στην εγκατάσταση.")
        files = index.get("files")
        if not isinstance(files, dict) or not files:
            raise ValueError("Κενή λίστα αρχείων ενημέρωσης.")
        expected_entry = APP_EXE if kind == "windows" else LAUNCHER
        if expected_entry not in files or "build_version.json" not in files:
            raise ValueError("Λείπει ο εκκινητής ή η έκδοση από την ενημέρωση.")
        if set(names) != set(files) | {PACKAGE_INDEX}:
            raise ValueError("Το ZIP περιέχει αρχεία εκτός της λίστας ενημέρωσης.")
        for name, checksum in files.items():
            if cancel is not None and cancel.is_set():
                raise UpdateCancelled("Η προετοιμασία ακυρώθηκε.")
            info = bundle.getinfo(name)
            if (not allowed_path(name, kind) or not re_full_hash(checksum) or
                    (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError(f"Μη επιτρεπτό αρχείο ενημέρωσης: {name}")
            target = stage.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output)
            if sha256_file(target) != checksum:
                raise ValueError(f"Αποτυχία ελέγχου αρχείου: {name}")
    return files


def prepare_update(package, progress=None, cancel=None):
    base = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "SlideshowVideoCreator" / "updates"
    work = base / uuid.uuid4().hex
    work.mkdir(parents=True)
    try:
        archive = work / "download.zip"
        download_package(package, archive, progress, cancel)
        stage = work / "stage"
        files = extract_package(archive, stage, package["kind"], package["version"], cancel)
        archive.unlink()
        return {"work": work, "stage": stage, "files": files,
                "version": package["version"], "kind": package["kind"]}
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


def launch_installer(prepared, app_dir):
    app_dir = Path(app_dir).resolve()
    work = prepared["work"]
    installer = work / "install-update.ps1"
    shutil.copy2(Path(__file__).with_name("update_install.ps1"), installer)
    frozen = prepared["kind"] == "windows"
    executable = Path(sys.executable).resolve()
    if frozen and executable.parent != app_dir:
        raise ValueError("Το εκτελέσιμο δεν βρίσκεται στον φάκελο εγκατάστασης.")
    # Keep the installed EXE name so shortcuts still work after every update.
    files = [{"source": name,
              "target": executable.name if frozen and name == APP_EXE else name,
              "sha256": checksum} for name, checksum in prepared["files"].items()]
    restart_exe = executable
    if not frozen and executable.with_name("pythonw.exe").exists():
        restart_exe = executable.with_name("pythonw.exe")
    config = {"pid": os.getpid(), "app_dir": str(app_dir),
              "stage": str(prepared["stage"]), "work": str(work), "files": files,
              "version": prepared["version"], "kind": prepared["kind"],
              "restart_exe": str(restart_exe),
              "restart_args": [] if frozen else [str(app_dir / LAUNCHER)],
              "python_exe": str(executable), "install_dependencies": False}
    req = prepared["stage"] / "requirements.txt"
    installed_req = app_dir / "requirements.txt"
    if not frozen and req.exists():
        config["install_dependencies"] = (not installed_req.exists() or
                                          sha256_file(req) != sha256_file(installed_req))
    config_path = work / "install.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", str(installer), "-ConfigPath", str(config_path)],
                     cwd=work, close_fds=True, creationflags=flags)
    return work
