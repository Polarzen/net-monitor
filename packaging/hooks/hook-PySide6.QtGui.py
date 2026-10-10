"""Use the official Qt dependency analysis with two unused optional plugins omitted.

Net Monitor uses Qt Widgets, file icons and painted charts. It never loads PDF
documents or a QML virtual keyboard. Selecting plugins here avoids collecting
their unrelated QtPdf/QtQuick dependency trees; no built DLL is deleted later.
"""
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, destination) for source, destination in binaries
            if Path(source).name.casefold() not in {"qpdf.dll", "qtvirtualkeyboardplugin.dll"}]
