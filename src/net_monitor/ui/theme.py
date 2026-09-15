from __future__ import annotations

DARK_STYLESHEET = """
QWidget {
    background-color: #171a1f;
    color: #e8edf2;
    font-size: 10pt;
}
QMainWindow { background-color: #171a1f; }
QLabel#titleLabel { font-size: 15pt; font-weight: 600; color: #f4f7fa; }
QLabel#metricValue { font-size: 17pt; font-weight: 650; color: #f4f7fa; }
QLabel#metricCaption, QLabel#secondaryLabel { color: #8f9aa6; }
QLabel#statusAvailable { color: #7dd3a8; }
QLabel#statusWarning { color: #e7b96b; }
QLabel#statusError { color: #e58b8b; }
QLabel#statusIdle { color: #99a2ad; }
QFrame#metricCard, QFrame#appRow, QFrame#emptyCard {
    background-color: #20242b;
    border: 1px solid #2b313a;
    border-radius: 9px;
}
QPushButton {
    background-color: #252b33;
    border: 1px solid #343c47;
    border-radius: 7px;
    padding: 6px 10px;
}
QPushButton:hover { background-color: #2c333d; border-color: #465260; }
QPushButton:pressed { background-color: #20262e; }
QPushButton#accentButton { color: #8bcde8; }
QCheckBox { spacing: 7px; color: #cbd2da; }
QTreeWidget {
    background-color: #1b1f25;
    alternate-background-color: #1e232a;
    border: 1px solid #2c333d;
    border-radius: 8px;
    outline: 0;
}
QTreeWidget::item { min-height: 28px; padding: 2px 5px; }
QTreeWidget::item:hover { background-color: #252c35; }
QTreeWidget::item:selected { background-color: #2d4656; color: #ffffff; }
QHeaderView::section {
    background-color: #20252c;
    color: #aeb8c3;
    border: 0;
    border-bottom: 1px solid #303741;
    padding: 7px 8px;
}
QMenu {
    background-color: #20242b;
    border: 1px solid #343b45;
    padding: 5px;
}
QMenu::item { padding: 6px 22px 6px 10px; border-radius: 5px; }
QMenu::item:selected { background-color: #2b333d; }
"""
