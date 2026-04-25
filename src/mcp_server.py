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

    def _get_alias_schema(self):
        aliases = self._get_aliases()
        schema = {"type": "string", "description": "项目别名"}
        if aliases:
            schema["enum"] = aliases
            schema["description"] = f"项目别名，可选值: {', '.join(aliases)}"
        else:
            schema["description"] = "项目别名，请先在脱敏小工具的界面中创建项目并设置别名"
        return schema

    def _setup_handlers(self):
        srv = self.server

        @srv.list_tools()
        async def list_tools() -> list[Tool]:
            alias_schema = self._get_alias_schema()
            file_type_schema = {
                "type": "string",
                "enum": ["yml", "env", "json"],
                "description": "文件类型"
            }

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
                Tool(
                    name="list_projects",
                    description="列出所有已配置的脱敏项目，包含项目名称、别名、路径等信息",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_project_rules",
                    description="获取指定项目的所有脱敏规则列表，每条规则包含ID、文件类型、文件匹配、字段路径、启用状态",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema)
                        },
                        "required": ["project_alias"]
                    }
                ),
                Tool(
                    name="add_project_rule",
                    description="为指定项目添加一条脱敏规则",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "fileType": dict(file_type_schema),
                            "fileMatch": {"type": "string", "description": "文件匹配模式，例如: application*.yml 或 application*.yml;bootstrap*.yml"},
                            "fieldPath": {"type": "string", "description": "字段路径，根据文件类型填写对应格式"},
                            "enabled": {"type": "boolean", "description": "是否启用，默认 true"}
                        },
                        "required": ["project_alias", "fileType", "fileMatch", "fieldPath"]
                    }
                ),
                Tool(
                    name="edit_project_rule",
                    description="编辑指定项目中的一条脱敏规则，先用 get_project_rules 查看规则列表获取 ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": "规则ID（从 get_project_rules 获取的 id 字段）"},
                            "fileType": dict(file_type_schema),
                            "fileMatch": {"type": "string", "description": "文件匹配模式"},
                            "fieldPath": {"type": "string", "description": "字段路径"},
                            "enabled": {"type": "boolean", "description": "是否启用"}
                        },
                        "required": ["project_alias", "rule_id", "fileType", "fileMatch", "fieldPath", "enabled"]
                    }
                ),
                Tool(
                    name="delete_project_rule",
                    description="删除指定项目中的一条脱敏规则，先用 get_project_rules 查看规则列表获取 ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": "规则ID（从 get_project_rules 获取的 id 字段）"}
                        },
                        "required": ["project_alias", "rule_id"]
                    }
                ),
                Tool(
                    name="toggle_project_rule",
                    description="启用或禁用指定项目中的一条脱敏规则，先用 get_project_rules 查看规则列表获取 ID",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": "规则ID（从 get_project_rules 获取的 id 字段）"}
                        },
                        "required": ["project_alias", "rule_id"]
                    }
                ),
                Tool(
                    name="add_project",
                    description="新增一个脱敏项目，需要指定项目路径和别名，敏感数据路径会自动生成",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_path": {"type": "string", "description": "项目根目录的绝对路径"},
                            "alias": {"type": "string", "description": "项目别名，需要唯一"}
                        },
                        "required": ["project_path", "alias"]
                    }
                ),
                Tool(
                    name="delete_project",
                    description="删除指定项目的配置，注意：不会删除项目文件和数据，请打开脱敏小工具软件在界面中手动删除",
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
                handlers = {
                    "desensitize": self._handle_desensitize,
                    "restore": self._handle_restore,
                    "list_projects": self._handle_list_projects,
                    "get_project_rules": self._handle_get_project_rules,
                    "add_project_rule": self._handle_add_project_rule,
                    "edit_project_rule": self._handle_edit_project_rule,
                    "delete_project_rule": self._handle_delete_project_rule,
                    "toggle_project_rule": self._handle_toggle_project_rule,
                    "add_project": self._handle_add_project,
                    "delete_project": self._handle_delete_project,
                }
                handler = handlers.get(name)
                if handler:
                    return await handler(arguments)
                return [TextContent(type="text", text=f"未知工具: {name}")]
            except Exception as e:
                return [TextContent(type="text", text=f"执行出错: {str(e)}")]

    def _get_project_by_alias_or_error(self, alias: str):
        projects = self.storage.get_projects()
        for p in projects:
            if p.get("alias") == alias:
                return p
        raise ValueError(f"未找到别名为「{alias}」的项目，请先在软件中创建项目并设置别名")

    async def _handle_list_projects(self, args: dict):
        projects = self.storage.get_projects()
        project_list = []
        for p in projects:
            project_list.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "alias": p.get("alias", ""),
                "projectPath": p.get("projectPath"),
                "secretPath": p.get("secretPath"),
                "createdAt": p.get("createdAt"),
                "updatedAt": p.get("updatedAt")
            })
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "total": len(project_list),
            "projects": project_list
        }, ensure_ascii=False, indent=2))]

    async def _handle_get_project_rules(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        secret_path = project.get("secretPath", "")
        rules = self.storage.load_secret_config(secret_path)

        rule_list = []
        for i, rule in enumerate(rules):
            rule_list.append({
                "id": i,
                "fileType": rule.get("fileType"),
                "fileMatch": rule.get("fileMatch"),
                "fieldPath": rule.get("fieldPath"),
                "enabled": rule.get("enabled", True)
            })

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "project_alias": project.get("alias"),
            "project_name": project.get("name"),
            "total": len(rule_list),
            "rules": rule_list
        }, ensure_ascii=False, indent=2))]

    async def _handle_add_project_rule(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        secret_path = project.get("secretPath", "")

        rules = self.storage.load_secret_config(secret_path)
        new_rule = {
            "fileType": args["fileType"],
            "fileMatch": args["fileMatch"],
            "fieldPath": args["fieldPath"],
            "enabled": args.get("enabled", True)
        }

        for r in rules:
            if r["fileType"] == new_rule["fileType"] and r["fileMatch"] == new_rule["fileMatch"] and r["fieldPath"] == new_rule["fieldPath"]:
                return [TextContent(type="text", text=json.dumps({
                    "success": False,
                    "message": "该规则已存在，请勿重复添加"
                }, ensure_ascii=False, indent=2))]

        rules.append(new_rule)
        self.storage.save_secret_config(secret_path, rules)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": f"规则添加成功，当前共 {len(rules)} 条规则",
            "rule": new_rule
        }, ensure_ascii=False, indent=2))]

    async def _handle_edit_project_rule(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        secret_path = project.get("secretPath", "")
        rule_id = args["rule_id"]

        rules = self.storage.load_secret_config(secret_path)
        if rule_id < 0 or rule_id >= len(rules):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"规则ID {rule_id} 无效，有效范围: 0 ~ {len(rules) - 1}"
            }, ensure_ascii=False, indent=2))]

        rules[rule_id] = {
            "fileType": args["fileType"],
            "fileMatch": args["fileMatch"],
            "fieldPath": args["fieldPath"],
            "enabled": args["enabled"]
        }
        self.storage.save_secret_config(secret_path, rules)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": f"规则 {rule_id} 编辑成功",
            "rule": rules[rule_id]
        }, ensure_ascii=False, indent=2))]

    async def _handle_delete_project_rule(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        secret_path = project.get("secretPath", "")
        rule_id = args["rule_id"]

        rules = self.storage.load_secret_config(secret_path)
        if rule_id < 0 or rule_id >= len(rules):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"规则ID {rule_id} 无效，有效范围: 0 ~ {len(rules) - 1}"
            }, ensure_ascii=False, indent=2))]

        deleted_rule = rules.pop(rule_id)
        self.storage.save_secret_config(secret_path, rules)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": f"规则 {rule_id} 已删除，当前共 {len(rules)} 条规则",
            "deleted_rule": deleted_rule
        }, ensure_ascii=False, indent=2))]

    async def _handle_toggle_project_rule(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        secret_path = project.get("secretPath", "")
        rule_id = args["rule_id"]

        rules = self.storage.load_secret_config(secret_path)
        if rule_id < 0 or rule_id >= len(rules):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"规则ID {rule_id} 无效，有效范围: 0 ~ {len(rules) - 1}"
            }, ensure_ascii=False, indent=2))]

        current = rules[rule_id].get("enabled", True)
        rules[rule_id]["enabled"] = not current
        self.storage.save_secret_config(secret_path, rules)

        status_text = "启用" if rules[rule_id]["enabled"] else "禁用"
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": f"规则 {rule_id} 已{status_text}",
            "rule": rules[rule_id]
        }, ensure_ascii=False, indent=2))]

    async def _handle_add_project(self, args: dict):
        alias = args["alias"]
        project_path = args["project_path"]

        if self.storage.is_alias_exists(alias):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"别名「{alias}」已被其他项目使用，请换一个"
            }, ensure_ascii=False, indent=2))]

        if not Path(project_path).exists():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": f"项目路径不存在: {project_path}"
            }, ensure_ascii=False, indent=2))]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        secret_path = str(self.storage.config_dir / f"{alias}_{timestamp}")

        project_name = Path(project_path).name
        project_data = {
            "name": project_name,
            "alias": alias,
            "projectPath": project_path,
            "secretPath": secret_path
        }
        new_project = self.storage.add_project(project_data)

        Path(secret_path).mkdir(parents=True, exist_ok=True)
        config_file = Path(secret_path) / "secret_config.csv"
        if not config_file.exists():
            rule = {"fileType": "yml", "fileMatch": "application*.yml", "fieldPath": "spring.datasource.password"}
            self.storage.save_secret_config(secret_path, [rule])

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": f"项目「{alias}」创建成功",
            "project": {
                "id": new_project["id"],
                "name": project_name,
                "alias": alias,
                "projectPath": project_path,
                "secretPath": secret_path
            }
        }, ensure_ascii=False, indent=2))]

    async def _handle_delete_project(self, args: dict):
        alias = args["project_alias"]
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "message": f"请在脱敏小工具软件界面中手动删除项目「{alias}」的配置。MCP 工具不支持自动删除，请打开软件后点击项目对应的「删除」按钮进行操作。"
        }, ensure_ascii=False, indent=2))]

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

    async def run_async(self):
        await self._run_server()

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
