# -*- coding: utf-8 -*-
"""
Utilitare comune pentru regulile de validare care lucreaza cu straturi din
fisierul GPKG activ (proiectul QGIS curent).

Nu este o regula de validare in sine; este folosit de regulile R12+ pentru a
evita duplicarea logicii de gasire a straturilor / fisierului GPKG, citirea
campurilor si normalizarea datelor calendaristice.
"""

from datetime import datetime

from qgis.core import NULL, QgsFeatureRequest, QgsVectorLayer

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
    """Strat unic dupa nume, deja incarcat in proiectul QGIS activ."""
    layers = project.mapLayersByName(layer_name)
    if not layers:
        raise ValueError(f"Stratul '{layer_name}' nu a fost gasit in proiect.")
    if len(layers) > 1:
        raise ValueError(
            f"Exista mai multe straturi cu numele '{layer_name}' in proiect; "
            "foloseste un identificator unic (layer id)."
        )
    return layers[0]


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
                return path

    for layer in project.mapLayers().values():
        try:
            path = layer.source().split("|")[0]
        except AttributeError:
            continue
        if path.lower().endswith(".gpkg"):
            return path

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
        return layers[0]

    path = gpkg_path or find_gpkg_path(project)
    layer = QgsVectorLayer(f"{path}|layername={layer_name}", layer_name, "ogr")
    if not layer.isValid():
        raise ValueError(
            f"Stratul '{layer_name}' nu a fost gasit nici in proiect, nici "
            f"in fisierul GPKG activ ('{path}')."
        )
    return layer


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
