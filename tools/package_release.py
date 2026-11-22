"""Build clean release ZIPs and the updater manifest (never include user data)."""

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slideshow.updates import PACKAGE_INDEX, SOURCE_ROOT_FILES, allowed_path, sha256_file
from slideshow.version import version_tuple


def create_package(root, paths, output, version, kind):
    paths = sorted(paths, key=lambda path: path.relative_to(root).as_posix())
    files = {path.relative_to(root).as_posix(): sha256_file(path) for path in paths}
    if any(not allowed_path(name, kind) for name in files):
        raise ValueError("Release includes a non-application file.")
    index = {"schema": 1, "version": version, "kind": kind, "files": files}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in paths:
            archive.write(path, path.relative_to(root).as_posix())
        archive.writestr(PACKAGE_INDEX, json.dumps(index, ensure_ascii=False, indent=2))
    return {"asset": output.name, "size": output.stat().st_size,
            "sha256": sha256_file(output)}


def write_version_resource(path, version):
    numeric = version_tuple(version)
    text = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Slideshow Video Creator'),
    StringStruct('FileDescription', 'Slideshow Video Creator Pro'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductName', 'Slideshow Video Creator Pro'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('OriginalFilename', 'SlideshowVideoCreator.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--version-resource", type=Path)
    args = parser.parse_args()
    version = json.loads((ROOT / "build_version.json").read_text(encoding="utf-8-sig"))["version"]
    version_tuple(version)
    if args.version_resource:
        write_version_resource(args.version_resource, version)
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_paths = [ROOT / name for name in SOURCE_ROOT_FILES if (ROOT / name).is_file()]
    source_paths += [path for path in (ROOT / "slideshow").rglob("*")
                     if path.is_file() and path.suffix in (".py", ".ps1")]
    source = args.output_dir / f"SlideshowVideoCreator_v{version}_source.zip"
    packages = {"source": create_package(ROOT, source_paths, source, version, "source")}
    if args.windows_dir:
        binary_paths = [path for path in args.windows_dir.rglob("*")
                        if path.is_file() and allowed_path(
                            path.relative_to(args.windows_dir).as_posix(), "windows")]
        windows = args.output_dir / f"SlideshowVideoCreator_v{version}_windows.zip"
        packages["windows"] = create_package(args.windows_dir, binary_paths, windows,
                                               version, "windows")
    manifest = {"schema": 1, "version": version, "packages": packages}
    (args.output_dir / "update-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    for package in packages.values():
        print(f"{package['asset']}: {package['size'] / 1048576:.1f} MB, SHA256 {package['sha256']}")


if __name__ == "__main__":
    main()
