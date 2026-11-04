# -*- coding: utf-8 -*-
"""
Preia dinamic limita administrativa (poligon) a unui singur UAT romanesc si
o scrie ca strat de referinta "~REF_UAT" (o singura entitate) direct in
fisierul GPKG al proiectului - NU ca strat in memorie - fara a include in
plugin sau in proiect intregul set national de limite UAT (ordinul de
marime: ~70-120 MB).

Sursa: serviciul WFS geo-spatial.org (OGC WFS 2.0.0), strat
"administrative-boundaries:ro_admin_lau_polygon":
    https://geo-spatial.org/ghiduri/procesari-etl/administrative-boundaries/ro-admin-lau-polygon/
    https://services.geo-spatial.org/geonetwork/srv/eng/catalog.search#/metadata/5d90a442-0659-4ad9-9af1-9b890b2ff0c8

Schema campurilor a fost verificata direct (DescribeFeatureType + GetFeature
de proba) si contine exact aceleasi informatii ca vechiul strat bundled
"~REF_UAT_HR": id, natcode (=SIRUTA), name, natlevname, countyid, countycode,
county, countymn, regionid, regioncode, region, version, geom - toate
campurile vechiului strat sunt acoperite, nimic nu lipseste. Proiectia
nativa este EPSG:3844, aceeasi ca proiectele PUG - nu e nevoie de
reproiectare.

Strategie de OBTINERE a datelor, in ordine (fiecare pas urmat doar daca cel
anterior esueaza), gandita explicit sa evite orice trafic de retea care nu
e strict necesar:

    1. Cache local per-UAT (un fisier .json mic per SIRUTA, in profilul
       QGIS) - daca exista deja (dintr-o creare anterioara de proiect
       pentru acelasi UAT), este folosit direct, fara niciun apel de retea.
    2. Interogare WFS filtrata server-side (CQL_FILTER pe natcode) - se
       transfera DOAR poligonul UAT-ului cerut (cateva zeci de KB), nu tot
       fisierul. Rezultatul e salvat in cache-ul per-UAT de mai sus, pentru
       urmatoarea creare de proiect pentru acelasi UAT.
    3. Daca interogarea filtrata esueaza (retea/serviciu indisponibil):
       cache local al INTREGULUI set de date (descarcat o singura data, la
       nevoie) - daca exista deja pe disc, UAT-ul cerut e filtrat local din
       el, fara alt apel de retea.
    4. Daca nici cache-ul intreg nu exista inca: se incearca o descarcare
       UNICA a intregului set de date (raspunsul WFS nefiltrat, format
       GeoPackage), care e apoi pastrata in cache pentru toate utilizarile
       viitoare (evita descarcari repetate ale intregului fisier).
    5. Daca niciuna dintre variantele de mai sus nu functioneaza (fara
       retea si fara niciun cache local): se ridica UatBoundaryError, cu un
       mesaj clar - crearea proiectului esueaza legitim in acest caz.

Strategie de SCRIERE in GPKG (write_boundary_layer/fetch_uat_boundary):
daca sablonul curent contine deja tabelul "~REF_UAT" gol (copiat automat in
orice proiect nou), se insereaza doar randul; altfel (sablon vechi, sau
proiect actualizat de tools/package_updater.py care nu avea deloc tabelul),
tabelul e creat intai. Crearea foloseste un nume temporar prin OGR (API-ul
de creare de straturi din GDAL respinge "~" in nume - "The layer name may
not contain special characters or spaces" - desi SQLite/GeoPackage insele
nu au nicio problema cu el), apoi redenumeste tabelul si intrarile de
bookkeeping GeoPackage prin SQL direct.
"""

import json
import os
import sqlite3
import urllib.parse
import uuid

from osgeo import ogr, osr
from qgis.core import QgsApplication, QgsBlockingNetworkRequest, QgsJsonUtils, QgsVectorLayer
from qgis.PyQt.QtCore import QDate, QDateTime, QUrl, QVariant
from qgis.PyQt.QtNetwork import QNetworkRequest

WFS_BASE_URL = "https://services.geo-spatial.org/geoserver/administrative-boundaries/ows"
WFS_TYPE_NAME = "administrative-boundaries:ro_admin_lau_polygon"
WFS_CRS_EPSG = 3844

FILTERED_TIMEOUT_MS = 20000
FULL_DOWNLOAD_TIMEOUT_MS = 10 * 60 * 1000  # descarcarea intregului set poate dura cateva minute

LAYER_NAME = "~REF_UAT"

# Schema campurilor stratului de referinta rezultat - identica cu vechiul
# strat bundled "~REF_UAT_HR" (id, SIRUTA, name, natLevName, countyId,
# countyCode, county, countyMn, regionId, regionCode, region, version),
# pentru compatibilitate cu restul plugin-ului (project_loader.py,
# validations/R26_planspatial_within_uat.py).
_FIELD_SPECS = [
    ("id", QVariant.Int),
    ("SIRUTA", QVariant.Int),
    ("name", QVariant.String),
    ("natLevName", QVariant.String),
    ("countyId", QVariant.Int),
    ("countyCode", QVariant.Int),
    ("county", QVariant.String),
    ("countyMn", QVariant.String),
    ("regionId", QVariant.Int),
    ("regionCode", QVariant.Int),
    ("region", QVariant.String),
    ("version", QVariant.String),
]

# maparea numelor de campuri publicate de WFS (natcode, natlevname, ...,
# vezi DescribeFeatureType, case-insensitive) la numele de campuri din
# schema de mai sus.
_WFS_TO_LOCAL_FIELD = {
    "natcode": "SIRUTA",
    "natlevname": "natLevName",
    "countyid": "countyId",
    "countycode": "countyCode",
    "countymn": "countyMn",
    "regionid": "regionId",
    "regioncode": "regionCode",
}


class UatBoundaryError(Exception):
    """Ridicata cand limita UAT nu poate fi obtinuta (nici online, nici din cache)."""


class _CacheUnreadable(UatBoundaryError):
    """
    Cache-ul intregului set de date exista pe disc dar nu poate fi deschis
    (fisier corupt/incomplet) - diferita in mod deliberat de "SIRUTA
    inexistent intr-un cache valid", care NU trebuie sa declanseze o
    redescarcare completa (ar insemna sa redescarcam ~70-120 MB de fiecare
    data cand cineva da un cod SIRUTA gresit).
    """


# -- cache -------------------------------------------------------------------

def _cache_root():
    base = QgsApplication.qgisSettingsDirPath()
    path = os.path.join(base, "PUGTools", "uat_cache")
    os.makedirs(path, exist_ok=True)
    return path


def _per_uat_cache_path(siruta):
    return os.path.join(_cache_root(), f"{siruta}.json")


def _full_dataset_cache_path():
    return os.path.join(_cache_root(), "ro_admin_lau_polygon_full.gpkg")


# -- retea ---------------------------------------------------------------

def _http_get(url, timeout_ms):
    """
    GET simplu, blocant, folosind stack-ul de retea al QGIS (respecta
    setarile de proxy/autentificare configurate in QGIS, spre deosebire de
    un apel HTTP facut direct din Python). Returneaza bytes, sau ridica
    UatBoundaryError cu un mesaj clar in caz de eroare de transport.
    """
    request = QNetworkRequest(QUrl(url))
    request.setTransferTimeout(timeout_ms)
    blocking = QgsBlockingNetworkRequest()
    err = blocking.get(request, forceRefresh=True)
    if err != QgsBlockingNetworkRequest.ErrorCode.NoError:
        raise UatBoundaryError(
            f"Cererea catre serviciul de limite administrative a esuat "
            f"({blocking.errorMessage()}):\n{url}"
        )
    return bytes(blocking.reply().content())


def _wfs_url(params):
    return WFS_BASE_URL + "?" + urllib.parse.urlencode(params)


def _fetch_filtered_geojson(siruta):
    """Interogare WFS filtrata server-side, pentru un singur UAT (natcode=siruta)."""
    url = _wfs_url(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": WFS_TYPE_NAME,
            "outputFormat": "application/json",
            "CQL_FILTER": f"natcode={siruta}",
        }
    )
    content = _http_get(url, FILTERED_TIMEOUT_MS)
    try:
        data = json.loads(content.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise UatBoundaryError(
            "Raspunsul serviciului WFS nu este un JSON valid "
            f"(posibil serviciul e indisponibil sau a returnat o eroare):\n"
            f"{content[:300]!r}"
        ) from exc

    if "features" not in data:
        raise UatBoundaryError(
            f"Raspunsul serviciului WFS nu contine un FeatureCollection:\n{content[:300]!r}"
        )
    return content


def _download_full_dataset(dest_path):
    """Descarca o singura data intregul set de date (raspunsul WFS nefiltrat, GeoPackage)."""
    url = _wfs_url(
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeName": WFS_TYPE_NAME,
            "outputFormat": "application/geopackage+sqlite3",
        }
    )
    content = _http_get(url, FULL_DOWNLOAD_TIMEOUT_MS)
    if content[:16] != b"SQLite format 3\x00":
        raise UatBoundaryError(
            "Descarcarea intregului set de date de limite UAT a esuat - "
            f"raspunsul primit nu este un fisier GeoPackage valid:\n{content[:300]!r}"
        )
    tmp_path = dest_path + ".part"
    with open(tmp_path, "wb") as f:
        f.write(content)
    os.replace(tmp_path, dest_path)


# -- extragerea datelor (attrs + geometrie), fara nicio scriere --------------

def _row_from_fields_feature(fields, feature):
    """Extrage (dict atribute mapate la schema locala, geometrie QgsGeometry)
    dintr-o pereche QgsFields+QgsFeature, indiferent daca provin dintr-un
    raspuns WFS (JSON) sau dintr-un strat OGR local (cache complet)."""
    attrs = {}
    for i in range(fields.count()):
        wfs_name = fields.at(i).name()
        local_name = _WFS_TO_LOCAL_FIELD.get(wfs_name.lower(), wfs_name)
        attrs[local_name] = feature[wfs_name]
    return attrs, feature.geometry()


def _row_from_geojson_bytes(content):
    text = content.decode("utf-8")
    raw_fields = QgsJsonUtils.stringToFields(text)
    raw_features = QgsJsonUtils.stringToFeatureList(text, raw_fields)
    if not raw_features:
        raise UatBoundaryError("Raspunsul serviciului nu contine nicio geometrie (UAT inexistent?).")
    if len(raw_features) != 1:
        raise UatBoundaryError(
            f"Raspunsul serviciului contine {len(raw_features)} geometrii in loc de exact 1 - "
            "filtrarea dupa cod SIRUTA nu a functionat cum era asteptat."
        )
    return _row_from_fields_feature(raw_fields, raw_features[0])


def _row_from_full_cache(siruta):
    cache_path = _full_dataset_cache_path()
    source = QgsVectorLayer(
        f"{cache_path}|layername=ro_admin_lau_polygon", "ro_admin_lau_polygon", "ogr"
    )
    if not source.isValid():
        raise _CacheUnreadable(
            f"Fisierul cache cu intregul set de date UAT nu a putut fi deschis:\n{cache_path}"
        )

    source.setSubsetString(f'"natcode" = {siruta}')
    features = list(source.getFeatures())
    if not features:
        raise UatBoundaryError(
            f"Codul SIRUTA {siruta} nu a fost gasit in setul de date de limite UAT "
            "(cache local existent si valid - codul SIRUTA este probabil gresit)."
        )
    if len(features) != 1:
        raise UatBoundaryError(
            f"Codul SIRUTA {siruta} se regaseste in {len(features)} inregistrari in loc de exact 1."
        )

    return _row_from_fields_feature(source.fields(), features[0])


def fetch_uat_boundary_data(siruta):
    """
    Returneaza (attrs, geometry) pentru UAT-ul cu codul SIRUTA dat, fara sa
    scrie nimic - vezi strategia din docstring-ul modulului. Ridica
    UatBoundaryError cu un mesaj clar daca datele nu pot fi obtinute in
    niciun fel.
    """
    siruta = int(siruta)

    # 1. cache local per-UAT
    per_uat_cache = _per_uat_cache_path(siruta)
    if os.path.isfile(per_uat_cache):
        with open(per_uat_cache, "rb") as f:
            content = f.read()
        try:
            return _row_from_geojson_bytes(content)
        except UatBoundaryError:
            pass  # cache corupt/invalid - se incearca reobtinerea mai jos

    # 2. interogare WFS filtrata server-side
    filtered_error = None
    try:
        content = _fetch_filtered_geojson(siruta)
        row = _row_from_geojson_bytes(content)
        with open(per_uat_cache, "wb") as f:
            f.write(content)
        return row
    except UatBoundaryError as exc:
        filtered_error = exc

    # 3. cache local al intregului set de date (daca exista deja)
    full_cache = _full_dataset_cache_path()
    if os.path.isfile(full_cache):
        try:
            return _row_from_full_cache(siruta)
        except _CacheUnreadable:
            pass  # cache corupt - se incearca o noua descarcare mai jos
        # o UatBoundaryError simpla (ex. "SIRUTA negasit intr-un cache valid")
        # se propaga direct, fara sa declanseze o redescarcare completa doar
        # pentru un cod SIRUTA gresit.

    # 4. descarcare unica a intregului set de date, apoi filtrare locala
    try:
        _download_full_dataset(full_cache)
    except UatBoundaryError as download_error:
        raise UatBoundaryError(
            "Nu s-a putut obtine limita administrativa a UAT-ului nici prin "
            "interogarea online filtrata, nici prin descarcarea intregului "
            "set de date, si nu exista niciun cache local valid.\n\n"
            f"Eroare interogare filtrata:\n{filtered_error}\n\n"
            f"Eroare descarcare completa:\n{download_error}\n\n"
            "Verifica conexiunea la internet si reincearca."
        ) from download_error

    return _row_from_full_cache(siruta)


# -- scriere in GPKG (strat de referinta persistent, nu in memorie) ----------

def _table_exists_in_gpkg(gpkg_path, table_name):
    con = sqlite3.connect(gpkg_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cur.fetchone() is not None
    finally:
        con.close()


def _create_empty_reference_table(gpkg_path):
    """
    Creeaza tabelul "~REF_UAT" (fara nicio inregistrare) in gpkg_path, cu
    schema din _FIELD_SPECS (MultiPolygon, EPSG:3844). Foloseste un nume
    temporar prin OGR - vezi docstring-ul modulului pentru motiv - apoi
    redenumeste tabelul si intrarile de bookkeeping GeoPackage prin SQL
    direct.
    """
    tmp_name = "REF_UAT_TMP_" + uuid.uuid4().hex[:8]

    ds = ogr.Open(gpkg_path, 1)
    if ds is None:
        raise UatBoundaryError(f"Nu s-a putut deschide pentru scriere fisierul GPKG:\n{gpkg_path}")

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(WFS_CRS_EPSG)
    layer = ds.CreateLayer(tmp_name, srs=srs, geom_type=ogr.wkbMultiPolygon, options=["SPATIAL_INDEX=NO"])
    if layer is None:
        ds = None
        raise UatBoundaryError(f"Nu s-a putut crea tabelul de referinta in:\n{gpkg_path}")

    for name, qtype in _FIELD_SPECS:
        ogr_type = ogr.OFTInteger if qtype == QVariant.Int else ogr.OFTString
        layer.CreateField(ogr.FieldDefn(name, ogr_type))

    ds = None  # flush/inchide - necesar inainte de a redeschide cu sqlite3

    con = sqlite3.connect(gpkg_path)
    try:
        cur = con.cursor()
        # curata orice intrare de bookkeeping ramasa orfana pentru LAYER_NAME
        # (ex. tabelul a fost sters manual fara curatarea acestor tabele) -
        # altfel UPDATE-urile de mai jos (tmp_name -> LAYER_NAME) ar da
        # UNIQUE constraint failed pe un rand vechi cu acelasi table_name.
        cur.execute("DELETE FROM gpkg_contents WHERE table_name=?", (LAYER_NAME,))
        cur.execute("DELETE FROM gpkg_geometry_columns WHERE table_name=?", (LAYER_NAME,))
        for meta_table in ("gpkg_ogr_contents", "sqlite_sequence"):
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (meta_table,)
            )
            if cur.fetchone() is not None:
                key_col = "table_name" if meta_table == "gpkg_ogr_contents" else "name"
                cur.execute(f'DELETE FROM "{meta_table}" WHERE {key_col}=?', (LAYER_NAME,))

        cur.execute(f'ALTER TABLE "{tmp_name}" RENAME TO "{LAYER_NAME}"')
        cur.execute(
            "UPDATE gpkg_contents SET table_name=?, identifier=? WHERE table_name=?",
            (LAYER_NAME, LAYER_NAME, tmp_name),
        )
        cur.execute(
            "UPDATE gpkg_geometry_columns SET table_name=? WHERE table_name=?",
            (LAYER_NAME, tmp_name),
        )
        for meta_table in ("gpkg_ogr_contents", "sqlite_sequence"):
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (meta_table,)
            )
            if cur.fetchone() is not None:
                key_col = "table_name" if meta_table == "gpkg_ogr_contents" else "name"
                cur.execute(
                    f'UPDATE "{meta_table}" SET {key_col}=? WHERE {key_col}=?',
                    (LAYER_NAME, tmp_name),
                )
        con.commit()
    finally:
        con.close()


def _replace_row(gpkg_path, attrs, geometry):
    """Sterge orice inregistrare existenta si insereaza (attrs, geometry) in
    tabelul "~REF_UAT" (presupus deja existent) din gpkg_path."""
    ds = ogr.Open(gpkg_path, 1)
    if ds is None:
        raise UatBoundaryError(f"Nu s-a putut deschide pentru scriere fisierul GPKG:\n{gpkg_path}")
    layer = ds.GetLayerByName(LAYER_NAME)
    if layer is None:
        ds = None
        raise UatBoundaryError(f"Tabelul de referinta '{LAYER_NAME}' nu a fost gasit in:\n{gpkg_path}")

    layer.ResetReading()
    for existing_fid in [f.GetFID() for f in layer]:
        layer.DeleteFeature(existing_fid)

    geom = ogr.CreateGeometryFromWkt(geometry.asWkt())
    if geom is not None and ogr.GT_Flatten(geom.GetGeometryType()) == ogr.wkbPolygon:
        geom = ogr.ForceToMultiPolygon(geom)

    defn = layer.GetLayerDefn()
    feat = ogr.Feature(defn)
    feat.SetGeometry(geom)
    for local_name, value in attrs.items():
        idx = defn.GetFieldIndex(local_name)
        if idx < 0 or value is None:
            continue
        # campuri precum "version" pot veni ca QDate/QDateTime (parsate de
        # QGIS din raspunsul WFS) - OGR.SetField accepta doar tipuri
        # primitive (int/float/str), asa ca le convertim explicit.
        if isinstance(value, (QDate, QDateTime)):
            value = value.toString("yyyy-MM-dd")
        feat.SetField(idx, value)

    if layer.CreateFeature(feat) != 0:
        ds = None
        raise UatBoundaryError(f"Nu s-a putut scrie inregistrarea UAT-ului in:\n{gpkg_path}")

    ds = None  # flush/inchide


def write_boundary_layer(gpkg_path, attrs, geometry):
    """
    Scrie/inlocuieste tabelul de referinta "~REF_UAT" din gpkg_path cu
    (attrs, geometry) - creeaza tabelul daca nu exista deja (sablon vechi,
    sau proiect fara acest strat inca) - si returneaza un QgsVectorLayer
    incarcat din acel tabel (strat GPKG persistent, NU in memorie).
    """
    if not _table_exists_in_gpkg(gpkg_path, LAYER_NAME):
        _create_empty_reference_table(gpkg_path)
    _replace_row(gpkg_path, attrs, geometry)

    layer = QgsVectorLayer(f"{gpkg_path}|layername={LAYER_NAME}", LAYER_NAME, "ogr")
    if not layer.isValid():
        raise UatBoundaryError(
            f"Stratul de referinta '{LAYER_NAME}' nu a putut fi incarcat din:\n{gpkg_path}"
        )
    return layer


def fetch_uat_boundary(siruta, gpkg_path):
    """
    Comoditate: fetch_uat_boundary_data(siruta) + write_boundary_layer(...).
    Returneaza un QgsVectorLayer (strat GPKG, MultiPolygon, EPSG:3844) cu o
    singura entitate: limita administrativa a UAT-ului cu codul SIRUTA dat,
    scrisa in tabelul "~REF_UAT" din gpkg_path.
    """
    attrs, geometry = fetch_uat_boundary_data(siruta)
    return write_boundary_layer(gpkg_path, attrs, geometry)


# -- gestiune cache (folosita de dialogul "Despre") ---------------------------
# Expuse ca functii publice separate de fetch_uat_boundary(), pentru a putea
# afisa starea cache-ului si a oferi actiuni de stergere/reimprospatare din
# UI, fara a duplica logica de cale de mai sus.

def cache_root():
    """Folderul de cache (creat daca nu exista deja)."""
    return _cache_root()


def list_per_uat_cache_files():
    """Lista (cale completa, dimensiune in octeti), cate o intrare per UAT cache."""
    root = _cache_root()
    result = []
    for fname in os.listdir(root):
        if fname.endswith(".json"):
            path = os.path.join(root, fname)
            try:
                result.append((path, os.path.getsize(path)))
            except OSError:
                continue
    return sorted(result)


def full_dataset_cache_status():
    """(cale completa, exista, dimensiune_octeti sau None, mtime unix sau None)."""
    path = _full_dataset_cache_path()
    if os.path.isfile(path):
        stat = os.stat(path)
        return path, True, stat.st_size, stat.st_mtime
    return path, False, None, None


def clear_per_uat_cache():
    """Sterge toate fisierele cache per-UAT (NU si setul complet de rezerva). Returneaza numarul sterse."""
    count = 0
    for path, _size in list_per_uat_cache_files():
        try:
            os.remove(path)
            count += 1
        except OSError:
            pass
    return count


def clear_full_dataset_cache():
    """Sterge fisierul cache cu intregul set de date (si eventualele fisiere temporare/jurnal asociate)."""
    path = _full_dataset_cache_path()
    removed = False
    for candidate in (path, path + "-wal", path + "-shm", path + "-journal", path + ".part"):
        if os.path.isfile(candidate):
            try:
                os.remove(candidate)
                removed = True
            except OSError:
                pass
    return removed


def refresh_full_dataset_cache():
    """
    Redescarca intregul set de date, inlocuind cache-ul existent. Poate dura
    cateva minute si transfera ~70-120 MB - a se folosi doar explicit, la
    cererea utilizatorului (ex. din dialogul "Despre"), niciodata automat.
    """
    clear_full_dataset_cache()
    _download_full_dataset(_full_dataset_cache_path())
