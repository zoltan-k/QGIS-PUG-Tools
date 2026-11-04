# -*- coding: utf-8 -*-
"""
Unealta "Pregateste proiectul pentru validare oficiala": creeaza o copie
("instantanee") a folderului/fisierului GPKG al proiectului curent, cu data
de azi in locul placeholder-ului AAAALLZZ din numele sablonului, si o
arhiveaza intr-un fisier .zip. La final, proiectul original este redeschis
neschimbat.

Acesta este scriptul prepare_to_validate.py adaptat pentru a rula ca
actiune de plugin. Motivul pentru care butonul nu facea nimic in versiunea
anterioara a plugin-ului: actiunea era creata si adaugata in toolbar/meniu,
dar linia care leaga semnalul `triggered` de metoda care ruleaza codul
lipsea din plugin.py (`self.prepare_action.triggered.connect(...)`) - deci
click-ul pe buton nu declansa nimic. Vezi plugin.py pentru corectare.

In plus, adaptarea/curatarea scriptului insusi a corectat:
    - modulul expune acum un `run(iface)` la nivel de modul, asa cum se
      asteapta din plugin.py (project_loader.py foloseste aceeasi conventie);
      clasa Preparator originala nu expunea asa ceva (`preparator.run(...)`
      ar fi aruncat AttributeError, deoarece run() era doar metoda clasei).
    - clasa originala folosea `path` (nedefinit) in loc de `self.path` in
      interiorul __init__ - NameError la instantiere.
    - metoda run() a clasei originale era declarata `def run(iface):`, fara
      `self` - apelata ca metoda de instanta, parametrul `iface` ar fi
      primit de fapt instanta insasi (self), nu obiectul QGIS iface.
    - fiecare extragere bazata pe regex (nume de foldere dupa tiparul
      "..._AAAALLZZ") verifica acum daca potrivirea a reusit si opreste
      executia cu un mesaj clar, in loc de un AttributeError criptic pe
      '.group(1)' cand structura de foldere nu corespunde asteptarilor.
    - proiectul original este redeschis si daca operatia de copiere/arhivare
      esueaza la jumatate (bloc try/finally), pentru ca golirea proiectului
      (project.clear()) sa nu lase QGIS cu un canvas gol in caz de eroare.
    - erorile neasteptate sunt prinse si afisate intr-un QMessageBox, plus
      logate in QGIS Message Log ("PUG Tools"), in loc de print()-uri care
      nu sunt vizibile utilizatorului obisnuit al plugin-ului.

De ce se goleste proiectul (project.clear()) inainte de shutil.copytree:
    Fisierul .gpkg al proiectului curent este deschis si blocat de OGR cat
    timp straturile sunt incarcate. Pe Windows, acest lucru ar impiedica
    shutil.copytree() sa copieze folderul care contine acel .gpkg. Golirea
    proiectului elibereaza blocarea fisierului; la final, proiectul
    original este redeschis din project_file.
"""

import re
import shutil
import traceback
from datetime import datetime

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis, QgsMessageLog, QgsProject

LOG_TAG = "PUG Tools"

# placeholder folosit in numele folderelor/fisierelor sablon, inlocuit cu
# data curenta (YYYYMMDD) la pregatirea pentru validare.
DATE_PLACEHOLDER = "AAAALLZZ"


class _AbortPreparation(Exception):
    """Ridicata pentru a opri operatia in mod controlat, cu un mesaj clar pentru utilizator."""


def run(iface):
    """Punct de intrare apelat din actiunea de plugin."""
    try:
        _run_impl(iface)
    except _AbortPreparation as exc:
        QMessageBox.warning(iface.mainWindow(), "Pregatire pentru validare", str(exc))
    except Exception as exc:  # nu lasa o eroare neasteptata sa inchida QGIS
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Pregatire pentru validare - eroare",
            f"A aparut o eroare la pregatirea proiectului:\n{exc}\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )


def _extract(pattern, source, description):
    match = re.search(pattern, source)
    if not match:
        raise _AbortPreparation(
            f"Nu s-a putut determina {description}.\n\n"
            f"Structura de foldere/nume asteptata (..._{DATE_PLACEHOLDER}...) "
            f"nu a fost gasita in:\n{source}"
        )
    return match.group(1)


def _run_impl(iface):
    project = QgsProject.instance()
    project_file = project.fileName()

    if not project_file:
        raise _AbortPreparation("Proiectul curent nu a fost inca salvat pe disc.")

    ps_layers = project.mapLayersByName("PlanSpatial")
    if not ps_layers:
        raise _AbortPreparation(
            "Stratul 'PlanSpatial' nu a fost gasit in proiectul curent."
        )
    path = ps_layers[0].source()

    pug_folder = _extract(
        r"(.*/HR_[^/]+_" + DATE_PLACEHOLDER + r")/.*\|",
        path,
        "folderul proiectului PUG",
    )
    gpkg_rel_path = _extract(
        r".*" + DATE_PLACEHOLDER + r"/(.*)\|",
        path,
        "calea relativa a fisierului GPKG",
    )
    root_folder = _extract(
        r"(.*)/HR_[^/]+_" + DATE_PLACEHOLDER + r"/.*\|",
        path,
        "folderul radacina",
    )

    # comite toate modificarile din straturile vectoriale editabile
    for layer in project.mapLayers().values():
        if layer.type() == Qgis.LayerType.Vector:
            layer.commitChanges()

    project.commitChanges()
    project.write()

    # goleste proiectul pentru a elibera blocarea fisierului .gpkg (vezi
    # explicatia din antetul modulului), inainte de copierea pe disc
    project.clear()

    try:
        thisday = datetime.today().strftime("%Y%m%d")

        new_pug_folder = pug_folder.replace(DATE_PLACEHOLDER, thisday)
        newfile = gpkg_rel_path.replace(DATE_PLACEHOLDER, thisday)
        base_folder = _extract(
            r".*/(HR_[^/]+_" + thisday + r")", new_pug_folder, "folderul de baza"
        )

        shutil.copytree(pug_folder, new_pug_folder, dirs_exist_ok=True)

        o_path = new_pug_folder + "/" + gpkg_rel_path
        n_path = new_pug_folder + "/" + newfile
        shutil.move(o_path, n_path)

        shutil.make_archive(
            new_pug_folder, "zip", root_dir=root_folder, base_dir=base_folder
        )
    finally:
        # indiferent de rezultatul copierii/arhivarii, proiectul original
        # trebuie redeschis - altfel utilizatorul ramane cu QGIS gol.
        project.read(project_file)

    iface.messageBar().pushSuccess(
        "Pregatire pentru validare",
        f"Arhiva a fost creata: {new_pug_folder}.zip",
    )
