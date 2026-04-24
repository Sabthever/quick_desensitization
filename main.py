# -*- coding: utf-8 -*-
import sys
import os
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from storage import Storage


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("脱敏小工具")
    app.setOrganizationName("DesensitizationTool")

    storage = Storage()
    window = MainWindow(storage)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
