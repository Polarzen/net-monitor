"""Build a committed Windows x64 test or public pre-release package."""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ["src", "packaging", "pyproject.toml", "tools/build_windows.py", "tools/build_windows.ps1"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-c", "core.quotepath=false", "-C", str(ROOT), *args], text=True, encoding="utf-8").strip()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_version() -> str:
    tree = ast.parse((ROOT / "src/net_monitor/__init__.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))


def package_name(version: str, commit: str, channel: str) -> str:
    suffixes = {"internal-test": "test", "public-prerelease": "prerelease"}
    if channel not in suffixes:
        raise ValueError(f"Unsupported release channel: {channel}")
    return f"NetMonitor-{version}-windows-x64-{commit[:12]}-{suffixes[channel]}"


def check_environment() -> dict[str, str]:
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build requires native Windows x64 Python")
    if platform.python_version() != "3.14.7":
        raise RuntimeError("Use the tested CPython 3.14.7 x64 build environment")
    versions = {}
    for line in (ROOT / "packaging/requirements-windows-x64.lock").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==([^ ]+) --hash=sha256:([0-9a-f]{64})", line)
        if not match:
            raise RuntimeError(f"Unpinned dependency: {line}")
        name, expected, _ = match.groups()
        actual = metadata.version(name)
        if actual != expected:
            raise RuntimeError(f"{name}: installed {actual}, required {expected}")
        versions[name] = actual
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True)
    return versions


def build_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "QT_QPA_PLATFORM", "QT_SCALE_FACTOR", "QT_SCREEN_SCALE_FACTORS", "QT_QPA_FONTDIR", "QT_PLUGIN_PATH", "NET_MONITOR_LAYOUT_FONT"):
        env.pop(key, None)
    # DLL analysis must not discover unrelated SDK/host DLLs via inherited PATH.
    # In particular, non-system ICU DLLs can have the same name but incompatible
    # symbols. Qt hooks discover their own wheel directories independently.
    windows = Path(env.get("SystemRoot") or env["SYSTEMROOT"])
    env["PATH"] = os.pathsep.join(str(p) for p in (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        windows / "System32", windows,
    ))
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def inspect_application_icon(pe, folder: Path) -> dict:
    source = ROOT / "src/net_monitor/assets/net-monitor.ico"
    bundled = folder / "_internal/net_monitor/assets/net-monitor.ico"
    content = source.read_bytes()
    if not bundled.is_file() or bundled.read_bytes() != content:
        raise RuntimeError("Bundled application icon is missing or differs from source")
    reserved, kind, count = struct.unpack_from("<HHH", content)
    if (reserved, kind) != (0, 1) or not count:
        raise RuntimeError("Invalid application ICO")
    frames, sizes = [], []
    for index in range(count):
        width, height, _, _, _, _, length, offset = struct.unpack_from(
            "<BBBBHHII", content, 6 + 16 * index)
        frames.append(content[offset:offset + length])
        sizes.append([width or 256, height or 256])
    resources = {}
    for resource_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        for name in resource_type.directory.entries:
            for language in name.directory.entries:
                data = language.data.struct
                resources.setdefault(resource_type.id, []).append(
                    (name.id, pe.get_data(data.OffsetToData, data.Size)))
    groups = resources.get(14, [])  # RT_GROUP_ICON links the actual RT_ICON frames.
    images = dict(resources.get(3, []))
    if len(groups) != 1 or struct.unpack_from("<HHH", groups[0][1]) != (0, 1, count):
        raise RuntimeError("EXE icon group differs from source ICO")
    group = groups[0][1]
    for index, frame in enumerate(frames):
        entry = group[6 + 14 * index:6 + 14 * (index + 1)]
        image_id = struct.unpack_from("<H", entry, 12)[0]
        if entry[:12] != content[6 + 16 * index:18 + 16 * index] or images.get(image_id) != frame:
            raise RuntimeError("EXE embedded icon frame differs from source ICO")
    return {"sizes": sizes, "sha256": sha256(source), "embedded_frames_match": True,
            "bundled_file": bundled.relative_to(folder).as_posix()}


def inspect_distribution(folder: Path, version: str) -> dict:
    import pefile
    exe = folder / "NetMonitor.exe"
    with pefile.PE(str(exe)) as pe:
        architecture, subsystem = pe.FILE_HEADER.Machine, pe.OPTIONAL_HEADER.Subsystem
        manifests = []
        for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if kind.id == 24:
                for name in kind.directory.entries:
                    for language in name.directory.entries:
                        data = language.data.struct
                        manifests.append(pe.get_data(data.OffsetToData, data.Size).decode("utf-8"))
        strings = {}
        for group in pe.FileInfo:
            for info in group:
                for table in getattr(info, "StringTable", []):
                    strings.update({k.decode(): v.decode() for k, v in table.entries.items()})
        numeric_version = [pe.VS_FIXEDFILEINFO[0].FileVersionMS >> 16,
                           pe.VS_FIXEDFILEINFO[0].FileVersionMS & 65535,
                           pe.VS_FIXEDFILEINFO[0].FileVersionLS >> 16,
                           pe.VS_FIXEDFILEINFO[0].FileVersionLS & 65535]
        application_icon = inspect_application_icon(pe, folder)
    if architecture != 0x8664 or subsystem != 2:
        raise RuntimeError("EXE is not Windows x64 GUI subsystem")
    if len(manifests) != 1 or 'level="asInvoker"' not in manifests[0] or 'uiAccess="false"' not in manifests[0]:
        raise RuntimeError("EXE manifest must use asInvoker with no UI access")
    if strings.get("ProductVersion") != version or strings.get("FileVersion") != version:
        raise RuntimeError("PE version disagrees with source")
    release, development = version.split(".dev")
    if numeric_version != [*(int(part) for part in release.split(".")), int(development)]:
        raise RuntimeError("PE numeric version disagrees with source")
    required = ["_internal/python314.dll", "_internal/PySide6/plugins/platforms/qwindows.dll",
                "_internal/PySide6/Qt6Core.dll", "_internal/PySide6/Qt6Gui.dll",
                "_internal/PySide6/Qt6Widgets.dll", "_internal/PySide6/__init__.py",
                "_internal/shiboken6/__init__.py", "_internal/PySide6/plugins/imageformats/qico.dll"]
    missing = [name for name in required if not (folder / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing runtime files: {missing}")
    forbidden = []
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    for name in files:
        parts = {p.lower() for p in Path(name).parts}
        if parts & {".git", ".vs", ".venv", ".venv-build-stage5", "tests", "pytest", "_pytest", "tools"} or Path(name).name.lower() in {"goal.md", "ui.json"} or name.lower().endswith((".pdb", ".ttf", ".otf")):
            forbidden.append(name)
    if forbidden:
        raise RuntimeError(f"Forbidden distribution content: {forbidden}")
    unused_plugins = [n for n in files if Path(n).name.lower() in {"qpdf.dll", "qtvirtualkeyboardplugin.dll", "qt6pdf.dll", "qt6virtualkeyboard.dll"}]
    if unused_plugins:
        raise RuntimeError(f"Unused PDF/virtual-keyboard dependencies collected: {unused_plugins}")
    return {"machine": hex(architecture), "subsystem": subsystem, "manifest": manifests[0],
            "application_icon": application_icon,
            "version_strings": strings, "numeric_version": numeric_version,
            "required_runtime_files": required, "forbidden_files": forbidden,
            "dlls_and_extensions": [p for p in files if p.lower().endswith((".dll", ".pyd"))]}


def collect_licenses(folder: Path, versions: dict) -> None:
    license_root = folder / "licenses"
    shutil.copytree(ROOT / "packaging/licenses", license_root)
    records = []
    for name in ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "psutil", "pyinstaller"):
        dist = metadata.distribution(name)
        dest = license_root / name
        dest.mkdir()
        copied = []
        for file in dist.files or []:
            if ".dist-info/" in file.as_posix() and any(s in file.name.lower() for s in ("license", "copying", "notice")):
                source = Path(dist.locate_file(file))
                target = dest / file.name
                shutil.copyfile(source, target)
                copied.append(target.relative_to(folder).as_posix())
        if not copied:
            raise RuntimeError(f"No installed license text found for {name}")
        records.append({"component": name, "version": versions[name],
                        "metadata_license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                        "license_files": copied})
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        python_license = ROOT / "packaging/licenses/Python-LICENSE.txt"
    shutil.copyfile(python_license, license_root / "Python-LICENSE.txt")
    records.append({"component": "CPython", "version": platform.python_version(),
                    "license_files": ["licenses/Python-LICENSE.txt"]})
    write_json(license_root / "installed-components.json", records)


def render_notice(name: str, folder: Path, version: str, commit: str, channel: str) -> None:
    text = (ROOT / "packaging" / name).read_text(encoding="utf-8")
    for token, value in {"@VERSION@": version, "@SOURCE_COMMIT@": commit,
                         "@CHANNEL@": channel}.items():
        text = text.replace(token, value)
    (folder / name).write_text(text, encoding="utf-8")


def build(output_root: Path, *, channel: str = "internal-test") -> dict:
    package_name(source_version(), "", channel)  # Reject invalid metadata before mutation.
    versions = check_environment()
    changes = git("status", "--porcelain", "--untracked-files=all", "--", *INPUTS)
    if changes:
        raise RuntimeError("Commit reviewed build inputs first; unrelated staged work is allowed:\n" + changes)
    commit = git("rev-parse", "HEAD")
    version = source_version()
    name = package_name(version, commit, channel)
    output_root = output_root.resolve()
    destination = output_root / name
    # New directory per commit: never delete or replace a pre-existing user output.
    destination.mkdir(parents=True, exist_ok=False)
    work = ROOT / "build/stage5" / (commit[:12] + "-" + uuid.uuid4().hex[:8])
    work.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--workpath", str(work / "pyinstaller"), "--distpath", str(work / "dist"),
               str(ROOT / "packaging/NetMonitor.spec")]
    env = build_environment()
    env["NET_MONITOR_BINARY_ORIGINS"] = str(work / "binary-origins.json")
    log = destination / "build.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"PyInstaller failed ({result.returncode}); see {log}")
    folder = destination / "NetMonitor"
    shutil.copytree(work / "dist/NetMonitor", folder)
    inspection = inspect_distribution(folder, version)
    collect_licenses(folder, versions)
    shutil.copyfile(work / "binary-origins.json", folder / "licenses/binary-origins.json")
    for notice in ("使用说明.txt", "THIRD-PARTY-NOTICES.txt"):
        render_notice(notice, folder, version, commit, channel)
    source_files = git("ls-files", "--", *INPUTS).splitlines()
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=all", "--", *INPUTS):
        raise RuntimeError("Build inputs changed during compilation; no ZIP produced")
    build_info = {
        "schema_version": 1, "product": "Net Monitor", "version": version,
        "status": channel, "source_commit": commit, "source_inputs_dirty": False,
        "source_sha256": {p: sha256(ROOT / p) for p in source_files},
        "configuration": {p: sha256(ROOT / p) for p in ("packaging/NetMonitor.spec", "packaging/requirements-windows-x64.lock")},
        "python": platform.python_version(), "dependencies": versions,
        "build_platform": platform.platform(), "architecture": "x64",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "mode": "onedir/windowed", "signed": False,
        "file_inventory": "FILE-MANIFEST.json",
        "license_review": "see THIRD-PARTY-NOTICES.txt and licenses/REDISTRIBUTION.txt; release acceptance is recorded separately",
        "corresponding_sources": "licenses/release-sources.json",
        "binary_origins": "licenses/binary-origins.json",
        "clean_machine_test": "not performed by build; see acceptance record",
    }
    write_json(folder / "BUILD-INFO.json", build_info)
    write_json(destination / "static-inspection.json", inspection)
    inventory = {p.relative_to(folder).as_posix(): {"bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in sorted(folder.rglob("*")) if p.is_file()}
    # The manifest deliberately excludes itself; the external ZIP hash covers it.
    write_json(folder / "FILE-MANIFEST.json", inventory)
    inspect_distribution(folder, version)
    archive = destination / (name + ".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                zip_file.write(file, "NetMonitor/" + file.relative_to(folder).as_posix())
    checksum = sha256(archive)
    (destination / "SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    report = {"source_commit": commit, "version": version, "zip": str(archive),
              "zip_bytes": archive.stat().st_size, "zip_sha256": checksum,
              "directory_bytes": sum(p.stat().st_size for p in folder.rglob("*") if p.is_file()),
              "file_count": len(inventory) + 1, "build_log": str(log),
              "static_inspection": str(destination / "static-inspection.json")}
    write_json(destination / "build-result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/stage5")
    parser.add_argument("--channel", choices=("internal-test", "public-prerelease"),
                        default="internal-test")
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output_root, channel=args.channel), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
