# -*- coding: utf-8 -*-
import asyncio
import json
import threading
import fnmatch
from pathlib import Path
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from storage import Storage
from desensitize_engine import DesensitizeEngine


class DesensitizationMCPServer:
    def __init__(self, storage: Storage):
        self.storage = storage
        self.engine = DesensitizeEngine()
        self.server = Server("desensitization-tool")
        self._setup_handlers()

    def _get_aliases(self):
        projects = self.storage.get_projects()
        aliases = [p.get("alias") for p in projects if p.get("alias")]
        return aliases

    def _setup_handlers(self):
        srv = self.server

        @srv.list_tools()
        async def list_tools() -> list[Tool]:
            aliases = self._get_aliases()
            alias_schema = {"type": "string", "description": "项目别名"}
            if aliases:
                alias_schema["enum"] = aliases
                alias_schema["description"] = f"项目别名，可选值: {', '.join(aliases)}"
            else:
                alias_schema["description"] = "项目别名，请先在脱敏小工具的界面中创建项目并设置别名"

            return [
                Tool(
                    name="desensitize",
                    description="对指定别名的项目执行脱敏操作，将所有配置规则匹配的敏感字段替换为占位符，原始值加密存储到敏感数据路径",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema)
                        },
                        "required": ["project_alias"]
                    }
                ),
                Tool(
                    name="restore",
                    description="对指定别名的项目执行恢复操作，将脱敏占位符替换回原始敏感数据",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema)
                        },
                        "required": ["project_alias"]
                    }
                ),
            ]

        @srv.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            try:
                if name == "desensitize":
                    return await self._handle_desensitize(arguments)
                elif name == "restore":
                    return await self._handle_restore(arguments)
                else:
                    return [TextContent(type="text", text=f"未知工具: {name}")]
            except Exception as e:
                return [TextContent(type="text", text=f"执行出错: {str(e)}")]

    def _get_project_by_alias_or_error(self, alias: str):
        projects = self.storage.get_projects()
        for p in projects:
            if p.get("alias") == alias:
                return p
        raise ValueError(f"未找到别名为「{alias}」的项目，请先在软件中创建项目并设置别名")

    async def _handle_desensitize(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        if not Path(project_path).exists():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"项目路径不存在: {project_path}"
            }, ensure_ascii=False, indent=2))]

        rules = self.storage.load_secret_config(secret_path)
        if not rules:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": "请先配置脱敏规则"
            }, ensure_ascii=False, indent=2))]

        enabled_rules = [r for r in rules if r.get("enabled", True)]
        if not enabled_rules:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": "没有启用的脱敏规则"
            }, ensure_ascii=False, indent=2))]

        self.storage.ensure_secret_path(secret_path)

        matched_files = self.engine.scan_files(project_path, enabled_rules)
        if not matched_files:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": "未找到匹配的文件"
            }, ensure_ascii=False, indent=2))]

        saved_entries = set()
        processed_files = []

        for file_type, files in matched_files.items():
            for rel_path, file_rules in files.items():
                file_path = Path(project_path) / rel_path
                if not file_path.exists():
                    continue

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                field_paths = [fr["fieldPath"] for fr in file_rules]

                if file_type in ["yml", "yaml"]:
                    new_content, changes = self.engine.process_yml(content, field_paths)
                elif file_type == "env":
                    new_content, changes = self.engine.process_env(content, field_paths)
                elif file_type == "json":
                    try:
                        new_content, changes = self.engine.process_json(content, field_paths)
                    except json.JSONDecodeError:
                        continue
                else:
                    continue

                if changes:
                    self.storage.create_backup(secret_path, file_path, content)

                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(new_content)

                    for change in changes:
                        secret_entry = {
                            "filePath": rel_path,
                            "fieldPath": change["fieldPath"],
                            "placeholder": change["placeholder"],
                            "originalValue": change["originalValue"],
                            "timestamp": datetime.now().isoformat()
                        }
                        self.storage.append_secret(secret_path, secret_entry)
                        saved_entries.add((rel_path, change["fieldPath"]))

                    processed_files.append({
                        "file": rel_path,
                        "type": file_type,
                        "changes_count": len(changes)
                    })

        return [TextContent(type="text", text=json.dumps({
            "success": len(saved_entries) > 0,
            "message": f"脱敏完成，共处理 {len(saved_entries)} 个字段" if saved_entries else "没有需要脱敏的字段",
            "project_alias": project.get("alias"),
            "project_name": project.get("name"),
            "processed_files": processed_files,
            "total_fields_desensitized": len(saved_entries)
        }, ensure_ascii=False, indent=2))]

    async def _handle_restore(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        secrets = self.storage.load_secrets(secret_path)
        if not secrets:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": "没有可恢复的数据"
            }, ensure_ascii=False, indent=2))]

        rules = self.storage.load_secret_config(secret_path)
        matched_files = {}
        for rule in rules:
            file_type = rule["fileType"]
            if file_type not in matched_files:
                matched_files[file_type] = []

            file_match = rule["fileMatch"]
            file_patterns = [pattern.strip() for pattern in file_match.split(';')]

            for file_path in Path(project_path).rglob("*"):
                if not file_path.is_file():
                    continue

                matched = False
                for pattern in file_patterns:
                    if pattern and fnmatch.fnmatch(file_path.name, pattern):
                        matched = True
                        break

                if matched:
                    matched_files[file_type].append(file_path)

        restored_count = 0
        restored_files = []
        for file_type, files in matched_files.items():
            for file_path in files:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if "${val_" not in content:
                    continue

                if file_type in ["yml", "yaml"]:
                    new_content = self.engine.restore_yml(content, secrets)
                elif file_type == "env":
                    new_content = self.engine.restore_env(content, secrets)
                elif file_type == "json":
                    try:
                        new_content = self.engine.restore_json(content, secrets)
                    except json.JSONDecodeError:
                        continue
                else:
                    continue

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                restored_count += 1
                restored_files.append(str(file_path.relative_to(project_path) if file_path.is_relative_to(project_path) else file_path.name))

        if restored_count > 0:
            self.storage.clear_secrets(secret_path)
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "message": f"恢复完成，共恢复 {restored_count} 个文件",
                "project_alias": project.get("alias"),
                "project_name": project.get("name"),
                "restored_files": restored_files
            }, ensure_ascii=False, indent=2))]
        else:
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "message": "配置文件未脱敏，无需恢复"
            }, ensure_ascii=False, indent=2))]

    def run(self):
        asyncio.run(self._run_server())

    async def _run_server(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )


def start_mcp_server_in_thread(storage: Storage):
    mcp_server = DesensitizationMCPServer(storage)

    thread = threading.Thread(
        target=mcp_server.run,
        daemon=True,
        name="MCP-Server-Thread"
    )
    thread.start()
    return thread
