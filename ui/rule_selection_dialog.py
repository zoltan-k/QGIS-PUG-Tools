# -*- coding: utf-8 -*-
"""
Dialog pentru alegerea regulilor de validare de rulat: o lista cu id-ul,
severitatea si numele fiecarei reguli inregistrate, fiecare cu propriul
checkbox, plus butoane pentru selectare/deselectare rapida a tuturor.
"""

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

        self.list_widget = QListWidget(self)
        for rule in self._rules:
            item = QListWidgetItem(f"R{rule.rule_id} ({rule.severity}) - {rule.name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(CHECKED)
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
        run_button.clicked.connect(self.accept)
        button_layout.addWidget(run_button)

        cancel_button = QPushButton("Renunta")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

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
