from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from services.credential_store import CredentialStore


class CredentialDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AWS Credentials")
        self.setFixedWidth(400)

        layout = QVBoxLayout(self)

        self.access_key = QLineEdit()
        self.secret_key = QLineEdit()
        self.region = QLineEdit()

        self.secret_key.setEchoMode(QLineEdit.Password)

        layout.addWidget(QLabel("Access Key ID"))
        layout.addWidget(self.access_key)

        layout.addWidget(QLabel("Secret Access Key"))
        layout.addWidget(self.secret_key)

        layout.addWidget(QLabel("Region (e.g. ap-south-1)"))
        layout.addWidget(self.region)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save)

        layout.addWidget(save_btn)

    def save(self):
        if not self.access_key.text().strip() or \
           not self.secret_key.text().strip() or \
           not self.region.text().strip():

            QMessageBox.warning(
                self,
                "Error",
                "All fields are required"
            )
            return

        CredentialStore.save(
            self.access_key.text().strip(),
            self.secret_key.text().strip(),
            self.region.text().strip()
        )

        self.accept()
