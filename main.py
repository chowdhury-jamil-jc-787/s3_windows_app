import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from ui.styles import LIGHT_STYLE

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(LIGHT_STYLE)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()