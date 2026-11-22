"""Exercise a real portable EXE update in an isolated disposable installation."""

import argparse
import ctypes
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slideshow.updates import extract_package, sha256_file
from slideshow.version import APP_EXE, installed_version


def wait_for_exit(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, 30000) != 0:
                raise RuntimeError("Smoke-test process did not exit.")
        finally:
            kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--temp-parent", type=Path, required=True)
    args = parser.parse_args()
    version = installed_version()
    with tempfile.TemporaryDirectory(prefix="portable updater ", dir=args.temp_parent) as folder:
        root = Path(folder)
        app, work, data = root / "installed", root / "work", root / "user profile"
        stage = work / "stage"
        data.mkdir()
        files = extract_package(args.bundle, app, "windows", version)
        extract_package(args.bundle, stage, "windows", version)
        secret = b'{"ai_api_key":"preserve-test-key"}'
        (app / "settings.json").write_bytes(secret)
        (app / "projects").mkdir()
        (app / "projects/user.json").write_bytes(b"preserve-project")
        helper = work / "update-install.ps1"
        shutil.copy2(app / "_internal/slideshow/update_install.ps1", helper)
        old = subprocess.Popen([str(app / APP_EXE), "--smoke-test-dir", str(data)])
        config = {"pid": old.pid, "app_dir": str(app), "stage": str(stage), "work": str(work),
                  "kind": "windows", "version": version, "quiet": True,
                  "restart_exe": str(app / APP_EXE), "restart_args": ["--smoke-test-dir", str(data)],
                  "install_dependencies": False, "files": [
                      {"source": name, "target": name, "sha256": checksum}
                      for name, checksum in files.items()]}
        config_file = work / "config.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(helper), "-ConfigPath", str(config_file)],
                                capture_output=True, timeout=180)
        report = json.loads((work / "result.json").read_text(encoding="utf-8-sig"))
        if result.returncode or report["status"] != "success":
            raise RuntimeError(report)
        wait_for_exit(report["restart_pid"])
        old.wait(timeout=10)
        assert (app / "settings.json").read_bytes() == secret
        assert (app / "projects/user.json").read_bytes() == b"preserve-project"
        assert json.loads((work / "startup-ready.json").read_text())["version"] == version
        assert sha256_file(app / APP_EXE) == files[APP_EXE]
        print(f"Portable EXE update/restart verified: {version}; profiles/projects preserved.")


if __name__ == "__main__":
    main()
