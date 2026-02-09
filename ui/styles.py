LIGHT_STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; }

QMainWindow { background-color: #f3f4f6; }

QToolBar {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    margin: 8px;
    padding: 6px;
    spacing: 10px;
}

/* ✅ toolbar buttons */
QToolButton { padding: 6px 10px; border-radius: 8px; }
QToolButton:hover { background: #f1f5f9; }
QToolButton:pressed { background: #e2e8f0; }

/* ✅ IMPORTANT: checked / selected look */
QToolButton:checked {
    background: #dbeafe;
    border: 1px solid #93c5fd;
}
QToolButton:checked:hover {
    background: #cfe8ff;
}

QLineEdit {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 6px 10px;
}

QWidget#crumbBar {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 6px 10px;
}

QTreeView, QTableView, QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    selection-background-color: #cfe8ff;
    selection-color: #0b1220;
    outline: 0;
}
QTreeView::item, QTableView::item, QTableWidget::item { padding: 6px; }

QHeaderView::section {
    background-color: #f8fafc;
    padding: 8px;
    border: 0;
    border-bottom: 1px solid #e5e7eb;
    font-weight: 600;
}

QStatusBar { background: #ffffff; border-top: 1px solid #e5e7eb; }

QLabel#statusPill {
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid #c7d2fe;
    background: #eef2ff;
    color: #1e3a8a;
}
QLabel#statusPill[state="disconnected"] {
    border: 1px solid #fecaca;
    background: #fef2f2;
    color: #991b1b;
}

/* Popup menu */
QMenu {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 18px;
    border-radius: 8px;
    color: #0b1220;
}
QMenu::item:selected { background: #e5f0ff; }
QMenu::item:disabled { color: #94a3b8; }
QMenu::separator {
    height: 1px;
    background: #e5e7eb;
    margin: 6px 8px;
}

/* Tooltip toast */
QToolTip {
    background: #111827;
    color: #ffffff;
    border: 1px solid #334155;
    padding: 6px 10px;
    border-radius: 8px;
}

/* Custom confirm dialog */
QDialog { background: #ffffff; }
QLabel#dlgTitle { font-size: 11pt; font-weight: 700; color: #0b1220; }
QLabel#dlgText { color: #334155; }
QPushButton {
    padding: 8px 14px;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    background: #ffffff;
}
QPushButton:hover { background: #f8fafc; }
QPushButton#danger {
    background: #ef4444;
    border: 1px solid #dc2626;
    color: #ffffff;
}
QPushButton#danger:hover { background: #dc2626; }
"""

DARK_STYLE = """
* { font-family: "Segoe UI"; font-size: 10pt; color: #e5e7eb; }

QMainWindow { background-color: #0b1220; }

QToolBar {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    margin: 8px;
    padding: 6px;
    spacing: 10px;
}

/* ✅ toolbar buttons */
QToolButton { padding: 6px 10px; border-radius: 8px; }
QToolButton:hover { background: #1f2937; }
QToolButton:pressed { background: #374151; }

/* ✅ IMPORTANT: checked / selected look */
QToolButton:checked {
    background: #1d4ed8;
    border: 1px solid #2563eb;
    color: #ffffff;
}
QToolButton:checked:hover {
    background: #2563eb;
}

QLineEdit {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 6px 10px;
}

QWidget#crumbBar {
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 6px 10px;
}

QTreeView, QTableView, QTableWidget {
    background-color: #111827;
    border: 1px solid #1f2937;
    border-radius: 10px;
    alternate-background-color: #0f172a;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: 0;
}
QTreeView::item, QTableView::item, QTableWidget::item { padding: 6px; }

QHeaderView::section {
    background-color: #0f172a;
    padding: 8px;
    border: 0;
    border-bottom: 1px solid #1f2937;
    font-weight: 600;
}

QStatusBar { background: #111827; border-top: 1px solid #1f2937; }

QLabel#statusPill {
    padding: 3px 10px;
    border-radius: 999px;
    border: 1px solid #334155;
    background: #0f172a;
    color: #93c5fd;
}
QLabel#statusPill[state="disconnected"] {
    border: 1px solid #7f1d1d;
    background: #1f0b0b;
    color: #fca5a5;
}

/* Popup menu (dark) */
QMenu {
    background: #0f172a;
    border: 1px solid #1f2937;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 18px;
    border-radius: 8px;
    color: #e5e7eb;
}
QMenu::item:selected { background: #1f2937; }
QMenu::item:disabled { color: #64748b; }
QMenu::separator {
    height: 1px;
    background: #1f2937;
    margin: 6px 8px;
}

/* Tooltip toast */
QToolTip {
    background: #0f172a;
    color: #e5e7eb;
    border: 1px solid #334155;
    padding: 6px 10px;
    border-radius: 8px;
}

/* Custom confirm dialog */
QDialog { background: #0f172a; }
QLabel#dlgTitle { font-size: 11pt; font-weight: 700; color: #e5e7eb; }
QLabel#dlgText { color: #cbd5e1; }
QPushButton {
    padding: 8px 14px;
    border-radius: 10px;
    border: 1px solid #334155;
    background: #111827;
    color: #e5e7eb;
}
QPushButton:hover { background: #1f2937; }
QPushButton#danger {
    background: #ef4444;
    border: 1px solid #dc2626;
    color: #ffffff;
}
QPushButton#danger:hover { background: #dc2626; }
"""
