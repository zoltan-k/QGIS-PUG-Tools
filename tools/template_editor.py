# -*- coding: utf-8 -*-
"""
Unealta "Editeaza sablonul" / "Salveaza sablonul": permite editarea in
siguranta a structurii, stilurilor si proprietatilor de camp ale sablonului
PUG, fara sa lase featureuri noi in straturile care trebuie sa ramana goale
in proiectele create ulterior din sablon.

Doua actiuni de plugin, folosite impreuna:

    load_template(iface) - "Editeaza sablonul":
        Porneste un proiect QGIS nou, gol (ca "Fisier > Proiect nou"), si
        incarca in el toate straturile din copia ACTIVA a sablonului (vezi
        template_paths.py), cu ACEEASI structura de arbore folosita la
        "Proiect nou PUG": straturile cu continut la nivelul radacina,
        straturile de referinta (nume care incep cu "~" sau "_") grupate
        intr-un grup "REF" adaugat la finalul arborelui (jos), expandat
        implicit. Retine, pentru fiecare strat, setul de FID-uri prezente la
        incarcare (prin project.writeEntry(), vezi mai jos), pentru a putea
        detecta ulterior orice feature adaugat in timpul editarii.

    save_template(iface) - "Salveaza sablonul":
        1. Comite orice editare in curs (Toggle Editing -> Save) pe toate
           straturile.
        2. Compara FID-urile curente cu cele retinute la incarcare; daca
           gaseste featureuri noi, intreaba utilizatorul daca vrea sa fie
           sterse automat inainte de salvare (sablonul trebuie sa ramana
           fara continut in straturile operationale).
        3. Salveaza stilul curent al fiecarui strat "de continut" (nu cele
           de referinta, prefixate cu "~" sau "_") in tabela layer_styles
           din gpkg.
        4. Elibereaza blocarea fisierului (project.clear()) si corecteaza
           contorul intern SQLite (sqlite_sequence) al fiecarui strat, ca
           urmatorul feature adaugat intr-un proiect nou sa primeasca
           FID=1 daca stratul a ramas gol. Acest pas este necesar pentru ca
           straturile GeoPackage create de QGIS folosesc de regula
           "INTEGER PRIMARY KEY AUTOINCREMENT" - SQLite NU refoloseste
           FID-uri sterse decat daca acest contor este corectat manual.

De ce modificarile persista intre actualizari de plugin:
    Ambele actiuni lucreaza pe copia ACTIVA a sablonului (in profilul QGIS),
    niciodata pe folderul "templates/" din interiorul plugin-ului. Acesta
    din urma este doar "samanta" folosita o singura data, la prima
    utilizare, pentru a popula copia activa - vezi template_paths.py.
"""

import json
import sqlite3
import traceback

from osgeo import ogr
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsVectorLayer

from . import save_style_to_database
from .template_paths import GPKG_RELATIVE, TemplateNotFoundError, resolve_template_dir

LOG_TAG = "PUG Tools"

# QgsProject nu are setCustomProperty()/customProperty() (acelea exista pe
# QgsMapLayer, nu pe QgsProject) - la nivel de proiect, perechile
# cheie/valoare se stocheaza prin writeEntry()/readEntry(), cu un "scope"
# (grup) si o cheie in stil de cale ("/"-delimitata).
_ENTRY_SCOPE = "PUGTools"
_GPKG_PATH_KEY = "template_edit/gpkg_path"
_BASELINE_KEY = "template_edit/baseline"

# straturi excluse de la verificarea "featureuri noi" si de la salvarea
# stilului - contin date de referinta/lookup, populate intentionat.
# "sys__" = tabele de sistem (ex. "sys__versiune", sablon >= 3.1.0): fara stil.
_REFERENCE_PREFIXES = ("~", "_", "sys__")

# acelasi nume de grup folosit de project_loader.py/package_updater.py
# pentru straturile de referinta.
REF_GROUP_NAME = "REF"


class _AbortEdit(Exception):
    """Ridicata pentru a opri operatia in mod controlat, cu un mesaj clar pentru utilizator."""


def load_template(iface):
    """Punct de intrare pentru actiunea 'Editeaza sablonul'."""
    try:
        _load_impl(iface)
    except _AbortEdit as exc:
        QMessageBox.warning(iface.mainWindow(), "Editare sablon", str(exc))
    except Exception:
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Editare sablon - eroare",
            "A aparut o eroare la incarcarea sablonului.\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )


def save_template(iface):
    """Punct de intrare pentru actiunea 'Salveaza sablonul'."""
    try:
        _save_impl(iface)
    except _AbortEdit as exc:
        QMessageBox.warning(iface.mainWindow(), "Salvare sablon", str(exc))
    except Exception:
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Salvare sablon - eroare",
            "A aparut o eroare la salvarea sablonului.\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )


def _load_impl(iface):
    try:
        template_dir = resolve_template_dir(ensure_active_copy=True)
    except TemplateNotFoundError as exc:
        raise _AbortEdit(str(exc))

    gpkg_path = template_dir + GPKG_RELATIVE

    ds = ogr.Open(gpkg_path, 0)
    if ds is None:
        raise _AbortEdit(f"Nu s-a putut deschide fisierul GPKG al sablonului:\n{gpkg_path}")
    layer_names = sorted(lyr.GetName() for lyr in ds if lyr.GetName() != "layer_styles")
    ds = None

    if not layer_names:
        raise _AbortEdit(f"Fisierul GPKG al sablonului nu contine niciun strat:\n{gpkg_path}")

    # porneste un proiect nou, gol (ca "Fisier > Proiect nou"); daca
    # utilizatorul anuleaza promptul de salvare, nu facem nimic mai departe.
    if not iface.newProject():
        return

    project = QgsProject.instance()
    root = project.layerTreeRoot()

    content_names = [n for n in layer_names if not n.startswith(_REFERENCE_PREFIXES)]
    ref_names = [n for n in layer_names if n.startswith(_REFERENCE_PREFIXES)]

    baseline = {}

    def _add_layer(name, parent_group):
        vlayer = QgsVectorLayer(f"{gpkg_path}|layername={name}", name, "ogr")
        if not vlayer.isValid():
            return
        project.addMapLayer(vlayer, False)
        parent_group.addLayer(vlayer)
        baseline[vlayer.id()] = {
            "name": name,
            "fids": [f.id() for f in vlayer.getFeatures()],
        }

    for name in content_names:
        _add_layer(name, root)

    if ref_names:
        ref_group = root.addGroup(REF_GROUP_NAME)
        ref_group.setExpanded(True)
        for name in ref_names:
            _add_layer(name, ref_group)

    project.writeEntry(_ENTRY_SCOPE, _GPKG_PATH_KEY, gpkg_path)
    project.writeEntry(_ENTRY_SCOPE, _BASELINE_KEY, json.dumps(baseline))

    iface.messageBar().pushInfo(
        "Editare sablon",
        "Sablonul a fost incarcat intr-un proiect nou. Fa modificarile "
        "dorite (structura, stiluri, proprietati de camp), apoi apasa "
        "'Salveaza sablonul'.",
    )


def _save_impl(iface):
    project = QgsProject.instance()
    gpkg_path, gpkg_path_ok = project.readEntry(_ENTRY_SCOPE, _GPKG_PATH_KEY, "")
    baseline_json, baseline_ok = project.readEntry(_ENTRY_SCOPE, _BASELINE_KEY, "")

    if not gpkg_path_ok or not baseline_ok or not gpkg_path or not baseline_json:
        raise _AbortEdit(
            "Proiectul curent nu a fost pornit cu 'Editeaza sablonul', asa ca "
            "nu se stie ce sablon trebuie salvat. Foloseste intai butonul "
            "'Editeaza sablonul'."
        )

    baseline = json.loads(baseline_json)

    vector_layers = [
        layer for layer in project.mapLayers().values() if layer.type() == Qgis.LayerType.Vector
    ]

    # 1. comite orice editare in curs
    for layer in vector_layers:
        if layer.isEditable():
            layer.commitChanges()

    # 2. detecteaza featureuri noi fata de momentul incarcarii
    additions = {}
    for layer in vector_layers:
        info = baseline.get(layer.id())
        if info is None:
            continue  # strat adaugat manual in timpul sesiunii; ignorat aici
        original_fids = set(info["fids"])
        current_fids = {f.id() for f in layer.getFeatures()}
        new_fids = current_fids - original_fids
        if new_fids:
            additions[layer] = new_fids

    if additions:
        summary_lines = "\n".join(
            f"  - {layer.name()}: +{len(fids)} feature(uri)" for layer, fids in additions.items()
        )
        answer = QMessageBox.question(
            iface.mainWindow(),
            "Featureuri noi detectate",
            "Urmatoarele straturi au acum featureuri fata de sablonul "
            f"original:\n\n{summary_lines}\n\n"
            "Sablonul trebuie sa ramana fara continut in straturile "
            "operationale, ca proiectele noi sa porneasca de la FID=1.\n\n"
            "Stergi automat featureurile noi inainte de salvare?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        if answer == QMessageBox.StandardButton.Yes:
            for layer, fids in additions.items():
                layer.startEditing()
                layer.dataProvider().deleteFeatures(list(fids))
                layer.commitChanges()

    # 3. salveaza stilul curent (simbolizare, valori implicite, widget-uri de
    #    camp etc.) in gpkg (layer_styles) pentru straturile de continut (nu
    #    cele de referinta/virtuale) - verificat, nu doar incercat: daca
    #    salvarea stilului esueaza pentru un strat, utilizatorul trebuie sa
    #    stie (altfel modificarile de stil facute in sesiune s-ar pierde
    #    tacut la project.clear() de mai jos).
    style_failures = []
    for layer in vector_layers:
        if layer.name().startswith(_REFERENCE_PREFIXES):
            continue
        try:
            current_style = layer.styleManager().currentStyle() or layer.name()
            error_msg = save_style_to_database(layer, current_style, "", True, "")
            if error_msg:
                style_failures.append(f"{layer.name()}: {error_msg}")
        except Exception as exc:
            style_failures.append(f"{layer.name()}: {exc}")

    # 4. elibereaza blocarea fisierului (Windows) inainte de a corecta
    #    contoarele interne SQLite
    project.clear()

    _reset_autoincrement_counters(gpkg_path)

    if style_failures:
        QgsMessageLog.logMessage(
            "Stiluri nesalvate la 'Salveaza sablonul':\n" + "\n".join(style_failures),
            LOG_TAG,
            level=Qgis.Warning,
        )
        QMessageBox.warning(
            iface.mainWindow(),
            "Salvare sablon - unele stiluri nu au putut fi salvate",
            "Sablonul a fost salvat, dar stilul urmatoarelor straturi NU a putut "
            "fi scris in baza de date (modificarile de stil pentru ele sunt "
            "pierdute):\n\n" + "\n".join(style_failures) +
            f"\n\nDetalii in QGIS Message Log (panou '{LOG_TAG}').",
        )
    else:
        iface.messageBar().pushSuccess(
            "Salvare sablon", f"Modificarile au fost salvate in sablon:\n{gpkg_path}"
        )


def _reset_autoincrement_counters(gpkg_path):
    """
    Corecteaza sqlite_sequence pentru fiecare strat de tip feature din gpkg,
    astfel incat urmatorul FID alocat sa corespunda numarului real de
    featureuri ramase (sau sa inceapa de la 1 daca stratul e gol), indiferent
    de FID-uri folosite si apoi sterse in timpul editarii sablonului.

    Tabelele GeoPackage create de QGIS/GDAL folosesc de regula
    "fid INTEGER PRIMARY KEY AUTOINCREMENT" - fara aceasta corectie, SQLite
    nu ar reutiliza FID-urile eliberate prin stergere, iar un proiect nou
    creat din sablon ar porni de la un FID mai mare decat 1.
    """
    conn = sqlite3.connect(gpkg_path)
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )
        if cur.fetchone() is None:
            return  # niciun tabel din acest gpkg foloseste AUTOINCREMENT

        cur.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")
        table_names = [row[0] for row in cur.fetchall()]

        for table_name in table_names:
            cur.execute(f'SELECT MAX("fid") FROM "{table_name}"')
            max_fid = cur.fetchone()[0]
            if max_fid is None:
                cur.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table_name,))
            else:
                cur.execute(
                    "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                    (max_fid, table_name),
                )
        conn.commit()
    finally:
        conn.close()
