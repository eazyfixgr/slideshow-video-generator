"""Updater contracts, protected data, integrity checks and Windows rollback."""

import hashlib
import ctypes
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from slideshow import updates
from slideshow.version import APP_EXE, LAUNCHER, installed_version, version_tuple


def make_archive(path, files, kind="source", version="4.5.0"):
    contents = {LAUNCHER: b"print('app')", "build_version.json": json.dumps(
        {"version": version}).encode(), **files}
    index = {"schema": 1, "kind": kind, "version": version, "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        archive.writestr(updates.PACKAGE_INDEX, json.dumps(index))


class UpdateTests(unittest.TestCase):
    def test_versions_are_numeric_and_old_two_part_versions_compare_equal(self):
        self.assertEqual(version_tuple("4.4"), version_tuple("v4.4.0"))
        self.assertGreater(version_tuple("4.10.0"), version_tuple("4.9.0"))
        self.assertLess(version_tuple("4.5.0"), version_tuple("5.0.0"))
        with self.assertRaises(ValueError):
            version_tuple("latest")
        self.assertNotEqual(installed_version(), "0.0.0")

    def test_update_manifest_selects_correct_asset_and_checks_version(self):
        url = f"https://github.com/{updates.REPOSITORY}/releases/download/v4.5.0/"
        release = {"version": "4.5.0", "assets": {
            updates.MANIFEST_NAME: {"browser_download_url": url + updates.MANIFEST_NAME},
            "source.zip": {"browser_download_url": url + "source.zip", "size": 200},
            "windows.zip": {"browser_download_url": url + "windows.zip", "size": 300},
        }}
        manifest = {"schema": 1, "version": "4.5.0", "packages": {
            "source": {"asset": "source.zip", "size": 200, "sha256": "a" * 64},
            "windows": {"asset": "windows.zip", "size": 300, "sha256": "b" * 64},
        }}
        with patch.object(updates, "_get_json", return_value=manifest):
            self.assertEqual(updates.update_package(release, "source")["size"], 200)
            self.assertEqual(updates.update_package(release, "windows")["sha256"], "b" * 64)
            manifest["version"] = "4.4.0"
            with self.assertRaises(ValueError):
                updates.update_package(release, "source")

    def test_only_same_repository_https_downloads_are_accepted(self):
        for url in ("http://github.com/file", "https://example.com/app.zip",
                    "https://github.com/another/repo/releases/download/v1/app.zip"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                updates._asset_url(url)

    def test_download_checksum_failure_removes_partial_file(self):
        data = b"a release package"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "download.zip"
            package = {"url": "https://example.invalid/app", "size": len(data),
                       "sha256": "0" * 64}
            with patch.object(updates.urllib.request, "urlopen", return_value=io.BytesIO(data)):
                with self.assertRaises(ValueError):
                    updates.download_package(package, target)
            self.assertFalse(target.exists())

    def test_cancelled_download_does_not_install_anything(self):
        with tempfile.TemporaryDirectory() as folder:
            cancel = threading.Event()
            cancel.set()
            target = Path(folder) / "download.zip"
            with patch.object(updates.urllib.request, "urlopen", return_value=io.BytesIO(b"abc")):
                with self.assertRaises(updates.UpdateCancelled):
                    updates.download_package({"url": "https://example.invalid/app", "size": 3,
                                              "sha256": "a" * 64}, target, cancel=cancel)
            self.assertFalse(target.exists())

    def test_source_extraction_accepts_only_application_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "source.zip"
            make_archive(archive, {"slideshow/ui_updates.py": b"# updater"})
            files = updates.extract_package(archive, root / "stage", "source", "4.5.0")
            self.assertIn("slideshow/ui_updates.py", files)
            self.assertFalse((root / "stage/settings.json").exists())

    def test_user_data_and_zip_traversal_are_rejected(self):
        for bad in ("settings.json", "profiles.json", "projects/test.json", "music/song.mp4",
                    "models/model.onnx", "../outside.py", "slideshow/../../bad.py"):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                archive = root / "source.zip"
                make_archive(archive, {bad: b"not application code"})
                with self.assertRaises(ValueError):
                    updates.extract_package(archive, root / "stage", "source", "4.5.0")
                self.assertFalse((root / "outside.py").exists())

    def test_windows_package_is_not_accepted_as_python_update(self):
        self.assertTrue(updates.allowed_path(APP_EXE, "windows"))
        self.assertTrue(updates.allowed_path("_internal/python314.dll", "windows"))
        self.assertFalse(updates.allowed_path(APP_EXE, "source"))
        self.assertFalse(updates.allowed_path("settings.json", "windows"))

    def test_staged_files_must_match_individual_checksums(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "source.zip"
            make_archive(archive, {})
            with zipfile.ZipFile(archive) as bundle:
                index = json.loads(bundle.read(updates.PACKAGE_INDEX))
                index["files"][LAUNCHER] = "0" * 64
                other = {name: bundle.read(name) for name in bundle.namelist()
                         if name != updates.PACKAGE_INDEX}
            with zipfile.ZipFile(archive, "w") as bundle:
                for name, data in other.items():
                    bundle.writestr(name, data)
                bundle.writestr(updates.PACKAGE_INDEX, json.dumps(index))
            with self.assertRaises(ValueError):
                updates.extract_package(archive, root / "stage", "source", "4.5.0")


@unittest.skipUnless(os.name == "nt", "Windows update helper")
class WindowsInstallerTests(unittest.TestCase):
    def run_installer(self, fail_startup=False):
        with tempfile.TemporaryDirectory(prefix="slideshow update test ") as folder:
            root = Path(folder)
            app, work = root / "installed app", root / "update work"
            stage = work / "stage"
            app.mkdir()
            stage.mkdir(parents=True)
            old_script = "# old application\n"
            (app / LAUNCHER).write_text(old_script, encoding="utf-8")
            (app / "build_version.json").write_text('{"version":"4.4.0"}', encoding="utf-8")
            secrets = b'{"ai_api_key":"do not touch"}'
            (app / "settings.json").write_bytes(secrets)
            (app / "projects").mkdir()
            (app / "projects/user.json").write_bytes(b"user project")
            if fail_startup:
                new_script = "raise SystemExit(1)\n"
            else:
                new_script = ("import sys,json\nfrom pathlib import Path\n"
                              "if '--update-ready' in sys.argv:\n"
                              " Path(sys.argv[-1]).write_text(json.dumps({'version':'4.5.0'}))\n")
            (stage / LAUNCHER).write_text(new_script, encoding="utf-8")
            (stage / "build_version.json").write_text('{"version":"4.5.0"}', encoding="utf-8")
            config = {"pid": 0, "kind": "source", "version": "4.5.0", "quiet": True,
                      "app_dir": str(app), "work": str(work), "stage": str(stage),
                      "restart_exe": sys.executable, "restart_args": [str(app / LAUNCHER)],
                      "install_dependencies": False, "files": [
                          {"source": name, "target": name,
                           "sha256": updates.sha256_file(stage / name)}
                          for name in (LAUNCHER, "build_version.json")]}
            config_path = work / "install.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            installer = Path(updates.__file__).with_name("update_install.ps1")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(installer), "-ConfigPath", str(config_path)],
                                    capture_output=True, timeout=60)
            report = json.loads((work / "result.json").read_text(encoding="utf-8-sig"))
            # The helper deliberately restarts asynchronously. Wait for the
            # tiny test launcher to exit before TemporaryDirectory removes its CWD.
            pid = report.get("restart_pid", 0)
            if pid:
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = ctypes.c_void_p
                kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
                kernel.CloseHandle.argtypes = [ctypes.c_void_p]
                handle = kernel.OpenProcess(0x00100000, False, pid)
                if handle:
                    kernel.WaitForSingleObject(handle, 10000)
                    kernel.CloseHandle(handle)
            self.assertEqual(result.returncode, 1 if fail_startup else 0,
                             result.stderr.decode(errors="replace"))
            self.assertEqual(report["status"], "failed" if fail_startup else "success")
            self.assertEqual((app / "settings.json").read_bytes(), secrets)
            self.assertEqual((app / "projects/user.json").read_bytes(), b"user project")
            self.assertEqual(json.loads((app / "build_version.json").read_text())["version"],
                             "4.4.0" if fail_startup else "4.5.0")
            if fail_startup:
                self.assertEqual((app / LAUNCHER).read_text(), old_script)

    def test_installs_and_restarts_without_modifying_user_data(self):
        self.run_installer()

    def test_startup_failure_rolls_back_application_and_preserves_data(self):
        self.run_installer(fail_startup=True)


if __name__ == "__main__":
    unittest.main()
