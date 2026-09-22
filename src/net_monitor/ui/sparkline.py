"""Minimal sparkline widget for Stage 3E rate history visualization.

Draws upload (green) and download (blue) lines from a sequence of RateSample
points. None values create gaps in the line (not drawn as 0).
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
    uses the full vertical range. None values create gaps in the line.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_SPARKLINE_WIDTH, _SPARKLINE_HEIGHT)
        self._upload: list[float | None] = []
        self._download: list[float | None] = []

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

        # Auto-scale Y to the peak of both series combined (ignoring None).
        valid_uploads = [v for v in self._upload if v is not None]
        valid_downloads = [v for v in self._download if v is not None]
        peak = max(
            max(valid_uploads, default=0.0),
            max(valid_downloads, default=0.0),
        )
        if peak <= 0.0:
            # All zeros or all None - draw flat lines at the vertical midpoint.
            mid_y = height / 2.0
            if valid_uploads:
                painter.setPen(QPen(_UPLOAD_COLOR, 1.0))
                painter.drawLine(0, int(mid_y), width, int(mid_y))
            if valid_downloads:
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

        def _draw_line(values: list[float | None], color: QColor) -> None:
            """Draw a line with gaps for None values."""
            painter.setPen(QPen(color, 1.0))
            prev_x = None
            prev_y = None
            for i, value in enumerate(values):
                if value is None:
                    # Gap: reset previous point
                    prev_x = None
                    prev_y = None
                    continue
                curr_x = _x(i)
                curr_y = _y(value)
                if prev_x is not None:
                    painter.drawLine(prev_x, prev_y, curr_x, curr_y)
                prev_x = curr_x
                prev_y = curr_y

        _draw_line(self._upload, _UPLOAD_COLOR)
        _draw_line(self._download, _DOWNLOAD_COLOR)

        painter.end()
