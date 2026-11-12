# -*- coding: utf-8 -*-
"""
Unealta "Copie de siguranta portabila": creeaza un singur fisier .zip, in
acelasi folder cu fisierul .qgz al proiectului activ, numit ca folderul
pachetului PUG (ex. HR_BALAN_83464_PUG_AAAALLZZ.zip), cu structura:

    PUG Balan.qgz                       (rescris cu cai STRICT relative)
    HR_BALAN_83464_PUG_AAAALLZZ\\        (intregul folder al pachetului)
        0_Seturi_date_spatiale\\HR_BALAN_83464_PUG_AAAALLZZ.gpkg
        1_Studii_fundamentare\\* ... 4_Avize_acorduri\\*
    Alte_surse\\*                        (doar daca proiectul are alte surse)

Arhiva poate fi dezarhivata oriunde si proiectul se deschide direct.

Fluxul (in aceasta ordine):
    1. Modificari nesalvate (proiect SAU straturi in editare): o singura
       intrebare Da/Nu pentru salvare. "Da" + esec la salvare = oprire.
       "Nu" = copia contine ultima versiune salvata pe disc.
    2. Proiectul de pe disc este incarcat intr-o instanta QgsProject separata
       (proiectul deschis in QGIS nu este modificat, inchis sau redeschis).
    3. Un singur avertisment (Ok/Anuleaza) daca exista:
         - straturi din memorie  -> se pierd (continutul lor nu e salvabil);
         - straturi bazate pe fisiere din afara folderului pachetului ->
           fisierele (cu fisierele auxiliare, ex. .dbf/.shx la shapefile) se
           copiaza in Alte_surse, iar caile din proiect devin relative;
         - straturi URI (WMS, PostGIS, WFS...) si straturi virtuale ->
           raman neschimbate.
    4. .qgz-ul este scris de instanta separata cu stocare relativa, sub un
       nume temporar in ACELASI folder (caile relative se calculeaza fata de
       folderul fisierului scris), apoi sursele straturilor mutate in
       Alte_surse sunt rescrise direct in XML-ul proiectului. Nu se creeaza
       nicio copie intermediara a datelor pe disc: fisierele sunt citite din
       locul lor original direct in arhiva.
    5. Verificare finala: daca in XML mai ramane o cale absoluta (in afara
       straturilor URI/virtuale pastrate intentionat), nu se livreaza arhiva.
"""

import io
import os
import re
import sqlite3
import traceback
import zipfile
from datetime import datetime
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis, QgsMessageLog, QgsProject, QgsProviderRegistry

LOG_TAG = "PUG Tools"
DATE_PLACEHOLDER = "AAAALLZZ"
EXTRA_FOLDER = "Alte_surse"

# litera de unitate (C:/ sau C:\) sau cale UNC; lookbehind-ul exclude "http://".
_ABS_PATH_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\[A-Za-z0-9_.$-]+\\")

# fisiere auxiliare uzuale (extensii care inlocuiesc extensia fisierului
# principal) si sufixe adaugate la numele complet (ex. "x.gpkg-wal").
_SIDECAR_EXTS = (
    ".shx", ".dbf", ".prj", ".cpg", ".qpj", ".qix", ".sbn", ".sbx", ".idm", ".ind",
    ".atx", ".fix", ".dat", ".map", ".id", ".mid", ".csvt", ".tfw", ".tifw", ".wld",
    ".jgw", ".pgw", ".rrd", ".msk", ".qml", ".qmd",
)
_SIDECAR_SUFFIXES = (
    "-wal", "-shm", "-journal", ".aux.xml", ".ovr", ".xml", ".qmd", ".qix",
)


class _AbortBackup(Exception):
    """Ridicata pentru a opri operatia in mod controlat, cu un mesaj clar pentru utilizator."""


def run(iface):
    """Punct de intrare apelat din actiunea de plugin."""
    try:
        _run_impl(iface)
    except _AbortBackup as exc:
        QMessageBox.warning(iface.mainWindow(), "Copie de siguranta portabila", str(exc))
    except Exception as exc:  # nu lasa o eroare neasteptata sa inchida QGIS
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Copie de siguranta portabila - eroare",
            f"A aparut o eroare la crearea copiei portabile:\n{exc}\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )


# -- utilitare de cai --------------------------------------------------------

def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _is_inside(path, folder):
    path, folder = _norm(path), _norm(folder)
    return path == folder or path.startswith(folder + os.sep)


def _layer_file_path(layer):
    """Calea absoluta a fisierului unui strat bazat pe fisier, sau None (memorie, URI, virtual, /vsi...)."""
    if layer.providerType() in ("memory", "virtual"):
        return None
    try:
        parts = QgsProviderRegistry.instance().decodeUri(layer.providerType(), layer.source())
    except Exception:
        return None
    path = parts.get("path") if isinstance(parts, dict) else None
    if path and not path.startswith("/vsi") and os.path.isabs(path):
        return path
    return None


# -- analiza proiectului -----------------------------------------------------

def _find_package_folder(project, project_dir):
    """
    Folderul pachetului PUG: subfolderul de nivel 1 (fata de folderul .qgz) care
    contine straturile proiectului, cu preferinta pentru cel al stratului
    'PlanSpatial'. Numele folderului/GPKG-ului nu conteaza (poate contine deja
    o data in loc de AAAALLZZ).
    """
    candidates = []
    ps = project.mapLayersByName("PlanSpatial")
    ordered = list(ps) + [l for l in project.mapLayers().values() if l not in ps]
    for layer in ordered:
        path = _layer_file_path(layer)
        if not path or not _is_inside(path, project_dir):
            continue
        top = os.path.relpath(path, project_dir).split(os.sep)[0]
        if top in ("", ".", ".."):
            continue
        folder = os.path.join(project_dir, top)
        if os.path.isdir(folder) and folder not in candidates:
            candidates.append(folder)

    if not candidates:
        raise _AbortBackup(
            "Nu s-a gasit folderul pachetului PUG.\n\n"
            "Folderul pachetului trebuie sa fie intr-un subfolder al folderului "
            "in care este salvat fisierul .qgz:\n" + project_dir
        )
    # numele folderului nu conteaza (poate fi deja redenumit cu o data):
    # primul candidat este cel al stratului 'PlanSpatial'.
    return candidates[0]


def package_folder_for_gpkg(gpkg_path, project_dir):
    """
    Folderul pachetului unui GPKG (independent de numele folderului/fisierului):
    subfolderul de nivel 1 fata de `project_dir` care il contine, sau, daca
    GPKG-ul e in afara folderului proiectului, structura sablonului
    (<pachet>/0_Seturi_date_spatiale/<gpkg>). None daca nu exista.
    """
    if _is_inside(gpkg_path, project_dir):
        top = os.path.relpath(gpkg_path, project_dir).split(os.sep)[0]
        folder = os.path.join(project_dir, top)
        if top not in ("", ".", "..") and os.path.isdir(folder):
            return folder
        return None
    folder = os.path.dirname(os.path.dirname(os.path.abspath(gpkg_path)))
    return folder if os.path.isdir(folder) else None


def checkpoint_gpkgs(package_folder):
    """
    Muta continutul fisierelor -wal in fisierele .gpkg ale pachetului
    (PRAGMA wal_checkpoint(TRUNCATE)), inainte de arhivare, ca .gpkg + -wal + -shm
    sa fie consistente. Merge si cu QGIS deschis; best-effort - o eroare (fisier
    blocat etc.) nu opreste copia, care include oricum si fisierele -wal/-shm.
    """
    for root, _dirs, files in os.walk(package_folder):
        for fname in files:
            if not fname.lower().endswith(".gpkg"):
                continue
            path = os.path.join(root, fname)
            try:
                con = sqlite3.connect("file:" + path.replace("\\", "/").replace("?", "%3f").replace("#", "%23") + "?mode=rw", uri=True, timeout=5)
                try:
                    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    con.close()
            except Exception as exc:  # noqa: BLE001
                QgsMessageLog.logMessage(
                    f"Checkpoint WAL esuat pentru {path}: {exc}", LOG_TAG, level=Qgis.Warning
                )


def add_package_folder(zf, package_folder, project_dir):
    """
    Adauga in `zf` intregul folder al pachetului (toate subfolderele, inclusiv
    cele goale), cu caile relative la `project_dir`; pentru un pachet din afara
    lui `project_dir` se foloseste doar numele folderului pachetului.
    """
    base = project_dir if _is_inside(package_folder, project_dir) else os.path.dirname(package_folder)
    for root, dirs, files in os.walk(package_folder):
        if not dirs and not files:
            zf.write(root, os.path.relpath(root, base).replace(os.sep, "/") + "/")
        for fname in files:
            full = os.path.join(root, fname)
            zf.write(full, os.path.relpath(full, base).replace(os.sep, "/"))


def _classify_layers(project, package_folder):
    """
    Imparte straturile proiectului in:
        memory  : [layer]                      - se pierd
        outside : [(layer, abs_path)]          - fisiere din afara pachetului -> Alte_surse
        keep    : [layer]                      - URI/virtual/altele, raman neschimbate
    Straturile din folderul pachetului nu apar nicaieri (sunt deja in arhiva).
    Ridica _AbortBackup daca un fisier sursa lipseste de pe disc.
    """
    memory, outside, keep, missing = [], [], [], []
    for layer in project.mapLayers().values():
        if layer.providerType() == "memory":
            memory.append(layer)
            continue
        path = _layer_file_path(layer)
        if path is None:
            keep.append(layer)
        elif _is_inside(path, package_folder):
            continue
        elif not os.path.exists(path):
            missing.append(f"{layer.name()}  ->  {path}")
        else:
            outside.append((layer, path))
    if missing:
        raise _AbortBackup(
            "Fisierele sursa ale urmatoarelor straturi nu exista pe disc si nu pot "
            "fi incluse in copie:\n\n" + "\n".join(missing[:15])
            + ("\n..." if len(missing) > 15 else "")
            + "\n\nReface sau elimina aceste straturi, apoi reincearca."
        )
    return memory, outside, keep


def _unsaved_edit_layers(project):
    return [
        layer for layer in project.mapLayers().values()
        if layer.type() == Qgis.LayerType.Vector and layer.isEditable() and layer.isModified()
    ]


# -- fisiere de arhivat pentru un strat extern -------------------------------

def _source_files(path):
    """
    Lista (cale_absoluta, cale_relativa_fata_de_nume) a fisierelor de copiat
    pentru o sursa: fisierul + auxiliarele lui, sau, pentru un folder (ex.
    .gdb), tot continutul. Prima intrare este mereu sursa insasi.
    """
    if os.path.isdir(path):
        base = os.path.basename(path.rstrip("\\/"))
        out = []
        for root, _dirs, files in os.walk(path):
            for fname in files:
                full = os.path.join(root, fname)
                out.append((full, os.path.join(base, os.path.relpath(full, path))))
        return out, True

    base = os.path.basename(path)
    stem, _ext = os.path.splitext(path)
    stem_name = os.path.basename(stem)
    out = [(path, base)]
    seen = {_norm(path)}

    def add(full, name):
        if os.path.isfile(full) and _norm(full) not in seen:
            seen.add(_norm(full))
            out.append((full, name))

    for ext in _SIDECAR_EXTS:
        add(stem + ext, stem_name + ext)
    for suffix in _SIDECAR_SUFFIXES:
        add(path + suffix, base + suffix)
    return out, False


def _plan_extra_sources(outside):
    """
    Atribuie fiecarui fisier/folder extern un nume unic in Alte_surse.
    Returneaza (lista_arhivare [(abs, arcname)], mapare {abs_norm: nume_nou}).
    Fisierele cu acelasi nume provenite din foldere diferite primesc sufix _2, _3...
    """
    archive, mapping, used = [], {}, set()
    for _layer, path in outside:
        key = _norm(path)
        if key in mapping:
            continue
        files, is_dir = _source_files(path)
        main_name = os.path.basename(path.rstrip("\\/"))
        stem, ext = os.path.splitext(main_name)
        new_name, n = main_name, 1
        # numele nou trebuie sa fie liber si pentru auxiliare
        def names_for(prefix):
            if is_dir:
                return [os.path.join(prefix, os.path.relpath(f, path)) for f, _ in files]
            old_stem = os.path.splitext(main_name)[0]
            return [prefix + rel[len(old_stem):] if rel.startswith(old_stem) else rel
                    for _f, rel in files]
        while any(x.lower() in used for x in names_for(new_name if is_dir else os.path.splitext(new_name)[0])):
            n += 1
            new_name = f"{stem}_{n}{ext}"
        new_stem = os.path.splitext(new_name)[0]
        for full, rel in files:
            if is_dir:
                arc_rel = os.path.join(new_name, os.path.relpath(full, path))
            else:
                old_stem = os.path.splitext(main_name)[0]
                arc_rel = (new_stem + rel[len(old_stem):]) if rel.startswith(old_stem) else rel
            used.add(arc_rel.lower())
            archive.append((full, EXTRA_FOLDER + "/" + arc_rel.replace(os.sep, "/")))
        mapping[key] = new_name
    return archive, mapping


# -- scrierea .qgz portabil --------------------------------------------------

def _write_portable_project(other, project_file, relocations, keep_layers):
    """
    Scrie `other` cu cai relative si returneaza (bytes_proiect, avertismente_xml).
    relocations: [(layer, abs_path, nume_nou_in_Alte_surse)]
    """
    project_dir = os.path.dirname(project_file)
    ext = os.path.splitext(project_file)[1] or ".qgz"
    tmp_path = os.path.join(project_dir, f".pug_portabil_tmp_{os.getpid()}{ext}")

    other.setFilePathStorage(Qgis.FilePathType.Relative)
    try:
        if not other.write(tmp_path):
            raise _AbortBackup(
                f"Nu s-a putut scrie fisierul temporar:\n{tmp_path}\n{other.error()}"
            )
        xml_text, qgs_name, entries = _read_project_xml(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    # sursa asa cum a fost scrisa in XML, per id de strat
    written = {}
    for ml in ET.fromstring(xml_text).iter("maplayer"):
        lid, ds = ml.findtext("id"), ml.findtext("datasource")
        if lid and ds is not None:
            written[lid] = ds

    resolver = other.pathResolver()
    for layer, path, new_name in relocations:
        old_ds = written.get(layer.id())
        if old_ds is None:
            raise _AbortBackup(f"Stratul '{layer.name()}' nu a fost gasit in proiectul scris.")
        new_rel = "./" + EXTRA_FOLDER + "/" + new_name
        candidates = []
        try:
            candidates.append(resolver.writePath(path))
        except Exception:
            pass
        candidates += [path.replace("\\", "/"), path]
        try:
            candidates.append(os.path.relpath(path, project_dir).replace("\\", "/"))
        except ValueError:
            pass  # alta unitate decat proiectul (ex. T: vs D:) - nu exista cale relativa
        new_ds = None
        for cand in candidates:
            if cand and cand in old_ds:
                new_ds = old_ds.replace(cand, new_rel, 1)
                break
        if new_ds is None:
            raise _AbortBackup(
                f"Nu s-a putut rescrie sursa stratului '{layer.name()}':\n{old_ds}"
            )
        # sursa apare si ca atribut (ex. <layer-tree-layer source="...">), nu doar
        # in <datasource>: inlocuim ambele forme de escape.
        replaced = False
        for esc in (_esc_text, _esc_attr):
            if esc(old_ds) in xml_text:
                xml_text = xml_text.replace(esc(old_ds), esc(new_ds))
                replaced = True
        if not replaced:
            raise _AbortBackup(f"Sursa stratului '{layer.name()}' nu a fost gasita in XML.")

    # verificare: nicio cale absoluta in afara straturilor URI/virtuale pastrate
    scan = xml_text
    for layer in keep_layers:
        ds = written.get(layer.id())
        if ds:
            for esc in (_esc_text, _esc_attr):
                scan = scan.replace(esc(ds), "")
    absolute = _absolute_paths_in(scan)
    if absolute:
        raise _AbortBackup(
            "Proiectul contine inca cai absolute dupa conversie, deci arhiva nu ar "
            "fi portabila:\n\n" + "\n".join(sorted(set(absolute))[:10])
            + "\n\nNu s-a creat nicio arhiva."
        )

    return _pack_project(xml_text, qgs_name, entries, ext)


def _read_project_xml(path):
    """Returneaza (xml_text, nume_qgs_in_arhiva|None, {nume: bytes} celelalte intrari)."""
    if path.lower().endswith(".qgz"):
        with zipfile.ZipFile(path) as zf:
            qgs_name, text, others = None, None, {}
            for name in zf.namelist():
                data = zf.read(name)
                if qgs_name is None and name.lower().endswith(".qgs"):
                    qgs_name, text = name, data.decode("utf-8")
                else:
                    others[name] = data
        if qgs_name is None:
            raise _AbortBackup("Fisierul .qgz generat nu contine un fisier .qgs.")
        return text, qgs_name, others
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read(), None, {}


def _pack_project(xml_text, qgs_name, entries, ext):
    if ext.lower() != ".qgz":
        return xml_text.encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(qgs_name, xml_text.encode("utf-8"))
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _esc_text(value):
    return escape(value)


def _esc_attr(value):
    return escape(value, {'"': "&quot;"})


def _absolute_paths_in(xml_text):
    """Atribute/elemente de tip cale care contin cai absolute."""
    found = []
    for match in re.finditer(r'(?:datasource|source|path|filename|file|uri|url)="([^"]*)"', xml_text):
        if _ABS_PATH_RE.search(match.group(1)):
            found.append(match.group(1))
    for match in re.finditer(r"<(?:Path|path|datasource)>([^<]*)<", xml_text):
        if _ABS_PATH_RE.search(match.group(1)):
            found.append(match.group(1))
    return found


# -- fluxul principal --------------------------------------------------------

def _confirm_save_if_needed(iface, project):
    """Pasul 1: o singura intrebare Da/Nu pentru modificari nesalvate. Returneaza False la esec/anulare."""
    edits = _unsaved_edit_layers(project)
    if not (project.isDirty() or edits):
        return True

    text = "Exista modificari nesalvate"
    if edits:
        text += " (inclusiv in straturile: " + ", ".join(l.name() for l in edits) + ")"
    text += ".\n\nLe salvez inainte de a crea copia?\n\nNu = copia contine ultima versiune salvata pe disc."
    answer = QMessageBox.question(
        iface.mainWindow(), "Copie de siguranta portabila", text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return True

    for layer in edits:
        if not layer.commitChanges():
            raise _AbortBackup(
                f"Nu s-au putut salva modificarile stratului '{layer.name()}':\n"
                + "\n".join(layer.commitErrors())
                + "\n\nOperatia a fost oprita."
            )
    if not project.write():
        raise _AbortBackup(f"Nu s-a putut salva proiectul:\n{project.error()}\n\nOperatia a fost oprita.")
    return True


def _warning_text(memory, outside, keep):
    lines = []
    if memory:
        lines.append("STRATURI DIN MEMORIE - vor fi PIERDUTE (continutul lor nu poate fi salvat):")
        lines += [f"  - {l.name()}" for l in memory[:10]]
        lines.append("")
    if outside:
        lines.append(
            f"Surse in afara pachetului - fisierele vor fi copiate in '{EXTRA_FOLDER}' "
            "si caile din proiect vor fi relative:"
        )
        lines += [f"  - {l.name()}  ({p})" for l, p in outside[:10]]
        if len(outside) > 10:
            lines.append(f"  ... (+{len(outside) - 10})")
        lines.append("")
    if keep:
        lines.append(
            "Straturi URI/virtuale - raman neschimbate in proiect (nu sunt incluse in "
            "arhiva si pot sa nu functioneze pe alt calculator):"
        )
        lines += [f"  - {l.name()}" for l in keep[:10]]
        lines.append("")
    lines.append("Continui?")
    return "\n".join(lines)


def _run_impl(iface):
    project = QgsProject.instance()
    project_file = project.fileName()
    if not project_file:
        raise _AbortBackup("Proiectul curent nu a fost inca salvat pe disc.")
    project_file = os.path.abspath(project_file)
    project_dir = os.path.dirname(project_file)

    # 1. salvare (Da/Nu); doar acum proiectul de pe disc este "adevarul"
    _confirm_save_if_needed(iface, project)

    # 2. proiectul de pe disc, intr-o instanta separata
    other = QgsProject()
    try:
        if not other.read(project_file):
            raise _AbortBackup(
                f"Nu s-a putut citi proiectul de pe disc:\n{project_file}\n{other.error()}"
            )

        package_folder = _find_package_folder(other, project_dir)
        memory, outside, keep = _classify_layers(other, package_folder)

        # 3. avertisment unic
        if memory or outside or keep:
            answer = QMessageBox.warning(
                iface.mainWindow(), "Copie de siguranta portabila",
                _warning_text(memory, outside, keep),
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Ok,
            )
            if answer != QMessageBox.StandardButton.Ok:
                return

        zip_path = os.path.join(project_dir, os.path.basename(package_folder) + ".zip")
        if os.path.exists(zip_path):
            answer = QMessageBox.question(
                iface.mainWindow(), "Copie de siguranta portabila",
                f"Exista deja:\n{zip_path}\n\nO inlocuiesc?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # 4. proiect portabil + plan Alte_surse
        extra_archive, mapping = _plan_extra_sources(outside)
        relocations = [(l, p, mapping[_norm(p)]) for l, p in outside]
        project_bytes = _write_portable_project(other, project_file, relocations, keep)
    finally:
        other.clear()

    checkpoint_gpkgs(package_folder)
    tmp_zip = zip_path + ".tmp"
    try:
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(os.path.basename(project_file), project_bytes)
            add_package_folder(zf, package_folder, project_dir)
            for full, arc in extra_archive:
                zf.write(full, arc)
        os.replace(tmp_zip, zip_path)
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    iface.messageBar().pushSuccess(
        "Copie de siguranta portabila",
        f"Arhiva a fost creata ({size_mb:.1f} MB): {zip_path}",
    )
