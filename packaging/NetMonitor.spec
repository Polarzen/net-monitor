# Windows x64 only. Official PyInstaller Qt hooks select the used Qt modules.
import ast
import hashlib
import json
import os
import sys
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct,
)

root = Path(SPECPATH).parent
app_icon = root / "src/net_monitor/assets/net-monitor.ico"
tree = ast.parse((root / "src/net_monitor/__init__.py").read_text(encoding="utf-8"))
version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
major, minor, patch = (int(n) for n in version.split(".dev")[0].split("."))
number = (major, minor, patch, int(version.split(".dev")[1]))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=number, prodvers=number, mask=0x3f, flags=0x2,
                     OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("FileDescription", "Net Monitor (pre-release)"),
        StringStruct("FileVersion", version),
        StringStruct("ProductName", "Net Monitor"),
        StringStruct("ProductVersion", version),
        StringStruct("OriginalFilename", "NetMonitor.exe"),
    ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
)
a = Analysis([str(root / "packaging/entry.py")], pathex=[str(root / "src")],
             binaries=[], datas=[(str(app_icon), "net_monitor/assets")],
             hiddenimports=[], hookspath=[str(root / "packaging/hooks")],
             hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
             # Keep LGPL Python wrappers replaceable alongside their DLLs.
             module_collection_mode={"PySide6": "py", "shiboken6": "py"})
# Fail closed if dependency discovery escaped the pinned environment and Windows.
allowed_binary_roots = [Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve(),
                        Path(os.environ["SystemRoot"]).resolve()]
for destination, source, kind in a.binaries:
    if not any(Path(source).resolve().is_relative_to(p) for p in allowed_binary_roots):
        raise RuntimeError(f"Unexpected binary source for {destination}: {source}")
# Preserve the actual build-time binary origins without publishing machine paths.
origins = []
for destination, source, kind in a.binaries:
    source = Path(source).resolve()
    for label, directory in zip(("build-environment", "CPython", "Windows"), allowed_binary_roots):
        if source.is_relative_to(directory):
            origins.append({"file": "_internal/" + destination.replace("\\", "/"),
                            "origin": label, "source_path": source.relative_to(directory).as_posix(),
                            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
            break
Path(os.environ["NET_MONITOR_BINARY_ORIGINS"]).write_text(
    json.dumps(origins, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="NetMonitor",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False, version=version_info, icon=str(app_icon),
          uac_admin=False, uac_uiaccess=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="NetMonitor")
