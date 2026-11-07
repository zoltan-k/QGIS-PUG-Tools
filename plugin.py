# -*- coding: utf-8 -*-
"""
Plugin QGIS "PUG Tools": adauga un toolbar cu sapte butoane, in aceasta ordine:
    1. Proiect nou PUG: creeaza un proiect PUG nou pe baza sablonului
       configurat, cu limita UAT-ului preluata dinamic pentru judetul/UAT-ul
       ales (tools/project_loader.py, tools/uat_boundary.py).
    2. Actualizeaza pachetul: adauga in proiectul curent straturile de
       referinta ("~"/"_") lipsa fata de sablonul curent si le actualizeaza
       stilurile (widget-uri de camp, valori implicite, actiuni,
       simbolizare), fara sa modifice datele (tools/package_updater.py).
    3. Copie de siguranta portabila: un .zip langa fisierul .qgz cu proiectul
       (cai strict relative) si tot folderul pachetului PUG
       (tools/portable_backup.py).
    -- separator --
    4. Ruleaza toate regulile de validare inregistrate (validations/rules_config.py)
       pe proiectul QGIS curent activ si afiseaza rezultatele intr-un dialog.
    5. Ruleaza doar regulile de validare bifate de utilizator, dintr-un
       dialog de selectie (ui/rule_selection_dialog.py).
    6. Pregateste proiectul curent pentru validare oficiala: creeaza o copie
       arhivata cu data curenta (tools/preparator.py).
    -- separator --
    7. Despre: informatii despre plugin si starea datelor locale (sablon,
       cache de limite UAT), cu actiuni de stergere/reimprospatare
       (ui/about_dialog.py). Include si "Editeaza sablonul"/"Salveaza
       sablonul" (tools/template_editor.py) - eliminate din toolbar/meniu,
       accesibile doar de aici, fiind actiuni rar folosite (editare sablon,
       nu a unui proiect).
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QDialog, QMessageBox
from qgis.core import QgsProject

from .tools import project_loader
from .tools import preparator
from .tools import package_updater
from .tools import portable_backup
from .ui.results_dialog import ValidationResultsDialog
from .ui.rule_selection_dialog import RuleSelectionDialog
from .ui.about_dialog import AboutDialog
from .validations import registry

# Importul de mai jos declanseaza inregistrarea regulilor definite in
# rules_config.py (register_rule(...) se executa la incarcarea modulului).
from .validations import rules_config  # noqa: F401  (import cu efect de inregistrare)

MENU_NAME = "PUG Tools"


class PugToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self.validate_action = None
        self.select_validate_action = None
        self.new_project_action = None
        self.prepare_action = None
        self.update_package_action = None
        self.portable_backup_action = None
        self.about_action = None

    # -- ciclul de viata al plugin-ului -------------------------------------

    def initGui(self):
        self.toolbar = self.iface.addToolBar(MENU_NAME)
        self.toolbar.setObjectName("PugToolsToolbar")

        self.validate_action = QAction(
            self._load_icon("icon.svg"),
            "Ruleaza validari GPKG",
            self.iface.mainWindow(),
        )
        self.validate_action.setToolTip(
            "Ruleaza toate regulile de validare inregistrate pe proiectul curent"
        )
        self.validate_action.triggered.connect(self.run_validations)

        self.select_validate_action = QAction(
            self._load_icon("icon_select_rules.svg"),
            "Ruleaza validari selective",
            self.iface.mainWindow(),
        )
        self.select_validate_action.setToolTip(
            "Alege ce reguli de validare sa ruleze pe proiectul curent"
        )
        self.select_validate_action.triggered.connect(self.run_select_and_validate)

        self.new_project_action = QAction(
            self._load_icon("newPUG.svg"),
            "Proiect nou PUG",
            self.iface.mainWindow(),
        )
        self.new_project_action.setToolTip(
            "Creaza un Proiect nou de PUG/PUZ/etc"
        )
        self.new_project_action.triggered.connect(self.run_new_project)

        self.prepare_action = QAction(
            self._load_icon("prepare_to_validate.svg"),
            "Pregateste proiectul pt validare oficiala",
            self.iface.mainWindow(),
        )
        self.prepare_action.setToolTip("Pregateste proiectul pt validare oficiala")
        self.prepare_action.triggered.connect(self.run_prepare)

        self.update_package_action = QAction(
            self._load_icon("icon_updatePUG.svg"),
            "Actualizeaza pachetul",
            self.iface.mainWindow(),
        )
        self.update_package_action.setToolTip(
            "Adauga straturile de referinta lipsa si actualizeaza stilurile "
            "proiectului curent la sablonul curent (nu modifica datele)"
        )
        self.update_package_action.triggered.connect(self.run_update_package)

        self.portable_backup_action = QAction(
            self._load_icon("icon_portable_backup.svg"),
            "Copie de siguranta portabila",
            self.iface.mainWindow(),
        )
        self.portable_backup_action.setToolTip(
            "Creeaza o arhiva .zip portabila (langa fisierul .qgz) cu proiectul "
            "(cai strict relative) si intregul folder al pachetului PUG"
        )
        self.portable_backup_action.triggered.connect(self.run_portable_backup)

        self.about_action = QAction(
            self._load_icon("icon_about.svg"),
            "Despre PUG Tools",
            self.iface.mainWindow(),
        )
        self.about_action.setToolTip(
            "Informatii despre plugin si starea datelor locale (sablon, cache UAT) - "
            "include si editarea/salvarea sablonului"
        )
        self.about_action.triggered.connect(self.run_about)

        self.toolbar.addAction(self.new_project_action)
        self.toolbar.addAction(self.update_package_action)
        self.toolbar.addAction(self.portable_backup_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.validate_action)
        self.toolbar.addAction(self.select_validate_action)
        self.toolbar.addAction(self.prepare_action)
        self.toolbar.addSeparator()
        self.toolbar.addAction(self.about_action)

        self.iface.addPluginToMenu(MENU_NAME, self.new_project_action)
        self.iface.addPluginToMenu(MENU_NAME, self.update_package_action)
        self.iface.addPluginToMenu(MENU_NAME, self.portable_backup_action)
        self.iface.addPluginToMenu(MENU_NAME, self.validate_action)
        self.iface.addPluginToMenu(MENU_NAME, self.select_validate_action)
        self.iface.addPluginToMenu(MENU_NAME, self.prepare_action)
        self.iface.addPluginToMenu(MENU_NAME, self.about_action)


    def unload(self):
        if self.validate_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.validate_action)
            self.validate_action = None
        if self.select_validate_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.select_validate_action)
            self.select_validate_action = None
        if self.new_project_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.new_project_action)
            self.new_project_action = None
        if self.prepare_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.prepare_action)
            self.prepare_action = None
        if self.update_package_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.update_package_action)
            self.update_package_action = None
        if self.portable_backup_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.portable_backup_action)
            self.portable_backup_action = None
        if self.about_action is not None:
            self.iface.removePluginMenu(MENU_NAME, self.about_action)
            self.about_action = None
        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None

    def _load_icon(self, filename):
        icon_path = os.path.join(self.plugin_dir, "ui", "icons", filename)
        return QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

    # -- actiunea de validare -------------------------------------------------

    def run_validations(self):
        rules = registry.get_registered_rules()

        if not rules:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Validari GPKG",
                "Nu exista reguli de validare inregistrate. "
                "Adauga reguli in validations/rules_config.py.",
            )
            return

        self._run_rules_and_show_results(rules)

    def run_select_and_validate(self):
        rules = registry.get_registered_rules()

        if not rules:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Validari GPKG",
                "Nu exista reguli de validare inregistrate. "
                "Adauga reguli in validations/rules_config.py.",
            )
            return

        selection_dialog = RuleSelectionDialog(rules, parent=self.iface.mainWindow())
        if selection_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_rules = selection_dialog.selected_rules()
        if not selected_rules:
            QMessageBox.information(
                self.iface.mainWindow(),
                "Validari GPKG",
                "Nu a fost bifata nicio regula.",
            )
            return

        self._run_rules_and_show_results(selected_rules)

    def _run_rules_and_show_results(self, rules):
        project = QgsProject.instance()

        all_failures = []
        errors = []

        for rule in rules:
            try:
                failures = rule.run(project)
                all_failures.extend(failures)
            except Exception as exc:  # nu opri celelalte reguli daca una esueaza
                errors.append(f"R{rule.rule_id} {rule.name}: {exc}")

        dialog = ValidationResultsDialog(
            all_failures, errors, rules=rules, parent=self.iface.mainWindow(), iface=self.iface
        )
        # .exec() functioneaza atat pe PyQt5 (>= 5.11, unde e alias pentru
        # .exec_(), eliminat in PyQt6) cat si pe PyQt6.
        dialog.exec()

    # -- actiunea de proiect nou -----------------------------------------------

    def run_new_project(self):
        project_loader.run(self.iface)

    def run_prepare(self):
        preparator.run(self.iface)

    def run_update_package(self):
        package_updater.run(self.iface)

    def run_portable_backup(self):
        portable_backup.run(self.iface)

    # -- actiunea "Despre" (include si editarea/salvarea sablonului) ------------

    def run_about(self):
        dialog = AboutDialog(self.plugin_dir, self.iface, parent=self.iface.mainWindow())
        dialog.exec()
