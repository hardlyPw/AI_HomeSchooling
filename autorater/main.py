from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from autorater.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Learning Friend Autorater")
    window = MainWindow()
    window.resize(1240, 820)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

