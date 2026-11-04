# -*- coding: utf-8 -*-
"""
Unealta "Proiect nou PUG": creeaza un proiect QGIS nou pe baza unui sablon
(vezi _resolve_template_dir), pentru un UAT ales de utilizator, si il
configureaza (grupuri, straturi de referinta, strat virtual, PlanSpatial,
stiluri).

Acesta este scriptul ProjectLoader_v3.py adaptat pentru a rula ca actiune de
plugin in loc de script independent in consola QGIS. Modificari fata de
scriptul original:

    - Intreaga logica este incapsulata in run(iface) in loc sa ruleze la
      nivel de modul (ceea ce ar declansa executia la simplul import).
    - Toate simbolurile folosite implicit in consola QGIS (QgsProject,
      QgsFeature, NULL, Qgis, edit, QgsEditorWidgetSetup, iface, re) sunt
      acum importate explicit / primite ca parametru.
    - exit() a fost inlocuit cu o exceptie controlata (_AbortLoad), pentru
      ca un exit() necontrolat poate opri intregul proces QGIS cand ruleaza
      din interiorul unui plugin.
    - add_layer_to(gpkg, layer, group) folosea din greseala variabila
      globala `package` in loc de parametrul `gpkg`; a fost corectat.
    - locale.setlocale foloseste un fallback, deoarece 'ro_RO.UTF-8' nu
      exista pe Windows; daca niciun locale romanesc nu e disponibil,
      sortarea continua cu locale-ul implicit al sistemului.
    - Erorile neasteptate sunt prinse si afisate intr-un QMessageBox plus
      logate in QGIS Message Log ("PUG Tools"), in loc sa produca doar un
      traceback in consola.

Sablonul (portabilitate intre calculatoare + persistenta intre update-uri):
    Rezolvarea caii catre sablon este acum in tools/template_paths.py
    (resolve_template_dir), folosita si de "Editeaza sablonul"
    (tools/template_editor.py). Pe scurt, in ordine:

        1. O cale suprascrisa manual in QGIS Settings, la cheia
           "PUGTools/template_dir" (utila daca echipa foloseste un sablon
           comun pe o unitate de retea).
        2. Copia "activa" din profilul QGIS, populata automat la prima
           utilizare dintr-o copie a sablonului bundled cu plugin-ul.
           Aceasta este copia care se modifica atunci cand editezi sablonul
           din plugin, si NU este suprascrisa la actualizarea plugin-ului.
        3. Sablonul bundled cu plugin-ul (templates/JUD_UAT_SIRUTA_PUG_AAAALLZZ/),
           folosit direct doar daca copia activa nu poate fi creata.

    Pentru portabilitate pe un calculator nou: copiaza intregul folder
    sablon in interiorul folderului plugin-ului, la
    "templates/JUD_UAT_SIRUTA_PUG_AAAALLZZ/", inainte de a arhiva plugin-ul
    in .zip. Vezi si README.md din folderul "templates/" si docstring-ul
    din tools/template_paths.py.
"""

import locale
import re
import shutil
import sqlite3
import traceback
import unicodedata
from datetime import datetime

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from qgis.core import (
    Qgis,
    NULL,
    QgsEditorWidgetSetup,
    QgsFeature,
    QgsFeatureRequest,
    QgsMessageLog,
    QgsProject,
    QgsVectorLayer,
    edit,
)
from osgeo import ogr

from . import save_style_to_database, uat_boundary, virtual_layers
from .template_paths import (
    GPKG_FOLDER,
    GPKG_RELATIVE,
    TemplateNotFoundError,
    active_copy_outdated,
    resolve_template_dir,
)

SIRUTA_LAYER = "_siruta"

REF_GROUP_NAME = "REF"
V_LAYER_REQ = ["~REF_SZF", "~REF_ZRS_D"]
DO_NOT_IMPORT = V_LAYER_REQ + ["layer_styles"]

# straturi de referinta - NU trebuie sa aiba stil salvat in layer_styles
# (nici sablonul nu are); acelasi prefix folosit in template_editor.py.
# "sys__" = tabele de sistem (sys__versiune, sablon >= 3.1.0): strat de referinta in grupul REF.
REFERENCE_PREFIXES = ("~", "_", "sys__")

LOG_TAG = "PUG Tools"

VERSIUNE_LAYER = "sys__versiune"


def _set_versiune_tip(gpkg_path, tip):
    """
    Sablonul bundled are mereu tabela "sys__versiune" cu tip='PUG' (un singur
    rand) - actualizata aici la tipul de proiect ales de utilizator
    (PUG/PUZ/PUD/PATJ/PMUD), scriind direct in fisier inainte ca acesta sa
    fie deschis ca straturi QGIS.
    """
    con = sqlite3.connect(gpkg_path)
    try:
        con.execute(f'UPDATE "{VERSIUNE_LAYER}" SET tip = ?', (tip,))
        con.commit()
    finally:
        con.close()


class _AbortLoad(Exception):
    """Ridicata pentru a opri crearea proiectului in mod controlat (inlocuieste exit())."""


def _set_romanian_locale():
    """Incearca locale-uri romanesti cunoscute; nu opreste executia daca niciunul nu exista."""
    for loc_name in ("ro_RO.UTF-8", "Romanian_Romania.1250", "ro_RO", "Romanian"):
        try:
            locale.setlocale(locale.LC_ALL, loc_name)
            return
        except locale.Error:
            continue
    # Niciun locale romanesc disponibil - sortarea UAT-urilor foloseste locale-ul implicit.


def _ctext(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


class _CustomInputForm(QDialog):
    def __init__(self, judete_dict, uats_by_judet, parent=None):
        super().__init__(parent)
        self.judete_dict = {siruta: name.title() for siruta, name in judete_dict.items()}
        self.uats_by_judet = {}
        for parent_siruta, uat_list in uats_by_judet.items():
            self.uats_by_judet[parent_siruta] = [
                (siruta, name.title()) for siruta, name in uat_list
            ]

        self._init_ui()

        # Populate the first dropdown (Judete) alphabetically
        sorted_judete = sorted(self.judete_dict.items(), key=lambda item: locale.strxfrm(item[1]))
        for key, value in sorted_judete:
            self.combo_jud.addItem(value, key)  # text, user data (siruta ID)

        DEFAULT_TO_HR = 190
        default_index = self.combo_jud.findData(DEFAULT_TO_HR)
        self.combo_jud.setCurrentIndex(default_index)

        # Connect the dependency signal
        self.combo_jud.currentIndexChanged.connect(self._update_uat_dropdown)

        # Trigger an initial update to populate UATs for the first item
        self._update_uat_dropdown()

    def _init_ui(self):
        self.setWindowTitle("Proiect nou GIS pt PUG/PUZ/etc")
        self.setMinimumWidth(450)

        main_layout = QVBoxLayout()

        main_layout.addWidget(QLabel("Tipul proiectului:"))
        self.combo_pug = QComboBox()
        self.combo_pug.addItems(["PUG", "PUZ", "PUD", "PATJ", "PMUD"])
        main_layout.addWidget(self.combo_pug)

        main_layout.addSpacing(10)

        main_layout.addWidget(QLabel("Județ:"))
        self.combo_jud = QComboBox()
        self.combo_jud.setEditable(True)
        self.combo_jud.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_jud.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo_jud.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        main_layout.addWidget(self.combo_jud)

        main_layout.addWidget(QLabel("UAT:"))
        self.combo_uat = QComboBox()
        self.combo_uat.setEditable(True)
        self.combo_uat.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo_uat.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo_uat.completer().setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        main_layout.addWidget(self.combo_uat)

        main_layout.addSpacing(10)

        main_layout.addWidget(QLabel("Alege folderul unde va fi salvat proiectul:"))
        path_layout = QHBoxLayout()

        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Folderul proiectului")
        path_layout.addWidget(self.path_input)

        browse_button = QPushButton("Alege")
        browse_button.clicked.connect(self._browse_folder)
        path_layout.addWidget(browse_button)

        main_layout.addLayout(path_layout)

        main_layout.addSpacing(20)

        buttons_layout = QHBoxLayout()
        submit_button = QPushButton("Creare")
        submit_button.clicked.connect(self.accept)

        cancel_button = QPushButton("Renunță")
        cancel_button.clicked.connect(self.reject)

        buttons_layout.addStretch()
        buttons_layout.addWidget(submit_button)
        buttons_layout.addWidget(cancel_button)
        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

    def _update_uat_dropdown(self):
        """Filters and updates the UAT combobox depending on selected Județ."""
        self.combo_uat.clear()

        # Get the selected Judet's siruta code stored in its user data slot
        selected_judet_siruta = self.combo_jud.currentData()
        if selected_judet_siruta is None:
            return

        # Fetch child UATs for this specific parent ID
        child_uats = self.uats_by_judet.get(selected_judet_siruta, [])

        # Sort UATs alphabetically using the localized string representation
        sorted_uats = sorted(child_uats, key=lambda item: locale.strxfrm(item[1]))

        # Repopulate the dependent combobox
        for siruta_id, uat_name in sorted_uats:
            self.combo_uat.addItem(uat_name, siruta_id)


    def _browse_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Alege folder")
        if folder_path:
            self.path_input.setText(folder_path)

    def get_values(self):
        return {
            "pug": self.combo_pug.currentText(),
            "uat": self.combo_uat.currentText(),
            "siruta": self.combo_uat.currentData(),
            "path": self.path_input.text(),
        }


def run(iface):
    """Punct de intrare apelat din actiunea de plugin."""
    try:
        _run_impl(iface)
    except _AbortLoad as exc:
        QMessageBox.warning(iface.mainWindow(), "Proiect nou PUG", str(exc))
    except Exception as exc:  # nu lasa o eroare neasteptata sa inchida QGIS
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Proiect nou PUG - eroare",
            f"A aparut o eroare la crearea proiectului:\n{exc}\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )


def _run_impl(iface):
    _set_romanian_locale()

    try:
        default_package = resolve_template_dir(ensure_active_copy=True)
    except TemplateNotFoundError as exc:
        raise _AbortLoad(str(exc))
    default_gpkg = default_package + GPKG_RELATIVE

    if active_copy_outdated():
        QMessageBox.information(
            iface.mainWindow(),
            "Proiect nou PUG",
            "Sablonul activ (folosit pentru acest proiect) pare sa fie dintr-o "
            "versiune mai veche decat cel inclus in plugin.\n\n"
            "Recomandat: deschide \"Despre PUG Tools\" si apasa \"Actualizeaza\" la "
            "sectiunea \"Copie activa\" a sablonului, apoi reia crearea proiectului.",
        )

    uri_sirutas = f"{default_gpkg}|layername={SIRUTA_LAYER}"
    _sirutas = QgsVectorLayer(uri_sirutas, SIRUTA_LAYER, "ogr")

    if not _sirutas.isValid():
        raise _AbortLoad(
            f"Stratul cu datele SIRUTA ('{SIRUTA_LAYER}') nu s-a putut incarca din:\n{default_gpkg}"
        )

    # "_siruta" (schema 3.0.3) e o lista plata de localitati, fiecare purtand
    # codul si numele judetului/UAT-ului parinte - nu mai are randuri separate
    # de nivel judet/UAT (niv=1/niv=2) ca sablonul vechi. Judetele si UAT-urile
    # se deduc dintr-o singura trecere peste toate localitatile.
    judete_dict = {}  # {siruta_jud: judet}
    uat_judet = {}  # {siruta_uat: siruta_jud}
    uat_name = {}  # {siruta_uat: uat}

    fields = _sirutas.fields()
    subset = [
        fields.indexOf(name)
        for name in ("siruta_jud", "judet", "siruta_uat", "uat")
    ]
    request = QgsFeatureRequest().setSubsetOfAttributes(subset)
    for feature in _sirutas.getFeatures(request):
        jud_id = int(feature["siruta_jud"])
        judete_dict.setdefault(jud_id, feature["judet"])

        uat_id = int(feature["siruta_uat"])
        uat_judet[uat_id] = jud_id
        uat_name[uat_id] = feature["uat"]

    uats_by_judet = {}  # {parent_siruta: [(siruta_uat, uat_name), ...]}
    for uat_id, jud_id in uat_judet.items():
        uats_by_judet.setdefault(jud_id, []).append((uat_id, uat_name[uat_id]))

    # Instantiate form with structured dict arrays
    form = _CustomInputForm(judete_dict=judete_dict, uats_by_judet=uats_by_judet, parent=iface.mainWindow())

    if form.exec() != QDialog.DialogCode.Accepted:
        iface.messageBar().pushInfo("Proiect nou PUG", "Nu s-a intamplat nimic")
        return

    ui_input = form.get_values()
    uat_name = _ctext(ui_input["uat"]).upper()
    siruta = str(ui_input["siruta"])
    pug = ui_input["pug"]

    if not ui_input["path"]:
        raise _AbortLoad("Nu a fost selectat un folder de destinatie.")
    if siruta is None or siruta == "None":
        raise _AbortLoad("Nu a fost selectat un UAT valid din lista.")

    # Limita administrativa a UAT-ului este preluata dinamic (WFS filtrat
    # server-side, cu fallback pe cache local) in loc sa fie inclusa in
    # sablon - vezi tools/uat_boundary.py pentru strategie si motivatie
    # (evitarea unui set national de date de ~70-120 MB in plugin/proiect).
    # Doar DATELE sunt preluate devreme (inainte de a calcula numele
    # proiectului, care are nevoie de indicativul judetului - nu mai e
    # hardcodat la Harghita) - scrierea efectiva ca strat de referinta in
    # GPKG se intampla mai jos, dupa ce fisierul exista pe disc (vezi
    # uat_boundary.write_boundary_layer).
    try:
        boundary_attrs, boundary_geometry = uat_boundary.fetch_uat_boundary_data(siruta)
    except uat_boundary.UatBoundaryError as exc:
        raise _AbortLoad(
            "Nu s-a putut prelua limita administrativa a UAT-ului selectat "
            f"(SIRUTA {siruta}):\n\n{exc}"
        )
    county_abbr = boundary_attrs["countyMn"]

    base = county_abbr + "_" + uat_name + "_" + siruta + "_" + pug + "_AAAALLZZ"
    new_path = ui_input["path"] + "/" + base
    newfile = base + ".gpkg"

    o_path = new_path + "/" + GPKG_RELATIVE
    n_path = new_path + "/" + GPKG_FOLDER + newfile

    package = n_path
    maingroup_name = "_".join(base.split("_")[:-1])

    project_name = pug + " " + uat_name
    project_path = "/".join(package.split("/")[:-3])

    # --- copiere sablon ---
    shutil.copytree(default_package, new_path, dirs_exist_ok=True)
    shutil.move(o_path, n_path)
    _set_versiune_tip(package, pug)

    # --- configurare proiect QGIS ---
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    canvas = iface.mapCanvas()
    ltv = iface.layerTreeView()
    project.setFilePathStorage(Qgis.FilePathType.Relative)

    maingroup = root.insertGroup(0, maingroup_name)
    refgroup = maingroup.addGroup(REF_GROUP_NAME)

    def add_layer_to(gpkg, layer_name, group):
        newlayer = QgsVectorLayer(gpkg + "|layername=" + layer_name, layer_name, "ogr")
        project.addMapLayer(newlayer, False)
        group.addLayer(newlayer)
        tl = root.findLayer(newlayer.id())
        if tl is not None:
            tl.setExpanded(False)
        return newlayer

    def create_uat(target_layer, geom, uat_name_, siruta_):
        """Helper pastrat din scriptul original; neapelat implicit in acest flux."""
        feat = QgsFeature()
        feat.setFields(target_layer.fields())
        feat.setGeometry(geom)
        feat.setAttributes([NULL, siruta_, "Harghita", uat_name_, "Local"])
        feat["ArieADM"] = round(geom.area() / 10000, 2)
        feat["AriePlan"] = feat["ArieADM"]

        iface.setActiveLayer(target_layer)
        res, out_feats = target_layer.dataProvider().addFeatures([feat])
        target_layer.commitChanges()
        return out_feats[0] if res and out_feats else None

    # init straturi de referinta custom / virtuale
    for rl in V_LAYER_REQ:
        add_layer_to(package, rl, refgroup)

    vlayer = virtual_layers.create_vref_layer(virtual_layers.VREF_SZF_ZRS_D_NAME)
    project.addMapLayer(vlayer, False)
    refgroup.addLayer(vlayer)

    # incarca restul gpkg-ului: straturile de referinta intai, cele normale dupa
    ref_layers = []
    regular_layers = []
    ds = ogr.Open(package)
    if ds is None:
        raise _AbortLoad(f"Nu s-a putut deschide fisierul GPKG copiat:\n{package}")

    for ogr_layer in ds:
        l_name = ogr_layer.GetName()
        if l_name in DO_NOT_IMPORT or l_name == uat_boundary.LAYER_NAME:
            continue
        if l_name.startswith(("~REF", "_", "sys__")):
            ref_layers.append(l_name)
        else:
            regular_layers.append(l_name)
    ds = None

    for l_name in sorted(ref_layers):
        add_layer_to(package, l_name, refgroup)
    for l_name in sorted(regular_layers):
        add_layer_to(package, l_name, maingroup)

    # scrie limita UAT-ului (preluata mai sus) ca strat de referinta in
    # GPKG-ul proiectului - creeaza tabelul "~REF_UAT" daca sablonul nu il
    # avea deja (gol), altfel doar insereaza inregistrarea - vezi
    # uat_boundary.write_boundary_layer. Exclus in mod deliberat din bucla
    # generica de mai sus (l_name == uat_boundary.LAYER_NAME), tocmai pentru
    # ca e scris/populat aici, nu doar incarcat ca atare.
    try:
        uats_layer = uat_boundary.write_boundary_layer(package, boundary_attrs, boundary_geometry)
    except uat_boundary.UatBoundaryError as exc:
        raise _AbortLoad(
            "Nu s-a putut scrie limita administrativa a UAT-ului in fisierul GPKG:\n\n"
            f"{exc}"
        )
    boundary_feature = next(uats_layer.getFeatures())

    project.addMapLayer(uats_layer, False)
    refgroup.addLayer(uats_layer)
    tl = root.findLayer(uats_layer.id())
    if tl is not None:
        tl.setExpanded(False)

    # muta grupul de referinta la final
    new_ref_group = refgroup.clone()
    maingroup.insertChildNode(-1, new_ref_group)
    maingroup.removeChildNode(refgroup)
    new_ref_group.setItemVisibilityChecked(False)

    # verifica daca exista deja o intrare PlanSpatial
    ps_layers = project.mapLayersByName("PlanSpatial")
    if not ps_layers:
        raise _AbortLoad("Stratul 'PlanSpatial' nu a fost gasit in sablon.")
    ps = ps_layers[0]

    uat_feature = next(ps.getFeatures(), False)

    if uat_feature is False and pug == "PUG":
        ps.commitChanges()
        with edit(ps):
            f = boundary_feature
            geom = f.geometry()

            feat = QgsFeature()
            feat.setFields(ps.fields())
            feat.setGeometry(geom)
            feat.setAttributes(
                [
                    NULL,
                    f["county"],
                    f["name"],
                    "Local",
                    "PUG " + f["name"],
                    0,
                    datetime.now(),
                    datetime.now(),
                    "În curs de elaborare",
                    round(geom.area() / 10000, 2),
                    0,
                    round(geom.area() / 10000, 2),
                    siruta,
                ]
            )
            ps.dataProvider().addFeatures([feat])

    # ordonare straturi in panoul de straturi (cosmetic)
    for l_name in V_LAYER_REQ:
        matched = project.mapLayersByName(l_name)
        if matched:
            ltv.setCurrentLayer(matched[0])
            ltv.defaultActions().moveToBottom()

    v_ref_matched = project.mapLayersByName("~vREF_SZF_ZRS_D")
    if v_ref_matched:
        ltv.setCurrentLayer(v_ref_matched[0])
        ltv.defaultActions().moveToBottom()

    ltv.setCurrentLayer(uats_layer)
    ltv.defaultActions().moveToBottom()
    ltv.setCurrentLayer(ps)
    iface.setActiveLayer(ps)

    new_ref_group.setExpanded(False)

    # zoom la UAT-ul continut
    uats_layer.select(boundary_feature.id())
    bbox = uats_layer.boundingBoxOfSelected()
    canvas.refresh()
    canvas.waitWhileRendering()
    canvas.setExtent(bbox.buffered(bbox.height() * 0.05))
    canvas.refresh()

    project.write(project_path + "/" + project_name + ".qgz")

    # actualizare sursa widget-uri de tip "relatie catre alt strat" + salvare stiluri
    style_names = []
    ps_layer = project.mapLayersByName("PlanSpatial")[0]
    path = ps_layer.source()
    match = re.search(r".*/(.*)\.", path)
    gpkg_stem = match.group(1) if match else newfile.rsplit(".", 1)[0]
    rel_path = gpkg_stem + "/0_Seturi_date_spatiale/" + gpkg_stem + ".gpkg"

    all_styles = None
    for lyr in project.mapLayers().values():
        for i, _field in enumerate(lyr.fields()):
            widget_config = lyr.editorWidgetSetup(i).config()
            if "LayerSource" in widget_config.keys():
                widget_type = lyr.editorWidgetSetup(i).type()
                widget_config = dict(widget_config)
                widget_config["LayerSource"] = re.sub(
                    r"^.*/.*\.gpkg", rel_path, widget_config["LayerSource"]
                )
                new_widget = QgsEditorWidgetSetup(widget_type, widget_config)
                lyr.setEditorWidgetSetup(i, new_widget)

        lyr.commitChanges()

        if not lyr.name().startswith(REFERENCE_PREFIXES):
            c_style = lyr.name() + "_style"
            lyr.styleManager().renameStyle(lyr.styleManager().currentStyle(), c_style)
            save_style_to_database(lyr, c_style, "", True, "")
            style_names.append(c_style)
            all_styles = lyr.listStylesInDatabase()

    if all_styles is not None:
        for i, n in enumerate(all_styles[1]):
            keeper = all_styles[2][i] in style_names
            if not keeper:
                ps_layer.deleteStyleFromDatabase(n)

    project.reloadAllLayers()

    iface.messageBar().pushSuccess(
        "Proiect nou PUG", f"Proiectul '{project_name}' a fost creat cu succes."
    )
