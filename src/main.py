# -*- coding: utf-8 -*-
import sys
import asyncio
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from storage import Storage
from mcp_server import DesensitizationMCPServer


def run_mcp_only(storage):
    print("[MCP] 以 MCP 模式启动（无界面）...")
    mcp_server = DesensitizationMCPServer(storage)
    asyncio.run(mcp_server.run_async())


def run_gui(storage):
    app = QApplication(sys.argv)
    app.setApplicationName("MultiMask")
    app.setOrganizationName("DesensitizationTool")

    from mcp_server import start_mcp_server_in_thread
    mcp_thread = start_mcp_server_in_thread(storage)
    print(f"[MCP] MCP Server 已启动 (线程: {mcp_thread.name})")

    window = MainWindow(storage)
    window.show()

    sys.exit(app.exec())


def main():
    storage = Storage()

    if "--mcp" in sys.argv:
        run_mcp_only(storage)
    else:
        run_gui(storage)


if __name__ == "__main__":
    main()
