# -*- coding: utf-8 -*-
"""
Dialog pentru afisarea rezultatelor validarii: un tabel cu regula (id +
nume), tip alerta (BLOCKER/WARNING), strat, FID si motivul esecului, plus
optiune de export CSV si dublu-click pentru a face zoom la feature-ul
respectiv pe canvas.
"""

import csv

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qgis.core import QgsProject

from ..tools import package_updater, rule_fixes

# regula "Structura GPKG conforma cu sablonul" - esecul ei sugereaza un pachet
# creat cu alta versiune de sablon (vezi _template_update_reason).
STRUCTURE_RULE_ID = 10

# Forma "scoped" (ex. QHeaderView.ResizeMode.ResizeToContents) functioneaza
# identic pe PyQt5 (>= 5.11 / sip >= 4.19.9, adica orice QGIS 3.x) si pe
# PyQt6, unde este singura forma acceptata. Se foloseste direct, fara nicio
# detectare la rulare intre binding-uri.
RESIZE_TO_CONTENTS = QHeaderView.ResizeMode.ResizeToContents
RESIZE_STRETCH = QHeaderView.ResizeMode.Stretch
SELECT_ROWS = QAbstractItemView.SelectionBehavior.SelectRows
NO_EDIT_TRIGGERS = QAbstractItemView.EditTrigger.NoEditTriggers
DISPLAY_ROLE = Qt.ItemDataRole.DisplayRole

# Coloane: Regula | Tip alerta | Strat | FID | Motiv
COL_REGULA, COL_SEVERITATE, COL_STRAT, COL_FID, COL_MOTIV = range(5)

SEVERITY_COLORS = {
    "BLOCKER": QColor("#c62828"),
    "WARNING": QColor("#e65100"),
}


class ValidationResultsDialog(QDialog):
    def __init__(self, failures, errors=None, rules=None, parent=None, iface=None):
        """
        `rules` este lista instantelor de regula (BaseValidationRule) care au
        fost efectiv rulate - folosita pentru a asocia fiecarui esec id-ul si
        severitatea regulii care l-a generat (ValidationFailure nu retine
        decat rule_name).

        `iface` (QgisInterface) e necesar pentru butonul "Actualizeaza
        pachetul"; fara el butonul nu e oferit.
        """
        super().__init__(parent)
        self._iface = iface
        self.failures = failures
        self.errors = errors or []
        self._rules = list(rules or [])
        self._rule_by_name = {r.name: r for r in self._rules}
        self._rule_by_id = {r.rule_id: r for r in self._rules}
        self.setWindowTitle("Rezultate validare GPKG")
        self.resize(1050, 550)
        self._build_ui()

    def _rule_label_and_severity(self, failure):
        rule = self._rule_by_name.get(failure.rule_name)
        if rule is None:
            return failure.rule_name, failure.severity or ""
        label = f"R{rule.rule_id} - {failure.rule_name}"
        return label, failure.severity or rule.severity

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        hint_label = QLabel(
            "Dublu-click pe un rand cu FID pentru a activa stratul, selecta si face "
            "zoom la feature si a deschide tabelul de atribute filtrat pe acesta."
        )
        hint_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(hint_label)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["Regula", "Tip alerta", "Strat", "FID", "Motiv"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_REGULA, RESIZE_TO_CONTENTS)
        header.setSectionResizeMode(COL_SEVERITATE, RESIZE_TO_CONTENTS)
        header.setSectionResizeMode(COL_STRAT, RESIZE_TO_CONTENTS)
        header.setSectionResizeMode(COL_FID, RESIZE_TO_CONTENTS)
        header.setSectionResizeMode(COL_MOTIV, RESIZE_STRETCH)
        self.table.setSelectionBehavior(SELECT_ROWS)
        self.table.setEditTriggers(NO_EDIT_TRIGGERS)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: darkred;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        fix_row = QVBoxLayout()
        self.update_reason_label = QLabel()
        self.update_reason_label.setStyleSheet("color: darkred;")
        self.update_reason_label.setWordWrap(True)
        self.update_reason_label.hide()
        fix_row.addWidget(self.update_reason_label)
        self.fix_hint_label = QLabel(
            "Remedieri disponibile pentru unele dintre esecurile de mai sus - "
            "fiecare buton modifica DIRECT stratul/straturile vizate, dupa "
            "confirmare:"
        )
        self.fix_hint_label.setStyleSheet("color: gray; font-style: italic;")
        self.fix_hint_label.hide()
        fix_row.addWidget(self.fix_hint_label)
        self.fix_button_layout = QHBoxLayout()
        fix_row.addLayout(self.fix_button_layout)
        layout.addLayout(fix_row)

        button_layout = QHBoxLayout()
        self.export_button = QPushButton("Exporta CSV...")
        self.export_button.clicked.connect(self._export_csv)
        button_layout.addWidget(self.export_button)

        button_layout.addStretch()

        self.close_button = QPushButton("Inchide")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

        self._refresh()

    def _refresh(self):
        """Repopuleaza tabelul, eticheta de sumar/erori si butoanele de
        remediere - apelata la construire si dupa fiecare remediere aplicata
        (numarul de esecuri, si deci setul de remedieri disponibile, se poate
        schimba)."""
        self._populate_table()
        self._populate_fix_buttons()

        summary_text = f"Total inregistrari esuate: {len(self.failures)}"
        if self.errors:
            summary_text += f"   |   Erori la rularea unor reguli: {len(self.errors)}"
        self.summary_label.setText(summary_text)

        if self.errors:
            self.error_label.setText("Erori la rularea unor reguli:\n" + "\n".join(self.errors))
            self.error_label.show()
        else:
            self.error_label.hide()

        self.export_button.setEnabled(bool(self.failures))

    def _populate_table(self):
        self.table.setRowCount(len(self.failures))
        for row, failure in enumerate(self.failures):
            regula_label, severity = self._rule_label_and_severity(failure)

            self.table.setItem(row, COL_REGULA, QTableWidgetItem(regula_label))

            severity_item = QTableWidgetItem(severity)
            color = SEVERITY_COLORS.get(severity)
            if color is not None:
                severity_item.setForeground(color)
            self.table.setItem(row, COL_SEVERITATE, severity_item)

            self.table.setItem(row, COL_STRAT, QTableWidgetItem(failure.layer_name))

            fid_item = QTableWidgetItem()
            fid_item.setData(DISPLAY_ROLE, failure.fid)
            self.table.setItem(row, COL_FID, fid_item)

            self.table.setItem(row, COL_MOTIV, QTableWidgetItem(failure.reason))

    def _failing_rule_ids(self):
        ids = set()
        for failure in self.failures:
            rule = self._rule_by_name.get(failure.rule_name)
            if rule is not None:
                ids.add(rule.rule_id)
        return ids

    def _populate_fix_buttons(self):
        while self.fix_button_layout.count():
            item = self.fix_button_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        failing_ids = self._failing_rule_ids()
        applicable_groups = [
            group
            for group in rule_fixes.FIX_GROUPS
            if any(rid in failing_ids and rid in self._rule_by_id for rid in group["rule_ids"])
        ]

        update_reason = self._template_update_reason(failing_ids)
        if update_reason:
            update_button = QPushButton("Actualizeaza pachetul (sablon)")
            update_button.setToolTip(update_reason)
            update_button.clicked.connect(self._on_update_package_clicked)
            self.fix_button_layout.addWidget(update_button)
            self.update_reason_label.setText(update_reason)
        self.update_reason_label.setVisible(bool(update_reason))

        self.fix_hint_label.setVisible(bool(applicable_groups))
        for group in applicable_groups:
            button = QPushButton(group["label"])
            button.clicked.connect(lambda checked=False, g=group: self._on_fix_clicked(g))
            self.fix_button_layout.addWidget(button)
        self.fix_button_layout.addStretch()

    def _template_update_reason(self, failing_ids):
        """
        Motivul pentru care se ofera "Actualizeaza pachetul", sau "" daca nu se
        ofera: versiunea pachetului difera de cea a sablonului curent, sau
        regula 10 (structura fata de sablon) a esuat. Necesita `iface`.
        """
        if self._iface is None:
            return ""
        try:
            needs_update, message = package_updater.package_update_status()
        except Exception:  # verificarea nu trebuie sa strice afisarea rezultatelor
            needs_update, message = False, ""
        if needs_update:
            return message
        if STRUCTURE_RULE_ID in failing_ids and STRUCTURE_RULE_ID in self._rule_by_id:
            return (
                "Regula 10 (structura fata de sablon) a esuat - actualizarea pachetului "
                "poate corecta straturile/campurile/tipurile care difera de sablonul curent."
            )
        return ""

    def _on_update_package_clicked(self):
        # exact acelasi cod ca butonul "Actualizeaza pachetul" din toolbar -
        # include propriul dialog de confirmare si copia de rezerva.
        project = QgsProject.instance()
        if package_updater.run(self._iface):
            self._rerun_rules(project)

    def _on_fix_clicked(self, group):
        rule_labels = ", ".join(f"R{rid}" for rid in group["rule_ids"])
        answer = QMessageBox.question(
            self,
            "Confirma remedierea",
            f"Aceasta va modifica DIRECT straturile GPKG afectate de {rule_labels}, "
            "in proiectul curent deschis.\n\nContinui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        project = QgsProject.instance()
        try:
            result = group["run"](project, self._rule_by_id)
        except Exception as exc:  # nu lasa dialogul intr-o stare inconsistenta
            QMessageBox.critical(self, "Eroare la remediere", str(exc))
            return

        self._rerun_rules(project)
        QMessageBox.information(self, "Remediere aplicata", result.summary())

    def _rerun_rules(self, project):
        all_failures = []
        errors = []
        for rule in self._rules:
            try:
                all_failures.extend(rule.run(project))
            except Exception as exc:
                errors.append(f"R{rule.rule_id} {rule.name}: {exc}")
        self.failures = all_failures
        self.errors = errors
        self._refresh()

    def _on_row_double_clicked(self, item):
        row = item.row()
        layer_name = self.table.item(row, COL_STRAT).text()
        fid = self.table.item(row, COL_FID).data(DISPLAY_ROLE)

        if not fid:
            # fid 0 inseamna ca esecul nu tine de un feature anume (esec la
            # nivel de strat/regula) - nu exista pe ce sa facem zoom/selectie.
            return

        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            return
        layer = layers[0]

        feature = layer.getFeature(int(fid))
        if not feature.isValid() or feature.geometry() is None or feature.geometry().isEmpty():
            return

        try:
            from qgis.utils import iface
        except ImportError:
            iface = None
        if iface is None:
            return

        iface.setActiveLayer(layer)

        canvas = iface.mapCanvas()
        layer.removeSelection()
        layer.select(int(fid))
        bbox = feature.geometry().boundingBox()
        bbox.scale(1.5)
        canvas.setExtent(bbox)
        canvas.refresh()

        iface.showAttributeTable(layer, filterExpression=f"$id = {int(fid)}")

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporta rezultate CSV", "validare_rezultate.csv", "CSV (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Regula", "Tip alerta", "Strat", "FID", "Motiv"])
                for failure in self.failures:
                    regula_label, severity = self._rule_label_and_severity(failure)
                    writer.writerow(
                        [regula_label, severity, failure.layer_name, failure.fid, failure.reason]
                    )
            QMessageBox.information(
                self, "Export reusit", f"Rezultatele au fost salvate in:\n{path}"
            )
        except OSError as exc:
            QMessageBox.critical(self, "Eroare export", f"Nu s-a putut salva fisierul:\n{exc}")
