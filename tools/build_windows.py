"""Build a committed Windows x64 internal-test package; never imported by the app."""
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
    windows = Path(env["SystemRoot"])
    env["PATH"] = os.pathsep.join(str(p) for p in (
        Path(sys.executable).parent, Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs",
        windows / "System32", windows,
    ))
    env["PYTHONIOENCODING"] = "utf-8"
    return env


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
    if architecture != 0x8664 or subsystem != 2:
        raise RuntimeError("EXE is not Windows x64 GUI subsystem")
    if len(manifests) != 1 or 'level="asInvoker"' not in manifests[0] or 'uiAccess="false"' not in manifests[0]:
        raise RuntimeError("EXE manifest must use asInvoker with no UI access")
    if strings.get("ProductVersion") != version or strings.get("FileVersion") != version:
        raise RuntimeError("PE version disagrees with source")
    required = ["_internal/python314.dll", "_internal/PySide6/plugins/platforms/qwindows.dll",
                "_internal/PySide6/Qt6Core.dll", "_internal/PySide6/Qt6Gui.dll",
                "_internal/PySide6/Qt6Widgets.dll"]
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
    return {"machine": hex(architecture), "subsystem": subsystem, "manifest": manifests[0],
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
    shutil.copyfile(ROOT / "packaging/THIRD-PARTY-NOTICES.txt", folder / "THIRD-PARTY-NOTICES.txt")


def build(output_root: Path) -> dict:
    versions = check_environment()
    changes = git("status", "--porcelain", "--untracked-files=all", "--", *INPUTS)
    if changes:
        raise RuntimeError("Commit reviewed build inputs first; unrelated staged work is allowed:\n" + changes)
    commit = git("rev-parse", "HEAD")
    version = source_version()
    name = f"NetMonitor-{version}-windows-x64-{commit[:12]}-test"
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
    log = destination / "build.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"PyInstaller failed ({result.returncode}); see {log}")
    folder = destination / "NetMonitor"
    shutil.copytree(work / "dist/NetMonitor", folder)
    inspection = inspect_distribution(folder, version)
    collect_licenses(folder, versions)
    shutil.copyfile(ROOT / "packaging/使用说明.txt", folder / "使用说明.txt")
    source_files = git("ls-files", "--", *INPUTS).splitlines()
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=all", "--", *INPUTS):
        raise RuntimeError("Build inputs changed during compilation; no ZIP produced")
    build_info = {
        "schema_version": 1, "product": "Net Monitor", "version": version,
        "status": "internal-test", "source_commit": commit, "source_inputs_dirty": False,
        "source_sha256": {p: sha256(ROOT / p) for p in source_files},
        "configuration": {p: sha256(ROOT / p) for p in ("packaging/NetMonitor.spec", "packaging/requirements-windows-x64.lock")},
        "python": platform.python_version(), "dependencies": versions,
        "build_platform": platform.platform(), "architecture": "x64",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "mode": "onedir/windowed", "signed": False,
        "file_inventory": "FILE-MANIFEST.json",
        "license_review": "component notices included; public redistribution review incomplete",
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
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.output_root), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
