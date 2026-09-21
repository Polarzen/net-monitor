from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from net_monitor.ui.micro_model import AppChoice
from net_monitor.ui.micro_window import ApplicationChooser
from test_stage3c_ui import app, make_controller, snapshot


def _choices(count: int, *, duplicate_name: bool = False) -> tuple[AppChoice, ...]:
    return tuple(
        AppChoice(
            f"application-key-{index}",
            "duplicate.exe" if duplicate_name else f"application-{index}.exe",
            rf"D:\Apps\application-{index}.exe",
        )
        for index in range(count)
    )


def test_application_chooser_bounds_and_wheel_reaches_last_item(app):
    chooser = ApplicationChooser(_choices(200))
    chooser.show()
    app.processEvents()
    try:
        assert (chooser.width(), chooser.height()) == (372, 460)
        scrollbar = chooser.scroll.verticalScrollBar()
        assert scrollbar.maximum() > 0

        viewport = chooser.scroll.viewport()
        center = viewport.rect().center()
        wheel = QWheelEvent(
            QPointF(center), QPointF(viewport.mapToGlobal(center)),
            QPoint(0, -120), QPoint(0, -120), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, False,
        )
        QApplication.sendEvent(viewport, wheel)
        app.processEvents()
        assert scrollbar.value() > 0

        scrollbar.setValue(scrollbar.maximum())
        app.processEvents()
        last = chooser._buttons[-1]
        last_rect = QRect(last.mapTo(viewport, QPoint(0, 0)), last.size())
        assert viewport.rect().intersects(last_rect)
    finally:
        chooser.close()
        app.processEvents()


def test_application_chooser_duplicate_names_keep_exact_last_key(app):
    choices = _choices(8, duplicate_name=True)
    chooser = ApplicationChooser(choices)
    selected: list[str] = []
    chooser.choice_selected.connect(selected.append)
    chooser.show()
    app.processEvents()
    try:
        chooser.scroll.verticalScrollBar().setValue(chooser.scroll.verticalScrollBar().maximum())
        chooser._buttons[-1].click()
        app.processEvents()
        assert selected == [choices[-1].key]
    finally:
        chooser.close()
        app.processEvents()


def test_application_chooser_escape_and_hide_clear_card_state_and_reopen(make_controller, app):
    controller = make_controller()
    controller._on_snapshot(snapshot())
    card = controller.card
    card.apply_frame(replace(controller.projection.frame(), choices=_choices(20)))
    card.show()
    card._show_chooser()
    app.processEvents()
    first = card._chooser
    assert first is not None and card._menu_open

    first.hide()
    app.processEvents()
    assert card._chooser is None and not card._menu_open

    card._show_chooser()
    app.processEvents()
    second = card._chooser
    assert second is not None and card._menu_open
    QTest.keyClick(second, Qt.Key.Key_Escape)
    app.processEvents()
    assert card._chooser is None and not card._menu_open

