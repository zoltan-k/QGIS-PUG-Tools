# -*- coding: utf-8 -*-
"""
Utilitare comune pentru regulile de validare care lucreaza cu straturi din
fisierul GPKG activ (proiectul QGIS curent).

Nu este o regula de validare in sine; este folosit de regulile R12+ pentru a
evita duplicarea logicii de gasire a straturilor / fisierului GPKG, citirea
campurilor si normalizarea datelor calendaristice.
"""

import contextlib
import gc
import os
import shutil
import tempfile
import time
from datetime import datetime

from qgis.core import NULL, Qgis, QgsFeatureRequest, QgsMessageLog, QgsVectorLayer

try:
    from ..tools import settings as pug_settings
except ImportError:  # pragma: no cover - fallback pentru rulare in afara plugin-ului
    from tools import settings as pug_settings

MAX_REPORTED = 100

_DATE_TEXT_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d",
    "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
)


def is_null(value):
    if value is None:
        return True
    try:
        return value == NULL
    except Exception:
        return False


def get_layer(project, layer_name):
    """Strat unic dupa nume, deja incarcat in proiectul QGIS activ.

    Daca ruleaza o sesiune de copie locala (vezi local_copy_session), se
    intoarce un strat echivalent deschis din copia locala a GPKG-ului.
    """
    layers = project.mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in proiect.")
    if len(layers) > 1:
        raise ValueError(
            f"Exista mai multe straturi cu numele '{layer_name}' in proiect; "
            "foloseste un identificator unic (layer id)."
        )
    return _localize_layer(layers[0])


def find_gpkg_path(project, preferred_layer_names=("PlanSpatial",)):
    """
    Deduce calea fisierului .gpkg activ pornind de la sursa unui strat deja
    incarcat in proiect. Incearca intai numele preferate (straturi mereu
    prezente intr-un GPKG PUG), apoi orice alt strat vector incarcat.
    """
    for name in preferred_layer_names:
        layers = project.mapLayersByName(name)
        if layers:
            path = layers[0].source().split("|")[0]
            if path.lower().endswith(".gpkg"):
                return resolve_path(path)

    for layer in project.mapLayers().values():
        try:
            path = layer.source().split("|")[0]
        except AttributeError:
            continue
        if path.lower().endswith(".gpkg"):
            return resolve_path(path)

    raise ValueError(
        "Nu s-a putut deduce calea fisierului GPKG activ din straturile "
        "incarcate in proiect."
    )


def get_layer_or_open(project, layer_name, gpkg_path=None):
    """
    Ca get_layer(), dar daca stratul nu este incarcat in proiect (ex. un
    tabel de referinta din grupul REF ascuns, care ar fi trebuit sa fie
    incarcat automat de "Proiect nou PUG" dar lipseste dintr-un motiv
    oarecare) este deschis direct din fisierul GPKG activ, fara a fi
    adaugat in proiect.
    """
    layers = project.mapLayersByName(layer_name)
    if len(layers) > 1:
        raise ValueError(
            f"Exista mai multe straturi cu numele '{layer_name}' in proiect; "
            "foloseste un identificator unic (layer id)."
        )
    if layers:
        return _localize_layer(layers[0])

    path = gpkg_path or find_gpkg_path(project)
    layer = QgsVectorLayer(f"{path}|layername={layer_name}", layer_name, "ogr")
    if not layer.isValid():
        raise ValueError(
            f"Stratul '{layer_name}' nu a fost gasit nici in proiect, nici "
            f"in fisierul GPKG activ ('{path}')."
        )
    return layer


# -- copie locala a GPKG-urilor de pe partajari de retea ---------------------
#
# GeoPackage = baza SQLite: citeste pagini mici, la offset-uri imprastiate, si
# ia/elibereaza lock-uri de fisier. Pe o partajare SMB fiecare operatie e un
# round-trip, deci timpul e dictat de latenta, nu de latimea de banda; iar
# regulile redeschid fisierul de zeci de ori. Solutia: o singura copie
# (read-only) intr-un folder temporar local pe durata unei rulari de validare.
#
# Modul ("auto" implicit - doar pentru cai de retea / "always" / "never") se
# alege in dialogul "Despre" (tools/settings.py); variabila de mediu
# PUG_TOOLS_LOCAL_COPY, daca e setata la o valoare valida, are prioritate (teste).

_session = None  # {"map": {cale_normalizata: cale_locala}, "layers": {id: strat}}


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _is_network_path(path):
    path = os.path.abspath(path)
    if path.startswith("\\\\"):
        return True
    if os.name != "nt":
        return False
    try:
        import ctypes

        drive = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(drive) == 4  # DRIVE_REMOTE
    except Exception:
        return False


def _log(message):
    QgsMessageLog.logMessage(message, "PUG Tools", Qgis.Info)


def resolve_path(path):
    """Calea locala daca GPKG-ul e copiat in sesiunea curenta, altfel cea data."""
    if _session is None:
        return path
    return _session["map"].get(_norm(path), path)


def _localize_layer(layer):
    """Strat echivalent deschis din copia locala (cache per sesiune), sau stratul dat."""
    if _session is None:
        return layer
    try:
        if layer.providerType() != "ogr":
            return layer
        source = layer.source()
        orig_path = source.split("|")[0]
    except AttributeError:
        return layer
    local = _session["map"].get(_norm(orig_path))
    if local is None:
        return layer
    cached = _session["layers"].get(layer.id())
    if cached is not None:
        return cached
    local_layer = QgsVectorLayer(local + source[len(orig_path):], layer.name(), "ogr")
    if not local_layer.isValid():
        return layer  # fallback: citeste de pe sursa originala
    _session["layers"][layer.id()] = local_layer
    return local_layer


@contextlib.contextmanager
def local_copy_session(project):
    """
    Pe durata blocului, regulile citesc GPKG-urile proiectului dintr-o copie
    locala temporara (doar pentru cai de retea, vezi PUG_TOOLS_LOCAL_COPY).
    Originalul nu este modificat. Daca copierea esueaza, se citeste direct
    de pe sursa.
    """
    global _session
    mode = os.environ.get("PUG_TOOLS_LOCAL_COPY", "").strip().lower()  # suprascriere pentru teste
    if mode not in pug_settings.LOCAL_COPY_MODES:
        mode = pug_settings.get_local_copy_mode()
    if _session is not None or mode == "never":
        yield
        return

    sources = {}
    for layer in project.mapLayers().values():
        try:
            if layer.providerType() != "ogr":
                continue
            path = layer.source().split("|")[0]
        except AttributeError:
            continue
        if path.lower().endswith(".gpkg") and os.path.isfile(path):
            sources.setdefault(_norm(path), path)

    mapping = {}
    tmp_dir = None
    t0 = time.perf_counter()
    for index, (key, path) in enumerate(sources.items()):
        if mode != "always" and not _is_network_path(path):
            continue
        try:
            if tmp_dir is None:
                tmp_dir = tempfile.mkdtemp(prefix="pug_validate_")
            sub_dir = os.path.join(tmp_dir, str(index))
            os.makedirs(sub_dir)
            dest = os.path.join(sub_dir, os.path.basename(path))
            shutil.copyfile(path, dest)
            for suffix in ("-wal", "-shm"):  # daca exista tranzactii nescrise
                if os.path.isfile(path + suffix):
                    shutil.copyfile(path + suffix, dest + suffix)
            mapping[key] = dest
        except Exception as exc:
            _log(f"Copia locala a '{path}' a esuat ({exc}); se citeste de pe sursa.")

    if mapping:
        _log(f"Copie locala: {len(mapping)} GPKG in {time.perf_counter() - t0:.2f}s.")
    _session = {"map": mapping, "layers": {}}
    try:
        yield
    finally:
        _session = None
        gc.collect()  # elibereaza straturile -> handle-urile pe fisierele temporare
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def run_rules(project, rules):
    """Ruleaza regulile intr-o sesiune de copie locala. Intoarce (esecuri, erori)."""
    failures = []
    errors = []
    t_all = time.perf_counter()
    with local_copy_session(project):
        for rule in rules:
            t0 = time.perf_counter()
            try:
                failures.extend(rule.run(project))
            except Exception as exc:  # nu opri celelalte reguli daca una esueaza
                errors.append(f"R{rule.rule_id} {rule.name}: {exc}")
            _log(f"R{rule.rule_id}: {time.perf_counter() - t0:.2f}s")
    _log(f"Validare totala: {time.perf_counter() - t_all:.2f}s")
    return failures, errors


def request_for_fields(layer, field_names):
    request = QgsFeatureRequest()
    request.setSubsetOfAttributes(list(field_names), layer.fields())
    request.setFlags(QgsFeatureRequest.NoGeometry)
    return request


def field_value_set(layer, field_name):
    """Multimea valorilor non-NULL dintr-o coloana a unui strat."""
    values = set()
    for feat in layer.getFeatures(request_for_fields(layer, [field_name])):
        value = feat[field_name]
        if not is_null(value):
            values.add(value)
    return values


def normalize_date_text(value):
    """
    Converteste o valoare de camp de tip DATE/DATETIME (QDate/QDateTime,
    intoarsa de API-ul QGIS pentru campuri GPKG de tip DATE) sau un string
    intr-un text canonic, fara a impune un format anume. Returneaza None
    pentru valori lipsa.
    """
    if is_null(value):
        return None

    from qgis.PyQt.QtCore import QDate, QDateTime

    if isinstance(value, QDateTime):
        value = value.date()
    if isinstance(value, QDate):
        if not value.isValid():
            return None
        return value.toString("yyyy-MM-dd")

    text = str(value).strip()
    return text or None


def parse_date(value):
    """Returneaza un datetime.date sau None daca valoarea lipseste/nu se poate interpreta."""
    text = normalize_date_text(value)
    if not text:
        return None
    for fmt in _DATE_TEXT_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def open_ogr_layer(gpkg_path, layer_name):
    """Deschide un strat direct cu GDAL/OGR (read-only); apelantul trebuie sa pastreze ds in viata."""
    from osgeo import ogr

    ds = ogr.Open(gpkg_path, 0)
    if ds is None:
        raise RuntimeError(f"Nu s-a putut deschide fisierul GPKG: {gpkg_path}")

    ogr_layer = ds.GetLayerByName(layer_name)
    if ogr_layer is None:
        raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in fisierul '{gpkg_path}'.")
    return ds, ogr_layer
