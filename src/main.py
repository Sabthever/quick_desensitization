# -*- coding: utf-8 -*-
import sys
import os
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from storage import Storage
from mcp_server import start_mcp_server_in_thread


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("脱敏小工具")
    app.setOrganizationName("DesensitizationTool")

    storage = Storage()

    mcp_thread = start_mcp_server_in_thread(storage)
    print(f"[MCP] MCP Server 已启动 (线程: {mcp_thread.name})")

    window = MainWindow(storage)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
