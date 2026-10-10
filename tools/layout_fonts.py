"""Pinned font for CI/offscreen evidence only; never imported by the product.

Noto Sans CJK SC is SIL OFL 1.1 licensed; upstream license:
https://github.com/notofonts/noto-cjk/blob/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE
Font files stay in RUNNER_TEMP and are not uploaded as artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import urllib.request

COMMIT = "f8d157532fbfaeda587e826d4cd5b21a49186f7c"
BLOB_SHA = "dc15562470b4f842321894787a0d066879ccff8b"
FONT_SIZE = 16437364
FONT_NAME = "NotoSansCJKsc-Regular.otf"
URL = f"https://raw.githubusercontent.com/notofonts/noto-cjk/{COMMIT}/Sans/OTF/SimplifiedChinese/{FONT_NAME}"
GLYPHS = "中文应用本次监控累计0123456789KiB/s↑↓—…●"


def verify_font(data: bytes) -> None:
    digest = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    if len(data) != FONT_SIZE or digest != BLOB_SHA:
        raise ValueError("Layout font does not match the pinned upstream Git blob")


def prepare(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / FONT_NAME
    if path.exists():
        verify_font(path.read_bytes())
        return path
    with urllib.request.urlopen(URL, timeout=45) as response:
        data = response.read(FONT_SIZE + 1)
    verify_font(data)
    path.write_bytes(data)
    return path


def configure_application(app) -> dict:
    from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics

    path_text = os.environ.get("NET_MONITOR_LAYOUT_FONT")
    if path_text:
        path = Path(path_text)
        verify_font(path.read_bytes())
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise RuntimeError("Qt could not load the pinned CI font")
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise RuntimeError("CI font has no usable Qt family")
        app.setFont(QFont(families[0], 10))
    metrics = QFontMetrics(app.font())
    missing = [char for char in GLYPHS if not metrics.inFontUcs4(ord(char))]
    if missing:
        raise RuntimeError(f"Offscreen font coverage missing: {missing}; prepare the layout font first")
    return {"family": QFontInfo(app.font()).family(), "glyphs_checked": GLYPHS,
            "pinned_font": bool(path_text), "upstream_commit": COMMIT if path_text else None,
            "upstream_blob": BLOB_SHA if path_text else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.prepare))
