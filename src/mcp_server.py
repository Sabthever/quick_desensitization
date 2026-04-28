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
from i18n import tr


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
        schema = {"type": "string", "description": tr("mcp_alias_schema")}
        if aliases:
            schema["enum"] = aliases
            schema["description"] = tr("mcp_alias_schema_has", aliases=", ".join(aliases))
        else:
            schema["description"] = tr("mcp_alias_schema_help")
        return schema

    def _setup_handlers(self):
        srv = self.server

        @srv.list_tools()
        async def list_tools() -> list[Tool]:
            alias_schema = self._get_alias_schema()
            file_type_schema = {
                "type": "string",
                "enum": ["yml", "env", "json"],
                "description": tr("mcp_file_type_desc")
            }

            return [
                Tool(
                    name="desensitize",
                    description=tr("mcp_desc_desensitize"),
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
                    description=tr("mcp_desc_restore"),
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
                    description=tr("mcp_desc_list_projects"),
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_project_rules",
                    description=tr("mcp_desc_get_rules"),
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
                    description=tr("mcp_desc_add_rule"),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "fileType": dict(file_type_schema),
                            "fileMatch": {"type": "string", "description": tr("mcp_desc_file_match")},
                            "fieldPath": {"type": "string", "description": tr("mcp_desc_field_path")},
                            "enabled": {"type": "boolean", "description": tr("mcp_desc_enabled")}
                        },
                        "required": ["project_alias", "fileType", "fileMatch", "fieldPath"]
                    }
                ),
                Tool(
                    name="edit_project_rule",
                    description=tr("mcp_desc_edit_rule"),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": tr("mcp_desc_rule_id")},
                            "fileType": dict(file_type_schema),
                            "fileMatch": {"type": "string", "description": tr("mcp_desc_file_match")},
                            "fieldPath": {"type": "string", "description": tr("mcp_desc_field_path")},
                            "enabled": {"type": "boolean", "description": tr("mcp_desc_enabled")}
                        },
                        "required": ["project_alias", "rule_id", "fileType", "fileMatch", "fieldPath", "enabled"]
                    }
                ),
                Tool(
                    name="delete_project_rule",
                    description=tr("mcp_desc_delete_rule"),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": tr("mcp_desc_rule_id")}
                        },
                        "required": ["project_alias", "rule_id"]
                    }
                ),
                Tool(
                    name="toggle_project_rule",
                    description=tr("mcp_desc_toggle_rule"),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_alias": dict(alias_schema),
                            "rule_id": {"type": "integer", "description": tr("mcp_desc_rule_id")}
                        },
                        "required": ["project_alias", "rule_id"]
                    }
                ),
                Tool(
                    name="add_project",
                    description=tr("mcp_desc_add_project"),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_path": {"type": "string", "description": tr("mcp_desc_project_path")},
                            "alias": {"type": "string", "description": tr("mcp_desc_alias")}
                        },
                        "required": ["project_path", "alias"]
                    }
                ),
                Tool(
                    name="delete_project",
                    description=tr("mcp_desc_delete_project"),
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
                return [TextContent(type="text", text=tr("mcp_unknown_tool", name=name))]
            except Exception as e:
                return [TextContent(type="text", text=tr("mcp_exec_error", error=str(e)))]

    def _get_project_by_alias_or_error(self, alias: str):
        projects = self.storage.get_projects()
        for p in projects:
            if p.get("alias") == alias:
                return p
        raise ValueError(tr("mcp_project_not_found", alias=alias))

    async def _handle_list_projects(self, args: dict):
        projects = self.storage.get_projects()
        project_list = []
        for p in projects:
            project_list.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "alias": p.get("alias", ""),
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
                    "message": tr("mcp_rule_exists")
                }, ensure_ascii=False, indent=2))]

        rules.append(new_rule)
        self.storage.save_secret_config(secret_path, rules)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": tr("mcp_rule_added", count=len(rules)),
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
                "message": tr("mcp_rule_id_invalid", id=rule_id, min=0, max=len(rules) - 1)
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
            "message": tr("mcp_rule_edited", id=rule_id),
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
                "message": tr("mcp_rule_id_invalid", id=rule_id, min=0, max=len(rules) - 1)
            }, ensure_ascii=False, indent=2))]

        deleted_rule = rules.pop(rule_id)
        self.storage.save_secret_config(secret_path, rules)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": tr("mcp_rule_deleted", id=rule_id, count=len(rules)),
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
                "message": tr("mcp_rule_id_invalid", id=rule_id, min=0, max=len(rules) - 1)
            }, ensure_ascii=False, indent=2))]

        current = rules[rule_id].get("enabled", True)
        rules[rule_id]["enabled"] = not current
        self.storage.save_secret_config(secret_path, rules)

        status_text = tr("mcp_status_enabled") if rules[rule_id]["enabled"] else tr("mcp_status_disabled")
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "message": tr("mcp_rule_toggled", id=rule_id, status=status_text),
            "rule": rules[rule_id]
        }, ensure_ascii=False, indent=2))]

    async def _handle_add_project(self, args: dict):
        alias = args["alias"]
        project_path = args["project_path"]

        if self.storage.is_alias_exists(alias):
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_alias_in_use", alias=alias)
            }, ensure_ascii=False, indent=2))]

        if not Path(project_path).exists():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_path_not_exist", path=project_path)
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
            "message": tr("mcp_project_created", alias=alias),
            "project": {
                "id": new_project["id"],
                "name": project_name,
                "alias": alias
            }
        }, ensure_ascii=False, indent=2))]

    async def _handle_delete_project(self, args: dict):
        alias = args["project_alias"]
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "message": tr("mcp_delete_in_gui", alias=alias)
        }, ensure_ascii=False, indent=2))]

    async def _handle_desensitize(self, args: dict):
        project = self._get_project_by_alias_or_error(args["project_alias"])
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        if not Path(project_path).exists():
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_path_not_exist", path=project_path)
            }, ensure_ascii=False, indent=2))]

        rules = self.storage.load_secret_config(secret_path)
        if not rules:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_no_rules")
            }, ensure_ascii=False, indent=2))]

        enabled_rules = [r for r in rules if r.get("enabled", True)]
        if not enabled_rules:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_no_enabled_rules")
            }, ensure_ascii=False, indent=2))]

        self.storage.ensure_secret_path(secret_path)

        matched_files = self.engine.scan_files(project_path, enabled_rules)
        if not matched_files:
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "message": tr("mcp_no_match")
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
            "message": tr("mcp_desensitize_done", count=len(saved_entries)) if saved_entries else tr("mcp_no_field"),
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
                "message": tr("mcp_no_restore_data")
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
                "message": tr("mcp_restore_done", count=restored_count),
                "project_alias": project.get("alias"),
                "project_name": project.get("name"),
                "restored_files": restored_files
            }, ensure_ascii=False, indent=2))]
        else:
            return [TextContent(type="text", text=json.dumps({
                "success": True,
                "message": tr("mcp_not_desensitized")
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
