# -*- coding: utf-8 -*-
"""
Dialogul "Consolideaza straturile": alegerea fisierului GPKG tinta (un singur
fisier). Fisierele fara nume standard sunt afisate dar nu pot fi alese.
Cand tinta aleasa difera ca SIRUTA/tip de alte fisiere, OK cere o confirmare
explicita (bifa).
"""

import os

from qgis.PyQt.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


class ConsolidateDialog(QDialog):
    def __init__(self, files, preselected, project_dir, mismatch_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Consolideaza straturile intr-un singur GPKG")
        self.setMinimumWidth(640)
        self._files = files
        self._mismatch_fn = mismatch_fn
        self._radios = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Straturile sablonului din proiect provin din mai multe fisiere GPKG.\n"
            "Alege fisierul in care sunt consolidate (tabelele din celelalte fisiere "
            "le inlocuiesc pe cele cu acelasi nume din fisierul ales):"
        ))

        group = QButtonGroup(self)
        for info in sorted(files, key=lambda f: (not f.valid_target, f.path.lower())):
            try:
                rel = os.path.relpath(info.path, project_dir)
                shown = info.path if rel.startswith("..") else rel
            except ValueError:
                shown = info.path
            text = f"{shown.replace(chr(92), '/')}\n    {len(info.layers)} straturi sablon"
            if info.other_count:
                text += f", {info.other_count} alte straturi"
            if info.generic:
                text += "  - nume generic (AAAALLZZ)"
            if not info.valid_target:
                text += "  - NU poate fi tinta: nume nestandard"
            radio = QRadioButton(text)
            radio.setEnabled(info.valid_target)
            group.addButton(radio)
            layout.addWidget(radio)
            self._radios[radio] = info
            if info is preselected:
                radio.setChecked(True)  # (inainte de connect: widget-urile de mai jos nu exista inca)
            radio.toggled.connect(self._refresh)

        self._warn = QLabel()
        self._warn.setWordWrap(True)
        self._warn.setStyleSheet("color: #b00020;")
        self._warn.hide()
        layout.addWidget(self._warn)
        self._confirm = QCheckBox("Inteleg ca datele provin din fisiere cu alt SIRUTA/tip si vreau sa continui")
        self._confirm.hide()
        self._confirm.toggled.connect(self._refresh)
        layout.addWidget(self._confirm)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._refresh()

    def selected_file(self):
        for radio, info in self._radios.items():
            if radio.isChecked():
                return info
        return None

    def _refresh(self, *_args):
        info = self.selected_file()
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if info is None:
            ok.setEnabled(False)
            return
        problems = self._mismatch_fn(info)
        if problems:
            self._warn.setText(
                "ATENTIE - fisiere cu alt SIRUTA/tip decat tinta aleasa:\n  - " + "\n  - ".join(problems)
            )
            self._warn.show()
            self._confirm.show()
        else:
            self._warn.hide()
            self._confirm.hide()
        ok.setEnabled(not problems or self._confirm.isChecked())
