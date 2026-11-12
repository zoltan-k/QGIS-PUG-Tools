# -*- coding: utf-8 -*-
"""
Unealta "Actualizeaza pachetul": aduce proiectul PUG curent la paritate
structurala cu sablonul curent folosit de "Proiect nou PUG", STRICT in
urmatoarele limite:

    1. Adauga in fisierul GPKG al proiectului orice strat de referinta (nume
       care incepe cu "~" sau "_") prezent in sablon dar lipsa din proiect,
       impreuna cu datele lui, si il adauga in proiect (grupul de straturi "REF").
       Cazul special "~REF_UAT" (limita administrativa a UAT-ului curent) nu
       e copiat din sablon (acolo e mereu gol) - daca lipseste sau e gol in
       proiect, e preluat/populat prin tools/uat_boundary.py, folosind codul
       SIRUTA din stratul PlanSpatial al proiectului.
    2. Actualizeaza stilul (simbolizare, configurari de camp - widget-uri,
       valori implicite, constrangeri, actiuni etc.) tuturor straturilor
       (de referinta SAU cu continut) pentru care sablonul are un stil salvat,
       inlocuind stilul din GPKG-ul proiectului cu cel din sablon - exact
       mecanismul folosit si la crearea unui proiect nou (stiluri salvate in
       tabela GeoPackage "layer_styles").
    3. Elimina din GPKG (si din proiect, daca erau incarcate) tabelele de
       referinta ("~"/"_") care nu mai fac parte din sablonul curent - ramase
       dintr-o schema de numire mai veche (vezi _remove_unused_reference_tables).
    4. Repozitioneaza grupul de straturi "REF" la finalul grupului lui parinte
       (colapsat) daca a ramas altundeva dintr-o versiune mai veche a
       plugin-ului - straturile de mai jos in arbore se deseneaza DEASUPRA
       celor de mai sus, deci un grup de referinta plasat sus (ex.
       "~REF_UAT", un poligon ce acopera tot UAT-ul) acoperea vizual harta.
    5. Copiaza in subfolderele proiectului (in afara de folderul GPKG-ului)
       fisierele din sablon lipsa din proiect (studii, piese scrise/desenate,
       avize; reguli pe prefix numeric in _template_file_plan: nepotrivirile
       de nume sunt doar raportate, in 4_ se adauga PDF-uri numai daca nu
       exista niciunul) - vezi _sync_missing_template_files. NU
       suprascrie fisiere existente, NU sterge fisiere din proiect absente
       din sablon.
    6. Reconstruieste straturile de referinta "virtuale" (provider QGIS
       "virtual", nu tabele GPKG - ex. "~vREF_SZF_ZRS_D", vezi
       tools/virtual_layers.py) daca lipsesc sau interogarea lor curenta
       difera de cea canonica, inclusiv un caz real de coruptie la salvare
       (diacritice romanesti transformate in "?").

NU adauga straturi cu continut (fara "~"/"_") care lipsesc din proiect, si NU
modifica in niciun fel datele (featureurile) din straturile cu continut -
doar structura (straturi de referinta lipsa/neutilizate) si stilurile.

Exceptii, explicit cerute, unde structura E modificata dincolo de straturile
de referinta lipsa/neutilizate:

    - tabelele de referinta "_*" (ex. "_siruta", "_stadiu_plan", "_subtip_rte"):
      daca schema sau continutul (fara coloana "fid") difera de cele din
      sablonul curent - cazul proiectelor create cu sabloane mai vechi
      (ex. inainte de 3.0.3 "_siruta" era o ierarhie judet/UAT/localitate pe 3
      niveluri; sablonul 3.1.0 a corectat diacriticele si denumirile) - tabela
      e inlocuita in intregime (schema + date) cu cea din sablon, vezi
      _reference_tables_needing_replacement(). Sunt tabele de referinta, fara
      date introduse de utilizator.

    - "PlanSpatial.Stadiu": valorile in forma veche, fara diacritice
      ("In curs de elaborare"), sunt rescrise in forma din "_stadiu_plan" a
      sablonului curent ("În curs de elaborare") - singura modificare de date
      de continut facuta de aceasta unealta, anuntata in dialogul de
      confirmare - vezi _migrate_stadiu_values().

    - "sys__versiune" (in sabloanele < 3.1.0: "__versiune"): "versiune" si
      "data" (numarul de schema) sunt sincronizate neconditionat cu cele din
      sablon la fiecare actualizare de pachet; "tip" (PUG/PUZ/PUD/PATJ/PMUD)
      NU e sincronizat - sablonul contine mereu 'PUG' (nu exista un sablon
      per tip de proiect), asa ca suprascrierea neconditionata ar strica
      proiectele PUZ/etc la fiecare actualizare. Un proiect cu vechiul
      "__versiune" primeste "sys__versiune" (cu "tip" preluat din vechiul
      tabel); "__versiune" e apoi eliminat ca tabel de referinta neutilizat -
      vezi _sync_versiune_table().

    - "RegulamentLocalUrbanismDetaliat": coloanele "Clad_Hmax", "POT" si
      "CUT" au fost TEXT in sabloanele 3.0.2, INTEGER 32 biti (MEDIUMINT /
      "Integer") in 3.0.3-3.0.4 si INTEGER 64 biti ("Integer64") in 3.1.0+.
      Pentru proiecte din sabloanele 2.x (fara coloanele "..._detaliu",
      coloane deja numerice) NU se schimba niciun tip - doar se adauga
      coloanele noi lipsa. Pentru 3.0.2 (TEXT) tabela e reconstruita cu
      schema curenta (SQLite nu suporta ALTER COLUMN TYPE): valorile care se
      convertesc curat la numeric sunt pastrate, convertite; cele care nu
      (notatii ca "P+2" sau "35%") sunt mutate in coloana "..._detaliu"
      corespunzatoare, in loc sa fie pierdute. Pentru 3.0.3+ (coloane
      "..._detaliu" prezente) tipurile sunt aliniate la cele din sablon
      (ex. Integer -> Integer64), valorile ramanand neschimbate. In toate
      cazurile, coloanele noi din sablonul curent, lipsa din proiect, sunt
      adaugate - vezi _migrate_rlud_schema().

Inainte de orice modificare, proiectul (.qgz) si intregul folder al pachetului
(GPKG + toate subfolderele, oricum s-ar numi - ca la "Copie de siguranta
portabila"; straturile cu surse externe nu sunt copiate si raman neatinse)
sunt salvate intr-o arhiva .zip de rezerva, cu data si ora curenta in numele
arhivei, in acelasi folder cu proiectul. Daca aceasta copie de rezerva nu poate fi
creata, actualizarea este anulata - nu se modifica nimic fara backup.

Copierea tabelelor de referinta se face prin SQL direct (sqlite3), nu prin
OGR CopyLayer: API-ul de creare de straturi din GDAL respinge nume care
contin caractere precum "~" ("The layer name may not contain special
characters or spaces"), desi SQLite/GeoPackage insele nu au nicio problema cu
ele - toate tabelele de referinta bundled cu pluginul folosesc asemenea
nume. Se presupune ca straturile de referinta sunt tabele de tip GeoPackage
"attributes" (fara geometrie) - singurul tip folosit in prezent de sablon;
daca un viitor sablon ar adauga un strat de referinta cu geometrie, ar trebui
extinsa si copierea intrarii din gpkg_geometry_columns.

Verificari minime de existenta sunt facute pentru a evita blocarea (fisiere
GPKG negasite, straturi asteptate lipsa), dar in rest se presupune ca
structura GPKG a proiectului este corecta.
"""

import os
import re
import shutil
import sqlite3
import traceback
import unicodedata
import uuid
import zipfile
from datetime import datetime

from osgeo import ogr
from qgis.core import Qgis, QgsLayerTreeGroup, QgsMessageLog, QgsProject, QgsVectorLayer
from qgis.PyQt.QtWidgets import QMessageBox

from . import uat_boundary, virtual_layers
from .portable_backup import add_package_folder, package_folder_for_gpkg
from .template_paths import (
    GPKG_FOLDER,
    GPKG_RELATIVE,
    TemplateNotFoundError,
    _gpkg_versiune,
    active_copy_outdated,
    resolve_template_dir,
)

LOG_TAG = "PUG Tools"
REF_GROUP_NAME = "REF"
REF_PREFIXES = ("~", "_", "sys__")  # "sys__" = tabele de sistem (sys__versiune), in grupul REF
SIRUTA_LAYER = "_siruta"
VERSIUNE_LAYER = "sys__versiune"
LEGACY_VERSIUNE_LAYER = "__versiune"  # sabloane < 3.1.0
STADIU_LOOKUP_LAYER = "_stadiu_plan"
PLANSPATIAL_LAYER = "PlanSpatial"

_LAYER_STYLES_CREATE_SQL = (
    'CREATE TABLE "layer_styles" ( "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, '
    '"f_table_catalog" TEXT(256), "f_table_schema" TEXT(256), "f_table_name" TEXT(256), '
    '"f_geometry_column" TEXT(256), "styleName" TEXT(30), "styleQML" TEXT, "styleSLD" TEXT, '
    '"useAsDefault" BOOLEAN, "description" TEXT, "owner" TEXT(30), "ui" TEXT(30), '
    "\"update_time\" DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))"
)

# tabele de bookkeeping GeoPackage/OGR pentru care se copiaza (daca exista)
# randul corespunzator unui strat de referinta nou adaugat.
_BOOKKEEPING_TABLES = ("gpkg_contents", "gpkg_ogr_contents")


class _AbortUpdate(Exception):
    """Ridicata pentru a opri actualizarea in mod controlat, cu un mesaj clar."""


def package_update_status(project=None):
    """
    (needs_update, message) - True cand versiunea pachetului (tabela
    "sys__versiune", sau vechiul "__versiune") difera de cea a sablonului
    folosit de "Actualizeaza pachetul", sau pachetul nu are deloc tabel de
    versiune. Folosit de dialogul de rezultate ale validarii pentru a oferi
    butonul "Actualizeaza pachetul". Nu modifica nimic; (False, "") daca
    proiectul/sablonul nu pot fi evaluate.
    """
    project = project or QgsProject.instance()
    ps_layers = project.mapLayersByName("PlanSpatial")
    if not ps_layers:
        return False, ""
    gpkg_path = ps_layers[0].source().split("|")[0]
    try:
        template_gpkg = resolve_template_dir(ensure_active_copy=True) + GPKG_RELATIVE
    except TemplateNotFoundError:
        return False, ""
    template_version = _gpkg_versiune(template_gpkg)
    if template_version is None:
        return False, ""
    package_version = _gpkg_versiune(gpkg_path)
    if package_version is None:
        return True, (
            "Pachetul nu are tabel de versiune (\"sys__versiune\") - e creat cu un "
            f"sablon mai vechi decat cel curent ({template_version})."
        )
    if package_version != template_version:
        return True, (
            f"Versiunea sablonului pachetului ({package_version}) difera de cea a "
            f"sablonului curent ({template_version})."
        )
    return False, ""


def run(iface):
    """
    Punct de intrare apelat din actiunea de plugin (si din butonul de
    actualizare al dialogului de rezultate ale validarii - acelasi cod).
    Returneaza True daca actualizarea a fost efectuata, False daca a fost
    anulata/oprita.
    """
    try:
        return bool(_run_impl(iface))
    except _AbortUpdate as exc:
        QMessageBox.warning(iface.mainWindow(), "Actualizeaza pachetul", str(exc))
    except Exception as exc:  # nu lasa o eroare neasteptata sa inchida QGIS
        QgsMessageLog.logMessage(traceback.format_exc(), LOG_TAG, level=Qgis.Critical)
        QMessageBox.critical(
            iface.mainWindow(),
            "Actualizeaza pachetul - eroare",
            f"A aparut o eroare la actualizarea pachetului:\n{exc}\n\n"
            f"Detalii in QGIS Message Log (panou '{LOG_TAG}').",
        )
    return False


# -- copie de rezerva (obligatorie, inainte de orice modificare) -------------

def _create_backup(project_file, gpkg_path):
    """
    Salveaza proiectul (.qgz) si fisierul GPKG (+ fisierele auxiliare
    .gpkg-wal/.gpkg-shm/.gpkg-journal, daca exista) intr-o arhiva .zip de
    rezerva, cu data si ora curenta in numele arhivei, in acelasi folder cu
    proiectul. Ridica _AbortUpdate daca backup-ul nu poate fi creat -
    actualizarea nu trebuie sa continue fara o copie de rezerva.

    Returneaza calea arhivei create.
    """
    project_dir = os.path.dirname(project_file)
    project_stem = os.path.splitext(os.path.basename(project_file))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(project_dir, f"{project_stem}_backup_{timestamp}.zip")

    try:
        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(project_file, os.path.basename(project_file))

            # acelasi continut ca la "Copie de siguranta portabila": intregul
            # folder al pachetului (toate subfolderele, indiferent de numele
            # lui - poate fi deja redenumit cu o data). Straturile cu surse
            # externe nu sunt copiate si raman neatinse.
            package_folder = package_folder_for_gpkg(gpkg_path, project_dir)
            if package_folder:
                add_package_folder(zf, package_folder, project_dir)
                return backup_path

            try:
                gpkg_arcname = os.path.relpath(gpkg_path, project_dir)
            except ValueError:
                # gpkg_path e pe alta unitate decat proiectul (ex. proiect pe
                # C:, GPKG pe D:) - relpath nu poate calcula o cale relativa
                # intre unitati diferite pe Windows; folosim doar numele
                # fisierului, plasat direct in radacina arhivei.
                gpkg_arcname = os.path.basename(gpkg_path)
            zf.write(gpkg_path, gpkg_arcname)

            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = gpkg_path + suffix
                if os.path.isfile(sidecar):
                    zf.write(sidecar, gpkg_arcname + suffix)
    except OSError as exc:
        raise _AbortUpdate(
            f"Nu s-a putut crea copia de rezerva inainte de actualizare:\n{backup_path}\n\n"
            f"Eroare: {exc}\n\n"
            "Actualizarea a fost anulata - nu s-a modificat nimic."
        ) from exc

    return backup_path


# -- helpers structura GPKG (citire, OGR read-only e sigur pt orice nume) ----

def _gpkg_table_names(path):
    ds = ogr.Open(path, 0)
    if ds is None:
        raise _AbortUpdate(f"Nu s-a putut deschide fisierul GPKG:\n{path}")
    names = {ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount())}
    ds = None
    return names


# -- copiere straturi de referinta lipsa (SQL direct) ------------------------

def _table_exists(con, table_name):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cur.fetchone() is not None


def _copy_bookkeeping_row(template_con, target_con, meta_table, table_name):
    if not _table_exists(template_con, meta_table) or not _table_exists(target_con, meta_table):
        return
    tcur = template_con.cursor()
    tcur.execute(f'PRAGMA table_info("{meta_table}")')
    columns = [c[1] for c in tcur.fetchall()]
    tcur.execute(
        f'SELECT {",".join(columns)} FROM "{meta_table}" WHERE table_name=?', (table_name,)
    )
    row = tcur.fetchone()
    if row is None:
        return
    dcur = target_con.cursor()
    dcur.execute(f'DELETE FROM "{meta_table}" WHERE table_name=?', (table_name,))
    placeholders = ",".join("?" * len(columns))
    dcur.execute(
        f'INSERT INTO "{meta_table}" ({",".join(columns)}) VALUES ({placeholders})', row
    )


def _copy_reference_table(template_con, target_con, table_name, drop_existing=False):
    """
    Copiaza schema + date + bookkeeping minim al unui tabel de referinta.
    `drop_existing=True` sterge intai tabela cu acelasi nume din `target_con`
    (daca exista) - folosit pentru inlocuirea completa a unui tabel de
    referinta a carui schema nu mai corespunde sablonului (ex. "_siruta"
    intr-un proiect creat cu un sablon anterior versiunii 3.0.3), spre
    deosebire de cazul normal (tabel complet lipsa, doar adaugat).
    """
    tcur = template_con.cursor()
    tcur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    row = tcur.fetchone()
    if row is None or row[0] is None:
        return False  # nu ar trebui sa se intample; nu blocam restul actualizarii

    dcur = target_con.cursor()
    if drop_existing:
        dcur.execute(f'DROP TABLE "{table_name}"')
    dcur.execute(row[0])  # CREATE TABLE ... (exact schema din sablon)

    tcur.execute(f'SELECT * FROM "{table_name}"')
    data_rows = tcur.fetchall()
    if data_rows:
        placeholders = ",".join("?" * len(data_rows[0]))
        dcur.executemany(f'INSERT INTO "{table_name}" VALUES ({placeholders})', data_rows)

    for meta_table in _BOOKKEEPING_TABLES:
        _copy_bookkeeping_row(template_con, target_con, meta_table, table_name)

    _copy_table_triggers(template_con, target_con, table_name)

    return True


def _copy_table_triggers(template_con, target_con, table_name):
    """
    Copiaza triggerele GDAL de contorizare ("trigger_*_feature_count_*") ale
    tabelei din sablon - se pierd la DROP TABLE, iar fara ele
    "gpkg_ogr_contents.feature_count" nu mai ramane la zi.
    """
    tcur = template_con.cursor()
    tcur.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND tbl_name=? AND sql IS NOT NULL",
        (table_name,),
    )
    dcur = target_con.cursor()
    for name, sql in tcur.fetchall():
        dcur.execute(f'DROP TRIGGER IF EXISTS "{name}"')
        dcur.execute(sql)


def _copy_missing_reference_layers(template_con, target_con, missing_tables):
    added = []
    for table_name in missing_tables:
        if _copy_reference_table(template_con, target_con, table_name):
            added.append(table_name)
    return added


# -- caz special: inlocuire completa a tabelelor de referinta "_*" -----------

def _table_column_names(con, table_name):
    cur = con.cursor()
    cur.execute(f'PRAGMA table_info("{table_name}")')
    return [row[1] for row in cur.fetchall()]


def _table_rows_without_fid(con, table_name, columns):
    keep = [c for c in columns if c != "fid"]
    if not keep:
        return set()
    cur = con.cursor()
    cur.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in keep)} FROM "{table_name}"')
    return set(cur.fetchall())


def _reference_tables_needing_replacement(template_con, target_con):
    """
    Numele tabelelor de referinta "_*" (nu "__*" - vechiul "__versiune" e tratat
    separat) existente si in sablon si in proiect, a caror schema (nume de
    coloane) sau continut (fara "fid") difera de cele din sablon - de
    inlocuit in intregime cu varianta din sablon. Cazuri reale: proiecte
    anterioare 3.0.3, unde "_siruta" era o ierarhie pe 3 niveluri (coloane
    "siruta", "denloc", "sirsup", ...) in loc de lista plata de localitati
    (coloane "siruta_jud", "judet", "siruta_uat", ...); sablonul 3.1.0, care a
    corectat diacriticele ("ş" -> "ș"), denumirea municipiului Oradea,
    mediul urban/rural al unor localitati si valorile din "_stadiu_plan".
    Nu contin date introduse de utilizator.
    """
    tcur = template_con.cursor()
    tcur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    candidates = [
        name for (name,) in tcur.fetchall()
        if name.startswith("_") and not name.startswith("__") and _table_exists(target_con, name)
    ]
    needing = []
    for name in candidates:
        template_columns = _table_column_names(template_con, name)
        if template_columns != _table_column_names(target_con, name):
            needing.append(name)
        elif _table_rows_without_fid(template_con, name, template_columns) != _table_rows_without_fid(
            target_con, name, template_columns
        ):
            needing.append(name)
    return needing


# -- caz special: valorile "PlanSpatial.Stadiu" (acentuate din 3.1.0) --------

def _strip_diacritics(text):
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _stadiu_value_map(template_con, target_con):
    """
    {valoare_veche: valoare_din_sablon} pentru valorile din
    "PlanSpatial.Stadiu" care difera doar prin diacritice de o valoare din
    "_stadiu_plan" a sablonului (ex. "In curs de elaborare" -> "În curs de
    elaborare"; compararea ignora si diferenta ş/ș). Gol daca stratul/coloana/
    tabela de referinta lipsesc.
    """
    if not _table_exists(template_con, STADIU_LOOKUP_LAYER) or not _table_exists(target_con, PLANSPATIAL_LAYER):
        return {}
    if "Stadiu" not in _table_column_names(target_con, PLANSPATIAL_LAYER):
        return {}
    tcur = template_con.cursor()
    tcur.execute(f'SELECT definitie FROM "{STADIU_LOOKUP_LAYER}"')
    canonical = {_strip_diacritics(v): v for (v,) in tcur.fetchall() if v}
    cur = target_con.cursor()
    cur.execute(f'SELECT DISTINCT Stadiu FROM "{PLANSPATIAL_LAYER}" WHERE Stadiu IS NOT NULL')
    mapping = {}
    for (value,) in cur.fetchall():
        target_value = canonical.get(_strip_diacritics(value.strip()))
        if target_value is not None and target_value != value:
            mapping[value] = target_value
    return mapping


def _count_stadiu_rows(target_con, mapping):
    cur = target_con.cursor()
    total = 0
    for old_value in mapping:
        cur.execute(f'SELECT COUNT(*) FROM "{PLANSPATIAL_LAYER}" WHERE Stadiu=?', (old_value,))
        total += cur.fetchone()[0]
    return total


def _migrate_stadiu_values(gpkg_path, mapping):
    """
    Rescrie valorile din `mapping` ({vechi: nou}) in PlanSpatial.Stadiu.
    Prin OGR, NU prin sqlite3: PlanSpatial e o tabela spatiala, iar triggerele
    ei rtree apeleaza functii SQL ("ST_IsEmpty" etc.) pe care sqlite3 nu le
    are - orice UPDATE direct esueaza cu "no such function". Driverul GPKG
    din GDAL le inregistreaza. Ruleaza dupa inchiderea conexiunilor sqlite3.
    """
    if not mapping:
        return
    ds = ogr.Open(gpkg_path, 1)
    if ds is None:
        raise _AbortUpdate(f"Nu s-a putut deschide GPKG-ul pentru scriere:\n{gpkg_path}")
    try:
        for old_value, new_value in mapping.items():
            old_sql = old_value.replace("'", "''")
            new_sql = new_value.replace("'", "''")
            ds.ExecuteSQL(f"UPDATE \"{PLANSPATIAL_LAYER}\" SET Stadiu='{new_sql}' WHERE Stadiu='{old_sql}'")
    finally:
        ds = None


# -- caz special: sincronizare continut "sys__versiune" ----------------------

def _read_versiune_tip(con, table_name):
    """Valoarea "tip" din primul rand al tabelei, sau None (tabela/coloana/rand lipsa sau gol)."""
    if not _table_exists(con, table_name) or "tip" not in _table_column_names(con, table_name):
        return None
    cur = con.cursor()
    cur.execute(f'SELECT tip FROM "{table_name}" LIMIT 1')
    row = cur.fetchone()
    return row[0] if row and row[0] else None


def _create_table_from_template(template_con, target_con, table_name):
    """CREATE TABLE (exact din sablon) + bookkeeping + triggere, FARA date."""
    tcur = template_con.cursor()
    tcur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    row = tcur.fetchone()
    if row is None or row[0] is None:
        return False
    target_con.cursor().execute(row[0])
    for meta_table in _BOOKKEEPING_TABLES:
        _copy_bookkeeping_row(template_con, target_con, meta_table, table_name)
    if _table_exists(target_con, "gpkg_ogr_contents"):
        target_con.cursor().execute(
            'UPDATE "gpkg_ogr_contents" SET feature_count=0 WHERE table_name=?', (table_name,)
        )
    _copy_table_triggers(template_con, target_con, table_name)
    return True


# Acelasi tipar de nume de fisier folosit si de valoarea implicita a
# "PlanSpatial.NivelPlan" din sablon (regexp_substr dupa segmentul SIRUTA,
# numeric): JUD_UAT_SIRUTA_TIP_AAAALLZZ.gpkg - foloseste segmentul numeric
# (SIRUTA) pentru a gasi urmatorul segment (tipul proiectului), indiferent
# daca numele UAT-ului insusi contine spatii.
_PROJECT_TIP_RE = re.compile(r"_(\d+)_([^_/\\]+)_")


def _guess_project_tip(gpkg_path, fallback):
    """
    Deduce tipul de proiect (PUG/PUZ/...) din numele fisierului GPKG.
    Folosit doar cand proiectul tinta nu are deja un rand in "sys__versiune"
    / "__versiune" (proiect vechi/corupt) - in caz normal, valoarea existenta e pastrata
    neschimbata in loc sa fie dedusa. Fallback pe tipul din sablon
    ('PUG') daca numele fisierului nu respecta tiparul asteptat.
    """
    match = _PROJECT_TIP_RE.search(os.path.basename(gpkg_path))
    return match.group(2) if match else fallback


def _sync_versiune_table(template_con, target_con, gpkg_path):
    """
    Sincronizeaza "versiune" si "data" (numarul de schema) ale tabelei
    "sys__versiune" a proiectului cu cele din sablon, neconditionat (la
    fiecare actualizare de pachet, indiferent daca tabelele de referinta/RLUD
    au trebuit sau nu modificate) - pastreaza ordinea/numele coloanelor
    proiectului, doar valorile sunt sincronizate. Daca proiectul nu are inca
    "sys__versiune" (sabloane < 3.1.0, unde tabela se numea "__versiune"),
    tabela e creata din sablon, iar "tip" e preluat din vechiul "__versiune";
    acesta din urma e eliminat mai tarziu, ca tabel de referinta neutilizat.

    "tip" (PUG/PUZ/PUD/PATJ/PMUD) e tratat separat: sablonul contine mereu
    'PUG' (nu exista un sablon per tip de proiect), asa ca NU e copiat din
    sablon - valoarea deja prezenta in proiectul tinta e pastrata. Doar la
    insertia unui rand nou (proiect fara "__versiune" existent) tipul e
    dedus din numele fisierului GPKG (_guess_project_tip), cu fallback pe
    tipul sablonului.

    Returneaza True daca a scris ceva.
    """
    if not _table_exists(template_con, VERSIUNE_LAYER):
        return False
    tcur = template_con.cursor()
    tcur.execute(f'SELECT versiune, tip, data FROM "{VERSIUNE_LAYER}" LIMIT 1')
    row = tcur.fetchone()
    if row is None:
        return False
    template_values = {"versiune": row[0], "tip": row[1], "data": row[2]}

    # tipul din vechiul "__versiune" (sabloane < 3.1.0) trebuie citit INAINTE
    # ca acel tabel sa fie eliminat ca tabel de referinta neutilizat.
    legacy_tip = _read_versiune_tip(target_con, LEGACY_VERSIUNE_LAYER)

    if not _table_exists(target_con, VERSIUNE_LAYER):
        _create_table_from_template(template_con, target_con, VERSIUNE_LAYER)

    cur = target_con.cursor()
    cur.execute(f'PRAGMA table_info("{VERSIUNE_LAYER}")')
    target_columns = [r[1] for r in cur.fetchall()]

    cur.execute(f'SELECT COUNT(*) FROM "{VERSIUNE_LAYER}"')
    has_existing_row = cur.fetchone()[0] > 0

    existing_tip = _read_versiune_tip(target_con, VERSIUNE_LAYER) or legacy_tip
    tip = existing_tip if existing_tip else _guess_project_tip(gpkg_path, template_values["tip"])

    values = {"versiune": template_values["versiune"], "tip": tip, "data": template_values["data"]}
    settable = [c for c in target_columns if c in values]
    if not settable:
        return False

    params = [values[c] for c in settable]
    if not has_existing_row:
        columns_sql = ", ".join(f'"{c}"' for c in settable)
        placeholders = ", ".join("?" * len(settable))
        cur.execute(f'INSERT INTO "{VERSIUNE_LAYER}" ({columns_sql}) VALUES ({placeholders})', params)
    else:
        set_clause = ", ".join(f'"{c}"=?' for c in settable)
        cur.execute(f'UPDATE "{VERSIUNE_LAYER}" SET {set_clause}', params)
    if _table_exists(target_con, "gpkg_ogr_contents"):
        cur.execute(
            'UPDATE "gpkg_ogr_contents" SET feature_count='
            f'(SELECT COUNT(*) FROM "{VERSIUNE_LAYER}") WHERE table_name=?',
            (VERSIUNE_LAYER,),
        )
    return True


def _versiune_needs_sync(template_con, target_con):
    """
    True daca _sync_versiune_table ar schimba ceva: tabela "sys__versiune"
    lipseste din proiect, nu are exact un rand sau "versiune"/"data" difera de
    sablon ("tip" nu se sincronizeaza niciodata - vezi _sync_versiune_table).
    """
    if not _table_exists(template_con, VERSIUNE_LAYER):
        return False
    if not _table_exists(target_con, VERSIUNE_LAYER):
        return True
    tcur = template_con.cursor()
    tcur.execute(f'SELECT versiune, data FROM "{VERSIUNE_LAYER}" LIMIT 1')
    template_row = tcur.fetchone()
    if template_row is None:
        return False
    expected = {"versiune": template_row[0], "data": template_row[1]}
    columns = [c for c in expected if c in _table_column_names(target_con, VERSIUNE_LAYER)]
    if not columns:
        return False
    cur = target_con.cursor()
    cur.execute(f'SELECT {", ".join(chr(34) + c + chr(34) for c in columns)} FROM "{VERSIUNE_LAYER}"')
    rows = cur.fetchall()
    return len(rows) != 1 or any(rows[0][i] != expected[c] for i, c in enumerate(columns))


# -- caz special: aliniere schema RegulamentLocalUrbanismDetaliat ------------

RLUD_LAYER = "RegulamentLocalUrbanismDetaliat"

# coloana numerica -> coloana "..._detaliu" (text liber, adaugata tot in
# sablonul 3.0.3) care primeste valorile ce nu pot fi convertite curat la
# numeric, la migrarea schemei vechi (3.0.2, unde erau TEXT) la cea curenta -
# vezi _migrate_rlud_schema(). Proiectele mai vechi (2.x), unde aceste
# coloane erau deja numerice, nu trec prin conversie - doar coloanele noi
# lipsa (inclusiv cele "..._detaliu") sunt adaugate.
RLUD_DETALIU_COLUMNS = {
    "Clad_Hmax": "Clad_Hmax_detaliu",
    "POT": "POT_detaliu",
    "CUT": "CUT_detaliu",
}


def _sqlite_type_affinity(declared_type):
    """
    Aproximeaza regula standard SQLite de determinare a afinitatii de tip
    (https://www.sqlite.org/datatype3.html#determination_of_column_affinity),
    suficient pentru a distinge "coloana e stocata ca TEXT" (schema 3.0.2,
    pentru Clad_Hmax/POT/CUT) de "coloana e deja numerica" (INTEGER/REAL -
    scheme pre-3.0.2, sau deja migrata).
    """
    t = (declared_type or "").upper()
    if "INT" in t:
        return "INTEGER"
    if "CHAR" in t or "CLOB" in t or "TEXT" in t:
        return "TEXT"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "REAL"
    if "BLOB" in t or t == "":
        return "BLOB"
    return "NUMERIC"


def _rlud_columns_needing_numeric_migration(con):
    """
    Coloanele din RLUD_DETALIU_COLUMNS care sunt inca stocate ca TEXT in
    `con` (schema veche 3.0.2) - trebuie convertite la afinitate numerica.
    Lista goala daca tabela nu exista sau daca toate coloanele sunt deja
    numerice (scheme pre-3.0.2, sau deja migrate).
    """
    if not _table_exists(con, RLUD_LAYER):
        return []
    cur = con.cursor()
    cur.execute(f'PRAGMA table_info("{RLUD_LAYER}")')
    declared = {row[1]: row[2] for row in cur.fetchall()}
    return [
        c for c in RLUD_DETALIU_COLUMNS
        if c in declared and _sqlite_type_affinity(declared[c]) == "TEXT"
    ]


def _ogr_field_type_names(gpkg_path, layer_name):
    """{nume_camp: nume_tip_OGR} (ex. "Integer" pe 32 biti, "Integer64"), sau {}."""
    ds = ogr.Open(gpkg_path, 0)
    if ds is None:
        return {}
    try:
        layer = ds.GetLayerByName(layer_name)
        if layer is None:
            return {}
        defn = layer.GetLayerDefn()
        return {
            defn.GetFieldDefn(i).GetName(): defn.GetFieldDefn(i).GetTypeName()
            for i in range(defn.GetFieldCount())
        }
    finally:
        ds = None


def _rlud_columns_needing_type_change(template_gpkg, target_gpkg):
    """
    Coloanele din RLUD_DETALIU_COLUMNS deja numerice in proiect, dar cu alt tip
    OGR decat in sablon (ex. "Integer" pe 32 biti din sabloanele 3.0.3-3.0.4 vs
    "Integer64" din 3.1.0+) - regula 10 a validatorului oficial cere tipuri
    identice. Se aplica TUTUROR proiectelor, inclusiv celor 2.x (fara
    coloanele "..._detaliu"): inainte de 2.2.3 acestea isi pastrau tipul
    "Integer"; actualizarea doar adauga coloanele "..._detaliu", iar regula 10
    continua sa esueze ("Clad_Hmax/POT: Integer, asteptat Integer64") pana la
    A DOUA rulare, cand coloanele "..._detaliu" existau deja. Cele 3.0.2
    (TEXT) sunt tratate de _rlud_columns_needing_numeric_migration().
    """
    template_types = _ogr_field_type_names(template_gpkg, RLUD_LAYER)
    target_types = _ogr_field_type_names(target_gpkg, RLUD_LAYER)
    if not template_types or not target_types:
        return []
    return [
        c for c in RLUD_DETALIU_COLUMNS
        if c in target_types and c in template_types
        and target_types[c] != "String"
        and target_types[c] != template_types[c]
    ]


def _rlud_missing_columns(template_con, target_con):
    """Coloane (nume, tip declarat) prezente in sablon dar lipsa din proiect."""
    if not _table_exists(template_con, RLUD_LAYER) or not _table_exists(target_con, RLUD_LAYER):
        return []
    tcur = template_con.cursor()
    tcur.execute(f'PRAGMA table_info("{RLUD_LAYER}")')
    template_columns = [(row[1], row[2]) for row in tcur.fetchall()]
    target_names = set(_table_column_names(target_con, RLUD_LAYER))
    return [(name, decl_type) for name, decl_type in template_columns if name not in target_names]


def _parse_rlud_numeric(raw):
    """
    Incearca sa converteasca `raw` (valoare TEXT existenta intr-o coloana
    Clad_Hmax/POT/CUT dintr-un proiect cu schema 3.0.2) la un numar.
    Returneaza (valoare_numerica_sau_None, text_de_pastrat_sau_None):
        - text gol/NULL: (None, None) - nimic de pastrat.
        - text care se converteste curat (ex. "12", "0,45" -> 0.45):
          (numar, None).
        - text care NU se converteste curat (ex. "P+2", "35%", "S+P+3E"):
          (None, text_original) - valoarea originala e pastrata in coloana
          "..._detaliu" corespunzatoare, nu pierduta.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    normalized = text.replace(",", ".")
    try:
        if "." in normalized:
            return float(normalized), None
        return int(normalized), None
    except ValueError:
        return None, text


def _migrate_rlud_schema(template_con, target_con, columns_to_numeric, force_rebuild=False):
    """
    Aliniaza schema RLUD_LAYER a proiectului cu cea din sablonul curent.

    Daca `columns_to_numeric` e gol si `force_rebuild` e False (proiect cu
    Clad_Hmax/POT/CUT deja numerice - scheme pre-3.0.2, sau deja migrate), nu
    se schimba niciun tip de coloana - doar coloanele lipsa fata de sablon
    sunt adaugate, cu ALTER TABLE ADD COLUMN (ieftin, fara reconstructie).
    `force_rebuild=True` (tipuri numerice de aliniat la sablon, ex. Integer ->
    Integer64 - vezi _rlud_columns_needing_type_change) reconstruieste tabela
    fara nicio conversie de valori.

    Daca `columns_to_numeric` contine coloane (proiect cu schema 3.0.2, unde
    acestea sunt TEXT), tabela e reconstruita cu schema curenta din sablon
    (SQLite nu suporta ALTER COLUMN TYPE): valorile care se pot converti
    curat la numeric sunt pastrate, convertite; cele care nu pot (notatii ca
    "P+2" sau "35%") sunt mutate in coloana "..._detaliu" corespunzatoare
    (vezi RLUD_DETALIU_COLUMNS) in loc sa fie pierdute, iar coloana numerica
    ramane NULL pentru acel rand. Coloanele lipsa sunt adaugate ca parte a
    aceleiasi reconstructii.

    Returneaza (rebuilt, added_columns, moved_to_detaliu):
        rebuilt = True daca a fost necesara reconstructia completa,
        added_columns = numele coloanelor noi adaugate,
        moved_to_detaliu = {coloana: numar_valori_mutate_in_detaliu}
        (doar coloane cu cel putin o valoare mutata).
    """
    tcur = template_con.cursor()
    tcur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (RLUD_LAYER,))
    row = tcur.fetchone()
    if row is None or row[0] is None:
        return False, [], {}  # sablonul nu are (inca) acest strat; nu blocam restul actualizarii

    cur = target_con.cursor()

    if not columns_to_numeric and not force_rebuild:
        missing = _rlud_missing_columns(template_con, target_con)
        for name, decl_type in missing:
            cur.execute(f'ALTER TABLE "{RLUD_LAYER}" ADD COLUMN "{name}" {decl_type}')
        return False, [name for name, _ in missing], {}

    tmp_name = f"{RLUD_LAYER}_migrare_{uuid.uuid4().hex[:8]}"
    cur.execute(f'ALTER TABLE "{RLUD_LAYER}" RENAME TO "{tmp_name}"')
    cur.execute(row[0])  # CREATE TABLE ... (schema curenta, din sablon)

    cur.execute(f'PRAGMA table_info("{tmp_name}")')
    old_columns = {r[1] for r in cur.fetchall()}
    cur.execute(f'PRAGMA table_info("{RLUD_LAYER}")')
    new_columns = [r[1] for r in cur.fetchall()]
    common_columns = [c for c in new_columns if c in old_columns]

    select_columns_sql = ", ".join(f'"{c}"' for c in common_columns)
    cur.execute(f'SELECT {select_columns_sql} FROM "{tmp_name}"')
    old_rows = cur.fetchall()
    col_index = {c: i for i, c in enumerate(common_columns)}

    # coloanele "..._detaliu" corespunzatoare coloanelor migrate, daca exista
    # in sablonul curent - primesc valorile text nemigrate curat.
    insert_columns = list(common_columns)
    for c in columns_to_numeric:
        detaliu_col = RLUD_DETALIU_COLUMNS.get(c)
        if detaliu_col and detaliu_col in new_columns and detaliu_col not in insert_columns:
            insert_columns.append(detaliu_col)

    insert_columns_sql = ", ".join(f'"{c}"' for c in insert_columns)
    placeholders = ", ".join("?" * len(insert_columns))
    insert_sql = f'INSERT INTO "{RLUD_LAYER}" ({insert_columns_sql}) VALUES ({placeholders})'

    moved_to_detaliu = {c: 0 for c in columns_to_numeric}
    for old_row in old_rows:
        row_values = {c: old_row[col_index[c]] for c in common_columns}
        for c in columns_to_numeric:
            if c not in row_values:
                continue
            numeric, leftover_text = _parse_rlud_numeric(row_values[c])
            row_values[c] = numeric
            detaliu_col = RLUD_DETALIU_COLUMNS.get(c)
            if leftover_text is not None and detaliu_col in insert_columns:
                row_values[detaliu_col] = leftover_text
                moved_to_detaliu[c] += 1
        cur.execute(insert_sql, [row_values.get(c) for c in insert_columns])

    cur.execute(f'DROP TABLE "{tmp_name}"')
    _copy_table_triggers(template_con, target_con, RLUD_LAYER)

    if _table_exists(target_con, "gpkg_ogr_contents"):
        cur.execute(
            'UPDATE "gpkg_ogr_contents" SET feature_count='
            f'(SELECT COUNT(*) FROM "{RLUD_LAYER}") WHERE table_name=?',
            (RLUD_LAYER,),
        )

    added_columns = [c for c in new_columns if c not in old_columns]
    return True, added_columns, {k: v for k, v in moved_to_detaliu.items() if v}


# -- actualizare stiluri --------------------------------------------------

_MAX_PROBED_STYLE_ID = 5000


def _find_unreadable_layer_styles_rows(con):
    """
    Returneaza id-urile din "layer_styles" ale caror randuri nu pot fi
    citite complet (pagini de overflow corupte) - detectate incercand sa
    citeasca fiecare rand in parte. SELECT-uri simple (ex. doar coloane
    scurte) pot reusi pentru astfel de randuri; abia citirea continutului
    complet (styleQML, de obicei zeci-sute de KB, stocat pe pagini de
    overflow) declanseaza eroarea.

    Daca nici macar lista de id-uri nu poate fi citita (arborele B al
    tabelei e deteriorat la nivel de noduri interne), se sondeaza id-urile
    1.._MAX_PROBED_STYLE_ID unul cate unul.
    """
    cur = con.cursor()
    try:
        cur.execute("SELECT id FROM layer_styles")
        all_ids = [row[0] for row in cur.fetchall()]
    except sqlite3.DatabaseError:
        all_ids = list(range(1, _MAX_PROBED_STYLE_ID + 1))
    bad_ids = []
    for rid in all_ids:
        try:
            cur.execute("SELECT * FROM layer_styles WHERE id=?", (rid,))
            cur.fetchone()
        except sqlite3.DatabaseError:
            bad_ids.append(rid)
    return bad_ids


def _layer_styles_needs_rebuild(con):
    """
    Detecteaza probleme structurale ale tabelei "layer_styles" care nu
    provoaca neaparat o eroare la citire/scriere normala prin sqlite3, dar
    care fac ca GDAL/OGR (folosit de QGIS pentru listStylesInDatabase(), deci
    si de dialogul "Load Style") sa parcurga gresit arborele B si sa arate
    randuri "fantoma" duplicate - vazut empiric pe un proiect legacy validat
    cu succes de validatorul oficial v2.0.5, unde PRAGMA integrity_check
    raporta "2nd reference to page X" (o pagina referentiata de doua ori in
    acelasi arbore) desi fiecare rand era individual citibil (deci
    _find_unreadable_layer_styles_rows nu detecta nimic) si "SELECT * FROM
    layer_styles" prin sqlite3 intorcea exact numarul corect de randuri, fara
    duplicate - doar accesul GDAL la nivel de pagina era afectat.

    Verificarea de integritate se limiteaza la tabela "layer_styles"
    (PRAGMA integrity_check(layer_styles), SQLite >= 3.33): o verificare pe
    intreaga baza de date ar esua si din cauza unor pagini corupte ramase
    in ALTE tabele - de ex. in tabela "orfana" lasata de o reconstructie
    anterioara (vezi _purge_orphan_layer_styles_tables) - si ar declansa o
    reconstructie inutila (si un nou orfan) la FIECARE actualizare. O eroare
    SQLite aruncata chiar de verificare (pagini corupte atinse in timpul
    parcurgerii) inseamna, ea insasi, "tabel deteriorat" - inainte de aceasta
    corectura, exceptia nu era prinsa si oprea actualizarea cu "database
    disk image is malformed".
    """
    if _find_unreadable_layer_styles_rows(con):
        return True
    cur = con.cursor()
    try:
        if sqlite3.sqlite_version_info >= (3, 33, 0):
            cur.execute("PRAGMA integrity_check(layer_styles)")
        else:
            cur.execute("PRAGMA integrity_check")
        rows = cur.fetchall()
    except sqlite3.DatabaseError:
        return True
    return not (len(rows) == 1 and rows[0][0] == "ok")


ORPHAN_PREFIX = "layer_styles_corrupted_orphan_"


def _orphan_layer_styles_tables(gpkg_path):
    """Numele tabelelor "orfane" (vezi _rebuild_layer_styles_table) din gpkg_path."""
    con = sqlite3.connect(gpkg_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (ORPHAN_PREFIX + "%",))
        return sorted(name for (name,) in cur.fetchall())
    finally:
        con.close()


def _purge_orphan_layer_styles_tables(gpkg_path):
    """
    Elimina DEFINITIV din fisier tabelele "layer_styles_corrupted_orphan_*"
    lasate de _rebuild_layer_styles_table (si de versiunile < 2.2.3 ale
    plugin-ului, care le pastrau "doar redenumite").

    Motivul: orfanul pastreaza chiar paginile corupte care au declansat
    reconstructia, deci "PRAGMA integrity_check" pe intreaga baza de date
    ramane "database disk image is malformed" PENTRU TOTDEAUNA, iar orice
    verificare/operatie ulterioara care parcurge tot fisierul esueaza (cazul
    raportat: a doua rulare a "Actualizeaza pachetul" se oprea cu aceasta
    eroare).

    1. DROP TABLE normal - merge cand lantul de pagini al randurilor este
       intact (ex. orfan creat din cauza unei coruptii "silentioase").
    2. Daca DROP TABLE esueaza (SQLite trebuie sa citeasca paginile corupte
       ca sa le elibereze): intrarea tabelei se sterge direct din
       sqlite_master (PRAGMA writable_schema), iar VACUUM reconstruieste
       fisierul numai din paginile ACCESIBILE din schema - paginile corupte,
       acum nereferentiate, nu mai sunt copiate. Verificat empiric: dupa
       aceasta operatie "PRAGMA integrity_check" intoarce "ok".

    Returneaza (nume_eliminate, eroare_sau_None). Apelata cu fisierul GPKG
    inchis de orice alta conexiune, ca restul pasilor sqlite3 directi.
    """
    names = _orphan_layer_styles_tables(gpkg_path)
    if not names:
        return [], None
    # autocommit: VACUUM nu poate rula intr-o tranzactie
    con = sqlite3.connect(gpkg_path, isolation_level=None)
    try:
        remaining = []
        for name in names:
            try:
                con.execute(f'DROP TABLE "{name}"')
            except sqlite3.DatabaseError:
                remaining.append(name)
        if remaining:
            quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in remaining)
            con.execute("PRAGMA writable_schema=ON")
            con.execute(f"DELETE FROM sqlite_master WHERE type='table' AND name IN ({quoted})")
            con.execute("PRAGMA writable_schema=OFF")
            con.close()
            con = sqlite3.connect(gpkg_path, isolation_level=None)  # schema reincarcata
            con.execute("VACUUM")
        return names, None
    except sqlite3.Error as exc:
        return [], str(exc)
    finally:
        con.close()


def _canonical_template_styles(template_con):
    """
    ({nume_strat: tuplu_de_11_coloane_fara_id}, {nume_strat: numar_randuri_in_sablon})
    - randul canonic per strat al sablonului (vezi _copy_layer_styles pentru
    regula de alegere); duplicatele sunt raportate separat. ({}, {}) daca
    sablonul nu are stiluri.
    """
    if not _table_exists(template_con, "layer_styles"):
        return {}, {}
    tcur = template_con.cursor()
    tcur.execute(
        "SELECT id, f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
        "styleName, styleQML, styleSLD, useAsDefault, description, owner, ui "
        "FROM layer_styles"
    )
    rows_by_table = {}
    for row in tcur.fetchall():
        rows_by_table.setdefault(row[3], []).append(row)  # row[3] = f_table_name
    duplicate_counts = {}
    canonical = {}
    for table_name, rows in rows_by_table.items():
        if len(rows) > 1:
            duplicate_counts[table_name] = len(rows)
        default_rows = [r for r in rows if r[8]]  # r[8] = useAsDefault
        chosen = default_rows[0] if len(default_rows) == 1 else max(rows, key=lambda r: r[0])
        canonical[table_name] = chosen[1:]  # elimina "id"
    return canonical, duplicate_counts


def _styles_needing_update(template_con, target_con, existing_target_tables):
    """
    Straturile (prezente in proiect) al caror stil din "layer_styles" difera de
    cel canonic din sablon: lipseste, exista in mai multe exemplare sau are alt
    continut. Un rand care nu poate fi citit conteaza ca "difera". Fara
    efecte secundare - folosita atat pentru dialogul de confirmare, cat si
    de _copy_layer_styles, ca sa NU rescrie stiluri deja identice cu sablonul.
    """
    canonical, _ = _canonical_template_styles(template_con)
    if not canonical:
        return []
    if not _table_exists(target_con, "layer_styles"):
        return sorted(t for t in canonical if t in existing_target_tables)
    cur = target_con.cursor()
    needing = []
    for table_name, row in canonical.items():
        if table_name not in existing_target_tables:
            continue
        try:
            cur.execute(
                "SELECT f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
                "styleName, styleQML, styleSLD, useAsDefault, description, owner, ui "
                "FROM layer_styles WHERE f_table_name = ?",
                (table_name,),
            )
            found = cur.fetchall()
        except sqlite3.DatabaseError:
            needing.append(table_name)
            continue
        if len(found) != 1 or tuple(found[0]) != tuple(row):
            needing.append(table_name)
    return sorted(needing)


def _rebuild_layer_styles_table(con, bad_ids):
    """
    Reconstruieste tabela "layer_styles", pastrand doar randurile din
    bad_ids excluse (poate fi o lista goala - vezi mai jos), intr-o tabela
    noua cu arbore B curat.

    O simpla stergere sau actualizare a unui rand cu pagini de overflow
    corupte esueaza (SQLite trebuie sa citeasca lantul de pagini ca sa le
    elibereze) - la fel si un DROP TABLE pe tabela veche. In schimb, se
    creeaza o tabela noua cu schema canonica si se copiaza (INSERT ...
    SELECT) doar randurile din afara bad_ids - filtrarea "id NOT IN (...)"
    se face pe rowid, inainte de a incerca sa citeasca payload-ul randurilor
    excluse, deci nu atinge paginile corupte (cu bad_ids gol, filtrul e un
    simplu "copiaza tot", dar tot construieste un arbore B nou, curat -
    necesar si pentru coruptii "silentioase" gen referinte duplicate de
    pagina, care nu impiedica citirea niciunui rand individual). Tabela
    veche (cu problema inca in ea) e doar redenumita ("orfana"), nu stearsa
    - ramane TEMPORAR in fisier, inaccesibila prin numele "layer_styles"
    folosit de QGIS/OGR; e eliminata definitiv, la finalul pasilor sqlite3,
    de _purge_orphan_layer_styles_tables (altfel paginile ei corupte
    pastreaza fisierul "malformed" pentru orice verificare de integritate).

    Returneaza (bad_ids, nume_tabela_orfana).
    """
    orphan_name = "layer_styles_corrupted_orphan_" + uuid.uuid4().hex[:8]
    rebuilt_name = "layer_styles_repaired_" + uuid.uuid4().hex[:8]

    cur = con.cursor()
    cur.execute(_LAYER_STYLES_CREATE_SQL.replace('"layer_styles"', f'"{rebuilt_name}"'))
    placeholders = ",".join("?" * len(bad_ids))
    cur.execute(
        f'INSERT INTO "{rebuilt_name}" SELECT * FROM layer_styles WHERE id NOT IN ({placeholders})',
        bad_ids,
    )
    cur.execute(f'ALTER TABLE layer_styles RENAME TO "{orphan_name}"')
    cur.execute(f'ALTER TABLE "{rebuilt_name}" RENAME TO layer_styles')
    con.commit()

    return bad_ids, orphan_name


def _repair_corrupted_layer_styles(con):
    """
    Varianta reactiva a _rebuild_layer_styles_table, apelata dintr-un bloc
    except dupa ce o operatie asupra "layer_styles" a esuat cu o eroare de
    coruptie SQLite ("database disk image is malformed") - vazut in practica
    pe un proiect vechi cu 13 randuri duplicate de stil pentru acelasi strat
    (semn ca stilul fusese re-salvat repetat fara sa inlocuiasca randul
    vechi, posibil dintr-o versiune mai veche a plugin-ului), dintre care 2
    aveau pagini de overflow corupte (probabil dintr-o scriere intrerupta).

    Ridica din nou eroarea originala daca nu s-a gasit niciun rand corupt -
    inseamna ca esecul avea alta cauza, nu una pe care stim sa o reparam.
    """
    bad_ids = _find_unreadable_layer_styles_rows(con)
    if not bad_ids:
        raise
    return _rebuild_layer_styles_table(con, bad_ids)


def _copy_layer_styles(template_con, target_con, existing_target_tables):
    """
    Pentru fiecare strat cu stil salvat in sablon SI prezent in proiect,
    inlocuieste intrarile din "layer_styles" ale proiectului cu cele din
    sablon - EXACT un rand per strat, indiferent cate are sablonul (vezi
    mai jos), astfel incat rezultatul sa fie mereu "acelasi stil ca in
    sablon, nici mai mult, nici mai putin".

    Returneaza (nume_actualizate, nume_ignorate, info_reparare) - ignorate
    fiind straturile cu stil in sablon dar care nu exista (inca) in proiect,
    iar info_reparare fiind None sau (id-uri_randuri_corupte,
    nume_tabela_orfana) daca "layer_styles" a trebuit reconstruita din cauza
    unei coruptii (vezi _repair_corrupted_layer_styles).
    """
    # sablonul ar trebui sa aiba UN SINGUR rand de stil per strat de continut.
    # Randuri suplimentare se pot acumula in timp in copia ACTIVA a
    # sablonului (nu in cea bundled cu plugin-ul) daca "Salveaza sablonul"
    # a fost apelat repetat cu un nume de stil diferit de fiecare data -
    # QGIS creeaza un rand nou in loc sa il inlocuiasca pe cel vechi cand
    # numele difera (confirmat empiric); vezi si _repair_corrupted_layer_styles
    # pentru acelasi fenomen, observat intr-un proiect cu 13 randuri
    # duplicate pentru un singur strat. Fara deduplicare (vezi
    # _canonical_template_styles: randul cu useAsDefault=1, daca exact unul,
    # altfel cel mai recent), un sablon "murdar" ar propaga toate randurile
    # vechi in fiecare proiect actualizat.
    canonical_by_table, duplicate_counts = _canonical_template_styles(template_con)
    if not canonical_by_table:
        return [], [], None, {}  # sablonul nu are (deloc) stiluri salvate

    updated = []
    skipped = sorted(t for t in canonical_by_table if t not in existing_target_tables)
    repaired_info = None

    dcur = target_con.cursor()
    if not _table_exists(target_con, "layer_styles"):
        dcur.execute(_LAYER_STYLES_CREATE_SQL)
    elif _layer_styles_needs_rebuild(target_con):
        # reconstructie proactiva, nu doar reactiva la o eroare sqlite3 - vezi
        # _layer_styles_needs_rebuild pentru coruptia "silentioasa" (pagini
        # referentiate de doua ori) care nu arunca nicio eroare la DELETE/INSERT
        # de mai jos, dar tot produce randuri fantoma duplicate in QGIS.
        repaired_info = _rebuild_layer_styles_table(
            target_con, _find_unreadable_layer_styles_rows(target_con)
        )
        dcur = target_con.cursor()

    # abia DUPA o eventuala reconstructie: doar stilurile care chiar difera de
    # sablon sunt rescrise (nu mai rescriem neconditionat 11 stiluri de sute
    # de KB la fiecare rulare, nici nu le mai raportam ca "actualizate").
    to_update = set(_styles_needing_update(template_con, target_con, existing_target_tables))

    insert_sql = (
        "INSERT INTO layer_styles "
        "(f_table_catalog, f_table_schema, f_table_name, f_geometry_column, "
        "styleName, styleQML, styleSLD, useAsDefault, description, owner, ui) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )

    # commit-uri per strat (nu o singura tranzactie mare): daca un rand corupt
    # provoaca o eroare la jumatatea buclei, progresul de pana atunci (inclusiv
    # straturile de referinta adaugate anterior in _run_impl, inca necomise)
    # trebuie pastrat - un rollback dupa o eroare de coruptie SQLite anuleaza
    # intreaga tranzactie curenta, nu doar instructiunea care a esuat.
    for table_name, row in canonical_by_table.items():
        if table_name not in to_update:
            continue
        try:
            dcur.execute("DELETE FROM layer_styles WHERE f_table_name = ?", (table_name,))
            dcur.execute(insert_sql, row)
            target_con.commit()
        except sqlite3.DatabaseError:
            # o eroare de coruptie lasa tranzactia curenta intr-o stare in care
            # nicio alta instructiune nu mai poate rula (nici macar CREATE TABLE
            # pentru reparare) pana la un rollback explicit.
            target_con.rollback()
            repaired_info = _repair_corrupted_layer_styles(target_con)
            dcur = target_con.cursor()
            dcur.execute("DELETE FROM layer_styles WHERE f_table_name = ?", (table_name,))
            dcur.execute(insert_sql, row)
            target_con.commit()
        updated.append(table_name)

    return sorted(updated), sorted(skipped), repaired_info, dict(sorted(duplicate_counts.items()))


def _remove_reference_layer_styles(target_con):
    """
    Straturile de referinta (nume care incep cu "~" sau "_") nu ar trebui sa
    aiba niciodata un rand in layer_styles - sablonul nu are (vezi
    _copy_layer_styles, care nu le atinge deloc), iar "nimic mai mult, nimic
    mai putin fata de sablon" inseamna ca nici proiectul nu ar trebui sa
    aiba. O versiune mai veche a "Proiect nou PUG" salva totusi din greseala
    un stil si pentru straturile de referinta prefixate cu "_" (corectat
    separat in project_loader.py) - proiectele deja create cu acea versiune
    raman cu aceste randuri nedorite pana la urmatoarea actualizare de
    pachet. Curatare defensiva, indiferent de cauza.
    """
    cur = target_con.cursor()
    if not _table_exists(target_con, "layer_styles"):
        return []
    cur.execute("SELECT DISTINCT f_table_name FROM layer_styles")
    stray_tables = sorted(name for (name,) in cur.fetchall() if name.startswith(REF_PREFIXES))
    if not stray_tables:
        return []
    for table_name in stray_tables:
        cur.execute("DELETE FROM layer_styles WHERE f_table_name = ?", (table_name,))
    target_con.commit()
    return stray_tables


# -- strat de referinta "~REF_UAT" (caz special, nu se copiaza din sablon) ---

def _project_siruta(ps_layer):
    """Codul SIRUTA unic din stratul PlanSpatial, sau None daca nu poate fi
    determinat univoc (camp lipsa, 0 sau mai multe valori distincte)."""
    field_names = {f.name() for f in ps_layer.fields()}
    if "SIRUTA" not in field_names:
        return None
    values = {feat["SIRUTA"] for feat in ps_layer.getFeatures() if feat["SIRUTA"] is not None}
    if len(values) != 1:
        return None
    return next(iter(values))


def _ref_uat_row_count(gpkg_path):
    """Numarul de inregistrari din tabelul "~REF_UAT" al gpkg_path, sau None daca tabelul nu exista."""
    con = sqlite3.connect(gpkg_path)
    try:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (uat_boundary.LAYER_NAME,),
        )
        if cur.fetchone() is None:
            return None
        cur.execute(f'SELECT COUNT(*) FROM "{uat_boundary.LAYER_NAME}"')
        return cur.fetchone()[0]
    finally:
        con.close()


# -- helpers proiect QGIS ------------------------------------------------------

def _find_group_by_name(node, name):
    for child in node.children():
        if isinstance(child, QgsLayerTreeGroup):
            if child.name() == name:
                return child
            found = _find_group_by_name(child, name)
            if found is not None:
                return found
    return None


def _add_layers_to_ref_group(project, gpkg_path, table_names):
    root = project.layerTreeRoot()
    ref_group = _find_group_by_name(root, REF_GROUP_NAME)
    if ref_group is None:
        if not table_names:
            return  # niciun grup existent si nimic de adaugat - nu crea unul gol
        # proiectele create de acest plugin (vezi project_loader.py) au
        # intotdeauna un grup "principal", numit dupa proiect, la radacina
        # arborelui, cu "REF" cuibarit in el - nu direct la radacina. Daca
        # exista exact un singur grup de nivel superior, e cu siguranta acel
        # grup principal; altfel (structura neobisnuita) se creeaza direct
        # la radacina, cel mai sigur fallback disponibil.
        top_groups = [c for c in root.children() if isinstance(c, QgsLayerTreeGroup)]
        parent = top_groups[0] if len(top_groups) == 1 else root
        ref_group = parent.addGroup(REF_GROUP_NAME)  # la finalul grupului parinte (jos)
    else:
        parent = ref_group.parent()
        if parent is not None and parent.children()[-1] is not ref_group:
            # grupul exista deja, dar nu e ultimul copil al parintelui lui
            # (ex. dintr-o versiune mai veche a plugin-ului, care il crea la
            # inceputul arborelui) - vizual, straturile de mai jos in arbore
            # se deseneaza DEASUPRA celor de mai sus, deci un grup de
            # referinta sus in arbore (ex. "~REF_UAT", un poligon ce acopera
            # tot UAT-ul) acoperea vizual toata harta. takeChild()+
            # addChildNode() muta nodul existent (cu tot ce contine) la
            # finalul PARINTELUI SAU REAL (poate fi grupul principal al
            # proiectului, nu neaparat radacina arborelui), fara sa il
            # recreeze. Spre deosebire de removeChildNode() (care sterge
            # nodul), takeChild() il doar detaseaza - obiectul "ref_group"
            # ramane valabil de refolosit (takeChild() returneaza bool, nu
            # nodul detasat).
            if parent.takeChild(ref_group):
                parent.addChildNode(ref_group)
    ref_group.setExpanded(False)

    for table_name in sorted(table_names):
        # elimina orice strat existent cu acelasi nume, ramas invalid din
        # proiectul vechi (sursa lipsea din GPKG pana acum) - fara aceasta
        # curatare ar ramane un strat "fantoma" invalid alaturi de cel nou,
        # iar mapLayersByName() ar deveni ambiguu.
        _remove_project_layers_for_tables(project, gpkg_path, [table_name])

        layer = QgsVectorLayer(f"{gpkg_path}|layername={table_name}", table_name, "ogr")
        if not layer.isValid():
            continue
        project.addMapLayer(layer, False)
        ref_group.addLayer(layer)
        tree_layer = root.findLayer(layer.id())
        if tree_layer is not None:
            tree_layer.setExpanded(False)


def _sync_virtual_ref_layers(project):
    """
    Straturile de referinta "virtuale" (provider QGIS "virtual" - o
    interogare SQL peste alte straturi deja incarcate, fara tabel propriu
    in GPKG - vezi tools/virtual_layers.py) nu sunt tabele GPKG, deci nu pot
    fi verificate/copiate ca restul straturilor de referinta. Se
    reconstruiesc direct daca lipsesc sau daca interogarea lor curenta
    difera de cea canonica (inclusiv cazul unui proiect vechi cu interogarea
    corupta - vezi virtual_layers.py pentru mecanismul de coruptie la
    salvare, intalnit intr-un proiect real).

    Trebuie apelata DUPA ce straturile sursa (ex. "~REF_SZF", "~REF_ZRS_D")
    sunt deja incarcate in proiect - altfel interogarea noua e invalida
    (straturile "virtual" rezolva FROM-urile dupa nume, printre straturile
    deja incarcate, nu direct din fisier) si e ignorata silentios.

    Returneaza lista numelor straturilor efectiv inlocuite.
    """
    root = project.layerTreeRoot()
    ref_group = _find_group_by_name(root, REF_GROUP_NAME)
    replaced = []

    for name in sorted(virtual_layers.VREF_QUERIES):
        new_layer = virtual_layers.create_vref_layer(name)
        if not new_layer.isValid():
            continue  # straturile sursa nu sunt (inca) incarcate - las asa cum e

        existing = project.mapLayersByName(name)
        if existing and virtual_layers.current_query(existing[0]) == virtual_layers.VREF_QUERIES[name]:
            continue  # deja corect - nu atinge inutil arborele de straturi

        for stale_layer in existing:
            project.removeMapLayer(stale_layer.id())

        project.addMapLayer(new_layer, False)
        if ref_group is not None:
            ref_group.addLayer(new_layer)
        tree_layer = root.findLayer(new_layer.id())
        if tree_layer is not None:
            tree_layer.setExpanded(False)

        replaced.append(name)

    return replaced


def _vref_layers_needing_rebuild(project):
    """Numele straturilor virtuale pe care _sync_virtual_ref_layers le-ar reconstrui (fara efecte)."""
    result = []
    for name in sorted(virtual_layers.VREF_QUERIES):
        if not virtual_layers.create_vref_layer(name).isValid():
            continue
        existing = project.mapLayersByName(name)
        if existing and virtual_layers.current_query(existing[0]) == virtual_layers.VREF_QUERIES[name]:
            continue
        result.append(name)
    return result


def _obsolete_virtual_ref_layers(project):
    """Straturile "virtual" necunoscute din grupul REF (vezi _remove_obsolete_virtual_ref_layers)."""
    ref_group = _find_group_by_name(project.layerTreeRoot(), REF_GROUP_NAME)
    if ref_group is None:
        return []
    found = []
    for tree_layer in ref_group.findLayers():
        layer = tree_layer.layer()
        if layer is None or layer.dataProvider() is None:
            continue
        if layer.dataProvider().name() == "virtual" and layer.name() not in virtual_layers.VREF_QUERIES:
            found.append(layer)
    return found


def _ref_group_misplaced(project):
    """True daca grupul REF exista si nu e ultimul copil al parintelui sau (sau e expandat)."""
    ref_group = _find_group_by_name(project.layerTreeRoot(), REF_GROUP_NAME)
    if ref_group is None:
        return False
    parent = ref_group.parent()
    return bool(parent is not None and parent.children()[-1] is not ref_group)


def _remove_obsolete_virtual_ref_layers(project):
    """
    Straturi "virtual" (acelasi provider QGIS ca in virtual_layers.py) ramase
    in grupul "REF", dar care NU corespund niciunui strat virtual cunoscut
    (virtual_layers.VREF_QUERIES) - ramase dintr-o schema mai veche, ex.
    "~vREF_ZF_ZRS", predecesorul lui "~vREF_SZF_ZRS_D", care refera tabele
    ("~REF_ZF", "~REF_ZRS") ce nu mai exista deloc in sablonul curent.
    _remove_unused_reference_tables() nu le poate prinde - acelea sunt
    straturi GPKG reale, verificate prin lista de tabele a fisierului
    (_gpkg_table_names), pe cand un strat "virtual" nu are niciun tabel
    propriu in GPKG. Scanarea se limiteaza la grupul "REF" (nu la tot
    proiectul), ca sa nu atinga vreun strat "virtual" adaugat manual de
    utilizator in afara lui, pentru propriile lui scopuri.

    Returneaza lista numelor straturilor eliminate.
    """
    removed = []
    for layer in _obsolete_virtual_ref_layers(project):
        removed.append(layer.name())
        project.removeMapLayer(layer.id())

    return sorted(removed)


def _deselect_ref_group(iface, project):
    """
    Grupul "REF" (sau un strat din el) nu ar trebui sa ramana "stratul
    curent" (evidentiat in panoul Straturi) dupa actualizare - QGIS
    evidentiaza automat ultimul strat inserat in arbore, ceea ce lasa un
    strat de referinta (nefolosit direct de utilizator) evidentiat in loc de
    un strat de continut relevant, imediat dupa ce _add_layers_to_ref_group
    a adaugat straturi noi. Muta explicit stratul activ pe un strat de
    continut (preferabil "PlanSpatial") si goleste selectia din panoul
    Straturi. Defensiv fata de un iface minimal (ex. in teste) - orice
    metoda lipsa e ignorata.
    """
    root = project.layerTreeRoot()
    content_layer = None
    for lyr in project.mapLayers().values():
        node = root.findLayer(lyr.id())
        if node is None:
            continue
        parent = node.parent()
        if isinstance(parent, QgsLayerTreeGroup) and parent.name() == REF_GROUP_NAME:
            continue
        if lyr.name() == "PlanSpatial":
            content_layer = lyr
            break
        if content_layer is None:
            content_layer = lyr
    if content_layer is not None:
        try:
            iface.setActiveLayer(content_layer)
        except Exception:
            pass
    try:
        iface.layerTreeView().selectionModel().clearSelection()
    except Exception:
        pass


def _remove_unused_reference_tables(gpkg_path, table_names):
    """
    Elimina din fisierul GPKG tabelele de referinta (prefix "~"/"_") care nu
    mai fac parte din sablonul curent - ramase dintr-o schema de numire mai
    veche (ex. un sablon specific unui judet, cu tabele precum "~REF_UAT_HR",
    inlocuit between timp cu unul generic).

    Foloseste DeleteLayer() din GDAL, nu DROP TABLE SQL direct - acesta
    curata corect si bookkeeping-ul GeoPackage asociat (gpkg_contents,
    gpkg_geometry_columns, gpkg_ogr_contents, indexul spatial rtree si
    declansatoarele lui), pe care o reconstructie manuala prin SQL ar fi
    fragila si greu de tinut sincronizata cu evolutia specificatiei
    GeoPackage.

    Trebuie apelata dupa ce orice conexiune sqlite3 catre gpkg_path a fost
    inchisa (ca in restul _run_impl - vezi comentariul de la apelul
    uat_boundary.fetch_uat_boundary) si INAINTE de project.read(), ca sa nu
    concureze cu vreun handle QGIS/GDAL deschis pe acelasi fisier.

    Returneaza lista tabelelor efectiv sterse.
    """
    if not table_names:
        return []

    removed = []
    ds = ogr.Open(gpkg_path, update=1)
    if ds is None:
        return []
    try:
        wanted = set(table_names)
        # DeleteLayer() ia un index, nu un nume - se cauta indexul curent al
        # fiecarui strat vizat inainte de fiecare stergere (indicii celor
        # ramase se pot renumerota dupa fiecare DeleteLayer()).
        while wanted:
            idx = next(
                (i for i in range(ds.GetLayerCount()) if ds.GetLayerByIndex(i).GetName() in wanted),
                None,
            )
            if idx is None:
                break
            name = ds.GetLayerByIndex(idx).GetName()
            wanted.discard(name)
            if ds.DeleteLayer(idx) == 0:
                removed.append(name)
    finally:
        ds = None
    return removed


_NUMBERED_PREFIX_RE = re.compile(r"^(\d+_\d+)_", re.IGNORECASE)


def _template_file_plan(template_dir, project_root):
    """
    (missing, mismatches), fara efecte secundare.

    missing    : [(cale_relativa, sursa, destinatie)] - fisiere din sablon, din
                 afara folderului GPKG, care trebuie copiate in proiect.
    mismatches : [(cale_relativa_sablon, nume_existent)] - fisiere PDF din sablon
                 NECOPIATE pentru ca proiectul are deja un fisier cu acelasi
                 prefix numeric (ex. "1_3_") dar alt nume; ramane neschimbat.

    Reguli (regula 5 a validatorului oficial: numele exacte 1_x_..3_x_ in
    folderele 1_/2_/3_, orice PDF care incepe cu "4_" in folderul 4_):
      - fisier lipsa dupa nume exact, in 1_/2_/3_: daca exista deja un fisier cu
        acelasi prefix numeric -> nepotrivire de nume (nu se copiaza, se
        raporteaza); altfel se copiaza;
      - folderul 4_: daca exista deja vreun PDF care incepe cu "4_", nu se
        adauga nimic; altfel se adauga toate PDF-urile din sablon;
      - orice alt fisier: se copiaza daca lipseste dupa nume exact.
    """
    template_dir = template_dir.rstrip("/\\")
    gpkg_folder_name = GPKG_FOLDER.rstrip("/")
    missing, mismatches = [], []
    for dirpath, dirnames, filenames in os.walk(template_dir):
        rel_dir = os.path.relpath(dirpath, template_dir)
        top_level = rel_dir.split(os.sep)[0]
        if top_level == gpkg_folder_name:
            dirnames[:] = []  # nu coboara deloc in acest subfolder
            continue
        target_dir = os.path.join(project_root, rel_dir)
        try:
            existing = os.listdir(target_dir) if os.path.isdir(target_dir) else []
        except OSError:
            existing = []
        existing_lower = [n.lower() for n in existing]
        is_avize = rel_dir != "." and top_level.startswith("4_") and os.sep not in rel_dir
        has_avize_pdf = is_avize and any(n.startswith("4_") and n.endswith(".pdf") for n in existing_lower)
        for filename in filenames:
            rel_path = filename if rel_dir == "." else os.path.join(rel_dir, filename)
            target_path = os.path.join(project_root, rel_path)
            if os.path.exists(target_path):
                continue
            is_pdf = filename.lower().endswith(".pdf")
            if is_avize and is_pdf:
                if has_avize_pdf:
                    continue
            elif is_pdf and rel_dir != ".":
                match = _NUMBERED_PREFIX_RE.match(filename)
                if match:
                    prefix = match.group(1).lower() + "_"
                    same = [n for n in existing if n.lower().startswith(prefix)]
                    if same:
                        mismatches.append((rel_path.replace(os.sep, "/"), same[0]))
                        continue
            missing.append((rel_path.replace(os.sep, "/"), os.path.join(dirpath, filename), target_path))
    return missing, mismatches


def _missing_template_files(template_dir, project_root):
    """[(cale_relativa, sursa, destinatie)] de copiat - vezi _template_file_plan."""
    return _template_file_plan(template_dir, project_root)[0]


def _template_name_mismatches(template_dir, project_root):
    """[(cale_sablon, nume_existent)] - vezi _template_file_plan."""
    return _template_file_plan(template_dir, project_root)[1]


def _sync_missing_template_files(template_dir, project_root):
    """
    Copiaza in folderul proiectului orice fisier prezent in sablon dar lipsa
    din proiect, in subfolderele DIN AFARA "0_Seturi_date_spatiale" (folderul
    GPKG-ului - continutul lui e gestionat separat, de restul acestei unelte,
    nu prin copiere bruta de fisiere).

    Strict aditiv, ca si restul acestei unelte: NU suprascrie niciun fisier
    deja existent in proiect (chiar daca difera de cel din sablon) si NU
    sterge niciun fisier din proiect care nu exista in sablon - doar adauga
    ce lipseste, pastrand structura de subfoldere din sablon.

    Returneaza lista cailor relative (fata de radacina proiectului) ale
    fisierelor copiate.
    """
    copied = []
    for rel_path, source, target_path in _missing_template_files(template_dir, project_root):
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(source, target_path)
        copied.append(rel_path)
    return sorted(copied)


def _reload_layer_styles_from_db(project, table_names):
    """
    Un strat QGIS deja incarcat in proiect NU isi reincarca automat stilul
    (widget-uri de camp, valori implicite, actiuni, simbolizare) doar pentru
    ca randul lui din "layer_styles" a fost suprascris prin SQL direct mai
    sus (_copy_layer_styles) - stilul unui strat deja incarcat vine din
    proiectul (.qgz) insusi, asa cum a fost salvat ultima data, nu este
    recitit din baza de date la fiecare operatie.

    Pentru straturile din table_names (cele returnate ca "updated_styles" de
    _copy_layer_styles), stilul e reincarcat IN-PLACE, pe obiectul de strat
    deja existent, prin layer.loadNamedStyle(layer.source(), False) (al
    doilea parametru = citeste din baza de date a sursei, nu din qgis.db
    local). Nu se creeaza niciun strat nou.

    O varianta anterioara facea acelasi lucru prin eliminarea si
    re-adaugarea stratului (un QgsVectorLayer nou creat dintr-un GPKG cu
    stil implicit salvat il incarca automat la creare) - functional corecta,
    dar mai costisitoare decat necesar (recreeaza obiectul de strat doar ca
    sa ii reincarce stilul). loadNamedStyle() face acelasi lucru in loc,
    fara sa creeze niciun QgsVectorLayer nou.

    NOTA: dialogul QGIS "Incarca stil din baza de date" poate arata acelasi
    nume de stil repetat de multe ori pentru un proiect cu multe straturi in
    acelasi fisier GPKG - INVESTIGAT (2026-07-28) si confirmat ca artefact
    la nivel GDAL/OGR al deschiderii mai multor straturi din acelasi fisier
    GPKG intr-o singura sesiune QGIS, reproductibil chiar si cu un
    QgsProject.read() simplu, fara nicio interventie de la package_updater -
    "layer_styles" insusi ramane mereu corect (un singur rand per strat,
    verificat direct prin SQL). Nu e cauzat de aceasta functie si nu poate
    fi reparat din codul plugin-ului.
    """
    reload_failures = []
    for table_name in sorted(table_names):
        layers = project.mapLayersByName(table_name)
        if not layers:
            continue  # nu era incarcat in proiect - nimic de reincarcat
        layer = layers[0]
        message, ok = layer.loadNamedStyle(layer.source(), False)
        if not ok:
            reload_failures.append(f"{table_name}: {message}")
    return reload_failures


# -- straturi din proiect care refera tabele ale GPKG-ului ------------------------

_LAYERNAME_RE = re.compile(r"\|layername=([^|]+)")


def _norm_path(path):
    return os.path.normcase(os.path.normpath(path))


def _layer_gpkg_table(layer):
    """
    (cale_gpkg_normalizata, nume_tabela) pentru un strat vectorial OGR cu sursa
    "<gpkg>|layername=<tabela>", altfel (None, None). Independent de NUMELE
    afisat al stratului (care poate fi redenumit de utilizator).
    """
    try:
        if layer.providerType() != "ogr":
            return None, None
        source = layer.source()
    except AttributeError:
        return None, None  # strat non-vectorial (raster etc.)
    match = _LAYERNAME_RE.search(source)
    if not match:
        return None, None
    return _norm_path(source.split("|")[0]), match.group(1)


def _project_layers_for_tables(project, gpkg_path, table_names):
    """
    Straturile din proiect care refera oricare dintre `table_names` ale lui
    `gpkg_path` - dupa SURSA (|layername=), nu doar dupa nume - plus orice strat
    cu numele egal cu al tabelei (inclusiv straturi invalide, cu sursa pierduta).
    """
    wanted = set(table_names)
    gp = _norm_path(gpkg_path)
    found = {}
    for layer in project.mapLayers().values():
        path, table = _layer_gpkg_table(layer)
        if path == gp and table in wanted:
            found[layer.id()] = layer
    for table_name in wanted:
        for layer in project.mapLayersByName(table_name):
            # potrivirea dupa nume atinge DOAR straturi ale acestui GPKG (sau
            # invalide, cu sursa pierduta) - niciodata un strat valid din alta
            # sursa (fisier extern, WMS, virtual...), chiar daca are acelasi nume.
            path, _table = _layer_gpkg_table(layer)
            if path is not None and path != gp:
                continue
            if path is None and layer.isValid():
                continue
            found[layer.id()] = layer
    return list(found.values())


def _remove_project_layers_for_tables(project, gpkg_path, table_names):
    """Elimina din proiect straturile din _project_layers_for_tables(); returneaza numele lor."""
    removed = []
    for layer in _project_layers_for_tables(project, gpkg_path, table_names):
        removed.append(layer.name())
        project.removeMapLayer(layer.id())
    return removed


def _remove_dangling_gpkg_layers(project, gpkg_path):
    """
    Elimina din proiect orice strat al carui tabel din `gpkg_path` nu mai exista
    (ex. tabel sters de actualizare, strat redenumit de utilizator, tabel
    ~REF_UAT disparut) - altfel QGIS se plange de un strat lipsa la urmatoarea
    deschidere a proiectului. Returneaza numele straturilor eliminate.
    """
    tables = _gpkg_table_names(gpkg_path)
    gp = _norm_path(gpkg_path)
    dangling = []
    for layer in list(project.mapLayers().values()):
        path, table = _layer_gpkg_table(layer)
        if path == gp and table not in tables:
            dangling.append(layer)
    names = []
    for layer in dangling:
        names.append(layer.name())
        project.removeMapLayer(layer.id())
    return names


# -- flux principal ------------------------------------------------------------

def _run_impl(iface):
    project = QgsProject.instance()
    project_file = project.fileName()
    if not project_file:
        raise _AbortUpdate("Proiectul curent nu a fost inca salvat pe disc.")

    ps_layers = project.mapLayersByName("PlanSpatial")
    if not ps_layers:
        raise _AbortUpdate(
            "Stratul 'PlanSpatial' nu a fost gasit in proiectul curent - "
            "acesta nu pare a fi un proiect PUG valid."
        )
    gpkg_path = ps_layers[0].source().split("|")[0]
    project_siruta = _project_siruta(ps_layers[0])

    try:
        template_dir = resolve_template_dir(ensure_active_copy=True)
    except TemplateNotFoundError as exc:
        raise _AbortUpdate(str(exc))
    template_gpkg = template_dir + GPKG_RELATIVE

    template_tables = _gpkg_table_names(template_gpkg)
    target_tables = _gpkg_table_names(gpkg_path)

    # "lipsa" inseamna aici "nu e incarcat ca strat in proiectul curent" -
    # NU doar "nu exista ca tabel in gpkg". Un tabel poate exista deja in
    # gpkg (dintr-o actualizare anterioara intrerupta, sau adaugat manual)
    # fara sa fi fost niciodata adaugat ca strat in proiect; verificarea
    # trebuie sa recupereze si acest caz, altfel ramane blocat definitiv -
    # odata ce tabelul exista in gpkg, o verificare bazata doar pe tabelele
    # din gpkg nu l-ar mai gasi vreodata "lipsa".
    # "~REF_UAT" e exclus: in sablon e mereu gol (doar structura), asa ca o
    # copiere naiva nu ar face decat sa adauge un tabel gol - trebuie populat
    # cu datele UAT-ului curent, vezi pasul dedicat de mai jos.
    # doar straturi VALIDE conteaza drept "incarcate" - un strat cu acelasi
    # nume poate exista in arborele proiectului dar invalid (sursa lipseste/
    # tabelul a fost sters), caz in care tot trebuie tratat ca "lipsa".
    loaded_layer_names = {lyr.name() for lyr in project.mapLayers().values() if lyr.isValid()}
    missing_ref_tables = sorted(
        t
        for t in template_tables
        if t.startswith(REF_PREFIXES) and t not in loaded_layer_names and t != uat_boundary.LAYER_NAME
    )
    # subset care chiar lipseste din gpkg si trebuie copiat din sablon (restul
    # din missing_ref_tables exista deja ca tabel, doar trebuie adaugat ca
    # strat in proiect - vezi mai jos, dupa project.read()).
    # "sys__versiune" NU se copiaza generic: _sync_versiune_table o creeaza,
    # pastrand "tip" din vechiul "__versiune" (o copie din sablon ar aduce 'PUG').
    tables_to_copy = [
        t for t in missing_ref_tables if t not in target_tables and t != VERSIUNE_LAYER
    ]

    ref_uat_count = _ref_uat_row_count(gpkg_path)
    needs_ref_uat = ref_uat_count is None or ref_uat_count == 0

    ref_uat_note = ""
    if needs_ref_uat:
        ref_uat_note = (
            "- Limita administrativa a UAT-ului curent (strat \"~REF_UAT\") lipseste "
            "sau este goala si va fi preluata online (sau din cache local).\n"
        )

    outdated_note = ""
    if active_copy_outdated():
        outdated_note = (
            "ATENTIE: sablonul activ (folosit pentru aceasta actualizare) pare sa fie "
            "dintr-o versiune mai veche decat cel inclus in plugin - actualizarea de mai "
            "jos va folosi totusi schema veche. Recomandat: anuleaza, deschide \"Despre "
            "PUG Tools\" si apasa \"Actualizeaza\" la sectiunea \"Copie activa\" a "
            "sablonului, apoi reia actualizarea pachetului.\n\n"
        )

    template_con_probe = sqlite3.connect(template_gpkg)
    target_con_probe = sqlite3.connect(gpkg_path)
    try:
        tables_to_replace = _reference_tables_needing_replacement(template_con_probe, target_con_probe)
        rlud_columns_to_migrate = _rlud_columns_needing_numeric_migration(target_con_probe)
        rlud_missing = _rlud_missing_columns(template_con_probe, target_con_probe)
        stadiu_value_map = _stadiu_value_map(template_con_probe, target_con_probe)
        stadiu_rows_to_migrate = _count_stadiu_rows(target_con_probe, stadiu_value_map)
        legacy_versiune_present = _table_exists(target_con_probe, LEGACY_VERSIUNE_LAYER)
        versiune_needs_sync = _versiune_needs_sync(template_con_probe, target_con_probe)
        styles_to_update = _styles_needing_update(
            template_con_probe, target_con_probe, target_tables | set(tables_to_copy)
        )
        layer_styles_damaged = (
            _table_exists(target_con_probe, "layer_styles")
            and _layer_styles_needs_rebuild(target_con_probe)
        )
        try:
            stray_ref_styles = (
                [] if not _table_exists(target_con_probe, "layer_styles") else sorted(
                    n for (n,) in target_con_probe.execute("SELECT DISTINCT f_table_name FROM layer_styles")
                    if n and n.startswith(REF_PREFIXES)
                )
            )
        except sqlite3.DatabaseError:
            stray_ref_styles = []  # tabela deteriorata - tratata de reconstructie
    finally:
        template_con_probe.close()
        target_con_probe.close()
    rlud_columns_to_retype = _rlud_columns_needing_type_change(template_gpkg, gpkg_path)

    replace_note = ""
    if tables_to_replace:
        replace_note = (
            f"- Tabelele de referinta {', '.join(tables_to_replace)} difera de cele din "
            "sablonul curent (schema veche sau date corectate in sablon) si vor fi "
            "inlocuite in intregime.\n"
        )

    stadiu_note = ""
    if stadiu_value_map:
        stadiu_note = (
            "- Valorile \"Stadiu\" din PlanSpatial vor fi rescrise cu diacritice, ca in "
            "sablonul curent: "
            + ", ".join(f"\"{old}\" -> \"{new}\"" for old, new in sorted(stadiu_value_map.items()))
            + " (singura modificare de date de continut).\n"
        )

    versiune_note = ""
    if legacy_versiune_present:
        versiune_note = (
            "- Tabela \"__versiune\" (sablon < 3.1.0) va fi inlocuita cu \"sys__versiune\" "
            "(tipul proiectului este pastrat).\n"
        )

    rlud_retype_note = ""
    if rlud_columns_to_retype:
        rlud_retype_note = (
            f"- Coloanele {', '.join(rlud_columns_to_retype)} din "
            "\"RegulamentLocalUrbanismDetaliat\" vor fi aliniate ca tip la sablonul curent "
            "(Integer pe 32 biti -> Integer pe 64 biti); valorile raman neschimbate.\n"
        )

    rlud_note = ""
    if rlud_columns_to_migrate:
        rlud_note = (
            f"- Coloanele {', '.join(rlud_columns_to_migrate)} din "
            "\"RegulamentLocalUrbanismDetaliat\" vor fi convertite la numeric (schema "
            "3.0.2 le avea text) - valorile care nu se pot converti curat sunt pastrate "
            "in coloanele \"..._detaliu\" corespunzatoare, nu pierdute.\n"
        )
        if rlud_missing:
            rlud_note += (
                f"- Coloanele noi {', '.join(name for name, _ in rlud_missing)} din "
                "\"RegulamentLocalUrbanismDetaliat\" vor fi adaugate.\n"
            )
    elif rlud_missing:
        rlud_note = (
            f"- Coloanele noi {', '.join(name for name, _ in rlud_missing)} din "
            "\"RegulamentLocalUrbanismDetaliat\" vor fi adaugate.\n"
        )

    # calculat AICI (nu doar mai tarziu, dupa stergerea efectiva) - straturile
    # din proiect care corespund acestor tabele trebuie eliminate din proiect
    # CAT TIMP E INCA INCARCAT, inainte sa disparta tabelele lor din GPKG -
    # vezi comentariul de la eliminarea lor de mai jos pentru motiv.
    unused_ref_tables_to_remove = sorted(
        t for t in target_tables if t.startswith(REF_PREFIXES) and t not in template_tables
    )

    # alte schimbari din afara GPKG-ului / la nivel de proiect - pentru ca
    # dialogul sa enumere DOAR ce se schimba cu adevarat (si ca "nimic de
    # facut" sa poata fi recunoscut) - vezi pasii corespunzatori mai jos.
    project_root_probe = os.path.dirname(os.path.dirname(gpkg_path))
    missing_files = _missing_template_files(template_dir, project_root_probe)
    orphan_tables_present = _orphan_layer_styles_tables(gpkg_path)
    vref_to_rebuild = _vref_layers_needing_rebuild(project)
    vref_obsolete = [lyr.name() for lyr in _obsolete_virtual_ref_layers(project)]
    ref_group_misplaced = _ref_group_misplaced(project)
    gp_norm = _norm_path(gpkg_path)
    dangling_probe = sorted(
        lyr.name() for lyr in project.mapLayers().values()
        if _layer_gpkg_table(lyr)[0] == gp_norm and _layer_gpkg_table(lyr)[1] not in target_tables
    )

    change_lines = []
    if missing_ref_tables:
        change_lines.append(
            f"- {len(missing_ref_tables)} strat(uri) de referinta lipsa vor fi adaugate "
            f"({', '.join(missing_ref_tables)}).\n"
        )
    for note in (
        ref_uat_note, replace_note, stadiu_note, rlud_retype_note, rlud_note, versiune_note
    ):
        if note:
            change_lines.append(note)
    if versiune_needs_sync:
        change_lines.append(
            "- Numarul de versiune al pachetului (tabela \"sys__versiune\") va fi actualizat "
            "la cel al sablonului curent.\n"
        )
    if styles_to_update:
        change_lines.append(
            f"- Stilul a {len(styles_to_update)} strat(uri) difera de sablon si va fi inlocuit "
            f"({', '.join(styles_to_update)}): widget-uri de camp, valori implicite, actiuni, "
            "simbolizare.\n"
        )
    if layer_styles_damaged:
        change_lines.append(
            "- Tabela \"layer_styles\" a fisierului GPKG este deteriorata (pagini corupte / "
            "referentiate de doua ori) si va fi reconstruita; randurile ilizibile se pierd, "
            "stilurile se refac din sablon.\n"
        )
    if orphan_tables_present or layer_styles_damaged:
        change_lines.append(
            "- Tabelele ramase dintr-o reparare anterioara (\"layer_styles_corrupted_orphan_*\") "
            "sau create acum vor fi eliminate definitiv din fisier (cu VACUUM, care "
            "reconstruieste fisierul GPKG).\n"
        )
    if stray_ref_styles:
        change_lines.append(
            "- Stiluri salvate gresit pentru straturi de referinta vor fi sterse "
            f"({', '.join(stray_ref_styles)}).\n"
        )
    if unused_ref_tables_to_remove:
        change_lines.append(
            "- Tabelele de referinta care nu mai fac parte din sablon vor fi eliminate: "
            f"{', '.join(unused_ref_tables_to_remove)}.\n"
        )
    if missing_files:
        change_lines.append(
            f"- {len(missing_files)} fisier(e) din sablon lipsa din folderele proiectului vor fi "
            "copiate (fisierele existente nu sunt atinse).\n"
        )
    if vref_to_rebuild or vref_obsolete:
        change_lines.append(
            "- Straturi virtuale de referinta de reconstruit/eliminat: "
            f"{', '.join(vref_to_rebuild + vref_obsolete)}.\n"
        )
    if dangling_probe:
        change_lines.append(
            f"- Straturi cu sursa lipsa vor fi eliminate din proiect: {', '.join(dangling_probe)}.\n"
        )
    if ref_group_misplaced:
        change_lines.append("- Grupul de straturi \"REF\" va fi mutat la finalul arborelui.\n")

    if not change_lines:
        QMessageBox.information(
            iface.mainWindow(),
            "Actualizeaza pachetul",
            "Pachetul este deja la zi fata de sablonul curent - nu e nimic de actualizat.",
        )
        return False

    answer = QMessageBox.question(
        iface.mainWindow(),
        "Actualizeaza pachetul",
        f"{outdated_note}"
        "Proiectul curent va fi actualizat la structura sablonului curent:\n\n"
        + "".join(change_lines)
        + "\n"
        "Datele din straturile cu continut (PlanSpatial, ZFExistenta etc.) NU sunt "
        "modificate.\n\n"
        "Inainte de orice modificare, proiectul (.qgz) si intregul folder al pachetului "
        "vor fi salvate intr-o arhiva .zip de rezerva, in acelasi folder cu proiectul.\n\n"
        "Continui?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return False

    # copie de rezerva obligatorie - PRIMUL lucru dupa confirmare, inainte de
    # orice modificare (inclusiv eliminarea straturilor de mai jos) - daca
    # esueaza, _AbortUpdate opreste actualizarea inainte de a modifica orice.
    backup_path = _create_backup(project_file, gpkg_path)

    # straturile corespunzatoare tabelelor de referinta neutilizate
    # (unused_ref_tables_to_remove, calculat mai sus) si orice strat
    # "virtual" neconoscut (vezi _remove_obsolete_virtual_ref_layers)
    # trebuie eliminate din proiect ACUM, cat timp e inca incarcat, si
    # SALVATE (project.write()) - inainte ca tabelele lor sa fie sterse
    # din GPKG mai jos. Fara acest pas, project.read() de la finalul
    # functiei ar incerca sa rezolve straturi ale caror tabele tocmai au
    # disparut din fisier; intr-o sesiune QGIS reala (cu iface, nu in
    # teste headless), asta declanseaza dialogul interactiv "Handle
    # Unavailable Layers" al QGIS-ului insusi, care blocheaza executia
    # pana la interventie manuala a utilizatorului - confirmat empiric.
    _remove_project_layers_for_tables(project, gpkg_path, unused_ref_tables_to_remove)
    _remove_obsolete_virtual_ref_layers(project)
    project.write()

    # elibereaza blocarea fisierului GPKG inainte de a-l modifica direct (Windows;
    # acelasi motiv ca in preparator.py).
    project.clear()

    added = []
    updated_styles = []
    skipped_styles = []
    repaired_info = None
    duplicate_style_counts = {}
    removed_ref_styles = []
    removed_unused_tables = []
    synced_files = []
    file_name_mismatches = []
    ref_uat_error = None
    replaced_tables = []
    stadiu_rows_migrated = 0
    versiune_synced = False
    rlud_rebuilt = False
    rlud_added_columns = []
    rlud_moved_to_detaliu = {}
    purged_orphans = []
    purge_error = None
    try:
        template_con = sqlite3.connect(template_gpkg)
        target_con = sqlite3.connect(gpkg_path)
        try:
            added = _copy_missing_reference_layers(template_con, target_con, tables_to_copy)
            for table_name in tables_to_replace:
                if _copy_reference_table(template_con, target_con, table_name, drop_existing=True):
                    replaced_tables.append(table_name)
            if rlud_columns_to_migrate or rlud_columns_to_retype or rlud_missing:
                rlud_rebuilt, rlud_added_columns, rlud_moved_to_detaliu = _migrate_rlud_schema(
                    template_con, target_con, rlud_columns_to_migrate,
                    force_rebuild=bool(rlud_columns_to_retype),
                )
            versiune_synced = versiune_needs_sync and _sync_versiune_table(template_con, target_con, gpkg_path)
            # comis separat, inainte de _copy_layer_styles: daca stilurile
            # necesita repararea "layer_styles" (vezi _repair_corrupted_layer_styles),
            # un rollback la mijlocul acelui proces nu trebuie sa anuleze si
            # straturile de referinta deja adaugate (sau schemele "_siruta"/RLUD
            # actualizate) mai sus.
            target_con.commit()
            updated_styles, skipped_styles, repaired_info, duplicate_style_counts = _copy_layer_styles(
                template_con, target_con, target_tables | set(added)
            )
            removed_ref_styles = _remove_reference_layer_styles(target_con)
        finally:
            template_con.close()
            target_con.close()

        # tabelele "orfane" ale layer_styles (vezi
        # _purge_orphan_layer_styles_tables): TREBUIE eliminate, altfel
        # fisierul ramane "malformed" pentru orice verificare de integritate
        # si urmatoarea actualizare se opreste cu eroarea de baza de date.
        purged_orphans, purge_error = _purge_orphan_layer_styles_tables(gpkg_path)

        # valorile PlanSpatial.Stadiu - prin OGR, dupa inchiderea conexiunilor
        # sqlite3 (vezi _migrate_stadiu_values pentru motiv).
        if stadiu_value_map:
            _migrate_stadiu_values(gpkg_path, stadiu_value_map)
            stadiu_rows_migrated = stadiu_rows_to_migrate

        # "~REF_UAT" - caz special, populat prin uat_boundary.py (nu prin
        # copiere din sablon, unde e mereu gol). Ruleaza dupa ce conexiunile
        # sqlite3 de mai sus s-au inchis, ca sa nu concureze pe acelasi fisier.
        if needs_ref_uat:
            if project_siruta is None:
                ref_uat_error = (
                    "codul SIRUTA nu a putut fi determinat univoc din stratul "
                    "'PlanSpatial'."
                )
            else:
                try:
                    uat_boundary.fetch_uat_boundary(project_siruta, gpkg_path)
                    added.append(uat_boundary.LAYER_NAME)
                except uat_boundary.UatBoundaryError as exc:
                    ref_uat_error = str(exc)

        # tabele de referinta ramase dintr-o schema de numire mai veche, care
        # nu mai fac parte din sablonul curent (unused_ref_tables_to_remove,
        # calculat mai sus, inainte de eliminarea corespunzatoare din proiect
        # si backup) - ruleaza dupa ce conexiunile sqlite3 de mai sus s-au
        # inchis, ca sa nu concureze pe acelasi fisier (acelasi motiv ca la
        # "~REF_UAT" de mai sus).
        removed_unused_tables = _remove_unused_reference_tables(
            gpkg_path, unused_ref_tables_to_remove
        )

        # fisiere non-GPKG (studii, piese scrise/desenate, avize) prezente in
        # sablon dar lipsa din subfolderele proiectului - vezi
        # _sync_missing_template_files pentru limitele stricte (nu suprascrie,
        # nu sterge).
        project_root = os.path.dirname(os.path.dirname(gpkg_path))
        file_name_mismatches = _template_name_mismatches(template_dir, project_root)
        synced_files = _sync_missing_template_files(template_dir, project_root)
    finally:
        # indiferent de rezultat, proiectul trebuie redeschis - altfel utilizatorul
        # ramane cu QGIS gol.
        project.read(project_file)

    # straturile din missing_ref_tables (calculate mai sus fata de straturile
    # incarcate INAINTE de aceasta actualizare) trebuie adaugate ca straturi
    # acum, indiferent daca tabelul lor a fost copiat chiar in aceasta rulare
    # sau exista deja in gpkg dintr-o rulare anterioara neterminata - project.read()
    # de mai sus a refacut arborele de straturi exact ca inainte, deci lista
    # ramane valabila.
    layers_to_add = list(missing_ref_tables)
    if needs_ref_uat and not ref_uat_error:
        layers_to_add.append(uat_boundary.LAYER_NAME)

    # straturile corespunzatoare tabelelor tocmai sterse (removed_unused_tables)
    # ramin in arborele proiectului ca straturi INVALIDE dupa project.read()
    # de mai sus, pentru ca sursa lor (tabelul GPKG) nu mai exista - trebuie
    # eliminate explicit din proiect, tabelul insusi fiind deja sters.
    _remove_project_layers_for_tables(project, gpkg_path, removed_unused_tables)
    # plasa de siguranta: orice alt strat al carui tabel lipseste din GPKG
    # (redenumit de utilizator, ~REF_UAT esuat etc.) - vezi _remove_dangling_gpkg_layers.
    removed_dangling_layers = _remove_dangling_gpkg_layers(project, gpkg_path)

    # apelat neconditionat: chiar daca nu sunt straturi noi de adaugat, un
    # grup "REF" existent trebuie tot repozitionat/colapsat daca a ramas
    # gresit pozitionat dintr-o versiune mai veche a plugin-ului.
    _add_layers_to_ref_group(project, gpkg_path, layers_to_add)
    synced_vref_layers = _sync_virtual_ref_layers(project)
    removed_obsolete_vref_layers = _remove_obsolete_virtual_ref_layers(project)
    _deselect_ref_group(iface, project)

    # straturile de continut ale caror stil/valori implicite au fost tocmai
    # suprascrise in GPKG (updated_styles) trebuie reincarcate in proiect
    # pentru ca modificarea sa aiba efect - vezi _reload_layer_styles_from_db.
    reload_failures = []
    if updated_styles:
        reload_failures = _reload_layer_styles_from_db(project, updated_styles)

    project.write()

    already_in_gpkg = sorted(set(missing_ref_tables) - set(tables_to_copy))
    summary_lines = [
        f"Copie de rezerva: {backup_path}",
        "Straturi de referinta adaugate: "
        + (f"{len(layers_to_add)} ({', '.join(sorted(layers_to_add))})" if layers_to_add else "0"),
        "Stiluri actualizate: "
        + (f"{len(updated_styles)} ({', '.join(updated_styles)})" if updated_styles else "0"),
    ]
    if already_in_gpkg:
        summary_lines.append(
            "Dintre acestea, prezente deja in GPKG dar neincarcate ca straturi "
            f"(ex. dintr-o actualizare anterioara intrerupta): {len(already_in_gpkg)} "
            f"({', '.join(already_in_gpkg)})"
        )
    if skipped_styles:
        summary_lines.append(
            f"Stiluri ignorate (stratul nu exista in proiect): {len(skipped_styles)} "
            f"({', '.join(skipped_styles)})"
        )
    if ref_uat_error:
        summary_lines.append(f"Strat '~REF_UAT' NEACTUALIZAT: {ref_uat_error}")
    if replaced_tables:
        summary_lines.append(
            f"Tabele de referinta inlocuite cu cele din sablonul curent: {', '.join(replaced_tables)}."
        )
    if stadiu_rows_migrated:
        summary_lines.append(
            f"PlanSpatial.Stadiu: {stadiu_rows_migrated} valoare/valori rescrise cu diacritice."
        )
    if versiune_synced:
        summary_lines.append(f"Tabela '{VERSIUNE_LAYER}' actualizata la versiunea sablonului curent.")
    if rlud_rebuilt:
        detail_parts = []
        if rlud_columns_to_migrate:
            detail_parts.append(
                f"coloanele {', '.join(rlud_columns_to_migrate)} convertite la numeric "
                "(valorile care nu s-au putut converti curat au fost pastrate in coloanele "
                "\"..._detaliu\" corespunzatoare)"
            )
        if rlud_columns_to_retype:
            detail_parts.append(
                f"tip aliniat la sablon pentru {', '.join(rlud_columns_to_retype)}"
            )
        detail = "; ".join(detail_parts) or "tabela reconstruita"
        if rlud_added_columns:
            detail += f"; coloane noi adaugate: {', '.join(rlud_added_columns)}"
        summary_lines.append(f"Schema '{RLUD_LAYER}' actualizata: {detail}.")
        if rlud_moved_to_detaliu:
            moved_detail = ", ".join(f"{col} ({n})" for col, n in rlud_moved_to_detaliu.items())
            summary_lines.append(
                f"Valori text nemigrate curat, pastrate in coloanele \"..._detaliu\": {moved_detail}."
            )
    elif rlud_added_columns:
        summary_lines.append(
            f"Schema '{RLUD_LAYER}' actualizata: coloane noi adaugate: "
            f"{', '.join(rlud_added_columns)}."
        )
    if removed_ref_styles:
        summary_lines.append(
            "Stiluri nedorite eliminate de la straturi de referinta (nu ar trebui "
            f"sa aiba stil salvat): {len(removed_ref_styles)} ({', '.join(removed_ref_styles)})"
        )
    if removed_dangling_layers:
        summary_lines.append(
            "Straturi cu sursa lipsa eliminate din proiect: "
            f"{len(removed_dangling_layers)} ({', '.join(removed_dangling_layers)})"
        )
    if removed_unused_tables:
        summary_lines.append(
            "Tabele de referinta neutilizate (nu mai fac parte din sablonul "
            f"curent) eliminate din GPKG: {len(removed_unused_tables)} "
            f"({', '.join(removed_unused_tables)})"
        )
    if synced_files:
        summary_lines.append(
            "Fisiere lipsa preluate din sablon: "
            f"{len(synced_files)} ({', '.join(synced_files)})"
        )
    if file_name_mismatches:
        summary_lines.append(
            "ATENTIE - nume de fisier diferit de sablon (fisierul existent a fost pastrat, "
            "nu s-a copiat nimic; validatorul cere numele exacte pentru 1_, 2_, 3_): "
            + "; ".join(f"{t} <> {e}" for t, e in file_name_mismatches)
        )
    if synced_vref_layers:
        summary_lines.append(
            "Straturi virtuale de referinta reconstruite (lipseau sau interogarea "
            f"lor era invechita/corupta): {len(synced_vref_layers)} "
            f"({', '.join(synced_vref_layers)})"
        )
    if removed_obsolete_vref_layers:
        summary_lines.append(
            "Straturi virtuale de referinta neutilizate (nu mai fac parte din "
            f"sablonul curent) eliminate: {len(removed_obsolete_vref_layers)} "
            f"({', '.join(removed_obsolete_vref_layers)})"
        )
    if reload_failures:
        summary_lines.append(
            "ATENTIE: stilul din baza de date nu a putut fi reincarcat in proiectul "
            f"deschis pentru: {'; '.join(reload_failures)} (tabela GPKG e totusi "
            "corecta - un 'Deschide proiectul' din nou va arata stilul corect)."
        )
    if repaired_info:
        bad_ids, _orphan_name = repaired_info
        if bad_ids:
            summary_lines.append(
                f"ATENTIE: tabela 'layer_styles' continea {len(bad_ids)} rand(uri) "
                "corupte (nu au putut fi citite) - au fost izolate si eliminate din "
                "fisier, iar stilurile au fost refacute din sablon."
            )
        else:
            summary_lines.append(
                "Tabela 'layer_styles' avea o problema de structura (pagini "
                "referentiate de doua ori, cauza probabila a stilurilor "
                "'fantoma' duplicate din dialogul QGIS 'Load Style') - a fost "
                "reconstruita automat."
            )
    if purged_orphans:
        summary_lines.append(
            "Tabele 'layer_styles' deteriorate eliminate definitiv din fisier "
            f"({len(purged_orphans)})."
        )
    if purge_error:
        summary_lines.append(
            "ATENTIE: tabela 'layer_styles' deteriorata NU a putut fi eliminata din "
            f"fisier ({purge_error}). Fisierul GPKG ramane cu pagini corupte; copia de "
            "rezerva e intacta."
        )
    if duplicate_style_counts:
        detail = ", ".join(f"{name} ({count})" for name, count in duplicate_style_counts.items())
        summary_lines.append(
            "ATENTIE: sablonul curent are mai multe randuri de stil salvate pentru "
            f"acelasi strat, pentru: {detail} - a fost folosit doar cel curent "
            "(useAsDefault, sau cel mai recent). Recomandat: deschide 'Editeaza "
            "sablonul', apoi 'Salveaza sablonul', ca sa cureti randurile vechi din "
            "sablonul activ (altfel se repeta la fiecare actualizare de pachet)."
        )

    iface.messageBar().pushSuccess("Actualizeaza pachetul", " | ".join(summary_lines))
    return True
