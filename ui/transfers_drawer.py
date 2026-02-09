from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem,
    QAbstractItemView, QToolButton, QStyle
)
from PySide6.QtCore import Qt, Signal


class TransfersDrawer(QWidget):
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(220)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ---- header row with X ----
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel("Transfers")
        self.title.setStyleSheet("font-weight:700;")
        header.addWidget(self.title)

        header.addStretch(1)

        self.btn_close = QToolButton()
        self.btn_close.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        self.btn_close.setToolTip("Close transfers")
        self.btn_close.clicked.connect(self.close_requested.emit)
        header.addWidget(self.btn_close)

        root.addLayout(header)

        # ---- table ----
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Type", "Bucket", "Key", "Progress", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)

        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        root.addWidget(self.table, 1)

        self.rows = {}  # transfer_id -> row index

    def upsert(self, transfer_id: str, mode: str, bucket: str, key: str, progress: int, status: str):
        if transfer_id not in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[transfer_id] = row

            self.table.setItem(row, 0, QTableWidgetItem(mode))
            self.table.setItem(row, 1, QTableWidgetItem(bucket))
            self.table.setItem(row, 2, QTableWidgetItem(key))
            self.table.setItem(row, 3, QTableWidgetItem(str(max(0, progress))))
            self.table.setItem(row, 4, QTableWidgetItem(status))
        else:
            row = self.rows[transfer_id]
            if progress >= 0:
                self.table.item(row, 3).setText(str(progress))
            self.table.item(row, 4).setText(status)
