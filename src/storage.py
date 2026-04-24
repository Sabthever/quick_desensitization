# -*- coding: utf-8 -*-
import json
import os
import csv
import uuid
import hashlib
from datetime import datetime
from pathlib import Path


class Storage:
    def __init__(self, config_dir=None):
        if config_dir is None:
            config_dir = Path.home() / ".desensitization"
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.projects_file = self.config_dir / "projects.json"
        self._init_projects_file()

    def _init_projects_file(self):
        if not self.projects_file.exists():
            self._save_projects({"projects": []})

    def _save_projects(self, data):
        with open(self.projects_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_projects(self):
        try:
            with open(self.projects_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {"projects": []}

    def save_projects(self, projects):
        data = {"projects": projects}
        self._save_projects(data)

    def get_projects(self):
        data = self.load_projects()
        return data.get("projects", [])

    def add_project(self, project_data):
        project_data["id"] = str(uuid.uuid4())
        project_data["createdAt"] = datetime.now().isoformat()
        project_data["updatedAt"] = datetime.now().isoformat()

        projects = self.get_projects()
        projects.append(project_data)
        self.save_projects(projects)
        return project_data

    def update_project(self, project_id, project_data):
        project_data["updatedAt"] = datetime.now().isoformat()
        projects = self.get_projects()
        for i, p in enumerate(projects):
            if p["id"] == project_id:
                projects[i] = {**p, **project_data}
                break
        self.save_projects(projects)

    def delete_project(self, project_id):
        projects = self.get_projects()
        projects = [p for p in projects if p["id"] != project_id]
        self.save_projects(projects)

    def get_project(self, project_id):
        projects = self.get_projects()
        for p in projects:
            if p["id"] == project_id:
                return p
        return None

    def get_projects_using_secret_path(self, secret_path):
        projects = self.get_projects()
        return [p for p in projects if p.get("secretPath") == secret_path]

    def get_projects_using_project_path(self, project_path):
        projects = self.get_projects()
        return [p for p in projects if p.get("projectPath") == project_path]

    def load_secret_config(self, secret_path):
        config_file = Path(secret_path) / "secret_config.csv"
        rules = []
        if config_file.exists():
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split(",")
                        if len(parts) >= 3:
                            enabled = True
                            if len(parts) >= 4:
                                enabled_str = parts[-1].strip().lower()
                                enabled = enabled_str != "false" and enabled_str != "0" and enabled_str != "禁用"
                                field_path = ",".join(parts[2:-1]).strip()
                            else:
                                field_path = ",".join(parts[2:]).strip()
                            rule = {
                                "fileType": parts[0].strip(),
                                "fileMatch": parts[1].strip(),
                                "fieldPath": field_path,
                                "enabled": enabled
                            }
                            rules.append(rule)
        return rules

    def save_secret_config(self, secret_path, rules):
        config_file = Path(secret_path) / "secret_config.csv"
        with open(config_file, "w", encoding="utf-8") as f:
            f.write("# 脱敏配置文件\n")
            f.write("# 格式：文件类型，文件匹配，字段路径，是否启用\n")
            f.write("# 文件类型：yml, env, json\n")
            f.write("# 文件匹配支持通配符 *，可用分号 ; 分隔多个匹配模式（或关系）\n")
            f.write("#   示例: application*.yml;bootstrap*.yml\n")
            f.write("# 字段路径格式见下方说明\n")
            f.write("# 是否启用：true/false\n\n")
            f.write("# yml/yaml 字段路径说明:\n")
            f.write("#   使用 * 跳过单个层级，如 spring.datasource.druid.*.password\n")
            f.write("#   使用 ** 跳过任意层级，如 spring.datasource.druid.**.password\n")
            f.write("# env 字段路径说明:\n")
            f.write("#   直接写 KEY 名称，支持 * 前缀/后缀匹配\n")
            f.write("# json 字段路径说明 (标准 JSONPath):\n")
            f.write("#   $.database.password - 精确路径\n")
            f.write("#   $..password - 任意位置的 password\n\n")
            for rule in rules:
                enabled = "true" if rule.get("enabled", True) else "false"
                f.write(f"{rule['fileType']},{rule['fileMatch']},{rule['fieldPath']},{enabled}\n")

    def load_secrets(self, secret_path):
        import base64
        secret_file = Path(secret_path) / "secret.csv"
        secrets = []
        if secret_file.exists():
            with open(secret_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split(",")
                        if len(parts) >= 5:
                            try:
                                original_value = base64.b64decode(parts[3].strip()).decode('utf-8')
                            except:
                                original_value = parts[3].strip()
                            secrets.append({
                                "filePath": parts[0].strip(),
                                "fieldPath": parts[1].strip(),
                                "placeholder": parts[2].strip(),
                                "originalValue": original_value,
                                "timestamp": parts[4].strip()
                            })
        return secrets

    def save_secrets(self, secret_path, secrets):
        import base64
        secret_file = Path(secret_path) / "secret.csv"
        with open(secret_file, "w", encoding="utf-8-sig") as f:
            f.write("# 敏感信息存储文件\n")
            f.write("# 格式: 文件路径,字段路径,占位符,原始值(Base64),脱敏时间\n")
            f.write("# 警告: 此文件包含敏感信息，请妥善保管！\n\n")
            for s in secrets:
                original_b64 = base64.b64encode(str(s['originalValue']).encode('utf-8')).decode('ascii')
                f.write(f"{s['filePath']},{s['fieldPath']},{s['placeholder']},{original_b64},{s['timestamp']}\n")

    def append_secret(self, secret_path, secret_entry):
        secret_file = Path(secret_path) / "secret.csv"
        secrets = self.load_secrets(secret_path)
        existing_idx = None
        for i, s in enumerate(secrets):
            if s["filePath"] == secret_entry["filePath"] and s["fieldPath"] == secret_entry["fieldPath"]:
                existing_idx = i
                break

        is_new = False
        if existing_idx is not None:
            secrets[existing_idx] = secret_entry
        else:
            secrets.append(secret_entry)
            is_new = True
        self.save_secrets(secret_path, secrets)
        return is_new

    def clear_secrets(self, secret_path):
        secret_file = Path(secret_path) / "secret.csv"
        if secret_file.exists():
            self.save_secrets(secret_path, [])

    def create_backup(self, secret_path, file_path, content):
        import hashlib
        backup_dir = Path(secret_path) / "backup"
        backup_dir.mkdir(parents=True, exist_ok=True)

        file_name = Path(file_path).name
        path_hash = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{path_hash}_{file_name}_{timestamp}.bak"

        with open(backup_file, "w", encoding="utf-8") as f:
            f.write(content)

        self._cleanup_old_backups(backup_dir, path_hash, file_name, keep_count=5)
        return backup_file

    def _cleanup_old_backups(self, backup_dir, path_hash, file_name, keep_count=5):
        pattern = f"{path_hash}_{file_name}_"
        backups = []
        for f in backup_dir.glob(f"{pattern}*.bak"):
            backups.append((f.stat().st_mtime, f))
        backups.sort(key=lambda x: x[0])
        if len(backups) > keep_count:
            for _, f in backups[:-keep_count]:
                f.unlink()

    def ensure_secret_path(self, secret_path):
        p = Path(secret_path)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            return True, "created"
        if not any(p.iterdir()):
            return True, "empty"
        return False, "not_empty"
