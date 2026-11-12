# -*- coding: utf-8 -*-
"""
Dialog pentru alegerea regulilor de validare de rulat: o lista cu id-ul,
severitatea si numele fiecarei reguli inregistrate, fiecare cu propriul
checkbox, plus butoane pentru selectare/deselectare rapida a tuturor.
"""

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

SETTINGS_KEY = "PUGTools/partial_validation/last_rules"

CHECKED = Qt.CheckState.Checked
UNCHECKED = Qt.CheckState.Unchecked
USER_ROLE = Qt.ItemDataRole.UserRole


class RuleSelectionDialog(QDialog):
    def __init__(self, rules, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Selecteaza regulile de validare")
        self.resize(600, 500)
        self._rules = sorted(rules, key=lambda r: r.rule_id)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        hint_label = QLabel("Bifeaza regulile de rulat pe proiectul curent:")
        layout.addWidget(hint_label)

        remembered = self._load_remembered()
        self.list_widget = QListWidget(self)
        for rule in self._rules:
            item = QListWidgetItem(f"R{rule.rule_id} ({rule.severity}) - {rule.name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(CHECKED if str(rule.rule_id) in remembered else UNCHECKED)
            item.setData(USER_ROLE, rule)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        toggle_layout = QHBoxLayout()
        select_all_button = QPushButton("Selecteaza tot")
        select_all_button.clicked.connect(lambda: self._set_all(CHECKED))
        toggle_layout.addWidget(select_all_button)

        deselect_all_button = QPushButton("Deselecteaza tot")
        deselect_all_button.clicked.connect(lambda: self._set_all(UNCHECKED))
        toggle_layout.addWidget(deselect_all_button)

        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        run_button = QPushButton("Ruleaza")
        run_button.clicked.connect(self._on_run)
        button_layout.addWidget(run_button)

        cancel_button = QPushButton("Renunta")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    @staticmethod
    def _load_remembered():
        """Id-urile regulilor bifate data trecuta (gol la prima utilizare)."""
        raw = QgsSettings().value(SETTINGS_KEY, "", type=str) or ""
        return {part for part in raw.split(",") if part}

    def _on_run(self):
        ids = ",".join(str(r.rule_id) for r in self.selected_rules())
        QgsSettings().setValue(SETTINGS_KEY, ids)
        self.accept()

    def _set_all(self, check_state):
        for i in range(self.list_widget.count()):
            self.list_widget.item(i).setCheckState(check_state)

    def selected_rules(self):
        """Lista instantelor de regula bifate, in ordinea rule_id."""
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == CHECKED:
                selected.append(item.data(USER_ROLE))
        return selected
