from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt


class ConfirmDialog(QDialog):
    """
    Usage:
        dlg = ConfirmDialog("Delete", "Delete?\n\npath/file.txt", "Delete", self)
        if dlg.exec() != QDialog.Accepted:
            return
    """

    def __init__(self, title: str, text: str, danger_text: str = "Delete", parent=None):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(True)

        # ✅ remove help button (?) properly
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("dlgTitle")
        lbl_title.setTextInteractionFlags(Qt.TextSelectableByMouse)

        lbl_text = QLabel(text)
        lbl_text.setObjectName("dlgText")
        lbl_text.setWordWrap(True)
        lbl_text.setTextInteractionFlags(Qt.TextSelectableByMouse)

        root.addWidget(lbl_title)
        root.addWidget(lbl_text)

        btns = QHBoxLayout()
        btns.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_ok = QPushButton(danger_text)
        self.btn_ok.setObjectName("danger")
        self.btn_ok.setDefault(True)

        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        root.addLayout(btns)
