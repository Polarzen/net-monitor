"""Convert the approved PNG master into a multi-resolution Windows ICO.

Run with the project's pinned PySide6 build environment. No image generation
or creative edits are performed here; this only encodes scaled icon frames.
"""
from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> None:
    master = QImage(str(ROOT / "packaging/branding/net-monitor-master.png"))
    if master.isNull() or master.width() != master.height() or not master.hasAlphaChannel():
        raise ValueError("Icon master must be a square PNG with transparency")
    entries, frames = [], []
    offset = 6 + 16 * len(SIZES)
    for size in SIZES:
        scaled = master.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not scaled.save(buffer, "PNG"):
            raise RuntimeError(f"Failed to encode {size}px icon")
        frame = bytes(buffer.data())
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                   1, 32, len(frame), offset))
        frames.append(frame)
        offset += len(frame)
    target = ROOT / "src/net_monitor/assets/net-monitor.ico"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(struct.pack("<HHH", 0, 1, len(SIZES)) + b"".join(entries + frames))
    print(target)


if __name__ == "__main__":
    main()
