from pathlib import Path
from types import SimpleNamespace
import ast
import os
import sys
import tomllib

import pytest

from net_monitor import __version__
from net_monitor.core import elevation
from net_monitor.ui.preferences import PreferencesStore, UiPreferences


class ShellCall:
    def __init__(self, result=42, error=None):
        self.result, self.error = result, error
        self.calls = []

    def __call__(self, *args):
        self.calls.append((args, os.environ.get("PYINSTALLER_RESET_ENVIRONMENT")))
        if self.error:
            raise self.error
        return self.result


def shell(monkeypatch, result=42, error=None):
    call = ShellCall(result, error)
    monkeypatch.setattr(elevation.ctypes, "windll", SimpleNamespace(
        shell32=SimpleNamespace(ShellExecuteW=call)), raising=False)
    return call


@pytest.mark.skipif(os.name != "nt", reason="Windows ShellExecute contract")
def test_source_restart_uses_venv_pythonw_and_only_module(monkeypatch, tmp_path):
    folder = tmp_path / "中文 空格" / "Scripts"
    folder.mkdir(parents=True)
    exe = folder / "python.exe"
    gui = folder / "pythonw.exe"
    gui.touch()
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "argv", ["ignored", "--external-input"])
    monkeypatch.chdir(tmp_path)
    call = shell(monkeypatch)
    assert elevation.restart_as_administrator()
    assert call.calls[0][0] == (None, "runas", str(gui), "-m net_monitor", str(tmp_path), 1)


@pytest.mark.skipif(os.name != "nt", reason="Windows ShellExecute contract")
@pytest.mark.parametrize("result", [None, 0, 5, 32, 33, 42])
@pytest.mark.parametrize("previous", [None, "original"])
def test_frozen_restart_is_absolute_independent_and_restores_environment(
        monkeypatch, tmp_path, result, previous):
    exe = tmp_path / "内部 测试" / "NetMonitor.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", [str(exe), "-m", "unsafe", "--test"])
    monkeypatch.chdir(tmp_path)
    if previous is None:
        monkeypatch.delenv("PYINSTALLER_RESET_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("PYINSTALLER_RESET_ENVIRONMENT", previous)
    call = shell(monkeypatch, result)
    assert elevation.restart_as_administrator() is bool(result and result > 32)
    assert call.calls == [((None, "runas", str(exe.resolve()), "", str(exe.parent), 1), "1")]
    assert os.environ.get("PYINSTALLER_RESET_ENVIRONMENT") == previous


@pytest.mark.skipif(os.name != "nt", reason="Windows ShellExecute contract")
def test_frozen_native_error_returns_failure_and_restores_environment(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("PYINSTALLER_RESET_ENVIRONMENT", raising=False)
    shell(monkeypatch, error=OSError("native launch failed"))
    assert not elevation.restart_as_administrator()
    assert "PYINSTALLER_RESET_ENVIRONMENT" not in os.environ


def test_entry_with_no_standard_streams(monkeypatch):
    from net_monitor import app
    calls = []
    application = SimpleNamespace(setApplicationName=lambda v: calls.append(v),
        setApplicationVersion=lambda v: calls.append(v), setStyleSheet=lambda v: None,
        setWindowIcon=lambda v: None,
        exec=lambda: 0)
    monkeypatch.setattr(app, "QApplication", SimpleNamespace(instance=lambda: application))
    monkeypatch.setattr(app, "UiController", lambda: SimpleNamespace(
        show_primary=lambda **kw: calls.append(kw)))
    with monkeypatch.context() as scoped:
        for name in ("stdin", "stdout", "stderr"):
            scoped.setattr(sys, name, None)
        assert app.main() == 0
    assert calls == ["Net Monitor", __version__, {"activate": False}]


def test_frozen_preferences_ignore_resource_directory_and_cwd(monkeypatch, tmp_path):
    dist = tmp_path / "只读 发行目录"
    dist.mkdir()
    local = tmp_path / "独立用户配置"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(dist / "_internal"), raising=False)
    monkeypatch.setattr(sys, "executable", str(dist / "NetMonitor.exe"))
    monkeypatch.chdir(dist)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    store = PreferencesStore()
    assert store.path == local / "NetMonitor/ui.json"
    assert store.load() == UiPreferences()
    assert store.save(UiPreferences(mode="compact"))
    assert store.load().mode == "compact"
    assert not list(dist.iterdir())
    store.path.write_text("{corrupt", encoding="utf-8")
    assert store.load() == UiPreferences()


def test_single_version_source_and_thin_entry():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project['project']['dynamic'] == ['version']
    assert project['tool']['setuptools']['dynamic']['version']['attr'] == 'net_monitor.__version__'
    assert __version__ == "0.2.1.dev5"
    tree = ast.parse((root / "packaging/entry.py").read_text(encoding="utf-8"))
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert imports == ["net_monitor.app"]


def test_build_search_path_excludes_host_sdks_without_changing_parent(monkeypatch, tmp_path):
    from tools.build_windows import build_environment
    monkeypatch.setenv("PATH", "unrelated-sdk-with-incompatible-icu")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setenv("QT_PLUGIN_PATH", "unrelated-qt")
    monkeypatch.setenv("PYTHONPATH", "unrelated-python")
    env = build_environment()
    assert "unrelated" not in env["PATH"]
    assert str(tmp_path / "Windows" / "System32") in env["PATH"]
    assert "QT_PLUGIN_PATH" not in env and "PYTHONPATH" not in env
    assert os.environ["PATH"] == "unrelated-sdk-with-incompatible-icu"


def test_qt_hook_keeps_required_plugins_and_official_dependency_results(monkeypatch):
    import runpy
    binaries = [(name, "plugins") for name in
                ("qwindows.dll", "qsvg.dll", "qico.dll", "qjpeg.dll", "qpdf.dll", "qtvirtualkeyboardplugin.dll")]
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks.qt", SimpleNamespace(
        add_qt6_dependencies=lambda filename: (["PySide6.QtCore"], binaries, [("data", ".")])))
    result = runpy.run_path(str(Path(__file__).resolve().parents[1] / "packaging/hooks/hook-PySide6.QtGui.py"))
    assert result['binaries'] == binaries[:4]
    assert result['hiddenimports'] == ['PySide6.QtCore']
    assert result['datas'] == [('data', '.')]


def test_release_channel_and_rendered_identity(tmp_path):
    from tools.build_windows import package_name, render_notice
    commit = "123456789abcdef0123456789abcdef0123456789a"
    for channel, suffix in (("internal-test", "test"), ("public-prerelease", "prerelease")):
        assert package_name("0.2.1.dev3", commit, channel).endswith(
            f"windows-x64-123456789abc-{suffix}")
        for name in ("使用说明.txt", "THIRD-PARTY-NOTICES.txt"):
            render_notice(name, tmp_path, "0.2.1.dev3", commit, channel)
            text = (tmp_path / name).read_text(encoding="utf-8")
            assert "0.2.1.dev3" in text and commit in text and channel in text
            assert "@VERSION@" not in text and "@SOURCE_COMMIT@" not in text
            assert "0.2.1.dev2" not in text


def test_invalid_release_channel_fails_before_environment_or_files(monkeypatch, tmp_path):
    from tools import build_windows
    monkeypatch.setattr(build_windows, "check_environment",
                        lambda: pytest.fail("must reject channel before starting a build"))
    with pytest.raises(ValueError, match="Unsupported release channel"):
        build_windows.build(tmp_path / "output", channel="stable-by-mistake")
    assert not (tmp_path / "output").exists()


def test_lgpl_wrappers_are_collected_outside_the_executable():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "packaging/NetMonitor.spec").read_text(encoding="utf-8"))
    analysis = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == "Analysis")
    mode = next(k.value for k in analysis.keywords if k.arg == "module_collection_mode")
    assert ast.literal_eval(mode) == {"PySide6": "py", "shiboken6": "py"}


def test_additional_license_sources_match_shipped_text():
    import hashlib
    import json
    root = Path(__file__).resolve().parents[1] / "packaging/licenses"
    for record in json.loads((root / "additional-sources.json").read_text(encoding="utf-8")):
        assert hashlib.sha256((root / record["file"]).read_bytes()).hexdigest() == record["sha256"]
