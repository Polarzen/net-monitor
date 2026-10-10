@echo off
setlocal
echo Net Monitor: bounded GUI idle-drain diagnostic.
echo This requests Windows administrator consent. No settings are changed.
echo After consent, the test runs for about 80 seconds and exits automatically.
"%~dp0..\.venv\Scripts\python.exe" -c "import ctypes,pathlib,subprocess,sys,uuid; root=pathlib.Path(sys.argv[1]).resolve(); out=root/'docs/evidence/stage4/desktop-acceptance/2026-10-10'/('gui-idle-drain-desktop-'+uuid.uuid4().hex[:12]); api=ctypes.windll.shell32.ShellExecuteW; api.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_wchar_p,ctypes.c_int]; api.restype=ctypes.c_void_p; params=subprocess.list2cmdline([str(root/'tools/verify_stage4_gui_drain.py'),'--output-dir',str(out)]); result=api(None,'runas',str(root/'.venv/Scripts/pythonw.exe'),params,str(root),1); print('Windows launch result:',result); print('Diagnostic output:',out); sys.exit(0 if result and result>32 else 1)" "%~dp0.."
if errorlevel 1 pause
endlocal
