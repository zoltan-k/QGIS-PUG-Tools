# -*- coding: utf-8 -*-
"""
Unealta "Consolideaza straturile intr-un singur GPKG".

Un proiect QGIS poate contine straturi din mai multe fisiere .gpkg; uneori
utilizatorul trage (din greseala) un strat al sablonului dintr-un alt .gpkg
(ex. dintr-o copie datata de o pregatire pentru validare), iar proiectul pare
standard. Unealta aduce toate straturile sablonului intr-un singur GPKG.

Fluxul:
    1. Straturile proiectului al caror nume exista si in sablon sunt grupate pe
       fisierul .gpkg sursa. Un singur fisier -> "totul e deja intr-un fisier".
    2. Fisierul tinta se alege intr-un dialog (un singur fisier). Sunt eligibile
       doar fisierele cu nume standard <JUD>_<UAT>_<SIRUTA>_<TIP>_<AAAALLZZ|AAAALLZZ-data>.gpkg.
       Preselectie: numele "AAAALLZZ" (cel creat de "Proiect nou PUG"), apoi
       fisierul cu cele mai multe straturi sablon. Daca niciun fisier nu e
       eligibil, un GPKG nou este construit din sablon, cu nume corect, pe baza
       datelor din PlanSpatial (+ ~REF_UAT, sys_versiune); daca nu exista
       destule informatii, unealta se opreste si recomanda un proiect nou.
    3. Se salveaza tot (straturi editabile + proiect; esec = oprire) si se
       creeaza o copie de rezerva "as is" (ca la "Actualizeaza pachetul").
    4. Tabelele straturilor din celelalte fisiere inlocuiesc tabelele cu acelasi
       nume din tinta (continutul tinta se sterge, randurile sursei se insereaza
       cu fid-urile pastrate, printr-o singura tranzactie GDAL: triggerele
       rtree/feature_count raman corecte; la eroare nu se modifica nimic).
         - tabele "_*" si "sys_*" (referinta, ale sablonului): stratul doar este
           re-indreptat spre copia din tinta; se copiaza doar daca tinta nu o are;
         - tabelele "~*" (inclusiv ~REF_UAT) si straturile de date: inlocuite.
       Straturile care nu sunt in sablon, straturile virtuale etc. nu sunt atinse.
    5. Proiectul este redeschis si straturile mutate primesc noua sursa cu
       QgsMapLayer.setDataSource (id, stil, pozitie in arbore, filtru raman);
       sursa widget-urilor "ValueRelation" este actualizata; proiectul se salveaza.
    6. Fisierele sursa fara alte straturi in proiect nu mai sunt referite: unealta
       NU le sterge de pe disc, doar avertizeaza; copia portabila, copiile de
       rezerva si pregatirea pentru validare le ignora (vezi gpkg_refs.py).

Valori implicite / actiuni din stiluri: tabelele sunt inlocuite cu pastrarea
numelor straturilor, iar expresiile din stiluri refera alte straturi dupa
nume (overlay_nearest('PlanSpatial'...), get_feature('~REF_UAT'...) etc.), deci
raman valabile. Atentie: unele expresii (UAT, SIRUTA, NivelPlan din PlanSpatial
si LimitaIntravilan*) extrag valori din NUMELE fisierului GPKG - de aceea
tinta trebuie sa aiba un nume standard, iar fisierele cu alt SIRUTA/tip cer
confirmare explicita.
"""

import os
import re
import shutil
import sqlite3
import traceback
import unicodedata

from osgeo import ogr
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QApplication, QDialog, QMessageBox
from qgis.core import (
    Qgis,
    QgsDataProvider,
    QgsEditorWidgetSetup,
    QgsMessageLog,
    QgsProject,
    QgsProviderRegistry,
)

from . import gpkg_refs
from .gpkg_refs import layer_gpkg_path, norm_path
from .template_paths import GPKG_FOLDER, GPKG_RELATIVE, TemplateNotFoundError, resolve_template_dir

LOG_TAG = "PUG Tools"
TITLE = "Consolideaza straturile intr-un singur GPKG"
DATE_PLACEHOLDER = "AAAALLZZ"
PLANSPATIAL = "PlanSpatial"
PROJECT_TYPES = ("PUG", "PUZ", "PUD", "PATJ", "PMUD")

# <JUD>_<UAT>_<SIRUTA>_<TIP>_<AAAALLZZ | YYYYMMDD>.gpkg (vezi project_loader.py)
NAME_RE = re.compile(
    r"^(?P<jud>[A-Z]{1,2})_(?P<uat>.+)_(?P<siruta>\d+)_(?P<tip>" + "|".join(PROJECT_TYPES)
    + r")_(?P<date>" + DATE_PLACEHOLDER + r"|\d{8})\.gpkg$"
)
_LAYERNAME_RE = re.compile(r"\|layername=([^|]+)")


class _AbortConsolidate(Exception):
    """Oprire controlata, cu un mesaj clar pentru utilizator (nu s-a modificat nimic / sau se spune ce)."""


# -- utilitare ---------------------------------------------------------------

def parse_pug_name(path):
    """dict(jud, uat, siruta, tip, date) pentru un nume standard de GPKG, altfel None."""
    match = NAME_RE.match(os.path.basename(path))
    return match.groupdict() if match else None


def is_reference_table(table):
    """Tabelele "_*" si "sys_*" apartin sablonului; "~*" (si ~REF_UAT) contin date ale proiectului."""
    return table.startswith(("_", "sys_"))


def _ctext(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _ro_uri(path):
    return "file:" + path.replace("\\", "/").replace("?", "%3f").replace("#", "%23") + "?mode=ro"


def _display_path(path, project_dir):
    try:
        rel = os.path.relpath(path, project_dir)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
    except ValueError:
        pass
    return path.replace("\\", "/")


def template_table_names(template_gpkg):
    con = sqlite3.connect(_ro_uri(template_gpkg), uri=True)
    try:
        return {r[0] for r in con.execute("SELECT table_name FROM gpkg_contents")} - {"layer_styles"}
    finally:
        con.close()


def _layer_table(layer):
    match = _LAYERNAME_RE.search(layer.source())
    return match.group(1) if match else None


# -- analiza -------------------------------------------------------------------

class FileInfo:
    def __init__(self, path):
        self.path = path
        self.norm = norm_path(path)
        self.parsed = parse_pug_name(path)
        self.layers = []         # straturi cu nume de sablon, din acest fisier
        self.other_count = 0     # alte straturi ale proiectului din acest fisier
        self.has_planspatial = False

    @property
    def valid_target(self):
        return self.parsed is not None

    @property
    def generic(self):
        return bool(self.parsed) and self.parsed["date"] == DATE_PLACEHOLDER


class Analysis:
    def __init__(self):
        self.files = {}      # norm -> FileInfo
        self.skipped = []    # (nume_strat, motiv)


def analyze(project, template_tables):
    """Grupeaza straturile cu nume de sablon pe fisierul .gpkg sursa. Ridica _AbortConsolidate la probleme."""
    result = Analysis()
    template_layers = {}
    for layer in project.mapLayers().values():
        if layer.name() not in template_tables:
            continue
        path = layer_gpkg_path(layer)
        src_table = _layer_table(layer)
        if layer.providerType() != "ogr" or not path or not src_table:
            result.skipped.append((layer.name(), "sursa nu este un tabel dintr-un fisier GPKG"))
            continue
        if src_table != layer.name() and is_reference_table(layer.name()):
            result.skipped.append((
                layer.name(),
                f"strat de referinta cu sursa din alt tabel ('{src_table}') - nu se muta; "
                "re-adauga-l din GPKG-ul tinta",
            ))
            continue
        template_layers.setdefault(layer.name(), []).append((layer, path))

    duplicates = [
        name for name, items in template_layers.items()
        if len({norm_path(p) for _l, p in items}) > 1
    ]
    if duplicates:
        raise _AbortConsolidate(
            "Exista straturi cu acelasi nume din fisiere diferite - nu se poate decide care "
            "ramane:\n\n" + "\n".join(
                f"  - {n}: " + "; ".join(sorted({p for _l, p in template_layers[n]})) for n in duplicates
            ) + "\n\nElimina din proiect duplicatele nedorite si reia operatia."
        )

    missing = sorted({
        p for items in template_layers.values() for _l, p in items if not os.path.isfile(p)
    })
    if missing:
        raise _AbortConsolidate(
            "Fisierele sursa urmatoare nu exista pe disc:\n\n" + "\n".join(missing)
            + "\n\nRefa sau elimina straturile respective, apoi reia operatia."
        )

    for name, items in template_layers.items():
        for layer, path in items:
            key = norm_path(path)
            info = result.files.setdefault(key, FileInfo(path))
            info.layers.append(layer)
            if name == PLANSPATIAL:
                info.has_planspatial = True

    # alte straturi ale proiectului (non-sablon) din aceleasi fisiere
    template_ids = {l.id() for info in result.files.values() for l in info.layers}
    for layer in project.mapLayers().values():
        if layer.id() in template_ids:
            continue
        paths = [layer_gpkg_path(layer)] + gpkg_refs._virtual_source_paths(layer)
        for path in paths:
            if path and norm_path(path) in result.files:
                result.files[norm_path(path)].other_count += 1
    return result


def preselect(files):
    """Fisierul tinta implicit dintre cele eligibile: nume AAAALLZZ, apoi cele mai multe straturi, apoi PlanSpatial."""
    valid = [f for f in files if f.valid_target]
    if not valid:
        return None
    valid.sort(key=lambda f: (not f.generic, -len(f.layers), not f.has_planspatial, f.norm))
    return valid[0]


def mismatches(target_parsed, files, target_norm):
    """Texte de avertisment pentru fisiere sursa cu alt SIRUTA/tip decat tinta."""
    out = []
    for info in files:
        if info.norm == target_norm or not info.parsed:
            continue
        diffs = []
        if info.parsed["siruta"] != target_parsed["siruta"]:
            diffs.append(f"SIRUTA {info.parsed['siruta']} (tinta: {target_parsed['siruta']})")
        if info.parsed["tip"] != target_parsed["tip"]:
            diffs.append(f"tip {info.parsed['tip']} (tinta: {target_parsed['tip']})")
        if diffs:
            out.append(f"{os.path.basename(info.path)}: " + ", ".join(diffs))
    return out


def new_package_info(project):
    """
    Datele pentru numele unui GPKG nou, din proiect: dict(jud, uat, siruta, tip).
    Ridica _AbortConsolidate cu motivul exact daca lipsesc informatii.
    """
    problems = []
    ps = project.mapLayersByName(PLANSPATIAL)
    feat = next(ps[0].getFeatures(), None) if ps and ps[0].isValid() else None
    siruta = uat = None
    if feat is None:
        problems.append("stratul 'PlanSpatial' lipseste sau nu are nicio inregistrare")
    else:
        siruta = str(feat["SIRUTA"]).strip() if feat["SIRUTA"] not in (None, "") else ""
        uat = str(feat["UAT"]).strip() if feat["UAT"] not in (None, "") else ""
        if not siruta.isdigit():
            problems.append("PlanSpatial.SIRUTA lipseste sau nu e numeric")
        if not uat:
            problems.append("PlanSpatial.UAT lipseste")

    jud = None
    ref = project.mapLayersByName("~REF_UAT")
    rfeat = next(ref[0].getFeatures(), None) if ref and ref[0].isValid() else None
    if rfeat is not None and rfeat["countyMn"] not in (None, ""):
        jud = str(rfeat["countyMn"]).strip().upper()
    if not jud or not re.fullmatch(r"[A-Z]{1,2}", jud):
        problems.append("indicativul judetului nu poate fi determinat (~REF_UAT.countyMn)")
        jud = None

    tip = None
    ver = project.mapLayersByName("sys_versiune") or project.mapLayersByName("sys__versiune")
    vfeat = next(ver[0].getFeatures(), None) if ver and ver[0].isValid() else None
    if vfeat is not None and vfeat["tip"] in PROJECT_TYPES:
        tip = vfeat["tip"]
    elif feat is not None and feat["TitluPlan"]:
        first = str(feat["TitluPlan"]).split()[0].upper()
        tip = first if first in PROJECT_TYPES else None
    if tip is None:
        problems.append("tipul proiectului (PUG/PUZ/...) nu poate fi determinat")

    if problems:
        raise _AbortConsolidate(
            "Niciunul dintre fisierele proiectului nu are un nume standard "
            "(<JUD>_<UAT>_<SIRUTA>_<TIP>_AAAALLZZ.gpkg), iar un fisier nou nu poate fi "
            "construit, deoarece:\n\n  - " + "\n  - ".join(problems)
            + "\n\nConsolidarea nu este posibila. Recomandare: creeaza un proiect nou cu "
            "\"Proiect nou PUG\" si transfera datele in el."
        )
    return {"jud": jud, "uat": _ctext(uat).upper(), "siruta": siruta, "tip": tip, "date": DATE_PLACEHOLDER}


def new_gpkg_path(info, project_dir):
    base = f"{info['jud']}_{info['uat']}_{info['siruta']}_{info['tip']}_{DATE_PLACEHOLDER}"
    return os.path.join(project_dir, base, GPKG_FOLDER.rstrip("/"), base + ".gpkg"), base


# -- verificari de schema (inainte de orice scriere) -----------------------------

def _is_geom(layer):
    return layer.GetGeomType() != ogr.wkbNone


def schema_report(src_path, tgt_path, table, src_table=None):
    """
    (abort_reasons, warnings, tgt_has_table, tgt_is_geometry) pentru inlocuirea tabelei
    `table` din `tgt_path` cu tabelul `src_table` (implicit `table`) din `src_path`.
    """
    src_table = src_table or table
    ds_s = ogr.Open(src_path, 0)
    ds_t = ogr.Open(tgt_path, 0)
    if ds_s is None or ds_t is None:
        raise _AbortConsolidate(f"Nu s-a putut deschide fisierul GPKG:\n{src_path if ds_s is None else tgt_path}")
    try:
        ls = ds_s.GetLayerByName(src_table)
        lt = ds_t.GetLayerByName(table)
        if ls is None:
            return [f"{table}: tabelul '{src_table}' lipseste din {os.path.basename(src_path)}"], [], lt is not None, False
        if lt is None:
            return [], [], False, _is_geom(ls)
        abort, warn = [], []
        if _is_geom(ls) != _is_geom(lt):
            abort.append(f"{table}: un tabel are geometrie, celalalt nu")
        elif _is_geom(ls):
            ss, st = ls.GetSpatialRef(), lt.GetSpatialRef()
            same = (ss is None and st is None) or (ss is not None and st is not None and ss.IsSame(st))
            if not same:
                abort.append(f"{table}: sisteme de coordonate diferite (nu se face reproiectare)")
            if ogr.GT_Flatten(ls.GetGeomType()) != ogr.GT_Flatten(lt.GetGeomType()):
                warn.append(
                    f"{table}: tip de geometrie diferit "
                    f"({ogr.GeometryTypeToName(ls.GetGeomType())} -> {ogr.GeometryTypeToName(lt.GetGeomType())})"
                )
        dsrc = ls.GetLayerDefn()
        dtgt = lt.GetLayerDefn()
        sf = [dsrc.GetFieldDefn(i).GetName() for i in range(dsrc.GetFieldCount())]
        tf = [dtgt.GetFieldDefn(i).GetName() for i in range(dtgt.GetFieldCount())]
        lost = [c for c in sf if c not in tf]
        added = [c for c in tf if c not in sf]
        if lost:
            warn.append(f"{table}: coloane din sursa care nu exista in tinta (se pierd): {', '.join(lost)}")
        if added:
            warn.append(f"{table}: coloane din tinta lipsa in sursa (raman goale): {', '.join(added)}")
        return abort, warn, True, _is_geom(lt)
    finally:
        ds_s = ds_t = None


class Moves:
    """Ce se face cu fiecare strat mutat."""

    def __init__(self):
        self.layers = []          # (layer_id, table, src_path)
        self.replace = []         # (table, src_path, src_table) - inlocuire continut (OGR)
        self.copy_missing = []    # (table, src_path)       - tabel atribut lipsa in tinta (SQL)
        self.repoint_only = []    # table                   - doar re-indreptare
        self.warnings = []
        self.aborts = []


def plan_moves(files, target, schema_target_path):
    """Calculeaza actiunile pentru straturile din fisierele != tinta; ruleaza verificarile de schema."""
    moves = Moves()
    seen_tables = set()
    for info in files:
        if info.norm == target.norm:
            continue
        for layer in info.layers:
            table = layer.name()
            moves.layers.append((layer.id(), table, info.path))
            if table in seen_tables:
                continue
            seen_tables.add(table)
            src_table = _layer_table(layer) or table
            abort, warn, tgt_has, tgt_geom = schema_report(info.path, schema_target_path, table, src_table)
            moves.aborts += abort
            moves.warnings += warn
            if abort:
                continue
            if not tgt_has:
                if tgt_geom:
                    moves.aborts.append(
                        f"{table}: tabelul cu geometrie lipseste din fisierul tinta - ruleaza "
                        "\"Actualizeaza pachetul\" pe fisierul tinta, apoi reia"
                    )
                elif src_table != table:
                    moves.aborts.append(
                        f"{table}: tabelul lipseste din tinta, iar sursa e in alt tabel ('{src_table}') - "
                        "ruleaza \"Actualizeaza pachetul\" pe fisierul tinta, apoi reia"
                    )
                else:
                    moves.copy_missing.append((table, info.path))
            elif is_reference_table(table):
                moves.repoint_only.append(table)
            else:
                moves.replace.append((table, info.path, src_table))
    return moves


# -- scriere: tabele ---------------------------------------------------------------

def _count(ds, table):
    res = ds.ExecuteSQL(f'SELECT COUNT(*) FROM "{table}"')
    try:
        return res.GetNextFeature().GetField(0)
    finally:
        ds.ReleaseResultSet(res)


def _replace_table_ogr(ds_t, src_path, table, src_table=None):
    """Sterge continutul `table` din ds_t si insereaza randurile tabelului `src_table` din src_path (fid pastrat)."""
    ds_s = ogr.Open(src_path, 0)
    if ds_s is None:
        raise RuntimeError(f"Nu s-a putut deschide {src_path}")
    try:
        ls = ds_s.GetLayerByName(src_table or table)
        lt = ds_t.GetLayerByName(table)
        defn = lt.GetLayerDefn()
        tgt_type = lt.GetGeomType()
        has_geom = tgt_type != ogr.wkbNone
        ds_t.ExecuteSQL(f'DELETE FROM "{table}"')
        n = 0
        ls.ResetReading()
        for feat in ls:
            nf = ogr.Feature(defn)
            nf.SetFrom(feat, True)  # camp cu camp, dupa nume
            nf.SetFID(feat.GetFID())
            if has_geom:
                geom = feat.GetGeometryRef()
                if geom is not None and geom.GetGeometryType() != tgt_type and ogr.GT_Flatten(geom.GetGeometryType()) != ogr.GT_Flatten(tgt_type):
                    nf.SetGeometry(ogr.ForceTo(geom.Clone(), tgt_type))
            if lt.CreateFeature(nf) != 0:
                raise RuntimeError(f"Inserarea in '{table}' a esuat (fid {feat.GetFID()})")
            n += 1
        expected = ls.GetFeatureCount(1)
        got = _count(ds_t, table)
        if got != expected or n != expected:
            raise RuntimeError(f"'{table}': {got} randuri in tinta, {expected} in sursa")
        return n
    finally:
        ds_s = None


def _apply_tables(target_path, moves):
    """Toate inlocuirile intr-o singura tranzactie GDAL (rollback complet la eroare)."""
    if moves.copy_missing:
        from .package_updater import _copy_reference_table  # copiere SQL, sigura pentru nume cu "~"
        tgt = sqlite3.connect(target_path)
        try:
            for table, src_path in moves.copy_missing:
                src = sqlite3.connect(_ro_uri(src_path), uri=True)
                try:
                    _copy_reference_table(src, tgt, table)
                finally:
                    src.close()
            tgt.commit()
        finally:
            tgt.close()

    if not moves.replace:
        return
    ds_t = ogr.Open(target_path, 1)
    if ds_t is None:
        raise _AbortConsolidate(
            f"Fisierul tinta nu poate fi deschis pentru scriere (blocat de alt program?):\n{target_path}"
        )
    started = ds_t.StartTransaction() == 0
    try:
        for table, src_path, src_table in moves.replace:
            _replace_table_ogr(ds_t, src_path, table, src_table)
        if started and ds_t.CommitTransaction() != 0:
            raise RuntimeError("Tranzactia nu a putut fi finalizata")
        started = False
    except Exception:
        if started:
            ds_t.RollbackTransaction()
        raise
    finally:
        ds_t = None  # inchide si scrie pe disc


# -- scriere: proiect ----------------------------------------------------------------

def _repoint_layer(project, layer_id, target_path, reload_style=False):
    """
    Re-indreapta stratul spre tabelul cu numele lui din `target_path` (sursa veche putea fi un
    tabel cu alt nume, ex. dintr-un export "Save Features As"). Cu `reload_style`, stilul implicit
    salvat in "layer_styles" din tinta (widget-uri, valori implicite, simbolizare) inlocuieste stilul
    stratului din proiect - un strat reincarcat dintr-un export nu are stilul sablonului.
    """
    layer = project.mapLayer(layer_id)
    if layer is None:
        raise RuntimeError(f"Stratul {layer_id} nu mai exista in proiect")
    registry = QgsProviderRegistry.instance()
    parts = registry.decodeUri("ogr", layer.source())
    parts["path"] = target_path
    parts["layerName"] = layer.name()
    parts.pop("layerId", None)
    new_uri = registry.encodeUri("ogr", parts)
    layer.setDataSource(new_uri, layer.name(), "ogr", QgsDataProvider.ProviderOptions())
    if not layer.isValid():
        raise RuntimeError(f"Stratul '{layer.name()}' nu s-a putut incarca din noua sursa:\n{new_uri}")
    if reload_style:
        message, ok = layer.loadNamedStyle(layer.source(), False)  # False = din baza de date a sursei
        if not ok:  # tinta fara stil implicit pentru acest strat: ramane stilul din proiect
            QgsMessageLog.logMessage(
                f"Stil implicit negasit in tinta pentru '{layer.name()}': {message}", LOG_TAG, level=Qgis.Info
            )


def _fix_value_relation_sources(project, project_dir, target_path, tables, moved_ids):
    """Actualizeaza LayerSource al widget-urilor ValueRelation care arata spre tabele mutate."""
    try:
        rel = os.path.relpath(target_path, project_dir).replace(os.sep, "/")
    except ValueError:
        rel = target_path.replace("\\", "/")
    fixed = 0
    for layer in project.mapLayers().values():
        if not hasattr(layer, "fields"):
            continue
        for i in range(len(layer.fields())):
            setup = layer.editorWidgetSetup(i)
            config = dict(setup.config())
            source = config.get("LayerSource")
            if not source:
                continue
            match = _LAYERNAME_RE.search(source)
            table = match.group(1) if match else None
            if table in tables or config.get("Layer") in moved_ids:
                tail = source.split("|", 1)[1] if "|" in source else ""
                config["LayerSource"] = rel + ("|" + tail if tail else "")
                layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup(setup.type(), config))
                fixed += 1
    return fixed


def _leftover_references(project_file, basenames):
    """Numele fisierelor (dintre `basenames`) mai mentionate in XML-ul proiectului salvat."""
    import zipfile
    try:
        if project_file.lower().endswith(".qgz"):
            with zipfile.ZipFile(project_file) as zf:
                name = next(n for n in zf.namelist() if n.lower().endswith(".qgs"))
                text = zf.read(name).decode("utf-8", "replace")
        else:
            with open(project_file, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
    except Exception:  # noqa: BLE001
        return []
    return [b for b in basenames if b in text]


# -- punct de intrare ------------------------------------------------------------------

def run(iface):
    try:
        return bool(_run_impl(iface))
    except _AbortConsolidate as exc:
        QMessageBox.warning(iface.mainWindow(), TITLE, str(exc))
    except Exception as exc:  # nu lasa o eroare neasteptata sa inchida QGIS
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            TITLE + " - eroare",
            f"A aparut o eroare la consolidare:\n{exc}\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )
    return False


def _save_everything(project):
    """Comite straturile editabile si salveaza proiectul; orice esec opreste operatia."""
    for layer in project.mapLayers().values():
        if hasattr(layer, "isEditable") and layer.isEditable():
            if not layer.commitChanges():
                raise _AbortConsolidate(
                    f"Modificarile stratului '{layer.name()}' nu au putut fi salvate:\n"
                    + "\n".join(layer.commitErrors())
                    + "\n\nCorecteaza problema (ex. geometrii invalide) si reia operatia. "
                    "Nu s-a modificat nimic."
                )
    if not project.write():
        raise _AbortConsolidate(
            f"Proiectul nu a putut fi salvat:\n{project.error()}\n\nNu s-a modificat nimic."
        )


def _run_impl(iface):
    project = QgsProject.instance()
    project_file = project.fileName()
    if not project_file:
        raise _AbortConsolidate("Proiectul curent nu a fost inca salvat pe disc. Salveaza-l si reia.")
    project_file = os.path.abspath(project_file)
    project_dir = os.path.dirname(project_file)

    try:
        template_dir = resolve_template_dir(ensure_active_copy=True)
    except TemplateNotFoundError as exc:
        raise _AbortConsolidate(str(exc))
    template_gpkg = template_dir + GPKG_RELATIVE
    template_tables = template_table_names(template_gpkg)

    analysis = analyze(project, template_tables)
    files = list(analysis.files.values())
    if not files:
        raise _AbortConsolidate("Proiectul nu contine niciun strat din sablonul PUG.")
    if len(files) == 1:
        text = (
            "Toate straturile sablonului din proiect sunt deja intr-un singur fisier:\n\n"
            + _display_path(files[0].path, project_dir)
        )
        if analysis.skipped:
            text += "\n\nStraturi ignorate:\n" + "\n".join(f"  - {n}: {r}" for n, r in analysis.skipped)
        QMessageBox.information(iface.mainWindow(), TITLE, text)
        return True

    # ---- alegerea tintei --------------------------------------------------------------
    new_info = None
    new_path = None
    target = preselect(files)
    if target is None:
        new_info = new_package_info(project)  # ridica _AbortConsolidate daca nu se poate
        new_path, base = new_gpkg_path(new_info, project_dir)
        if os.path.exists(new_path):
            raise _AbortConsolidate(
                f"Niciun fisier existent nu are un nume standard, iar fisierul nou ar fi:\n{new_path}\n\n"
                "dar acesta exista deja. Redenumeste/muta fisierul existent si reia."
            )
        target = FileInfo(new_path)
        target.parsed = new_info
        answer = QMessageBox.question(
            iface.mainWindow(), TITLE,
            "Niciunul dintre fisierele GPKG din proiect nu are un nume standard "
            "(<JUD>_<UAT>_<SIRUTA>_<TIP>_AAAALLZZ.gpkg), deci niciunul nu poate fi tinta.\n\n"
            "Se poate construi un fisier nou, din sablon, pe baza datelor din PlanSpatial:\n\n"
            f"{_display_path(new_path, project_dir)}\n\n"
            "si toate tabelele straturilor din proiect vor fi inlocuite in el. "
            "Fisierele curente nu se sterg.\n\nContinui?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        warnings_mismatch = mismatches(target.parsed, files, target.norm)
    else:
        from ..ui.consolidate_dialog import ConsolidateDialog
        dialog = ConsolidateDialog(
            files, target, project_dir, mismatch_fn=lambda t: mismatches(t.parsed, files, t.norm),
            parent=iface.mainWindow(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        target = dialog.selected_file()
        warnings_mismatch = []  # deja confirmate explicit in dialog

    # ---- planificare + verificari de schema (nimic nu e scris) ---------------------------------
    schema_target = target.path if new_path is None else template_gpkg
    moves = plan_moves(files, target, schema_target)
    if moves.aborts:
        raise _AbortConsolidate(
            "Consolidarea nu este posibila:\n\n  - " + "\n  - ".join(moves.aborts)
            + "\n\nNu s-a modificat nimic."
        )

    source_files = [f for f in files if f.norm != target.norm]
    lines = [
        f"Tinta: {_display_path(target.path, project_dir)}" + ("  (fisier NOU, din sablon)" if new_path else ""),
        "",
        f"Tabele inlocuite in tinta: {len(moves.replace)}",
    ]
    lines += [
        f"  - {t}   <- {os.path.basename(p)}" + (f" (tabel '{st}')" if st != t else "")
        for t, p, st in moves.replace
    ]
    if moves.repoint_only:
        lines += ["", "Tabele de referinta doar re-indreptate spre copia din tinta: "
                  + ", ".join(moves.repoint_only)]
    if moves.copy_missing:
        lines += ["", "Tabele lipsa in tinta, copiate: " + ", ".join(t for t, _p in moves.copy_missing)]
    if analysis.skipped:
        lines += ["", "STRATURI NEMUTATE (raman unde sunt, nu fac parte din consolidare):"]
        lines += [f"  - {name}: {reason}" for name, reason in analysis.skipped]
    if moves.warnings:
        lines += ["", "DIFERENTE DE SCHEMA:"] + [f"  - {w}" for w in moves.warnings]
    if warnings_mismatch:
        lines += ["", "ATENTIE - fisiere cu alt SIRUTA/tip decat tinta:"] + [f"  - {w}" for w in warnings_mismatch]
    lines += [
        "",
        "Se vor salva modificarile din straturi si proiectul (la esec, operatia se opreste), "
        "se va crea o copie de rezerva (.zip) langa proiect, apoi se aplica schimbarile. "
        "Straturile de date mutate primesc stilul implicit salvat in fisierul tinta.",
        "",
        "Continui?",
    ]
    answer = QMessageBox.question(
        iface.mainWindow(), TITLE, "\n".join(lines),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False

    # ---- salvare + copie de rezerva (ca la "Actualizeaza pachetul") --------------------------
    _save_everything(project)

    from .package_updater import _AbortUpdate, _create_backup
    ps_infos = [f for f in files if f.has_planspatial]
    backup_anchor = target.path if new_path is None else (ps_infos[0].path if ps_infos else files[0].path)
    try:
        backup_path = _create_backup(
            project_file, backup_anchor, extra_gpkgs=[f.path for f in files if f.path != backup_anchor]
        )
    except _AbortUpdate as exc:
        raise _AbortConsolidate(str(exc))

    # ---- scriere --------------------------------------------------------------------------------
    created_new = False
    moved_ids = {lid for lid, _t, _p in moves.layers}
    moved_tables = {t for _lid, t, _p in moves.layers}
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        project.clear()  # elibereaza blocarile pe fisierele .gpkg (Windows)
        try:
            if new_path is not None:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.copy2(template_gpkg, new_path)
                created_new = True
                con = sqlite3.connect(new_path)
                try:
                    con.execute('UPDATE "sys_versiune" SET tip = ?', (new_info["tip"],))
                    con.commit()
                finally:
                    con.close()
            _apply_tables(target.path, moves)
        except Exception:
            if created_new and os.path.isfile(new_path):
                try:  # doar fisierul NOU creat de aceasta unealta
                    os.remove(new_path)
                except OSError:
                    pass
            raise
        finally:
            project.read(project_file)  # in orice caz: proiectul este redeschis

        # tabelele sunt scrise; acum proiectul re-indreptat spre tinta
        try:
            for lid, table, _p in moves.layers:
                _repoint_layer(project, lid, target.path, reload_style=not is_reference_table(table))
            _fix_value_relation_sources(project, project_dir, target.path, moved_tables, moved_ids)
            if not project.write(project_file):
                raise RuntimeError(f"Proiectul nu a putut fi salvat: {project.error()}")
        except Exception as exc:
            project.read(project_file)  # revine la proiectul salvat (sursele vechi inca exista)
            raise _AbortConsolidate(
                "Datele au fost copiate in fisierul tinta, dar proiectul nu a putut fi actualizat "
                f"({exc}).\n\nProiectul a ramas neschimbat; copia de rezerva este:\n{backup_path}"
            )
    finally:
        QApplication.restoreOverrideCursor()

    # ---- raport -------------------------------------------------------------------------------------
    referenced = gpkg_refs.referenced_gpkgs(project)
    orphans = [f.path for f in source_files if f.norm not in referenced]
    leftovers = _leftover_references(project_file, [os.path.basename(p) for p in orphans])

    iface.messageBar().pushSuccess(TITLE, f"Straturile au fost consolidate in {os.path.basename(target.path)}.")
    text = [
        f"Consolidare incheiata. Tinta: {_display_path(target.path, project_dir)}",
        f"Copie de rezerva: {backup_path}",
    ]
    if orphans:
        text += [
            "",
            "ATENTIE: urmatoarele fisiere nu mai sunt folosite de niciun strat al proiectului. "
            "NU au fost sterse de pe disc - sterge-le tu daca nu mai ai nevoie de ele "
            "(copia portabila, copiile de rezerva si pregatirea pentru validare le ignora):",
        ] + [f"  - {p}" for p in orphans]
    if leftovers:
        text += ["", "Avertisment: proiectul mai mentioneaza (in afara straturilor): " + ", ".join(leftovers)]
    (QMessageBox.warning if orphans or leftovers else QMessageBox.information)(
        iface.mainWindow(), TITLE, "\n".join(text)
    )
    return True

