# -*- coding: utf-8 -*-
import re
import yaml
import json
import fnmatch
import uuid
from pathlib import Path
from datetime import datetime
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


class DesensitizeEngine:
    PLACEHOLDER_PREFIX = "${val_"
    PLACEHOLDER_SUFFIX = "}"

    def __init__(self):
        self.operations = []

    def generate_placeholder(self):
        return f"{self.PLACEHOLDER_PREFIX}{uuid.uuid4().hex[:12]}{self.PLACEHOLDER_SUFFIX}"

    def is_placeholder(self, value):
        if not isinstance(value, str):
            return False
        if bool(re.match(r'\$\{val_[a-f0-9]+\}', value)):
            return True
        if bool(re.match(r'"\$\{val_[a-f0-9]+\}"$', value)):
            return True
        return False

    def scan_files(self, project_path, rules):
        matched_files = {}
        for rule in rules:
            file_type = rule["fileType"]
            file_match = rule["fileMatch"]
            field_path = rule["fieldPath"]

            if file_type not in matched_files:
                matched_files[file_type] = {}

            for file_path in Path(project_path).rglob("*"):
                if not file_path.is_file():
                    continue
                if not fnmatch.fnmatch(file_path.name, file_match):
                    continue
                rel_path = str(file_path.relative_to(project_path))
                if rel_path not in matched_files[file_type]:
                    matched_files[file_type][rel_path] = []
                matched_files[file_type][rel_path].append({
                    "filePath": str(file_path),
                    "fieldPath": field_path,
                    "rule": rule
                })
        return matched_files

    def process_yml(self, content, field_paths):
        try:
            yaml_handler = YAML()
            yaml_handler.preserve_quotes = True
            yaml_handler.indent(mapping=4, sequence=4, offset=2)
            yaml_handler.width = float("inf")
            data = yaml_handler.load(content)
        except:
            return content, []

        if data is None:
            return content, []

        changes = []

        def find_keys_with_line_info(obj, current_path, target_key, results):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    full_path = f"{current_path}.{key}" if current_path else key
                    if key == target_key:
                        results.append((full_path, value))
                    find_keys_with_line_info(value, full_path, target_key, results)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_keys_with_line_info(item, current_path, target_key, results)

        def replace_at_line(content, line_num, old_value, placeholder):
            lines = content.split('\n')
            line = lines[line_num]

            indent_match = re.match(r'^(\s*)', line)
            indent = indent_match.group(1) if indent_match else ""

            key_match = re.match(r'^\s*([^:#\s]+)\s*:', line)
            if not key_match:
                return content
            key_name = key_match.group(1)

            new_line = f"{indent}{key_name}: {placeholder}"
            lines[line_num] = new_line
            return '\n'.join(lines)

        for fp in field_paths:
            path_parts = fp.split('.')
            results = []
            last_key = path_parts[-1]
            find_keys_with_line_info(data, "", last_key, results)

            for full_path, value in results:
                if self.is_placeholder(str(value)):
                    continue
                if value is None or not isinstance(value, str):
                    continue

                line_num = None
                value_str = str(value)

                for ln, line in enumerate(content.split('\n')):
                    if re.match(r'\s*$', line) or line.strip().startswith('#'):
                        continue
                    key_m = re.match(r'^\s*([^:#\s]+)\s*:\s*(.*)$', line)
                    if key_m and key_m.group(2) == value_str:
                        line_num = ln
                        break

                if line_num is not None:
                    placeholder = self.generate_placeholder()
                    content = replace_at_line(content, line_num, value_str, placeholder)
                    changes.append({
                        "fieldPath": full_path,
                        "originalValue": value,
                        "placeholder": placeholder
                    })

        return content, changes

    def _yml_path_matches(self, key_path, field_path):
        keys = key_path.split('.')
        fields = field_path.split('.')

        def match(k_list, f_list, k_idx, f_idx):
            if f_idx >= len(f_list):
                return k_idx >= len(k_list)
            if k_idx >= len(k_list):
                return f_idx >= len(f_list)

            f_current = f_list[f_idx]
            if f_current == '**':
                if f_idx == len(f_list) - 1:
                    return True
                for i in range(k_idx, len(k_list)):
                    if match(k_list, f_list, i, f_idx + 1):
                        return True
                return False
            elif f_current == '*':
                return match(k_list, f_list, k_idx + 1, f_idx + 1)
            else:
                if k_list[k_idx] != f_current:
                    return False
                return match(k_list, f_list, k_idx + 1, f_idx + 1)

        return match(keys, fields, 0, 0)

    def process_env(self, content, field_paths):
        lines = content.split('\n')
        result_lines = []
        changes = []

        field_set = set()
        for fp in field_paths:
            if fp == '*':
                field_set.add(('*', 'prefix', ''))
            elif fp.endswith('*'):
                prefix = fp[:-1]
                field_set.add(('*', 'prefix', prefix))
            elif fp.startswith('*'):
                suffix = fp[1:]
                field_set.add(('*', 'suffix', suffix))
            else:
                field_set.add(('exact', '', fp))

        def parse_env_line(rest):
            comment = ""
            value_part = rest
            in_quote = False
            quote_char = None
            for i, ch in enumerate(rest):
                if ch in ('"', "'") and (i == 0 or rest[i-1] != '\\'):
                    if not in_quote:
                        in_quote = True
                        quote_char = ch
                    elif ch == quote_char:
                        in_quote = False
                        quote_char = None
                elif ch == '#' and not in_quote:
                    comment = rest[i:]
                    value_part = rest[:i]
                    break
            return value_part, comment

        for line in lines:
            if '=' not in line or line.strip().startswith('#'):
                result_lines.append(line)
                continue

            eq_idx = line.index('=')
            key_part = line[:eq_idx]
            rest = line[eq_idx+1:]

            key = key_part.strip()

            value_part, comment = parse_env_line(rest)

            leading_space = ""
            trailing_space = ""
            stripped_value = value_part.strip()
            if value_part:
                for i, ch in enumerate(value_part):
                    if ch not in ' \t':
                        leading_space = value_part[:i]
                        break
                for i in range(len(value_part)-1, -1, -1):
                    if value_part[i] not in ' \t':
                        trailing_space = value_part[i+1:]
                        break

            if self.is_placeholder(stripped_value):
                result_lines.append(line)
                continue

            matched = False
            matched_fp = None
            for match_type, modifier, pattern in field_set:
                if match_type == 'exact' and key == pattern:
                    matched = True
                    matched_fp = pattern
                    break
                elif match_type == 'prefix' and key.startswith(pattern):
                    matched = True
                    matched_fp = pattern + '*'
                    break
                elif match_type == 'suffix' and key.endswith(pattern):
                    matched = True
                    matched_fp = '*' + pattern
                    break
                elif match_type == 'prefix' and pattern == '':
                    matched = True
                    matched_fp = '*'
                    break

            if matched:
                placeholder = self.generate_placeholder()
                changes.append({
                    "fieldPath": matched_fp,
                    "originalValue": stripped_value,
                    "placeholder": placeholder
                })
                line = f"{key_part}={leading_space}{placeholder}{trailing_space}{comment}"

            result_lines.append(line)

        return '\n'.join(result_lines), changes

    def process_json(self, content, field_paths):
        def remove_json_comments(text):
            lines = text.split('\n')
            result_lines = []
            for line in lines:
                in_string = False
                string_char = None
                comment_start = -1
                i = 0
                while i < len(line):
                    ch = line[i]
                    if ch in ('"', "'") and (i == 0 or line[i-1] != '\\'):
                        if not in_string:
                            in_string = True
                            string_char = ch
                        elif ch == string_char:
                            in_string = False
                            string_char = None
                    elif ch == '#' and not in_string:
                        comment_start = i
                        break
                    i += 1
                if comment_start >= 0:
                    result_lines.append(line[:comment_start].rstrip())
                else:
                    result_lines.append(line)
            return '\n'.join(result_lines)

        clean_content = remove_json_comments(content)
        
        try:
            data = json.loads(clean_content)
        except json.JSONDecodeError:
            return content, []

        changes = []

        for fp in field_paths:
            matched_values = self._jsonpath_match(data, fp)
            for path, value in matched_values:
                if self.is_placeholder(value):
                    continue

                value_str = str(value)
                pattern = f'"{value_str}"'
                if pattern in content:
                    placeholder = self.generate_placeholder()
                    actual_path = "$." + ".".join(str(p) for p in path)
                    changes.append({
                        "fieldPath": actual_path,
                        "originalValue": value,
                        "placeholder": placeholder
                    })
                    content = content.replace(pattern, placeholder, 1)

        return content, changes

    def _jsonpath_match(self, data, path):
        results = []

        if path.startswith('$..'):
            field_name = path[3:]
            results.extend(self._jsonpath_recurse(data, field_name))
        elif path.startswith('$.'):
            clean_path = path[2:]
            if clean_path:
                results.extend(self._jsonpath_exact(data, clean_path.split('.'), []))
        elif path.startswith('$'):
            clean_path = path[1:]
            if clean_path:
                results.extend(self._jsonpath_exact(data, clean_path.split('.'), []))
        elif '**' in path:
            parts = path.split('.')
            results.extend(self._jsonpath_wildcard(data, parts, 0, []))
        else:
            results.extend(self._jsonpath_exact(data, path.split('.'), []))

        return results

    def _jsonpath_recurse(self, obj, field_name, current_path=None):
        if current_path is None:
            current_path = []
        results = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                path = current_path + [key]
                if key == field_name:
                    results.append((path, value))
                results.extend(self._jsonpath_recurse(value, field_name, path))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                path = current_path + [i]
                results.extend(self._jsonpath_recurse(item, field_name, path))
        return results

    def _jsonpath_exact(self, obj, parts, current_path):
        results = []
        if not parts:
            if isinstance(obj, (dict, list)):
                return results
            results.append((current_path, obj))
            return results

        current = parts[0]
        rest = parts[1:]

        if current == '*':
            if isinstance(obj, dict):
                for key in obj:
                    results.extend(self._jsonpath_exact(obj[key], rest, current_path + [key]))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    results.extend(self._jsonpath_exact(item, rest, current_path + [i]))
        elif isinstance(obj, dict) and current in obj:
            results.extend(self._jsonpath_exact(obj[current], rest, current_path + [current]))
        elif isinstance(obj, list):
            try:
                idx = int(current)
                if 0 <= idx < len(obj):
                    results.extend(self._jsonpath_exact(obj[idx], rest, current_path + [idx]))
            except ValueError:
                pass

        return results

    def _jsonpath_wildcard(self, obj, parts, idx, current_path):
        results = []
        if idx >= len(parts):
            if not isinstance(obj, (dict, list)):
                results.append((current_path, obj))
            return results

        current = parts[idx]

        if current == '**':
            results.extend(self._jsonpath_wildcard(obj, parts, idx + 1, current_path))
            if isinstance(obj, dict):
                for key in obj:
                    results.extend(self._jsonpath_wildcard(obj[key], parts, idx, current_path + [key]))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    results.extend(self._jsonpath_wildcard(item, parts, idx, current_path + [i]))
        elif current == '*':
            if isinstance(obj, dict):
                for key in obj:
                    results.extend(self._jsonpath_wildcard(obj[key], parts, idx + 1, current_path + [key]))
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    results.extend(self._jsonpath_wildcard(item, parts, idx + 1, current_path + [i]))
        elif isinstance(obj, dict) and current in obj:
            results.extend(self._jsonpath_wildcard(obj[current], parts, idx + 1, current_path + [current]))
        elif isinstance(obj, list):
            try:
                idx_int = int(current)
                if 0 <= idx_int < len(obj):
                    results.extend(self._jsonpath_wildcard(obj[idx_int], parts, idx + 1, current_path + [idx_int]))
            except ValueError:
                pass

        return results

    def _jsonpath_set(self, data, path, value):
        current = data
        for i, key in enumerate(path[:-1]):
            if isinstance(current, list):
                current = current[key]
            else:
                current = current[key]
        final_key = path[-1]
        if isinstance(current, list):
            current[final_key] = value
        else:
            current[final_key] = value

    def restore_yml(self, content, secrets):
        placeholder_map = {}
        for s in secrets:
            placeholder_map[s["placeholder"]] = s["originalValue"]

        for placeholder, original_value in placeholder_map.items():
            for line_num, line in enumerate(content.split('\n')):
                if re.match(r'\s*$', line) or line.strip().startswith('#'):
                    continue
                key_match = re.match(r'^(\s*)([^:#\s]+)\s*:\s*(.*)$', line)
                if not key_match:
                    continue
                current_value = key_match.group(3)
                if current_value == placeholder:
                    indent = key_match.group(1)
                    key_name = key_match.group(2)
                    new_line = f"{indent}{key_name}: {original_value}"
                    lines = content.split('\n')
                    lines[line_num] = new_line
                    content = '\n'.join(lines)
                    break

        return content

    def restore_env(self, content, secrets):
        placeholder_map = {}
        for s in secrets:
            placeholder_map[s["placeholder"]] = s["originalValue"]

        lines = content.split('\n')
        result_lines = []

        def parse_env_line(rest):
            comment = ""
            value_part = rest
            in_quote = False
            quote_char = None
            for i, ch in enumerate(rest):
                if ch in ('"', "'") and (i == 0 or rest[i-1] != '\\'):
                    if not in_quote:
                        in_quote = True
                        quote_char = ch
                    elif ch == quote_char:
                        in_quote = False
                        quote_char = None
                elif ch == '#' and not in_quote:
                    comment = rest[i:]
                    value_part = rest[:i]
                    break
            return value_part, comment

        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                eq_idx = line.index('=')
                key_part = line[:eq_idx]
                rest = line[eq_idx+1:]

                value_part, comment = parse_env_line(rest)

                leading_space = ""
                trailing_space = ""
                stripped_value = value_part.strip()
                if value_part:
                    for i, ch in enumerate(value_part):
                        if ch not in ' \t':
                            leading_space = value_part[:i]
                            break
                    for i in range(len(value_part)-1, -1, -1):
                        if value_part[i] not in ' \t':
                            trailing_space = value_part[i+1:]
                            break

                if stripped_value in placeholder_map:
                    line = f"{key_part}={leading_space}{placeholder_map[stripped_value]}{trailing_space}{comment}"

            result_lines.append(line)

        return '\n'.join(result_lines)

    def restore_json(self, content, secrets):
        for s in secrets:
            placeholder = s["placeholder"]
            original = s["originalValue"]
            if isinstance(original, str):
                content = content.replace(placeholder, f'"{original}"')
            else:
                content = content.replace(placeholder, json.dumps(original))
        return content
