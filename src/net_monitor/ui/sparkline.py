"""Minimal sparkline widget for Stage 3E rate history visualization.

Draws upload (green) and download (blue) lines from a sequence of RateSample
points. No axes, no labels - just the two lines scaled to the data range.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from net_monitor.ui.rate_history import RateSample

# Dark-theme palette consistent with theme.py
_UPLOAD_COLOR = QColor("#7dd3a8")
_DOWNLOAD_COLOR = QColor("#6ba4d9")

# Fixed logical size - keeps the micro window layout stable.
_SPARKLINE_WIDTH = 60
_SPARKLINE_HEIGHT = 20


class Sparkline(QWidget):
    """Tiny two-line chart: upload (green) and download (blue).

    The widget is fixed at 60x20 logical pixels. Y-axis is auto-scaled to the
    maximum absolute value across both series so that the dominant line always
    uses the full vertical range.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SPARKLINE_WIDTH, _SPARKLINE_HEIGHT)
        self._upload: list[float] = []
        self._download: list[float] = []

    def set_data(self, samples: tuple[RateSample, ...]) -> None:
        """Replace the displayed data with a new sample sequence (oldest first)."""
        self._upload = [s.upload_bytes_per_second for s in samples]
        self._download = [s.download_bytes_per_second for s in samples]
        self.update()

    def clear(self) -> None:
        """Remove all data and repaint."""
        self._upload.clear()
        self._download.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming convention)
        if not self._upload and not self._download:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()
        count = max(len(self._upload), len(self._download))
        if count < 1:
            painter.end()
            return

        # Auto-scale Y to the peak of both series combined.
        peak = max(
            max(self._upload, default=0.0),
            max(self._download, default=0.0),
        )
        if peak <= 0.0:
            # All zeros - draw flat lines at the vertical midpoint.
            mid_y = height / 2.0
            painter.setPen(QPen(_UPLOAD_COLOR, 1.0))
            painter.drawLine(0, int(mid_y), width, int(mid_y))
            painter.setPen(QPen(_DOWNLOAD_COLOR, 1.0))
            painter.drawLine(0, int(mid_y), width, int(mid_y))
            painter.end()
            return

        step_x = width / max(count - 1, 1) if count > 1 else 0.0

        def _y(value: float) -> int:
            # Invert so that larger values are drawn higher.
            return int(height - 1 - (value / peak) * (height - 1))

        def _x(index: int) -> int:
            return int(index * step_x)

        # Draw upload (green) line.
        if len(self._upload) >= 2:
            painter.setPen(QPen(_UPLOAD_COLOR, 1.0))
            for i in range(len(self._upload) - 1):
                painter.drawLine(_x(i), _y(self._upload[i]),
                                 _x(i + 1), _y(self._upload[i + 1]))
        elif len(self._upload) == 1:
            painter.setPen(QPen(_UPLOAD_COLOR, 1.0))
            painter.drawPoint(_x(0), _y(self._upload[0]))

        # Draw download (blue) line.
        if len(self._download) >= 2:
            painter.setPen(QPen(_DOWNLOAD_COLOR, 1.0))
            for i in range(len(self._download) - 1):
                painter.drawLine(_x(i), _y(self._download[i]),
                                 _x(i + 1), _y(self._download[i + 1]))
        elif len(self._download) == 1:
            painter.setPen(QPen(_DOWNLOAD_COLOR, 1.0))
            painter.drawPoint(_x(0), _y(self._download[0]))

        painter.end()

