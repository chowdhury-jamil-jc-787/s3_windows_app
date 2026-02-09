from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTreeView,
    QTableView,
    QToolBar,
    QStatusBar,
    QLabel,
    QProgressBar,
    QSplitter,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("S3 Browser")
        self.resize(1100, 700)

        self.create_toolbar()
        self.create_center()
        self.create_status_bar()

    def create_toolbar(self):
        toolbar = QToolBar()
        self.addToolBar(toolbar)

        toolbar.addAction(QAction("Connect", self))
        toolbar.addAction(QAction("Refresh", self))
        toolbar.addSeparator()
        toolbar.addAction(QAction("Upload", self))
        toolbar.addAction(QAction("Download", self))

    def create_center(self):
        splitter = QSplitter(Qt.Horizontal)

        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)

        self.table = QTableView()

        splitter.addWidget(self.tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(splitter)

        self.setCentralWidget(container)

    def create_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)

        self.status_label = QLabel("Disconnected")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFixedWidth(200)

        status.addWidget(self.status_label)
        status.addPermanentWidget(self.progress)
