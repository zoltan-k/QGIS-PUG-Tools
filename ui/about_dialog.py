# -*- coding: utf-8 -*-
"""
Dialog "Despre": informatii despre plugin (nume, versiune, descriere) si
starea datelor locale folosite de plugin - sablonul PUG (unde e cautat, care
dintre surse exista efectiv, cu cale completa) si cache-ul local de limite
UAT (tools/uat_boundary.py) - cu actiuni de stergere/reimprospatare pentru
ambele.
"""

import configparser
import datetime
import os
import traceback

from qgis.core import Qgis, QgsMessageLog
from qgis.PyQt.QtCore import QUrl, Qt
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..tools import settings as pug_settings
from ..tools import template_editor, template_paths, uat_boundary

LOG_TAG = "PUG Tools"
README_URL = "https://github.com/zoltan-k/QGIS-PUG-Tools#readme"


def _read_metadata(plugin_dir):
    parser = configparser.ConfigParser()
    parser.read(os.path.join(plugin_dir, "metadata.txt"), encoding="utf-8")
    general = parser["general"] if parser.has_section("general") else {}
    return {
        "name": general.get("name", "PUG Tools"),
        "version": general.get("version", "-"),
        "description": general.get("description", ""),
        "about": general.get("about", ""),
    }


def _format_size(num_bytes):
    if num_bytes is None:
        return "-"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def _format_mtime(unix_time):
    if unix_time is None:
        return "-"
    return datetime.datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M")


def _bold(label):
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class AboutDialog(QDialog):
    def __init__(self, plugin_dir, iface, parent=None):
        super().__init__(parent)
        self.plugin_dir = plugin_dir
        self.iface = iface
        self.setWindowTitle("Despre PUG Tools")
        self.setMinimumWidth(640)

        self._outer_layout = QVBoxLayout(self)
        self._build_header()
        self._outer_layout.addWidget(_make_separator())

        self._data_container = QWidget()
        self._outer_layout.addWidget(self._data_container)
        self._build_data_sections()

        self._outer_layout.addStretch()
        self._build_close_button()

    # -- sectiuni statice (nu se schimba dupa actiuni) ------------------------

    def _build_header(self):
        meta = _read_metadata(self.plugin_dir)

        title_label = QLabel(f"{meta['name']} — v{meta['version']}")
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        title_label.setFont(title_font)
        self._outer_layout.addWidget(title_label)

        if meta["description"]:
            desc_label = QLabel(meta["description"])
            desc_label.setWordWrap(True)
            self._outer_layout.addWidget(desc_label)

        readme_label = QLabel(f'<a href="{README_URL}">Documentatie completa (README, GitHub)</a>')
        readme_label.setOpenExternalLinks(True)
        self._outer_layout.addWidget(readme_label)

    def _build_close_button(self):
        button_row = QHBoxLayout()
        button_row.addStretch()
        close_button = QPushButton("Inchide")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        self._outer_layout.addLayout(button_row)

    # -- sectiuni cu date (rebuild-uite dupa fiecare actiune) -----------------

    @staticmethod
    def _clear_layout(layout):
        """
        layout.takeAt(0) + item.widget().deleteLater() singur nu e suficient:
        pentru un item care e un layout imbricat (adaugat prin addLayout(),
        cazul tuturor sectiunilor de mai jos), item.widget() e None, deci
        widget-urile lui nu erau niciodata sterse - ramaneau "fantoma",
        suprapuse peste continutul reconstruit la fiecare _refresh() (bug
        vizibil dupa orice actiune: Sterge/Actualizeaza afisau text
        suprapus). Curatare recursiva: si widget-uri, si layout-uri imbricate.
        """
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
                continue
            child_layout = item.layout()
            if child_layout is not None:
                AboutDialog._clear_layout(child_layout)
                child_layout.deleteLater()

    def _build_data_sections(self):
        """(Re)construieste continutul dependent de starea de pe disc, pastrand
        antetul si butonul 'Inchide' neschimbate."""
        layout = self._data_container.layout()
        if layout is None:
            layout = QVBoxLayout(self._data_container)
        else:
            self._clear_layout(layout)

        layout.addWidget(_bold(QLabel("Editare sablon")))
        layout.addLayout(self._build_template_edit_rows())

        layout.addWidget(_make_separator())

        layout.addWidget(_bold(QLabel("Sablon PUG")))
        layout.addLayout(self._build_template_rows())

        layout.addWidget(_make_separator())

        layout.addWidget(_bold(QLabel("Cache local limite UAT")))
        layout.addLayout(self._build_uat_cache_rows())

        layout.addWidget(_make_separator())

        layout.addWidget(_bold(QLabel("Validare geometrica (R26/R27)")))
        layout.addLayout(self._build_validation_settings_rows())

    def _refresh(self):
        self._build_data_sections()

    # -- randuri cu informatie + actiuni ---------------------------------------

    def _info_row(self, label_text, path_text, status_text, status_ok, buttons=None, note=None):
        container = QVBoxLayout()

        row = QHBoxLayout()
        row.addWidget(_bold(QLabel(label_text + ":")))

        path_label = QLabel(path_text or "-")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(path_label, 1)

        status_label = QLabel(status_text)
        status_label.setStyleSheet(
            "color: #2e7d32; font-weight: bold;" if status_ok else "color: #9e9e9e;"
        )
        row.addWidget(status_label)

        for button in buttons or []:
            row.addWidget(button)

        container.addLayout(row)

        if note:
            note_label = QLabel(note)
            note_label.setWordWrap(True)
            note_label.setStyleSheet("color: gray; font-style: italic;")
            container.addWidget(note_label)

        return container

    @staticmethod
    def _open_folder_button(path):
        button = QPushButton("Deschide folder")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))
        return button

    # -- sectiunea editare sablon (actiuni, nu doar informatie) -----------------

    def _build_template_edit_rows(self):
        section = QVBoxLayout()

        row = QHBoxLayout()
        edit_btn = QPushButton("Editeaza sablonul")
        edit_btn.setToolTip(
            "Incarca sablonul intr-un proiect nou, pentru editare in siguranta "
            "(structura, stiluri, proprietati de camp)"
        )
        edit_btn.clicked.connect(self._on_edit_template)
        row.addWidget(edit_btn)

        save_btn = QPushButton("Salveaza sablonul")
        save_btn.setToolTip("Salveaza modificarile din proiectul de editare inapoi in sablon")
        save_btn.clicked.connect(self._on_save_template)
        row.addWidget(save_btn)
        row.addStretch()
        section.addLayout(row)

        note = QLabel(
            "Actiuni rar folosite - editeaza structura/stilurile sablonului insusi, "
            "nu ale proiectului curent. Foloseste-le doar daca stii ce faci."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        section.addWidget(note)

        return section

    def _on_edit_template(self):
        self.accept()
        template_editor.load_template(self.iface)

    def _on_save_template(self):
        self.accept()
        template_editor.save_template(self.iface)

    # -- sectiunea sablon ------------------------------------------------------

    def _build_template_rows(self):
        section = QVBoxLayout()

        override_path = template_paths.override_template_dir()
        if override_path:
            override_ok = os.path.isdir(override_path)
            section.addLayout(
                self._info_row(
                    "Suprascriere manuala",
                    override_path,
                    "prezent" if override_ok else "lipsa",
                    override_ok,
                    buttons=[self._open_folder_button(override_path)] if override_ok else None,
                    note='Setata in QGIS Settings ("PUGTools/template_dir") - are prioritate fata de celelalte doua surse.',
                )
            )

        active_dir = template_paths.active_template_dir()
        active_ok = template_paths.active_copy_exists()
        active_buttons = []
        if active_ok:
            active_buttons.append(self._open_folder_button(active_dir))
        refresh_btn = QPushButton("Actualizeaza")
        refresh_btn.setToolTip(
            "Sterge si recreeaza imediat copia activa din sablonul inclus in plugin."
        )
        refresh_btn.clicked.connect(self._on_refresh_active_template)
        active_buttons.append(refresh_btn)
        if active_ok:
            delete_btn = QPushButton("Sterge")
            delete_btn.clicked.connect(self._on_delete_active_template)
            active_buttons.append(delete_btn)
        section.addLayout(
            self._info_row(
                "Copie activa (profil QGIS)",
                active_dir,
                "prezenta" if active_ok else "lipsa",
                active_ok,
                buttons=active_buttons,
                note=(
                    'Folosita si editata de "Editeaza sablonul"/"Salveaza sablonul"; NU este '
                    "suprascrisa automat la actualizarea plugin-ului - de aceea unele "
                    "corectii aduse sablonului bundled pot necesita apasarea butonului "
                    '"Actualizeaza" de mai sus. ATENTIE: actualizarea/stergerea elimina '
                    "orice modificare facuta local si nesalvata inca in sablonul din plugin."
                ),
            )
        )

        bundled_dir = template_paths.bundled_template_dir()
        bundled_ok = template_paths.bundled_exists()
        section.addLayout(
            self._info_row(
                "Sablon din fabrica (in plugin)",
                bundled_dir,
                "prezent" if bundled_ok else "lipsa",
                bundled_ok,
                buttons=[self._open_folder_button(bundled_dir)] if bundled_ok else None,
                note="Inclus in plugin; suprascris automat la fiecare reinstalare/actualizare a plugin-ului.",
            )
        )

        return section

    def _on_refresh_active_template(self):
        answer = QMessageBox.question(
            self,
            "Actualizeaza copia activa a sablonului",
            "Copia activa a sablonului va fi stearsa si recreata din sablonul "
            "inclus in plugin.\n\n"
            "Orice modificare facuta prin \"Editeaza sablonul\"/\"Salveaza "
            "sablonul\" si nesalvata inca in sablonul din plugin va fi PIERDUTA.\n\n"
            "Continui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            template_paths.refresh_active_copy()
        except Exception as exc:
            self._show_error("Actualizare sablon", exc)
            return
        self._refresh()

    def _on_delete_active_template(self):
        answer = QMessageBox.question(
            self,
            "Sterge copia activa a sablonului",
            "Copia activa a sablonului va fi stearsa.\n\n"
            "Va fi recreata automat din sablonul inclus in plugin la urmatoarea "
            "creare de proiect nou.\n\n"
            "Orice modificare facuta prin \"Editeaza sablonul\"/\"Salveaza "
            "sablonul\" si nesalvata inca in sablonul din plugin va fi PIERDUTA.\n\n"
            "Continui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            template_paths.delete_active_copy()
        except Exception as exc:
            self._show_error("Stergere sablon", exc)
            return
        self._refresh()

    # -- sectiunea cache UAT -----------------------------------------------------

    def _build_uat_cache_rows(self):
        section = QVBoxLayout()

        per_uat_files = uat_boundary.list_per_uat_cache_files()
        total_size = sum(size for _path, size in per_uat_files)
        per_uat_ok = bool(per_uat_files)
        per_uat_buttons = [self._open_folder_button(uat_boundary.cache_root())]
        if per_uat_ok:
            clear_btn = QPushButton("Sterge toate")
            clear_btn.clicked.connect(self._on_clear_per_uat_cache)
            per_uat_buttons.append(clear_btn)
        section.addLayout(
            self._info_row(
                "Fisiere cache per-UAT",
                uat_boundary.cache_root(),
                f"{len(per_uat_files)} fisier(e), {_format_size(total_size)}"
                if per_uat_ok
                else "niciunul",
                per_uat_ok,
                buttons=per_uat_buttons,
                note=(
                    "Cate un fisier mic (JSON) per UAT deja folosit la crearea unui "
                    "proiect - evita reinterogarea serviciului online pentru acelasi UAT."
                ),
            )
        )

        full_path, full_exists, full_size, full_mtime = uat_boundary.full_dataset_cache_status()
        full_buttons = []
        if full_exists:
            full_buttons.append(self._open_folder_button(os.path.dirname(full_path)))
        refresh_full_btn = QPushButton("Actualizeaza")
        refresh_full_btn.setToolTip(
            "Redescarca intregul set national de limite UAT (~70-120 MB, poate dura cateva minute)."
        )
        refresh_full_btn.clicked.connect(self._on_refresh_full_cache)
        full_buttons.append(refresh_full_btn)
        if full_exists:
            delete_full_btn = QPushButton("Sterge")
            delete_full_btn.clicked.connect(self._on_clear_full_cache)
            full_buttons.append(delete_full_btn)

        status_text = (
            f"prezent, {_format_size(full_size)}, din {_format_mtime(full_mtime)}"
            if full_exists
            else "lipsa"
        )
        section.addLayout(
            self._info_row(
                "Set complet (rezerva)",
                full_path,
                status_text,
                full_exists,
                buttons=full_buttons,
                note=(
                    "Folosit doar daca interogarea online filtrata per-UAT esueaza - "
                    "in mod normal nu exista, deoarece filtrarea per-UAT e suficienta. "
                    '"Actualizeaza" descarca din nou intregul set (trafic mare); '
                    '"Sterge" il elimina (va fi redescarcat automat doar daca va fi '
                    "din nou necesar ca rezerva)."
                ),
            )
        )

        return section

    # -- sectiunea setari de validare (R26/R27) --------------------------------

    def _build_validation_settings_rows(self):
        section = QVBoxLayout()

        row = QHBoxLayout()
        row.addWidget(_bold(QLabel("Toleranta avertizare (buffer):")))

        self._buffer_spin = QDoubleSpinBox()
        self._buffer_spin.setRange(pug_settings.BOUNDARY_BUFFER_STRICT_M, 1000.0)
        self._buffer_spin.setDecimals(1)
        self._buffer_spin.setSuffix(" m")
        self._buffer_spin.setValue(pug_settings.get_boundary_buffer_m())
        row.addWidget(self._buffer_spin)

        save_btn = QPushButton("Salveaza")
        save_btn.clicked.connect(self._on_save_boundary_buffer)
        row.addWidget(save_btn)
        row.addStretch()
        section.addLayout(row)

        note = QLabel(
            f"Geometrii aflate strict in interiorul limitei ({pug_settings.BOUNDARY_BUFFER_STRICT_M:g} m, "
            "fixa, valoarea publicata de validatorul oficial) trec fara observatie. Peste "
            "aceasta limita dar sub toleranta de mai sus: avertisment (WARNING) la regulile "
            "26 si 27, nu esec. Peste toleranta: esec (BLOCKER). Implicit 10 m, conform "
            "precizarilor tehnice OMDLPA 904."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        section.addWidget(note)

        return section

    def _on_save_boundary_buffer(self):
        pug_settings.set_boundary_buffer_m(self._buffer_spin.value())
        QMessageBox.information(
            self, "Setari validare", "Toleranta de avertizare a fost salvata."
        )

    def _on_clear_per_uat_cache(self):
        answer = QMessageBox.question(
            self,
            "Sterge cache-ul per-UAT",
            "Toate fisierele cache per-UAT vor fi sterse.\n\n"
            "Vor fi reobtinute automat (interogare online mica, filtrata) la "
            "urmatoarea creare de proiect pentru fiecare UAT.\n\n"
            "Continui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            uat_boundary.clear_per_uat_cache()
        except Exception as exc:
            self._show_error("Stergere cache UAT", exc)
            return
        self._refresh()

    def _on_clear_full_cache(self):
        answer = QMessageBox.question(
            self,
            "Sterge setul complet de rezerva",
            "Fisierul cache cu intregul set de date va fi sters.\n\n"
            "Continui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            uat_boundary.clear_full_dataset_cache()
        except Exception as exc:
            self._show_error("Stergere set complet", exc)
            return
        self._refresh()

    def _on_refresh_full_cache(self):
        answer = QMessageBox.question(
            self,
            "Actualizeaza setul complet de rezerva",
            "Intregul set national de limite UAT va fi descarcat din nou "
            "(~70-120 MB). Operatia poate dura cateva minute, timp in care "
            "QGIS nu va raspunde.\n\n"
            "Continui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            uat_boundary.refresh_full_dataset_cache()
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            self._show_error("Actualizare set complet", exc)
            return
        QApplication.restoreOverrideCursor()
        self._refresh()

    # -- utilitare ---------------------------------------------------------------

    def _show_error(self, title, exc):
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(self, title, f"A aparut o eroare:\n{exc}")
