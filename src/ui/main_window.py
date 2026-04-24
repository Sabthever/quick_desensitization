# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDialog, QLineEdit,
    QLabel, QFileDialog, QAbstractItemView, QGroupBox,
    QFormLayout, QCheckBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from pathlib import Path
import subprocess
import json

from desensitize_engine import DesensitizeEngine
from storage import Storage


class ProjectDialog(QDialog):
    def __init__(self, storage, parent=None, project=None):
        super().__init__(parent)
        self.storage = storage
        self.project = project
        self.project_path = None
        self.secret_path = None
        self.init_ui()

    def init_ui(self):
        is_edit = self.project is not None
        self.setWindowTitle("编辑项目" if is_edit else "新增项目")
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        self.name_label = QLabel()
        self.name_label.setStyleSheet("color: #666; font-size: 12px;")
        name_row = QWidget()
        name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.addWidget(self.name_label)
        if not is_edit:
            name_layout.addWidget(QLabel("(从路径自动提取，不可编辑)"))
        form_layout.addRow("项目名称", name_row)

        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText("可选，用于界面显示")
        form_layout.addRow("别名", self.alias_input)

        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("必填，选择项目根目录")
        self.path_btn = QPushButton("浏览...")
        self.path_btn.clicked.connect(self.select_project_path)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.path_btn)
        if is_edit:
            self.path_input.setEnabled(False)
            self.path_btn.setEnabled(False)
        form_layout.addRow("项目路径 *", path_layout)

        secret_layout = QHBoxLayout()
        self.secret_input = QLineEdit()
        self.secret_input.setPlaceholderText("必填，敏感数据存放路径（必须在项目路径外）")
        self.secret_btn = QPushButton("浏览...")
        self.secret_btn.clicked.connect(self.select_secret_path)
        secret_layout.addWidget(self.secret_input)
        secret_layout.addWidget(self.secret_btn)
        form_layout.addRow("敏感数据路径 *", secret_layout)

        layout.addLayout(form_layout)

        self.tip_group = QGroupBox("提示")
        tip_layout = QVBoxLayout()
        tip_layout.addWidget(QLabel("• 敏感数据路径必须位于项目路径外"))
        tip_layout.addWidget(QLabel("• 如果路径不存在或为空，将自动创建"))
        tip_layout.addWidget(QLabel("• 如果路径已存在且非空，会提示确认是否继续"))
        self.tip_group.setLayout(tip_layout)
        layout.addWidget(self.tip_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        next_btn = QPushButton("下一步: 配置规则" if not is_edit else "保存")
        next_btn.setObjectName("primaryBtn")
        next_btn.clicked.connect(self.on_next if not is_edit else self.on_save)
        btn_layout.addWidget(next_btn)

        layout.addLayout(btn_layout)

        if is_edit:
            self.name_label.setText(self.project.get("name", ""))
            self.alias_input.setText(self.project.get("alias", ""))
            self.path_input.setText(self.project.get("projectPath", ""))
            self.secret_input.setText(self.project.get("secretPath", ""))
            self.project_path = self.project.get("projectPath", "")
            self.secret_path = self.project.get("secretPath", "")

    def select_project_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择项目路径")
        if path:
            existing_projects = self.storage.get_projects_using_project_path(path)
            if existing_projects:
                project_names = ", ".join([p.get("name", "未命名") for p in existing_projects])
                QMessageBox.warning(
                    self, "路径已被使用",
                    f"该路径已被以下项目使用：\n{project_names}\n\n请选择其他路径"
                )
                return
            self.path_input.setText(path)
            self.project_path = path
            project_name = Path(path).name
            self.name_label.setText(project_name)

    def select_secret_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择敏感数据路径")
        if path:
            existing_projects = self.storage.get_projects_using_secret_path(path)
            if existing_projects:
                project_names = ", ".join([p.get("name", "未命名") for p in existing_projects])
                QMessageBox.warning(
                    self, "路径已被使用",
                    f"该路径已被以下项目使用：\n{project_names}\n\n请选择其他路径"
                )
                return
            self.secret_input.setText(path)
            self.secret_path = path

    def validate(self):
        if self.project is None:
            if not self.project_path:
                QMessageBox.warning(self, "校验失败", "请选择项目路径")
                return False

            if not self.secret_path:
                QMessageBox.warning(self, "校验失败", "请选择敏感数据路径")
                return False

            if not self._is_path_outside_project():
                QMessageBox.warning(self, "校验失败", "敏感数据路径不能在项目路径下")
                return False

            check_result, status = self.storage.ensure_secret_path(self.secret_path)
            if not check_result and status == "not_empty":
                reply = QMessageBox.question(
                    self, "确认",
                    "该目录可能包含其他项目的数据，是否继续？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply != QMessageBox.Yes:
                    return False

        return True

    def _is_path_outside_project(self):
        if not self.project_path or not self.secret_path:
            return True
        project_p = Path(self.project_path).resolve()
        secret_p = Path(self.secret_path).resolve()
        try:
            secret_p.relative_to(project_p)
            return False
        except ValueError:
            return True

    def on_next(self):
        if not self.validate():
            return
        self.accept()

    def on_save(self):
        if not self.validate():
            return
        self.accept()

    def get_project_data(self):
        return {
            "name": self.name_label.text(),
            "alias": self.alias_input.text(),
            "projectPath": self.path_input.text(),
            "secretPath": self.secret_input.text()
        }


class RuleDialog(QDialog):
    FILE_TYPES = ["yml", "env", "json"]

    def __init__(self, parent=None, rule=None):
        super().__init__(parent)
        self.rule = rule
        self._selected_type = "yml"
        self.init_ui()

    def init_ui(self):
        is_edit = self.rule is not None
        self.setWindowTitle("编辑规则" if is_edit else "新增脱敏规则")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()

        type_layout = QHBoxLayout()
        self.type_buttons = {}
        for ft in self.FILE_TYPES:
            rb = QPushButton(ft)
            rb.setCheckable(True)
            rb.setObjectName("type_" + ft)
            rb.clicked.connect(lambda checked, t=ft: self.on_type_changed(t))
            type_layout.addWidget(rb)
            self.type_buttons[ft] = rb
        form_layout.addRow("文件类型 *", type_layout)

        self.file_match_input = QLineEdit()
        self.file_match_input.setPlaceholderText("例如: application*.yml")
        form_layout.addRow("文件匹配 *", self.file_match_input)

        self.field_path_input = QLineEdit()
        self.field_path_input.setPlaceholderText("根据文件类型填写对应格式")
        form_layout.addRow("字段路径 *", self.field_path_input)

        self.enabled_checkbox = QCheckBox("启用此规则")
        self.enabled_checkbox.setChecked(True)
        form_layout.addRow("状态", self.enabled_checkbox)

        layout.addLayout(form_layout)

        self.hint_group = QGroupBox("字段路径格式说明")
        hint_layout = QVBoxLayout()

        yml_hint = QLabel(
            "【yml/yaml】\n"
            "  • 完整路径: spring.datasource.password\n"
            "  • 通配符 * : spring.datasource.*.password (精确深度匹配一级)\n"
            "  • 通配符 ** : spring.datasource.**.password (匹配任意层级)"
        )
        yml_hint.setWordWrap(True)
        hint_layout.addWidget(yml_hint)

        env_hint = QLabel(
            "【env】\n"
            "  • 直接写 KEY: DB_PASSWORD\n"
            "  • 前缀匹配: DB_* (匹配所有以 DB_ 开头)\n"
            "  • 后缀匹配: *_PASSWORD"
        )
        env_hint.setWordWrap(True)
        hint_layout.addWidget(env_hint)

        json_hint = QLabel(
            "【json (JSONPath)】\n"
            "  • 完整路径: $.database.password\n"
            "  • 递归匹配: $..password (匹配任意位置的 password)\n"
            "  • 通配符: $.database.*.password"
        )
        json_hint.setWordWrap(True)
        hint_layout.addWidget(json_hint)

        self.hint_group.setLayout(hint_layout)
        layout.addWidget(self.hint_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("primaryBtn")
        ok_btn.clicked.connect(self.on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        if is_edit:
            self._selected_type = self.rule.get("fileType", "yml")
            self.file_match_input.setText(self.rule.get("fileMatch", ""))
            self.field_path_input.setText(self.rule.get("fieldPath", ""))
            self.enabled_checkbox.setChecked(self.rule.get("enabled", True))
            self.type_buttons[self._selected_type].setChecked(True)
        else:
            self.enabled_checkbox.setChecked(True)
            self.type_buttons["yml"].setChecked(True)

    def on_type_changed(self, file_type):
        self._selected_type = file_type
        for ft, btn in self.type_buttons.items():
            btn.setChecked(ft == file_type)

    def on_ok(self):
        file_match = self.file_match_input.text().strip()
        field_path = self.field_path_input.text().strip()

        if not file_match:
            QMessageBox.warning(self, "校验失败", "请填写文件匹配")
            return
        if not field_path:
            QMessageBox.warning(self, "校验失败", "请填写字段路径")
            return

        self.rule = {
            "fileType": self._selected_type,
            "fileMatch": file_match,
            "fieldPath": field_path,
            "enabled": self.enabled_checkbox.isChecked()
        }
        self.accept()

    def get_rule(self):
        return self.rule


class ProjectEditDialog(QDialog):
    def __init__(self, storage, project, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.project = project
        self.rules = []
        self.is_desensitized = False
        self.init_ui()
        self.load_rules()
        self.check_desensitized_status()

    def init_ui(self):
        self.setWindowTitle(f"编辑项目: {self.project.get('name', '')} - {self.project.get('alias', '')}")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        layout = QVBoxLayout(self)

        info_group = QGroupBox("基本信息")
        info_layout = QFormLayout()

        self.name_label = QLabel(self.project.get("name", ""))
        info_layout.addRow("项目名称", self.name_label)

        self.alias_input = QLineEdit(self.project.get("alias", ""))
        info_layout.addRow("别名", self.alias_input)

        path_layout = QHBoxLayout()
        self.path_label = QLabel()
        self.path_label.setText(self.project.get("projectPath", ""))
        self.path_label.setStyleSheet("QLabel { color: #666; }")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_path_btn = QPushButton("打开文件夹")
        open_path_btn.setFixedSize(open_path_btn.sizeHint().width() + 20, open_path_btn.sizeHint().height())
        open_path_btn.clicked.connect(lambda: self.open_in_explorer(self.project.get("projectPath", "")))
        change_path_btn = QPushButton("更改路径")
        change_path_btn.setFixedSize(change_path_btn.sizeHint().width() + 20, change_path_btn.sizeHint().height())
        change_path_btn.clicked.connect(lambda: self.change_project_path())
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(open_path_btn)
        path_layout.addWidget(change_path_btn)
        info_layout.addRow("项目路径", path_layout)

        secret_layout = QHBoxLayout()
        self.secret_label = QLabel()
        self.secret_label.setText(self.project.get("secretPath", ""))
        self.secret_label.setStyleSheet("QLabel { color: #666; }")
        self.secret_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_secret_btn = QPushButton("打开文件夹")
        open_secret_btn.setFixedSize(open_secret_btn.sizeHint().width() + 20, open_secret_btn.sizeHint().height())
        open_secret_btn.clicked.connect(lambda: self.open_in_explorer(self.project.get("secretPath", "")))
        change_secret_btn = QPushButton("更改路径")
        change_secret_btn.setFixedSize(change_secret_btn.sizeHint().width() + 20, change_secret_btn.sizeHint().height())
        change_secret_btn.clicked.connect(lambda: self.change_secret_path())
        secret_layout.addWidget(self.secret_label)
        secret_layout.addWidget(open_secret_btn)
        secret_layout.addWidget(change_secret_btn)
        info_layout.addRow("敏感数据路径", secret_layout)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        rule_group = QGroupBox("脱敏规则配置")
        rule_layout = QVBoxLayout()

        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        rule_layout.addWidget(self.warning_label)

        self.add_rule_btn = QPushButton("+ 新增规则")
        self.add_rule_btn.clicked.connect(self.add_rule)
        rule_layout.addWidget(self.add_rule_btn)

        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(6)
        self.rule_table.setHorizontalHeaderLabels(["选择？", "序号", "文件类型", "文件匹配", "字段路径", "状态"])
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setShowGrid(False)
        self.rule_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rule_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rule_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rule_table.setFocusPolicy(Qt.NoFocus)
        self.rule_table.setColumnWidth(0, 60)
        self.rule_table.setColumnWidth(1, 50)
        self.rule_table.setColumnWidth(5, 60)
        self.rule_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.rule_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.rule_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.rule_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.rule_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.rule_table.horizontalHeader().setToolTip("<b>多选操作：</b><br>Ctrl + 点击：选择多条不连续的规则<br>Shift + 点击：选择范围内多条规则<br>Ctrl + A：全选")
        self.rule_table.setStyleSheet("")
        self.rule_table.itemSelectionChanged.connect(self.on_selection_changed)
        rule_layout.addWidget(self.rule_table)

        btn_widget = QWidget()
        btn_layout = QHBoxLayout()
        self.open_config_btn = QPushButton("打开配置文件")
        self.open_config_btn.clicked.connect(self.open_config_file)
        btn_layout.addWidget(self.open_config_btn)

        self.edit_rule_btn = QPushButton("编辑选中规则")
        self.edit_rule_btn.clicked.connect(self.edit_selected_rule)
        btn_layout.addWidget(self.edit_rule_btn)

        self.delete_rule_btn = QPushButton("删除选中规则")
        self.delete_rule_btn.clicked.connect(self.delete_selected_rule)
        btn_layout.addWidget(self.delete_rule_btn)

        self.toggle_rule_btn = QPushButton("启用/禁用选中规则")
        self.toggle_rule_btn.clicked.connect(self.toggle_selected_rule)
        btn_layout.addWidget(self.toggle_rule_btn)

        rule_layout.addWidget(btn_widget)
        btn_widget.setLayout(btn_layout)

        rule_group.setLayout(rule_layout)
        layout.addWidget(rule_group)

        footer_btn_layout = QHBoxLayout()
        footer_btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        footer_btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save)
        footer_btn_layout.addWidget(save_btn)

        layout.addLayout(footer_btn_layout)

    def open_in_explorer(self, path):
        if path:
            import os
            os.startfile(path)

    def change_project_path(self):
        new_path = QFileDialog.getExistingDirectory(self, "选择新的项目路径")
        if not new_path:
            return
        reply = QMessageBox.question(
            self, "确认更改",
            "更改路径后，原路径下的文件不会被移动到新路径。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.project["projectPath"] = new_path
        self.storage.update_project(self.project["id"], self.project)
        self.path_label.setText(new_path)
        QMessageBox.information(self, "成功", "项目路径已更改")

    def change_secret_path(self):
        new_path = QFileDialog.getExistingDirectory(self, "选择新的敏感数据路径")
        if not new_path:
            return
        reply = QMessageBox.question(
            self, "确认更改",
            "更改路径后，原路径下的文件不会被移动到新路径。\n\n是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.project["secretPath"] = new_path
        self.storage.update_project(self.project["id"], self.project)
        self.secret_label.setText(new_path)
        QMessageBox.information(self, "成功", "敏感数据路径已更改")

    def load_rules(self):
        self.rules = self.storage.load_secret_config(self.project.get("secretPath", ""))
        self.selected_rule_indices = []
        self.update_rule_table()
        self.update_button_states()

    def on_selection_changed(self):
        if not hasattr(self, 'selected_rule_indices'):
            return
        try:
            selection_model = self.rule_table.selectionModel()
            if selection_model is None:
                return
            selected_rows = selection_model.selectedRows()
            self.selected_rule_indices = [row.row() for row in selected_rows if row.row() < len(self.rules)]
            self.update_rule_table()
            self.update_button_states()
        except Exception:
            pass

    def update_rule_table(self):
        if not hasattr(self, 'selected_rule_indices'):
            self.selected_rule_indices = []
        self.rule_table.itemSelectionChanged.disconnect()
        try:
            current_selection = self.selected_rule_indices
            self.rule_table.setRowCount(len(self.rules))
            for i, rule in enumerate(self.rules):
                is_selected = (i in current_selection)

                select_item = QTableWidgetItem("✓" if is_selected else "")
                select_item.setTextAlignment(Qt.AlignCenter)
                select_item.setFlags(select_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 0, select_item)

                seq_item = QTableWidgetItem(str(i + 1))
                seq_item.setTextAlignment(Qt.AlignCenter)
                seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 1, seq_item)

                type_item = QTableWidgetItem(rule.get("fileType", ""))
                type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 2, type_item)

                match_item = QTableWidgetItem(rule.get("fileMatch", ""))
                match_item.setFlags(match_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 3, match_item)

                field_item = QTableWidgetItem(rule.get("fieldPath", ""))
                field_item.setFlags(field_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 4, field_item)

                status = rule.get("enabled", True)
                status_item = QTableWidgetItem("启用" if status else "禁用")
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 5, status_item)
        finally:
            self.rule_table.itemSelectionChanged.connect(self.on_selection_changed)

    def update_button_states(self):
        if self.is_desensitized:
            self.add_rule_btn.setEnabled(False)
            self.open_config_btn.setEnabled(False)
            self.edit_rule_btn.setEnabled(False)
            self.delete_rule_btn.setEnabled(False)
            self.toggle_rule_btn.setEnabled(False)
            return

        selection_count = len(self.selected_rule_indices)
        self.add_rule_btn.setEnabled(True)
        self.open_config_btn.setEnabled(True)
        self.edit_rule_btn.setEnabled(selection_count == 1)
        self.delete_rule_btn.setEnabled(selection_count >= 1)
        self.toggle_rule_btn.setEnabled(selection_count >= 1)

    def add_rule(self):
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.Accepted:
            rule = dialog.get_rule()
            for r in self.rules:
                if r["fileType"] == rule["fileType"] and r["fileMatch"] == rule["fileMatch"] and r["fieldPath"] == rule["fieldPath"]:
                    QMessageBox.warning(self, "重复规则", "该规则已存在")
                    return
            self.rules.append(rule)
            self.update_rule_table()

    def edit_selected_rule(self):
        if len(self.selected_rule_indices) != 1:
            QMessageBox.warning(self, "提示", "请选择一条规则进行编辑")
            return

        index = self.selected_rule_indices[0]
        rule = self.rules[index]
        dialog = RuleDialog(self, rule)
        if dialog.exec() == QDialog.Accepted:
            new_rule = dialog.get_rule()
            self.rules[index] = new_rule
            self.update_rule_table()

    def delete_selected_rule(self):
        if not self.selected_rule_indices:
            QMessageBox.warning(self, "提示", "请先选择要删除的规则")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(self.selected_rule_indices)} 条规则吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.rule_table.itemSelectionChanged.disconnect()
        try:
            for index in sorted(self.selected_rule_indices, reverse=True):
                self.rules.pop(index)
            self.selected_rule_indices = []
            self.update_rule_table()
            self.update_button_states()
        finally:
            self.rule_table.itemSelectionChanged.connect(self.on_selection_changed)

    def toggle_selected_rule(self):
        if not self.selected_rule_indices:
            QMessageBox.warning(self, "提示", "请先选择要切换状态的规则")
            return

        for index in self.selected_rule_indices:
            self.rules[index]["enabled"] = not self.rules[index].get("enabled", True)
        self.update_rule_table()

    def open_config_file(self):
        config_file = Path(self.project.get("secretPath", "")) / "secret_config.csv"
        if not config_file.exists():
            self.storage.save_secret_config(self.project.get("secretPath", ""), [])
        subprocess.run(["notepad", str(config_file)])

    def save(self):
        reply = QMessageBox.question(
            self, "确认保存",
            "确定要保存规则吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.storage.save_secret_config(self.project.get("secretPath", ""), self.rules)
        alias = self.alias_input.text().strip()
        if alias != self.project.get("alias"):
            self.project["alias"] = alias
            self.storage.update_project(self.project["id"], {"alias": alias})
        self.accept()

    def check_desensitized_status(self):
        project_path = self.project.get("projectPath", "")
        self.is_desensitized = self._has_placeholder_in_project(project_path)
        
        if self.is_desensitized:
            self.warning_label.setText("⚠ 项目已脱敏，请先恢复后再修改脱敏规则！")
            self.warning_label.show()
            
            self.add_rule_btn.setEnabled(False)
            self.open_config_btn.setEnabled(False)
            self.edit_rule_btn.setEnabled(False)
            self.delete_rule_btn.setEnabled(False)
            self.toggle_rule_btn.setEnabled(False)

    def _has_placeholder_in_project(self, project_path):
        if not project_path or not Path(project_path).exists():
            return False

        rules = self.storage.load_secret_config(self.project.get("secretPath", ""))
        for rule in rules:
            file_match = rule.get("fileMatch", "")
            for file_path in Path(project_path).rglob("*"):
                if file_path.is_file() and __import__('fnmatch').fnmatch(file_path.name, file_match):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        if "${val_" in content:
                            return True
                    except:
                        continue
        return False


class MainWindow(QWidget):
    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        self.projects = []
        self.engine = DesensitizeEngine()
        self.init_ui()
        self.load_projects()

    def init_ui(self):
        self.setWindowTitle("脱敏小工具")
        self.setMinimumWidth(900)
        self.setMinimumHeight(500)

        layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        title = QLabel("脱敏小工具")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        header_layout.addWidget(title)
        header_layout.addStretch()

        add_btn = QPushButton("+ 新增项目")
        add_btn.setObjectName("primaryBtn")
        add_btn.clicked.connect(self.add_project)
        header_layout.addWidget(add_btn)

        move_up_btn = QPushButton("↑ 上移")
        move_up_btn.clicked.connect(self.move_up_project)
        header_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("↓ 下移")
        move_down_btn.clicked.connect(self.move_down_project)
        header_layout.addWidget(move_down_btn)

        layout.addLayout(header_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["序号", "项目名称", "别名", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(3, 400)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setStyleSheet("")
        self.table.itemClicked.connect(self.on_project_row_clicked)
        layout.addWidget(self.table)

        self.status_label = QLabel("状态栏: 共 0 个项目")
        layout.addWidget(self.status_label)

    def load_projects(self):
        self.projects = self.storage.get_projects()
        self.selected_project_index = None
        self.update_table()

    def on_project_row_clicked(self, item):
        row = item.row()
        self.selected_project_index = row
        self.update_table()

    def move_up_project(self):
        if self.selected_project_index is None or self.selected_project_index <= 0:
            return
        idx = self.selected_project_index
        self.projects[idx], self.projects[idx - 1] = self.projects[idx - 1], self.projects[idx]
        self.storage.save_projects(self.projects)
        self.selected_project_index = idx - 1
        self.update_table()

    def move_down_project(self):
        if self.selected_project_index is None or self.selected_project_index >= len(self.projects) - 1:
            return
        idx = self.selected_project_index
        self.projects[idx], self.projects[idx + 1] = self.projects[idx + 1], self.projects[idx]
        self.storage.save_projects(self.projects)
        self.selected_project_index = idx + 1
        self.update_table()

    def update_table(self):
        self.table.setRowCount(len(self.projects))
        for i, project in enumerate(self.projects):
            seq_item = QTableWidgetItem(str(i + 1))
            seq_item.setTextAlignment(Qt.AlignCenter)
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, seq_item)
            
            name_item = QTableWidgetItem(project.get("name", ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, name_item)
            
            alias_item = QTableWidgetItem(project.get("alias", ""))
            alias_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            alias_item.setFlags(alias_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, alias_item)

            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)

            desensitize_btn = QPushButton("脱敏")
            desensitize_btn.clicked.connect(lambda checked, p=project: self.desensitize_project(p))
            restore_btn = QPushButton("恢复")
            restore_btn.clicked.connect(lambda checked, p=project: self.restore_project(p))
            edit_btn = QPushButton("编辑")
            edit_btn.clicked.connect(lambda checked, p=project: self.edit_project(p))
            delete_btn = QPushButton("删除")
            delete_btn.clicked.connect(lambda checked, p=project: self.delete_project(p))

            for btn in [desensitize_btn, restore_btn, edit_btn, delete_btn]:
                btn.setMinimumSize(50, 25)
                btn.setStyleSheet("padding: 2px 6px; margin: 0 1px;")
                btn_layout.addWidget(btn)

            btn_widget.setLayout(btn_layout)
            self.table.setCellWidget(i, 3, btn_widget)

        self.status_label.setText(f"状态栏: 共 {len(self.projects)} 个项目")

    def add_project(self):
        dialog = ProjectDialog(self.storage, self)
        if dialog.exec() == QDialog.Accepted:
            project_data = dialog.get_project_data()
            project_data["name"] = Path(project_data["projectPath"]).name
            new_project = self.storage.add_project(project_data)

            secret_path = project_data["secretPath"]
            config_file = Path(secret_path) / "secret_config.csv"
            if not config_file.exists():
                rule = {"fileType": "yml", "fileMatch": "application*.yml", "fieldPath": "spring.datasource.password"}
                self.storage.save_secret_config(secret_path, [rule])

            edit_dialog = ProjectEditDialog(self.storage, new_project, self)
            edit_dialog.exec()

            self.load_projects()

    def edit_project(self, project):
        dialog = ProjectEditDialog(self.storage, project, self)
        dialog.exec()
        self.load_projects()

    def desensitize_project(self, project):
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        if not Path(project_path).exists():
            QMessageBox.warning(self, "错误", f"项目路径不存在: {project_path}")
            return

        rules = self.storage.load_secret_config(secret_path)
        if not rules:
            QMessageBox.warning(self, "提示", "请先配置脱敏规则")
            return

        enabled_rules = [r for r in rules if r.get("enabled", True)]
        if not enabled_rules:
            QMessageBox.warning(self, "提示", "没有启用的脱敏规则")
            return

        self.storage.ensure_secret_path(secret_path)

        matched_files = self.engine.scan_files(project_path, enabled_rules)

        if not matched_files:
            QMessageBox.information(self, "提示", "未找到匹配的文件")
            return

        saved_entries = set()

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
                            "timestamp": __import__('datetime').datetime.now().isoformat()
                        }
                        self.storage.append_secret(secret_path, secret_entry)
                        saved_entries.add((rel_path, change["fieldPath"]))

        if saved_entries:
            msg = f"脱敏完成！\n\n记录了 {len(saved_entries)} 个敏感字段\n\n敏感数据已保存至:\n{secret_path}/secret.csv"
            QMessageBox.information(self, "脱敏报告", msg)
        else:
            QMessageBox.information(self, "提示", "没有需要脱敏的字段")

        self.load_projects()

    def restore_project(self, project):
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        secrets = self.storage.load_secrets(secret_path)
        if not secrets:
            QMessageBox.information(self, "提示", "没有可恢复的数据")
            return

        rules = self.storage.load_secret_config(secret_path)
        matched_files = {}
        for rule in rules:
            file_type = rule["fileType"]
            if file_type not in matched_files:
                matched_files[file_type] = []
            for file_path in Path(project_path).rglob("*"):
                if file_path.is_file() and __import__('fnmatch').fnmatch(file_path.name, rule["fileMatch"]):
                    matched_files[file_type].append(file_path)

        restored_count = 0
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

        if restored_count > 0:
            QMessageBox.information(self, "恢复报告", f"已恢复 {restored_count} 个文件\n\n请尽快使用，调试完成后请重新执行脱敏！")
        else:
            QMessageBox.information(self, "提示", "配置文件未脱敏，无需恢复")

    def open_secret_path(self, project):
        secret_path = project.get("secretPath", "")
        if secret_path:
            subprocess.run(["explorer", secret_path])

    def delete_project(self, project):
        project_name = project.get("name", "")
        alias = project.get("alias", "")
        display_name = f"{project_name} - {alias}" if alias else project_name

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除项目「{display_name}」的配置吗？\n\n"
            f"此操作仅删除项目配置，不会删除：\n"
            f"• 项目文件\n"
            f"• 敏感数据文件\n"
            f"• 备份文件",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.storage.delete_project(project["id"])
            self.load_projects()
            QMessageBox.information(self, "删除成功", "项目配置已删除")
