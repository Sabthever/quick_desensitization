# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QDialog, QLineEdit,
    QLabel, QFileDialog, QAbstractItemView, QGroupBox,
    QFormLayout, QCheckBox, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from pathlib import Path
from datetime import datetime
import sys
import subprocess
import json

from desensitize_engine import DesensitizeEngine
from storage import Storage
from i18n import tr, get_lang, toggle_lang


class ProjectDialog(QDialog):
    def __init__(self, storage, parent=None, project=None):
        super().__init__(parent)
        self.storage = storage
        self.project = project
        self.project_path = None
        self.init_ui()

    def init_ui(self):
        is_edit = self.project is not None
        self.setWindowTitle(tr("dlg_edit_project") if is_edit else tr("dlg_add_project"))
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
            name_layout.addWidget(QLabel(tr("lbl_from_path")))
        form_layout.addRow(tr("lbl_project_name"), name_row)

        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText(tr("ph_alias"))
        form_layout.addRow(tr("lbl_alias"), self.alias_input)

        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText(tr("ph_path"))
        self.path_btn = QPushButton(tr("btn_browse"))
        self.path_btn.clicked.connect(self.select_project_path)
        path_layout.addWidget(self.path_input)
        path_layout.addWidget(self.path_btn)
        if is_edit:
            self.path_input.setEnabled(False)
            self.path_btn.setEnabled(False)
        form_layout.addRow(tr("lbl_project_path"), path_layout)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        next_btn = QPushButton(tr("btn_save") if is_edit else tr("btn_next"))
        next_btn.setObjectName("primaryBtn")
        next_btn.clicked.connect(self.on_save if is_edit else self.on_next)
        btn_layout.addWidget(next_btn)

        layout.addLayout(btn_layout)

        if is_edit:
            self.name_label.setText(self.project.get("name", ""))
            self.alias_input.setText(self.project.get("alias", ""))
            self.path_input.setText(self.project.get("projectPath", ""))
            self.project_path = self.project.get("projectPath", "")

    def select_project_path(self):
        path = QFileDialog.getExistingDirectory(self, tr("msg_select_project_path"))
        if path:
            existing_projects = self.storage.get_projects_using_project_path(path)
            if existing_projects:
                project_names = ", ".join([p.get("name", "未命名") for p in existing_projects])
                QMessageBox.warning(
                    self, tr("msg_path_used_title"),
                    tr("msg_path_used", names=project_names)
                )
                return
            self.path_input.setText(path)
            self.project_path = path
            project_name = Path(path).name
            self.name_label.setText(project_name)

    def validate(self):
        alias = self.alias_input.text().strip()
        if alias and self.storage.is_alias_exists(alias):
            QMessageBox.warning(self, tr("msg_validation_failed"), tr("msg_alias_exists", alias=alias))
            return False

        if self.project is None:
            if not self.project_path:
                QMessageBox.warning(self, tr("msg_validation_failed"), tr("msg_select_path"))
                return False

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
        alias = self.alias_input.text().strip() or self.name_label.text()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        secret_path = str(self.storage.config_dir / f"{alias}_{timestamp}")
        return {
            "name": self.name_label.text(),
            "alias": self.alias_input.text(),
            "projectPath": self.path_input.text(),
            "secretPath": secret_path
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
        self.setWindowTitle(tr("dlg_edit_rule") if is_edit else tr("dlg_add_rule"))
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
        form_layout.addRow(tr("lbl_file_type"), type_layout)

        self.file_match_input = QLineEdit()
        self.file_match_input.setPlaceholderText(tr("ph_file_match"))
        form_layout.addRow(tr("lbl_file_match"), self.file_match_input)

        self.field_path_input = QLineEdit()
        self.field_path_input.setPlaceholderText(tr("ph_field_path"))
        form_layout.addRow(tr("lbl_field_path"), self.field_path_input)

        self.enabled_checkbox = QCheckBox(tr("chk_enable_rule"))
        self.enabled_checkbox.setChecked(True)
        form_layout.addRow(tr("lbl_status"), self.enabled_checkbox)

        layout.addLayout(form_layout)

        self.hint_group = QGroupBox(tr("grp_format_hint"))
        hint_layout = QVBoxLayout()

        file_match_hint = QLabel(tr("hint_file_match"))
        file_match_hint.setWordWrap(True)
        hint_layout.addWidget(file_match_hint)

        yml_hint = QLabel(tr("hint_yml"))
        yml_hint.setWordWrap(True)
        hint_layout.addWidget(yml_hint)

        env_hint = QLabel(tr("hint_env"))
        env_hint.setWordWrap(True)
        hint_layout.addWidget(env_hint)

        json_hint = QLabel(tr("hint_json"))
        json_hint.setWordWrap(True)
        hint_layout.addWidget(json_hint)

        self.hint_group.setLayout(hint_layout)
        layout.addWidget(self.hint_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton(tr("btn_ok"))
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
            QMessageBox.warning(self, tr("msg_validation_failed"), tr("msg_fill_file_match"))
            return
        if not field_path:
            QMessageBox.warning(self, tr("msg_validation_failed"), tr("msg_fill_field_path"))
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
        self.config_file_opened = False
        self.init_ui()
        self.load_rules()
        self.check_desensitized_status()

    def init_ui(self):
        self.setWindowTitle(tr("dlg_edit_project_title", 
            name=self.project.get('name', ''), 
            alias=self.project.get('alias', '')))
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        layout = QVBoxLayout(self)

        info_group = QGroupBox(tr("grp_basic_info"))
        info_layout = QFormLayout()

        self.name_label = QLabel(self.project.get("name", ""))
        info_layout.addRow(tr("lbl_project_name"), self.name_label)

        self.alias_input = QLineEdit(self.project.get("alias", ""))
        info_layout.addRow(tr("lbl_alias"), self.alias_input)

        path_layout = QHBoxLayout()
        self.path_label = QLabel()
        self.path_label.setText(self.project.get("projectPath", ""))
        self.path_label.setStyleSheet("QLabel { color: #666; }")
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_path_btn = QPushButton(tr("btn_open_folder"))
        open_path_btn.setFixedSize(open_path_btn.sizeHint().width() + 20, open_path_btn.sizeHint().height())
        open_path_btn.clicked.connect(lambda: self.open_in_explorer(self.project.get("projectPath", "")))
        change_path_btn = QPushButton(tr("btn_change_path"))
        change_path_btn.setFixedSize(change_path_btn.sizeHint().width() + 20, change_path_btn.sizeHint().height())
        change_path_btn.clicked.connect(lambda: self.change_project_path())
        path_layout.addWidget(self.path_label)
        path_layout.addWidget(open_path_btn)
        path_layout.addWidget(change_path_btn)
        info_layout.addRow(tr("lbl_project_path_val"), path_layout)

        secret_layout = QHBoxLayout()
        self.secret_label = QLabel()
        self.secret_label.setText(self.project.get("secretPath", ""))
        self.secret_label.setStyleSheet("QLabel { color: #666; }")
        self.secret_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        open_secret_btn = QPushButton(tr("btn_open_folder"))
        open_secret_btn.setFixedSize(open_secret_btn.sizeHint().width() + 20, open_secret_btn.sizeHint().height())
        open_secret_btn.clicked.connect(lambda: self.open_in_explorer(self.project.get("secretPath", "")))
        change_secret_btn = QPushButton(tr("btn_change_path"))
        change_secret_btn.setFixedSize(change_secret_btn.sizeHint().width() + 20, change_secret_btn.sizeHint().height())
        change_secret_btn.clicked.connect(lambda: self.change_secret_path())
        secret_layout.addWidget(self.secret_label)
        secret_layout.addWidget(open_secret_btn)
        secret_layout.addWidget(change_secret_btn)
        info_layout.addRow(tr("lbl_secret_path_val"), secret_layout)

        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        rule_group = QGroupBox(tr("grp_rules_config"))
        rule_layout = QVBoxLayout()

        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: red; font-weight: bold; padding: 5px;")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        rule_layout.addWidget(self.warning_label)

        rule_btn_widget = QWidget()
        rule_btn_layout = QHBoxLayout()
        rule_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.add_rule_btn = QPushButton(tr("btn_add_rule"))
        self.add_rule_btn.clicked.connect(self.add_rule)
        rule_btn_layout.addWidget(self.add_rule_btn)
        self.import_rule_btn = QPushButton(tr("btn_import_rules"))
        self.import_rule_btn.clicked.connect(self.import_rules)
        rule_btn_layout.addWidget(self.import_rule_btn)
        self.export_rule_btn = QPushButton(tr("btn_export_selected"))
        self.export_rule_btn.clicked.connect(self.export_selected_rules)
        rule_btn_layout.addWidget(self.export_rule_btn)
        rule_btn_widget.setLayout(rule_btn_layout)
        rule_layout.addWidget(rule_btn_widget)

        self.rule_table = QTableWidget()
        self.rule_table.setColumnCount(6)
        self.rule_table.setHorizontalHeaderLabels([
            tr("tbl_col_select"), tr("tbl_col_seq"), tr("tbl_col_type"),
            tr("tbl_col_match"), tr("tbl_col_field"), tr("tbl_col_status")
        ])
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
        self.rule_table.horizontalHeader().setToolTip(tr("tooltip_multiselect"))
        self.rule_table.setStyleSheet("")
        self.rule_table.itemSelectionChanged.connect(self.on_selection_changed)
        rule_layout.addWidget(self.rule_table)

        btn_widget = QWidget()
        btn_layout = QHBoxLayout()
        self.open_config_btn = QPushButton(tr("btn_open_config"))
        self.open_config_btn.clicked.connect(self.open_config_file)
        btn_layout.addWidget(self.open_config_btn)

        self.edit_rule_btn = QPushButton(tr("btn_edit_selected"))
        self.edit_rule_btn.clicked.connect(self.edit_selected_rule)
        btn_layout.addWidget(self.edit_rule_btn)

        self.delete_rule_btn = QPushButton(tr("btn_delete_selected"))
        self.delete_rule_btn.clicked.connect(self.delete_selected_rule)
        btn_layout.addWidget(self.delete_rule_btn)

        self.toggle_rule_btn = QPushButton(tr("btn_toggle_selected"))
        self.toggle_rule_btn.clicked.connect(self.toggle_selected_rule)
        btn_layout.addWidget(self.toggle_rule_btn)

        rule_layout.addWidget(btn_widget)
        btn_widget.setLayout(btn_layout)

        rule_group.setLayout(rule_layout)
        layout.addWidget(rule_group)

        footer_btn_layout = QHBoxLayout()
        footer_btn_layout.addStretch()

        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        footer_btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton(tr("btn_save"))
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save)
        footer_btn_layout.addWidget(save_btn)

        layout.addLayout(footer_btn_layout)

    def open_in_explorer(self, path):
        if path:
            import os
            os.startfile(path)

    def change_project_path(self):
        new_path = QFileDialog.getExistingDirectory(self, tr("msg_select_new_path"))
        if not new_path:
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm_change_path_title"),
            tr("msg_confirm_change_path"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.project["projectPath"] = new_path
        self.storage.update_project(self.project["id"], self.project)
        self.path_label.setText(new_path)
        QMessageBox.information(self, tr("msg_success"), tr("msg_path_changed"))

    def change_secret_path(self):
        new_path = QFileDialog.getExistingDirectory(self, tr("msg_select_new_secret_path"))
        if not new_path:
            return
        reply = QMessageBox.question(
            self, tr("msg_confirm_change_path_title"),
            tr("msg_confirm_change_path"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.project["secretPath"] = new_path
        self.storage.update_project(self.project["id"], self.project)
        self.secret_label.setText(new_path)
        QMessageBox.information(self, tr("msg_success"), tr("msg_secret_path_changed"))

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
                status_item = QTableWidgetItem(tr("tbl_status_enabled") if status else tr("tbl_status_disabled"))
                status_item.setTextAlignment(Qt.AlignCenter)
                status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
                self.rule_table.setItem(i, 5, status_item)
        finally:
            self.rule_table.itemSelectionChanged.connect(self.on_selection_changed)

    def update_button_states(self):
        selection_count = len(self.selected_rule_indices)

        if self.is_desensitized:
            self.add_rule_btn.setEnabled(False)
            self.import_rule_btn.setEnabled(False)
            self.export_rule_btn.setEnabled(False)
            self.open_config_btn.setEnabled(False)
            self.edit_rule_btn.setEnabled(False)
            self.delete_rule_btn.setEnabled(False)
            self.toggle_rule_btn.setEnabled(False)
            return

        self.add_rule_btn.setEnabled(True)
        self.import_rule_btn.setEnabled(True)
        self.export_rule_btn.setEnabled(selection_count >= 1)
        self.open_config_btn.setEnabled(True)
        self.edit_rule_btn.setEnabled(selection_count == 1)
        self.delete_rule_btn.setEnabled(selection_count >= 1)
        self.toggle_rule_btn.setEnabled(selection_count >= 1)

    def check_config_file_opened(self):
        if self.config_file_opened:
            reply = QMessageBox.question(
                self, tr("msg_confirm_file_opened_title"),
                tr("msg_confirm_file_opened"),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.config_file_opened = False
                return False
            return True
        return False

    def add_rule(self):
        if self.check_config_file_opened():
            return
        dialog = RuleDialog(self)
        if dialog.exec() == QDialog.Accepted:
            rule = dialog.get_rule()
            for r in self.rules:
                if r["fileType"] == rule["fileType"] and r["fileMatch"] == rule["fileMatch"] and r["fieldPath"] == rule["fieldPath"]:
                    QMessageBox.warning(self, tr("msg_info"), tr("msg_duplicate_rule"))
                    return
            self.rules.append(rule)
            self.update_rule_table()

    def export_selected_rules(self):
        if self.check_config_file_opened():
            return
        if not self.selected_rule_indices:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_select_rule_export"))
            return

        count = len(self.selected_rule_indices)
        reply = QMessageBox.question(
            self, tr("msg_confirm_export_title"),
            tr("msg_confirm_export", count=count),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("btn_export_selected"), "", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        import csv
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["fileType", "fileMatch", "fieldPath", "enabled"])
                for index in self.selected_rule_indices:
                    rule = self.rules[index]
                    writer.writerow([
                        rule.get("fileType", ""),
                        rule.get("fileMatch", ""),
                        rule.get("fieldPath", ""),
                        rule.get("enabled", True)
                    ])
            QMessageBox.information(self, tr("msg_success"), tr("msg_export_success", count=count, path=file_path))
        except Exception as e:
            QMessageBox.warning(self, tr("msg_error"), tr("msg_export_failed", error=str(e)))

    def import_rules(self):
        if self.check_config_file_opened():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("btn_import_rules"), "", "CSV Files (*.csv)"
        )
        if not file_path:
            return

        import csv
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                if header != ["fileType", "fileMatch", "fieldPath", "enabled"]:
                    QMessageBox.warning(self, tr("msg_error"), tr("msg_import_wrong_format"))
                    return

                imported_count = 0
                skipped_count = 0
                for row in reader:
                    if len(row) < 3:
                        continue
                    rule = {
                        "fileType": row[0],
                        "fileMatch": row[1],
                        "fieldPath": row[2],
                        "enabled": row[3].lower() == "true" if len(row) > 3 else True
                    }
                    is_duplicate = False
                    for r in self.rules:
                        if r["fileType"] == rule["fileType"] and r["fileMatch"] == rule["fileMatch"] and r["fieldPath"] == rule["fieldPath"]:
                            is_duplicate = True
                            break
                    if is_duplicate:
                        skipped_count += 1
                    else:
                        self.rules.append(rule)
                        imported_count += 1

                self.update_rule_table()
                msg = tr("msg_import_success", imported=imported_count, skipped=skipped_count)
                QMessageBox.information(self, tr("msg_success"), msg)
        except Exception as e:
            QMessageBox.warning(self, tr("msg_error"), tr("msg_import_failed", error=str(e)))

    def edit_selected_rule(self):
        if self.check_config_file_opened():
            return
        if len(self.selected_rule_indices) != 1:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_select_one_rule"))
            return

        index = self.selected_rule_indices[0]
        rule = self.rules[index]
        dialog = RuleDialog(self, rule)
        if dialog.exec() == QDialog.Accepted:
            new_rule = dialog.get_rule()
            self.rules[index] = new_rule
            self.update_rule_table()

    def delete_selected_rule(self):
        if self.check_config_file_opened():
            return
        if not self.selected_rule_indices:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_select_to_delete"))
            return

        reply = QMessageBox.question(
            self, tr("msg_confirm_delete_title"),
            tr("msg_confirm_delete_rules", count=len(self.selected_rule_indices)),
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
        if self.check_config_file_opened():
            return
        if not self.selected_rule_indices:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_select_to_toggle"))
            return

        for index in self.selected_rule_indices:
            self.rules[index]["enabled"] = not self.rules[index].get("enabled", True)
        self.update_rule_table()

    def open_config_file(self):
        config_file = Path(self.project.get("secretPath", "")) / "secret_config.csv"
        if not config_file.exists():
            self.storage.save_secret_config(self.project.get("secretPath", ""), [])
        self.config_file_opened = True
        subprocess.Popen(["notepad", str(config_file)])

    def save(self):
        reply = QMessageBox.question(
            self, tr("msg_confirm_save_title"),
            tr("msg_confirm_save"),
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        config_file = Path(self.project.get("secretPath", "")) / "secret_config.csv"
        if self.storage.is_file_locked(config_file):
            QMessageBox.warning(self, tr("msg_error"), tr("msg_file_locked_config"))
            return

        self.storage.save_secret_config(self.project.get("secretPath", ""), self.rules)
        alias = self.alias_input.text().strip()
        if alias:
            if alias != self.project.get("alias") and self.storage.is_alias_exists(alias, exclude_project_id=self.project.get("id")):
                QMessageBox.warning(self, tr("msg_validation_failed"), tr("msg_alias_exists", alias=alias))
                return
            self.project["alias"] = alias
            self.storage.update_project(self.project["id"], {"alias": alias})
        else:
            if self.project.get("alias"):
                self.project["alias"] = ""
                self.storage.update_project(self.project["id"], {"alias": ""})
        self.accept()

    def check_desensitized_status(self):
        project_path = self.project.get("projectPath", "")
        self.is_desensitized = self._has_placeholder_in_project(project_path)
        
        if self.is_desensitized:
            self.warning_label.setText(tr("msg_warning_desensitized"))
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
        self.setWindowTitle(tr("window_title"))
        self.setMinimumWidth(900)
        self.setMinimumHeight(500)

        self._main_layout = QVBoxLayout(self)

        header_layout = QHBoxLayout()
        self._title_label = QLabel(tr("title_project_list"))
        self._title_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._add_btn = QPushButton(tr("btn_add_project"))
        self._add_btn.setObjectName("primaryBtn")
        self._add_btn.clicked.connect(self.add_project)
        header_layout.addWidget(self._add_btn)

        self._mcp_btn = QPushButton(tr("btn_mcp_config"))
        self._mcp_btn.clicked.connect(self.copy_mcp_config)
        header_layout.addWidget(self._mcp_btn)

        self._move_up_btn = QPushButton(tr("btn_move_up"))
        self._move_up_btn.clicked.connect(self.move_up_project)
        header_layout.addWidget(self._move_up_btn)

        self._move_down_btn = QPushButton(tr("btn_move_down"))
        self._move_down_btn.clicked.connect(self.move_down_project)
        header_layout.addWidget(self._move_down_btn)

        self._main_layout.addLayout(header_layout)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels([
            tr("table_col_seq"), tr("table_col_name"),
            tr("table_col_alias"), tr("table_col_actions")
        ])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setColumnWidth(3, 400)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setStyleSheet("")
        self._table.itemClicked.connect(self.on_project_row_clicked)
        self._main_layout.addWidget(self._table)

        bottom_layout = QHBoxLayout()
        self._status_label = QLabel()
        bottom_layout.addWidget(self._status_label)
        bottom_layout.addStretch()

        self._lang_btn = QPushButton(tr("btn_lang_toggle"))
        self._lang_btn.setObjectName("langToggle")
        self._lang_btn.clicked.connect(self._toggle_language)
        bottom_layout.addWidget(self._lang_btn)

        self._main_layout.addLayout(bottom_layout)

    def _toggle_language(self):
        toggle_lang()
        self._refresh_lang_ui()

    def _refresh_lang_ui(self):
        self.setWindowTitle(tr("window_title"))
        self._title_label.setText(tr("title_project_list"))
        self._add_btn.setText(tr("btn_add_project"))
        self._mcp_btn.setText(tr("btn_mcp_config"))
        self._move_up_btn.setText(tr("btn_move_up"))
        self._move_down_btn.setText(tr("btn_move_down"))
        self._table.setHorizontalHeaderLabels([
            tr("table_col_seq"), tr("table_col_name"),
            tr("table_col_alias"), tr("table_col_actions")
        ])
        self._lang_btn.setText(tr("btn_lang_toggle"))
        self.update_table()

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
        self._table.setRowCount(len(self.projects))
        for i, project in enumerate(self.projects):
            seq_item = QTableWidgetItem(str(i + 1))
            seq_item.setTextAlignment(Qt.AlignCenter)
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 0, seq_item)
            
            name_item = QTableWidgetItem(project.get("name", ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 1, name_item)
            
            alias_item = QTableWidgetItem(project.get("alias", ""))
            alias_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            alias_item.setFlags(alias_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(i, 2, alias_item)

            btn_widget = QWidget()
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(2, 2, 2, 2)

            desensitize_btn = QPushButton(tr("btn_desensitize"))
            desensitize_btn.clicked.connect(lambda checked, p=project: self.desensitize_project(p))
            restore_btn = QPushButton(tr("btn_restore"))
            restore_btn.clicked.connect(lambda checked, p=project: self.restore_project(p))
            edit_btn = QPushButton(tr("btn_edit"))
            edit_btn.clicked.connect(lambda checked, p=project: self.edit_project(p))
            delete_btn = QPushButton(tr("btn_delete"))
            delete_btn.clicked.connect(lambda checked, p=project: self.delete_project(p))

            for btn in [desensitize_btn, restore_btn, edit_btn, delete_btn]:
                btn.setMinimumSize(50, 25)
                btn.setStyleSheet("padding: 2px 6px; margin: 0 1px;")
                btn_layout.addWidget(btn)

            btn_widget.setLayout(btn_layout)
            self._table.setCellWidget(i, 3, btn_widget)

        self._status_label.setText(tr("status_projects", count=len(self.projects)))

    def add_project(self):
        dialog = ProjectDialog(self.storage, self)
        if dialog.exec() == QDialog.Accepted:
            project_data = dialog.get_project_data()
            project_data["name"] = Path(project_data["projectPath"]).name
            new_project = self.storage.add_project(project_data)

            secret_path = project_data["secretPath"]
            Path(secret_path).mkdir(parents=True, exist_ok=True)
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
            QMessageBox.warning(self, tr("msg_error"), tr("msg_path_not_exist", path=project_path))
            return

        rules = self.storage.load_secret_config(secret_path)
        if not rules:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_no_rules"))
            return

        enabled_rules = [r for r in rules if r.get("enabled", True)]
        if not enabled_rules:
            QMessageBox.warning(self, tr("msg_info"), tr("msg_no_enabled_rules"))
            return

        self.storage.ensure_secret_path(secret_path)

        secret_file = Path(secret_path) / "secret.csv"
        if self.storage.is_file_locked(secret_file):
            QMessageBox.warning(self, tr("msg_error"), tr("msg_file_locked_desensitize"))
            return

        matched_files = self.engine.scan_files(project_path, enabled_rules)

        if not matched_files:
            QMessageBox.information(self, tr("msg_info"), tr("msg_no_match"))
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
            QMessageBox.information(self, tr("msg_desensitize_success"), tr("msg_desensitize_done"))
        else:
            QMessageBox.information(self, tr("msg_info"), tr("msg_no_field"))

        self.load_projects()

    def restore_project(self, project):
        project_path = project.get("projectPath", "")
        secret_path = project.get("secretPath", "")

        secrets = self.storage.load_secrets(secret_path)
        if not secrets:
            QMessageBox.information(self, tr("msg_info"), tr("msg_no_restore_data"))
            return

        secret_file = Path(secret_path) / "secret.csv"
        if self.storage.is_file_locked(secret_file):
            QMessageBox.warning(self, tr("msg_error"), tr("msg_file_locked_restore"))
            return

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
                    if pattern and __import__('fnmatch').fnmatch(file_path.name, pattern):
                        matched = True
                        break
                
                if matched:
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
            self.storage.clear_secrets(secret_path)
            QMessageBox.information(self, tr("msg_restore_success"), tr("msg_restore_done"))
        else:
            QMessageBox.information(self, tr("msg_info"), tr("msg_not_desensitized"))

    def open_secret_path(self, project):
        secret_path = project.get("secretPath", "")
        if secret_path:
            subprocess.run(["explorer", secret_path])

    def delete_project(self, project):
        project_name = project.get("name", "")
        alias = project.get("alias", "")
        display_name = f"{project_name} - {alias}" if alias else project_name

        reply = QMessageBox.question(
            self, tr("msg_confirm_delete_title"),
            tr("msg_confirm_delete_text", name=display_name),
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.storage.delete_project(project["id"])
            self.load_projects()
            QMessageBox.information(self, tr("msg_delete_success"), tr("msg_delete_success_text"))

    def _is_frozen(self):
        if getattr(sys, 'frozen', False):
            return True
        try:
            return __compiled__ is not None
        except NameError:
            return False

    def copy_mcp_config(self):
        is_frozen = self._is_frozen()

        if is_frozen:
            config = {
                "mcpServers": {
                    "desensitization-tool": {
                        "command": sys.executable,
                        "args": ["--mcp"]
                    }
                }
            }
            mode_text = tr("msg_copied_text_exe")
        else:
            src_dir = str(Path(__file__).resolve().parent.parent)
            config = {
                "mcpServers": {
                    "desensitization-tool": {
                        "command": "python",
                        "args": ["-u", "main.py"],
                        "cwd": src_dir
                    }
                }
            }
            mode_text = tr("msg_copied_text_py")

        text = json.dumps(config, ensure_ascii=False, indent=2)
        QApplication.clipboard().setText(text)
        QMessageBox.information(self, tr("msg_copied_title"), mode_text)
